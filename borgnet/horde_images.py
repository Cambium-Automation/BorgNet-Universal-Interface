"""AI Horde queued image jobs with bounded polling and anonymous access."""
import asyncio
import json
import re
import httpx
from .media_responses import capture, ProviderResponseError

BASE = 'https://aihorde.net/api/v2'
QUEUE_TIMEOUT = 20 * 60


async def poll_json(client, path, headers):
    # Retry only reads: resubmitting a timed-out POST could create duplicate jobs.
    for attempt in range(6):
        try:
            return await read_json(client, 'GET', path, headers=headers)
        except ProviderResponseError as error:
            if error.status not in {408, 429, 500, 502, 503, 504} or attempt == 5:
                raise
        except httpx.TransportError:
            if attempt == 5:
                raise
        await asyncio.sleep(min(30, 2 ** (attempt + 1)))


async def read_json(client, method, path, **kwargs):
    async with client.stream(method, BASE + path, **kwargs) as response:
        raw = bytearray()
        async for chunk in response.aiter_bytes():
            raw.extend(chunk)
            if len(raw) > 90_000_000:
                raise ValueError('AI Horde response is too large')
        try:
            data = json.loads(raw)
        except ValueError:
            if response.status_code not in {200, 202}:
                raise ProviderResponseError(f'AI Horde returned HTTP {response.status_code}.', {'messages': [], 'codes': [], 'truncated': False}, response.status_code) from None
            raise ValueError('AI Horde returned invalid JSON') from None
        reply = capture(data, [kwargs.get('headers', {}).get('apikey', '')])
        if response.status_code not in {200, 202}:
            raise ProviderResponseError(f'AI Horde returned HTTP {response.status_code}. Check queue, key and kudos requirements.', reply, response.status_code)
    return data


async def generate(model, prompt, size, key, transport=None):
    dimensions = {'auto': (512, 512), '1:1': (512, 512), '16:9': (768, 448),
                  '9:16': (448, 768), '4:3': (640, 448), '3:4': (448, 640)}
    width, height = dimensions[size]
    headers = {'apikey': key or '0000000000', 'Client-Agent': 'BorgNet:0.1.0:github.com/Cambium-Automation/BorgNet-Universal-Interface'}
    payload = {'prompt': prompt, 'params': {'width': width, 'height': height, 'steps': 20, 'n': 1},
               'r2': False, 'shared': False, 'trusted_workers': True}
    if model != 'auto':
        payload['models'] = [model]
    job = None
    complete = False
    async with httpx.AsyncClient(timeout=30, trust_env=False, follow_redirects=False, transport=transport) as client:
        try:
            async with asyncio.timeout(QUEUE_TIMEOUT):
                submitted = await read_json(client, 'POST', '/generate/async', headers=headers, json=payload)
                job = submitted.get('id', '')
                if not re.fullmatch(r'[a-zA-Z0-9-]{1,64}', job):
                    job = None
                    raise ValueError('AI Horde returned an invalid job identifier')
                while True:
                    check = await poll_json(client, '/generate/check/' + job, headers)
                    if check.get('faulted'):
                        raise ValueError('AI Horde cannot fulfill this request with current workers.')
                    if check.get('done'):
                        result = await poll_json(client, '/generate/status/' + job, headers)
                        complete = True
                        images = result.get('generations') or []
                        if not images or images[0].get('censored'):
                            raise ValueError('AI Horde returned no available image. A worker may have filtered the result.')
                        encoded = images[0].get('img', '')
                        if not isinstance(encoded, str) or encoded.startswith(('http:', 'https:')):
                            raise ValueError('AI Horde did not return inline image data.')
                        return encoded
                    await asyncio.sleep(5)
        except TimeoutError:
            raise ValueError('AI Horde did not finish within 20 minutes. Cancellation will be attempted. Try Auto or a smaller image, or use an account key for queue priority. No new generation was submitted automatically.') from None
        finally:
            if job and not complete:
                try:
                    await read_json(client, 'DELETE', '/generate/status/' + job, headers=headers)
                except (httpx.HTTPError, ValueError):
                    pass
