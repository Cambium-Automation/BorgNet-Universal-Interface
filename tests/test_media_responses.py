import json
import httpx
import pytest
from borgnet.media_responses import capture, public_response
from borgnet.config import Store
from borgnet.server import create_app
from borgnet.videos import Videos
from tests.client import TestClient


def test_public_text_redaction_and_reasoning_exclusion():
    reply = public_response({'error': {'message': 'Declined fixture-secret https://example.org/private', 'code': 'policy'},
        'candidates': [{'finishReason': 'SAFETY', 'content': {'parts': [{'thought': True, 'text': 'hidden reasoning'}, {'text': 'Public explanation.'}]}}],
        'choices': [{'message': {'refusal': 'Cannot provide this image.', 'reasoning': 'hidden reasoning'}}],
        'data': [{'revised_prompt': 'A synthetic leaf'}]}, ['fixture-secret'])
    text = json.dumps(reply)
    assert 'Public explanation.' in text and 'Cannot provide this image.' in text
    assert 'fixture-secret' not in text and 'example.org' not in text and 'hidden reasoning' not in text
    assert reply['codes'] == ['policy', 'SAFETY']
    assert public_response({'candidates': [None, {'content': None}], 'data': None})['messages'] == []
    assert public_response({'message': 'x' * 40000})['truncated']


@pytest.mark.parametrize('success', [True, False])
def test_image_response_persists_with_or_without_media(tmp_path, success):
    app = create_app(tmp_path)
    identity = '20260914-010000-abcdef01'
    async def generate(body):
        capture({'message': 'Synthetic public response.', 'refusal': '' if success else 'Synthetic refusal.'})
        if not success:
            raise ValueError('No image returned')
        result = {'id': identity, 'prompt': 'synthetic', 'url': '/api/imagegen/images/' + identity}
        app.state.store.write('api-image-history', [result])
        return result
    app.state.image_api.generate = generate
    with TestClient(app) as client:
        client.headers['X-BorgNet-Token'] = client.get('/api/state').json()['token']
        response = client.post('/api/images/imagegen/generate', json={'model_id': 'test', 'prompt': 'synthetic'})
        assert response.status_code == (201 if success else 400)
    with TestClient(create_app(tmp_path)) as client:
        client.headers['X-BorgNet-Token'] = client.get('/api/state').json()['token']
        record = client.get('/api/images/imagegen/history').json()['images'][0]
        assert record['provider_responses'][0]['messages'][0] == 'Synthetic public response.'
        if not success:
            assert 'Synthetic refusal.' in record['provider_responses'][0]['messages']
            assert client.post('/api/images/imagegen/library', json={'id': record['id'], 'action': 'delete'}).status_code == 200
            assert client.get('/api/images/imagegen/history').json()['trash'][0]['provider_responses'] == record['provider_responses']
            assert client.post('/api/images/imagegen/library', json={'id': record['id'], 'action': 'restore'}).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize('provider,model,size', [('xai','grok-imagine-video-1.5','16:9'), ('gemini','veo-3.1-generate-preview','16:9'), ('openai','sora-2','1280x720')])
async def test_video_http_refusal_preserved(tmp_path, monkeypatch, provider, model, size):
    for name in ['XAI_API_KEY', 'GEMINI_API_KEY', 'GOOGLE_API_KEY', 'OPENAI_API_KEY']:
        monkeypatch.delenv(name, raising=False)
    store = Store(tmp_path)
    store.save_secret('image-' + provider, 'fixture-secret')
    service = Videos(tmp_path, store, httpx.MockTransport(lambda req: httpx.Response(400, json={'error': {'message': 'Synthetic refusal. fixture-secret', 'code': 'content_policy'}})))
    with pytest.raises(ValueError):
        await service.create({'model_id': provider+'::'+model, 'prompt': 'synthetic', 'duration': 5 if provider == 'xai' else 4, 'size': size})
    record = Videos(tmp_path, store).jobs()[0]
    assert record['status'] == 'failed'
    assert record['provider_responses'][0]['messages'] == ['Synthetic refusal. [redacted]']


@pytest.mark.asyncio
async def test_video_filtered_completion_keeps_reason(tmp_path, monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY', 'fixture-key')
    service = Videos(tmp_path, Store(tmp_path), httpx.MockTransport(lambda req: httpx.Response(200, json=
        {'name': 'operations/test'} if req.method == 'POST' else {'done': True, 'response': {'generateVideoResponse': {'raiMediaFilteredCount': 1, 'raiMediaFilteredReasons': ['Synthetic video refusal.']}}})))
    job = await service.create({'model_id': 'gemini::veo-3.1-generate-preview', 'prompt': 'synthetic', 'duration': 4, 'size': '16:9'})
    result = await service.refresh(job['id'])
    assert result['status'] == 'failed'
    assert result['provider_responses'][-1]['messages'] == ['Synthetic video refusal.']
