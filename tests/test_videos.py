import json
import time
import httpx
import pytest
from tests.client import TestClient
from borgnet.config import Store
from borgnet.server import create_app
from borgnet.videos import Videos

MP4 = b'\x00\x00\x00\x18ftypisom' + b'fixture-video'


@pytest.mark.asyncio
@pytest.mark.parametrize('provider,model,duration,size', [
    ('xai','grok-imagine-video-1.5',5,'16:9'),
    ('gemini','veo-3.1-generate-preview',4,'16:9'),
    ('openai','sora-2',4,'1280x720'),
])
async def test_video_lifecycle(tmp_path, monkeypatch, provider, model, duration, size):
    monkeypatch.delenv({'xai':'XAI_API_KEY','gemini':'GEMINI_API_KEY','openai':'OPENAI_API_KEY'}[provider], raising=False)
    store = Store(tmp_path)
    store.save_secret('image-' + provider, 'test-secret')
    calls = []
    def transport(request):
        calls.append(request)
        if request.url.host == 'vidgen.x.ai':
            assert 'authorization' not in request.headers
            return httpx.Response(200, content=MP4)
        expected = 'x-goog-api-key' if provider == 'gemini' else 'authorization'
        assert 'test-secret' in request.headers[expected]
        if request.method == 'POST':
            if provider == 'gemini':
                assert json.loads(request.content)['parameters']['durationSeconds'] == duration
                return httpx.Response(200, json={'name':'models/'+model+'/operations/test123'})
            if provider == 'xai':
                assert json.loads(request.content)['duration'] == duration
                return httpx.Response(200, json={'request_id':'test123'})
            assert 'multipart/form-data' in request.headers['content-type']
            assert b'name="seconds"' in request.content
            return httpx.Response(200, json={'id':'video_123'})
        if request.url.path.endswith('/content') or request.url.path.endswith('/download'):
            return httpx.Response(200, content=MP4)
        if provider == 'gemini':
            return httpx.Response(200, json={'done':True,'response':{'generateVideoResponse':{'generatedSamples':[{'video':{'uri':'https://generativelanguage.googleapis.com/download'}}]}}})
        if provider == 'xai':
            return httpx.Response(200, json={'status':'done','video':{'url':'https://vidgen.x.ai/video.mp4','respect_moderation':True}})
        return httpx.Response(200, json={'status':'completed','progress':100})
    service = Videos(tmp_path, store, httpx.MockTransport(transport))
    job = await service.create({'model_id':provider+'::'+model,'prompt':'A leaf moves','duration':duration,'size':size})
    assert job['status'] == 'pending' and 'remote_id' not in job
    # A new service instance resumes the saved job after server/page reload.
    service = Videos(tmp_path, store, httpx.MockTransport(transport))
    completed = await service.refresh(job['id'])
    assert completed['status'] == 'completed'
    assert (tmp_path/'api-videos'/(job['id']+'.mp4')).read_bytes() == MP4
    await service.refresh(job['id'])
    assert sum(r.method == 'POST' for r in calls) == 1
    with TestClient(create_app(tmp_path)) as client:
        response = client.get(completed['url'])
        assert response.status_code == 200 and response.content == MP4
        assert client.get(completed['url']+'?download=true').headers['content-disposition'].startswith('attachment')
        assert client.post('/api/videos',json={}).status_code == 403
        assert 'test-secret' not in client.get('/api/videos').text


def test_video_download_boundaries():
    for url in ['http://vidgen.x.ai/video.mp4','https://127.0.0.1/a','https://vidgen.x.ai.evil.com/a','https://user:pass@vidgen.x.ai/a','https://vidgen.x.ai:8443/a']:
        assert not Videos.allowed_download('xai',url)
    assert Videos.allowed_download('xai','https://vidgen.x.ai/a.mp4')


@pytest.mark.asyncio
async def test_video_failure_does_not_resubmit(tmp_path,monkeypatch):
    monkeypatch.setenv('XAI_API_KEY','fixture')
    store=Store(tmp_path)
    calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(200,json={'request_id':'a'} if request.method=='POST' else {'status':'failed'})
    service=Videos(tmp_path,store,httpx.MockTransport(handler))
    job=await service.create({'model_id':'xai::grok-imagine-video-1.5','prompt':'fixture','duration':5,'size':'16:9'})
    with pytest.raises(ValueError,match='Finish'):
        await service.create({'model_id':'xai::grok-imagine-video-1.5','prompt':'fixture','duration':5,'size':'16:9'})
    assert (await service.refresh(job['id']))['status']=='failed'
    await service.refresh(job['id'])
    assert len(calls)==2


def test_interrupted_submission_recovery(tmp_path):
    store = Store(tmp_path)
    store.write('video-jobs', [{'id':'a'*32, 'status':'submitting'}])
    service = Videos(tmp_path, store)
    assert service.jobs()[0]['status'] == 'unknown'
    assert 'provider history' in service.jobs()[0]['error']


@pytest.mark.asyncio
async def test_missing_video_key_never_calls_provider(tmp_path, monkeypatch):
    monkeypatch.delenv('XAI_API_KEY', raising=False)
    service = Videos(tmp_path, Store(tmp_path), httpx.MockTransport(lambda request: pytest.fail('Unexpected provider call')))
    with pytest.raises(ValueError, match='API key'):
        await service.create({'model_id':'xai::grok-imagine-video-1.5','prompt':'fixture','duration':5,'size':'16:9'})
    assert service.jobs() == []
