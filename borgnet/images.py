"""Local image library: generation, export, and recoverable deletion."""
from pathlib import Path
from fastapi import Request
from fastapi.responses import FileResponse, JSONResponse
from .image_api import create_image_api
from .subscription_images import create_subscription_images


def register_images(app, root, store):
    api = create_image_api(root, store)
    native = create_subscription_images(root, store)
    api.register(app)
    app.state.image_api, app.state.image_native = api, native

    @app.get('/api/images/imagegen/models')
    async def models():
        return {'models': native.catalog() + await api.catalog()}

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
        return JSONResponse(await adapter.generate(body), 201)

    @app.post('/api/images/imagegen/library')
    async def library(request: Request):
        body = await request.json()
        identity, action = str(body.get('id', '')), body.get('action')
        if action not in {'save', 'delete', 'restore'}:
            raise ValueError('Invalid image action')
        path = api.image_path(identity)
        if not path:
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
