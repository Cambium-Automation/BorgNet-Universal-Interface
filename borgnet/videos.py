"""Persistent text-to-video jobs using existing official-provider API credentials."""
import asyncio
import os
import re
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urljoin, quote

import httpx
from fastapi import Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from .image_api import create_image_api
from .media_responses import public_response, ProviderResponseError

PROVIDERS = {
    'xai': {'base': 'https://api.x.ai/v1', 'models': ['grok-imagine-video-1.5'], 'durations': [5, 10, 15], 'sizes': ['16:9', '9:16', '1:1']},
    'gemini': {'base': 'https://generativelanguage.googleapis.com/v1beta', 'models': ['veo-3.1-generate-preview', 'veo-3.1-fast-generate-preview'], 'durations': [4, 6, 8], 'sizes': ['16:9', '9:16']},
    'openai': {'base': 'https://api.openai.com/v1', 'models': ['sora-2', 'sora-2-pro'], 'durations': [4, 8, 12], 'sizes': ['1280x720', '720x1280']},
}


class Videos:
    def __init__(self, root, store, transport=None):
        self.root, self.store, self.transport = Path(root), store, transport
        self.credentials = create_image_api(root, store).credential
        self.lock = asyncio.Lock()
        for job in self.jobs():
            if job['status'] == 'submitting':
                job.update(status='unknown', error='Server restarted during submission. Check provider history before generating again.')
                self.save(job)

    def catalog(self):
        return [{'id': p + '::' + m, 'label': p.title() + ' · ' + m,
                 'ready': bool(self.credentials(p)), 'durations': v['durations'], 'sizes': v['sizes']}
                for p, v in PROVIDERS.items() for m in v['models']]

    def jobs(self):
        return self.store.read('video-jobs', [])

    def save(self, job):
        with self.store.lock:
            jobs = self.jobs()
            jobs = [j for j in jobs if j['id'] != job['id']]
            jobs.append(job)
            self.store.write('video-jobs', jobs)

    @staticmethod
    def public(job):
        return {k: v for k, v in job.items() if k != 'remote_id'}

    def client(self):
        return httpx.AsyncClient(timeout=60, trust_env=False, follow_redirects=False, transport=self.transport)

    def headers(self, provider):
        key = self.credentials(provider)
        if not key:
            raise ValueError('Add this provider API key through Connect image API first. CLI sign-in is separate.')
        return {'x-goog-api-key': key} if provider == 'gemini' else {'Authorization': 'Bearer ' + key}

    async def json_request(self, client, method, url, **kwargs):
        async with client.stream(method, url, **kwargs) as response:
            data = bytearray()
            async for chunk in response.aiter_bytes():
                data.extend(chunk)
                if len(data) > 2_000_000:
                    raise ValueError('Video status response too large')
        import json
        result = json.loads(data)
        auth = kwargs.get('headers', {})
        keys = [value.removeprefix('Bearer ') for name, value in auth.items() if name.lower() in {'authorization', 'x-goog-api-key'}]
        reply = public_response(result, keys)
        if not response.is_success:
            reason = {401: 'API key rejected', 403: 'Account lacks access', 429: 'Quota or rate limit reached'}.get(response.status_code, 'Provider request failed')
            raise ProviderResponseError(f'{reason} (HTTP {response.status_code}).', reply, response.status_code)
        if not isinstance(result, dict):
            raise ValueError('Provider returned an invalid video response')
        result['_borgnet_reply'] = reply
        return result

    async def create(self, body):
        model = next((m for m in self.catalog() if m['id'] == body.get('model_id')), None)
        prompt = str(body.get('prompt', '')).strip()
        if not model or not prompt or len(prompt) > 4000:
            raise ValueError('Select a video model and enter a prompt of 1–4000 characters')
        duration, size = body.get('duration'), body.get('size')
        if type(duration) is not int or duration not in model['durations'] or size not in model['sizes']:
            raise ValueError('Unsupported duration or size')
        provider, name = model['id'].split('::', 1)
        headers = self.headers(provider)
        async with self.lock:
            if any(j['status'] in {'pending', 'submitting'} for j in self.jobs()):
                raise ValueError('Finish the current video job before starting another')
            job = {'id': uuid.uuid4().hex, 'model_id': model['id'], 'prompt': prompt, 'duration': duration,
                   'size': size, 'created_at': time.time(), 'status': 'submitting'}
            self.save(job)
            try:
                base = PROVIDERS[provider]['base']
                async with self.client() as client:
                    if provider == 'gemini':
                        result = await self.json_request(client, 'POST', base + '/models/' + name + ':predictLongRunning', headers=headers,
                            json={'instances': [{'prompt': prompt}], 'parameters': {'durationSeconds': duration, 'aspectRatio': size, 'resolution': '720p'}})
                        job['provider_responses'] = [result['_borgnet_reply']]
                        remote = result.get('name', '')
                        if not re.fullmatch(r'models/[\w.-]+/operations/[\w.-]+|operations/[\w.-]+', remote):
                            raise ValueError('Provider returned an invalid operation ID')
                    elif provider == 'xai':
                        result = await self.json_request(client, 'POST', base + '/videos/generations', headers=headers,
                            json={'model': name, 'prompt': prompt, 'duration': duration, 'aspect_ratio': size, 'resolution': '720p'})
                        job['provider_responses'] = [result['_borgnet_reply']]
                        remote = result.get('request_id', '')
                    else:
                        result = await self.json_request(client, 'POST', base + '/videos', headers=headers,
                            files={k: (None, str(v)) for k, v in {'model': name, 'prompt': prompt, 'seconds': duration, 'size': size}.items()})
                        job['provider_responses'] = [result['_borgnet_reply']]
                        remote = result.get('id', '')
                    if provider != 'gemini' and not re.fullmatch(r'[\w-]{1,200}', remote):
                        raise ValueError('Provider returned an invalid video ID')
                job.update(remote_id=remote, status='pending', provider_responses=[result['_borgnet_reply']])
            except ProviderResponseError as error:
                job.update(status='failed' if error.status and 400 <= error.status < 500 else 'unknown', error=str(error), provider_responses=[error.reply])
                self.save(job)
                raise
            except Exception:
                job.update(status='unknown', error='Submission could not be confirmed. Check provider history before generating again; it may have accepted the request.')
                self.save(job)
                raise
            self.save(job)
            return self.public(job)

    @staticmethod
    def allowed_download(provider, url):
        parsed = urlsplit(url)
        hosts = {'xai': ('vidgen.x.ai',), 'gemini': ('generativelanguage.googleapis.com', 'storage.googleapis.com', 'googleusercontent.com'), 'openai': ('api.openai.com',)}[provider]
        return parsed.scheme == 'https' and not parsed.username and not parsed.password and parsed.port in (None, 443) and any(parsed.hostname == h or (h == 'googleusercontent.com' and (parsed.hostname or '').endswith('.' + h)) for h in hosts)

    async def download(self, client, provider, url, headers, job):
        path = self.root / 'api-videos' / (job['id'] + '.mp4')
        path.parent.mkdir(mode=0o700, exist_ok=True)
        temp = path.with_suffix('.part')
        try:
            for _ in range(5):
                if not self.allowed_download(provider, url):
                    raise ValueError('Provider returned an unsupported video download host')
                # API keys stay on the exact API origin, never on CDN redirects.
                auth = headers if urlsplit(url).netloc == urlsplit(PROVIDERS[provider]['base']).netloc else {}
                async with client.stream('GET', url, headers=auth) as response:
                    if response.is_redirect:
                        url = urljoin(url, response.headers.get('location', ''))
                        continue
                    if not response.is_success:
                        raise ValueError(f'Video download failed (HTTP {response.status_code})')
                    total, prefix = 0, b''
                    with temp.open('wb') as output:
                        os.chmod(temp, 0o600)
                        async for chunk in response.aiter_bytes():
                            total += len(chunk)
                            prefix = (prefix + chunk)[:16]
                            if total > 256_000_000:
                                raise ValueError('Video exceeds 256 MB download limit')
                            output.write(chunk)
                    if prefix[4:8] != b'ftyp':
                        raise ValueError('Provider did not return an MP4 video')
                    temp.replace(path)
                    return '/api/videos/' + job['id'] + '/content'
            raise ValueError('Too many video download redirects')
        finally:
            temp.unlink(missing_ok=True)

    async def refresh(self, identity):
        async with self.lock:
            job = next((j for j in self.jobs() if j['id'] == identity), None)
            if not job:
                raise HTTPException(404, 'Video not found')
            if job['status'] != 'pending' or time.time() - job.get('checked_at', 0) < 5:
                return self.public(job)
            job['checked_at'] = time.time()
            provider = job['model_id'].split('::')[0]
            base, remote = PROVIDERS[provider]['base'], job['remote_id']
            try:
                headers = self.headers(provider)
                async with self.client() as client:
                    url = base + ('/' + remote if provider == 'gemini' else '/videos/' + quote(remote, safe=''))
                    result = await self.json_request(client, 'GET', url, headers=headers)
                    reply = result['_borgnet_reply']
                    if reply not in job.setdefault('provider_responses', []):
                        if len(job['provider_responses']) < 16:
                            job['provider_responses'].append(reply)
                        else:
                            job['provider_responses'][-1]['truncated'] = True
                    status = result.get('status', '')
                    if result.get('error') or status in {'failed', 'expired'}:
                        job.update(status='failed', error='Provider could not generate this video. Check its content policy, account access and quota.')
                    else:
                        done = result.get('done', False) if provider == 'gemini' else status in {'done', 'completed'}
                        if done:
                            if provider == 'gemini':
                                samples = result.get('response', {}).get('generateVideoResponse', {}).get('generatedSamples', [])
                                url = samples[0].get('video', {}).get('uri', '') if samples else ''
                            elif provider == 'xai':
                                video = result.get('video', {})
                                url = video.get('url', '') if video.get('respect_moderation', True) else ''
                            else:
                                url = base + '/videos/' + quote(remote, safe='') + '/content'
                            if not url:
                                job.update(status='failed', error='Provider returned no video; generation may have been filtered.')
                            else:
                                job.update(url=await self.download(client, provider, url, headers, job), status='completed')
                        progress = result.get('progress')
                        if isinstance(progress, (int, float)):
                            job['progress'] = max(0, min(100, progress))
                        job.pop('warning', None)
            except ProviderResponseError as error:
                if error.reply not in job.setdefault('provider_responses', []) and len(job['provider_responses']) < 16:
                    job['provider_responses'].append(error.reply)
                job['warning'] = str(error) + ' No new generation was submitted.'
            except (httpx.HTTPError, ValueError, OSError):
                job['warning'] = 'Could not retrieve video status or download. Automatic checks will retry; no new generation is submitted.'
            self.save(job)
            return self.public(job)


def register_videos(app, root, store):
    service = Videos(root, store)
    app.state.videos = service

    @app.get('/api/videos/models')
    async def models():
        return {'models': service.catalog()}

    @app.get('/api/videos')
    async def history():
        return {'jobs': [service.public(j) for j in reversed(service.jobs())]}

    @app.post('/api/videos')
    async def generate(request: Request):
        try:
            return JSONResponse(await service.create(await request.json()), status_code=202)
        except httpx.HTTPError:
            raise ValueError('Provider connection failed. Check video history before retrying generation.') from None

    @app.post('/api/videos/{identity}/refresh')
    async def refresh(identity: str):
        return await service.refresh(identity)

    @app.get('/api/videos/{identity}/content')
    async def content(identity: str, download: bool = False):
        if not re.fullmatch('[a-f0-9]{32}', identity):
            raise HTTPException(404)
        path = Path(root) / 'api-videos' / (identity + '.mp4')
        if not path.is_file() or path.is_symlink():
            raise HTTPException(404)
        return FileResponse(path, media_type='video/mp4', filename=('BorgNet-' + identity + '.mp4') if download else None)
