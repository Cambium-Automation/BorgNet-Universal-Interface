import base64
import httpx
from tests.client import TestClient
from fastapi.testclient import TestClient as PublicClient
from borgnet.server import create_app


def test_media_auth_validation_and_ephemeral_request(tmp_path):
    captured = []
    def upstream(request):
        captured.append(request)
        return httpx.Response(200, json={'candidates': [{'content': {'parts': [
            {'text': 'private', 'thought': True}, {'text': 'A short answer.'}]}}]})
    app = create_app(tmp_path, provider_transport=httpx.MockTransport(upstream))
    app.state.store.write('config', {**app.state.store.config(), 'connections': [{'id':'gem', 'kind':'gemini',
        'url':'https://generativelanguage.googleapis.com/v1beta', 'model':'chosen-model'}]})
    app.state.store.save_secret('gem', 'fixture-key')
    data = {'connection':'gem','mime':'audio/webm',
            'data':base64.b64encode(b'\x1aE\xdf\xa3fixture').decode(),'mode':'transcribe'}
    with TestClient(app) as client, PublicClient(app,base_url='http://127.0.0.1') as public:
        token = client.get('/api/state').json()['token']
        headers = {'X-BorgNet-Token':token}
        assert public.post('/api/voice-video/respond',json=data).status_code == 401
        assert client.post('/api/voice-video/respond',json=data).status_code == 403
        assert client.post('/api/voice-video/respond',json={**data,'data':'not base64'},headers=headers).status_code == 400
        assert client.post('/api/voice-video/respond',json={**data,'mime':'text/html'},headers=headers).status_code == 400
        assert client.post('/api/voice-video/respond',json={**data,'connection':'missing'},headers=headers).status_code == 400
        result = client.post('/api/voice-video/respond',json=data,headers=headers)
        assert result.status_code == 200
        assert result.json()['text'] == 'A short answer.'
        assert len(captured) == 1
        assert captured[0].headers['x-goog-api-key'] == 'fixture-key'
        assert b'inlineData' in captured[0].content
        assert b'Transcribe' in captured[0].content
        # Larger media exemption does not affect ordinary endpoints.
        assert client.post('/api/settings',content=b'x'*1_000_001,headers=headers).status_code == 413
        assert client.post('/api/voice-video/respond',content=b'x'*11_000_001,headers=headers).status_code == 413
    assert not list(tmp_path.glob('*.webm'))
    assert not list(tmp_path.glob('*history*'))


def test_disabled_media_connection_not_advertised(tmp_path):
    app=create_app(tmp_path)
    app.state.store.write('config', {**app.state.store.config(), 'connections': [{'id':'gem','kind':'gemini','enabled':False,
        'url':'https://generativelanguage.googleapis.com/v1beta','model':'chosen-model'}]})
    with TestClient(app) as client:
        assert client.get('/api/voice-video/models').json() == {'models':[]}
