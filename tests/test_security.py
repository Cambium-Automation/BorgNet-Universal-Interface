import asyncio
import json
import os
import httpx
import pytest
from fastapi.testclient import TestClient as RawClient
from tests.client import TestClient
from borgnet.server import create_app
from borgnet.config import Store, Connection
from borgnet.providers import Providers, Tunnels


def test_private_api_and_media_scope(tmp_path):
    app = create_app(tmp_path)
    with RawClient(app, base_url='http://127.0.0.1') as public, TestClient(app) as owner:
        assert public.get('/').status_code == 200
        for route in ['/api/state', '/api/session', '/api/videos', '/api/images/imagegen/models']:
            assert public.get(route).status_code == 401
        assert public.post('/api/mcp',json={'command':'anything'}).status_code == 401
        media = owner.get('/api/session').json()['media_token']
        assert public.get('/api/state',params={'media_token':media}).status_code == 401
        assert public.get('/api/state',headers={'X-BorgNet-Session':media}).status_code == 401
        assert owner.get('/api/state').status_code == 200
        identity='20260914-010000-abcdef01'
        directory=tmp_path/'api-images'; directory.mkdir()
        (directory/identity).write_bytes(b'\x89PNG\r\n\x1a\nfixture')
        route='/api/images/imagegen/images/'+identity
        assert public.get(route).status_code == 401
        assert public.get(route,params={'media_token':media}).status_code == 200
        assert owner.get('/api/state',headers={'Sec-Fetch-Site':'same-site'}).status_code == 403
        assert owner.get(route,headers={'Sec-Fetch-Site':'cross-site'}).status_code == 403
        for host in ['evil.example', 'testserver', 'user@localhost', '[invalid', 'localhost:bad']:
            assert owner.get('/api/state',headers={'Host':host}).status_code == 403
        assert owner.get('/').headers['cross-origin-resource-policy']=='same-origin'
        assert (tmp_path/'browser-session.json').stat().st_mode & 0o777 == 0o600


def test_declared_and_chunked_body_limit(tmp_path):
    app = create_app(tmp_path)
    with TestClient(app) as owner:
        token=owner.get('/api/state').json()['token']
        headers={'X-BorgNet-Token':token,'Content-Type':'application/json'}
        assert owner.post('/api/settings',content=b'{}',headers={**headers,'Content-Length':'bad'}).status_code==400
        assert owner.post('/api/settings',content=b'x'*1_000_001,headers=headers).status_code==413
        # Streaming content has no declared Content-Length.
        assert owner.post('/api/settings',content=iter([b'x'*600_000,b'x'*600_000]),headers=headers).status_code==413
        assert owner.get('/api/state').status_code==200


def test_changed_destination_cannot_reuse_secret(tmp_path):
    app=create_app(tmp_path)
    with TestClient(app) as owner:
        owner.headers['X-BorgNet-Token']=owner.get('/api/state').json()['token']
        body={'kind':'openai','url':'https://api.openai.com/v1','api_key':'private-fixture'}
        identity=owner.post('/api/connections',json=body).json()['id']
        changed={'id':identity,'kind':'openai','url':'https://attacker.example/v1'}
        assert owner.post('/api/connections',json=changed).status_code==400
        assert app.state.store.config()['connections'][0]['url']=='https://api.openai.com/v1'
        assert owner.post('/api/connections',json={**changed,'api_key':'replacement'}).status_code==200
        assert app.state.store.read('secrets',{})[identity]=='replacement'


@pytest.mark.asyncio
async def test_provider_reply_limit(tmp_path):
    class Oversized(httpx.AsyncByteStream):
        async def __aiter__(self):
            for _ in range(9):
                yield b'x'*1_000_000
    transport=httpx.MockTransport(lambda request:httpx.Response(200,stream=Oversized()))
    providers=Providers(Store(tmp_path),Tunnels(),transport)
    with pytest.raises(ValueError,match='8 MB'):
        await providers.models(Connection(url='http://localhost:1234'))


def test_session_rotates_after_restart(tmp_path):
    old=create_app(tmp_path).state.session_token
    app=create_app(tmp_path)
    with RawClient(app,base_url='http://127.0.0.1') as client:
        assert client.get('/api/state',headers={'X-BorgNet-Session':old}).status_code==401
