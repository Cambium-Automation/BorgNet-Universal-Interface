"""Local image library: generation, export, and recoverable deletion."""
from pathlib import Path
import uuid
from datetime import datetime, timezone
import httpx
from .media_responses import responses, redact
from fastapi import Request
from fastapi.responses import FileResponse, JSONResponse
from .image_api import create_image_api
from .subscription_images import create_subscription_images


def register_images(app, root, store):
    generating = 0
    from .local_images import LocalImages
    local = LocalImages(root, store)
    app.state.local_images = local
    api = create_image_api(root, store)
    native = create_subscription_images(root, store)
    api.register(app)
    app.state.image_api, app.state.image_native = api, native

    @app.get('/api/images/imagegen/models')
    async def models():
        return {'models': local.catalog() + native.catalog() + await api.catalog()}

    @app.get('/api/images/imagegen/history')
    async def history():
        deleted = set(store.read('image-library-deleted', []))
        images = sorted(store.read('api-image-history', []), key=lambda x: x.get('created_at', ''), reverse=True)
        return {'images': [x for x in images if x['id'] not in deleted],
                'trash': [x for x in images if x['id'] in deleted]}

    @app.get('/api/images/imagegen/images/{identity}')
    async def image(identity: str):
        path = api.image_path(identity)
        if not path:
            return JSONResponse({'error': 'Image not found'}, 404)
        return FileResponse(path, media_type=image_type(path)[0])

    @app.post('/api/images/imagegen/generate')
    async def generate(request: Request):
        body = await request.json()
        adapter = native if str(body.get('model_id', '')).startswith('signedin::') else api
        if body.get('model_id') == 'local::bonsai':
            adapter = local
        nonlocal generating
        generating += 1
        replies = []
        marker = responses.set(replies)
        def sanitized_replies():
            secrets = store.read('secrets', {}).values()
            return [{**reply, 'messages': [redact(x, secrets) for x in reply['messages']],
                     'codes': [redact(x, secrets) for x in reply['codes']]} for reply in replies]
        try:
            result = await adapter.generate(body)
            replies[:] = sanitized_replies()
            result['provider_responses'] = replies
            result['status'] = 'completed'
            with store.lock:
                history = store.read('api-image-history', [])
                for entry in history:
                    if entry.get('id') == result['id']:
                        entry.update(provider_responses=replies, status='completed')
                store.write('api-image-history', history)
            return JSONResponse(result, 201)
        except (ValueError, httpx.HTTPError, TimeoutError, OSError) as error:
            replies[:] = sanitized_replies()
            # Preserve failed attempts alongside successful images, not just in a toast.
            message = str(error) if isinstance(error, ValueError) else 'Provider connection failed or timed out.'
            message = redact(message, store.read('secrets', {}).values())[:32768]
            entry = {'id': datetime.now().strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8],
                     'created_at': datetime.now(timezone.utc).isoformat(), 'status': 'failed',
                     'model_id': str(body.get('model_id', ''))[:400], 'prompt': str(body.get('prompt', ''))[:4000],
                     'error': message, 'provider_responses': replies}
            with store.lock:
                history = store.read('api-image-history', [])
                history.append(entry)
                store.write('api-image-history', history)
            return JSONResponse({'error': message, 'history_id': entry['id']}, 400)
        finally:
            responses.reset(marker)
            generating -= 1

    @app.post('/api/images/imagegen/clear-history')
    async def clear_history(request: Request):
        body = await request.json()
        if body.get('confirm') is not True:
            raise ValueError('Confirm permanent removal of image history first.')
        if generating:
            raise ValueError('Wait for image generation to finish before clearing history.')
        with store.lock:
            history = store.read('api-image-history', [])
            for item in history:
                path = api.image_path(str(item.get('id', '')))
                if path:
                    path.unlink(missing_ok=True)
            store.write('api-image-history', [])
            store.write('image-library-deleted', [])
        return {'ok': True, 'message': 'Image history cleared. Copies saved to Downloads are unchanged.'}

    @app.post('/api/images/imagegen/library')
    async def library(request: Request):
        body = await request.json()
        identity, action = str(body.get('id', '')), body.get('action')
        if action not in {'save', 'delete', 'restore'}:
            raise ValueError('Invalid image action')
        path = api.image_path(identity)
        if not path and (action == 'save' or not any(item.get('id') == identity for item in store.read('api-image-history', []))):
            return JSONResponse({'error': 'Image not found'}, 404)
        if action == 'save':
            _, extension = image_type(path)
            destination = Path.home() / 'Downloads'
            destination.mkdir(exist_ok=True)
            data = path.read_bytes()
            for number in range(1000):
                suffix = '' if number == 0 else f'-{number}'
                target = destination / f'BorgNet-{identity}{suffix}.{extension}'
                try:
                    with target.open('xb') as output:
                        output.write(data)
                    return {'ok': True, 'message': f'Saved to Downloads: {target.name}'}
                except FileExistsError:
                    continue
            raise ValueError('Could not choose an unused download filename')
        with store.lock:
            deleted = set(store.read('image-library-deleted', []))
            if action == 'delete':
                deleted.add(identity)
            else:
                deleted.discard(identity)
            store.write('image-library-deleted', sorted(deleted))
        return {'ok': True, 'message': 'Moved to Recently deleted.' if action == 'delete' else 'Image restored.'}


def image_type(path):
    if path.stat().st_size > 64_000_000:
        raise ValueError('Image is too large')
    with path.open('rb') as source:
        header = source.read(16)
    if header.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png', 'png'
    if header.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg', 'jpg'
    if header[:4] == b'RIFF' and header[8:12] == b'WEBP':
        return 'image/webp', 'webp'
    raise ValueError('Invalid image format')
