import base64
import json
import httpx
import pytest
from borgnet.config import Store, Connection
from borgnet.providers import Providers, Tunnels
from borgnet.horde_images import generate
from borgnet.image_api import create_image_api


@pytest.mark.asyncio
async def test_horde_queue_and_inline_image():
    requests=[]
    encoded=base64.b64encode(b'\x89PNG\r\n\x1a\nfixture').decode()
    def route(request):
        requests.append(request)
        path=request.url.path
        if path.endswith('/async'):return httpx.Response(202,json={'id':'job-123'})
        if '/check/' in path:return httpx.Response(200,json={'done':True})
        return httpx.Response(200,json={'generations':[{'img':encoded,'censored':False}]})
    result=await generate('auto','A lake','auto','',httpx.MockTransport(route))
    assert result==encoded
    body=json.loads(requests[0].content)
    assert body['shared'] is False and body['r2'] is False
    assert body['trusted_workers'] is True and body['params']['n']==1
    assert requests[0].headers['apikey']=='0000000000'


@pytest.mark.asyncio
async def test_horde_fault_cancels_job():
    methods=[]
    def route(request):
        methods.append(request.method)
        if request.method=='POST':return httpx.Response(202,json={'id':'job-123'})
        return httpx.Response(200,json={'faulted':True})
    with pytest.raises(ValueError,match='cannot fulfill'):
        await generate('auto','A lake','auto','fixture',httpx.MockTransport(route))
    assert methods==['POST','GET','DELETE']


@pytest.mark.asyncio
async def test_openrouter_free_only(tmp_path):
    called=[]
    def route(request):
        called.append(request)
        return httpx.Response(200,json={'data':[{'id':'vendor/paid'},{'id':'vendor/free:free'}]})
    provider=Providers(Store(tmp_path),Tunnels(),httpx.MockTransport(route))
    item=Connection(url='https://openrouter.ai/api/v1',kind='openai',model='vendor/paid',options={'free_only':True})
    assert await provider.models(item)==['openrouter/free','vendor/free:free']
    with pytest.raises(ValueError,match='restricted to free'):
        await provider.chat(item,[{'role':'user','content':'hello'}])
    assert len(called)==1


@pytest.mark.asyncio
async def test_pollinations_catalog_and_generation(tmp_path,monkeypatch):
    store=Store(tmp_path);store.save_secret('image-pollinations','fixture-pollen')
    real_client=httpx.AsyncClient
    encoded=base64.b64encode(b'\x89PNG\r\n\x1a\nfixture').decode()
    def route(request):
        if request.url.host=='aihorde.net':return httpx.Response(200,json=[])
        assert request.headers['authorization']=='Bearer fixture-pollen'
        if request.method=='GET':return httpx.Response(200,json=[{'name':'freeish'},{'name':'paid','paid_only':True}])
        assert str(request.url)=='https://gen.pollinations.ai/v1/images/generations'
        assert json.loads(request.content)['response_format']=='b64_json'
        return httpx.Response(200,json={'data':[{'b64_json':encoded}]})
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:real_client(**kwargs,transport=httpx.MockTransport(route)))
    for env in ['OPENAI_API_KEY','GEMINI_API_KEY','XAI_API_KEY','POLLINATIONS_API_KEY']:
        monkeypatch.delenv(env,raising=False)
    api=create_image_api(tmp_path,store)
    catalog=await api.catalog()
    assert [item['model'] for item in catalog if item['provider']=='pollinations']==['freeish']
    result=await api.generate({'model_id':'api::pollinations::freeish','prompt':'A lake'})
    assert api.image_path(result['id']).read_bytes().startswith(b'\x89PNG')
    with pytest.raises(ValueError,match='Refresh image models'):
        await api.generate({'model_id':'api::pollinations::paid','prompt':'A lake'})


@pytest.mark.asyncio
async def test_openrouter_image_key_reuse_and_endpoint(tmp_path,monkeypatch):
    store=Store(tmp_path)
    store.write('config',{'connections':[Connection(id='router',kind='openai',url='https://openrouter.ai/api/v1',model='openrouter/free').model_dump()]})
    store.save_secret('router','router-fixture')
    real_client=httpx.AsyncClient
    encoded=base64.b64encode(b'\x89PNG\r\n\x1a\nfixture').decode()
    def route(request):
        if request.url.host=='aihorde.net':return httpx.Response(200,json=[])
        assert request.headers['authorization']=='Bearer router-fixture'
        if request.method=='GET':
            assert request.url.path=='/api/v1/images/models'
            return httpx.Response(200,json={'data':[
                {'id':'vendor/image','architecture':{'output_modalities':['image']},'supported_parameters':{'aspect_ratio':{'values':['1:1','16:9']},'quality':{'values':['low','high']}}},
                {'id':'vendor/text','architecture':{'output_modalities':['text']}}]})
        assert request.url.path=='/api/v1/images'
        payload=json.loads(request.content)
        assert payload=={'model':'vendor/image','prompt':'A lake','n':1,'aspect_ratio':'16:9','quality':'high'}
        return httpx.Response(200,json={'data':[{'b64_json':encoded,'media_type':'image/png'}]})
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:real_client(**kwargs,transport=httpx.MockTransport(route)))
    for env in ['OPENAI_API_KEY','GEMINI_API_KEY','XAI_API_KEY','POLLINATIONS_API_KEY','OPENROUTER_API_KEY']:
        monkeypatch.delenv(env,raising=False)
    api=create_image_api(tmp_path,store)
    catalog=await api.catalog()
    images=[m for m in catalog if m['provider']=='openrouter']
    assert len(images)==1 and images[0]['installed']
    assert '16:9' in images[0]['sizes']
    result=await api.generate({'model_id':'api::openrouter::vendor/image','prompt':'A lake','size':'16:9','quality':'high'})
    assert api.image_path(result['id']).read_bytes().startswith(b'\x89PNG')


@pytest.mark.asyncio
async def test_horde_transient_poll_failures_keep_same_job(monkeypatch):
    from borgnet import horde_images
    async def no_sleep(seconds): pass
    monkeypatch.setattr(horde_images.asyncio, 'sleep', no_sleep)
    calls=[]
    def route(request):
        calls.append(request)
        if request.method == 'POST':return httpx.Response(202,json={'id':'same-job'})
        checks=sum('/check/' in r.url.path for r in calls)
        if '/check/' in request.url.path:
            if checks==1:raise httpx.ReadTimeout('synthetic',request=request)
            if checks==2:return httpx.Response(503,text='temporary gateway failure')
            if checks==3:return httpx.Response(200,json={'done':False,'is_possible':False})
            return httpx.Response(200,json={'done':True})
        return httpx.Response(200,json={'generations':[{'img':'synthetic-inline','censored':False}]})
    assert await generate('auto','synthetic','auto','',httpx.MockTransport(route))=='synthetic-inline'
    assert sum(r.method=='POST' for r in calls)==1
    assert not any(r.method=='DELETE' for r in calls)
    assert horde_images.QUEUE_TIMEOUT == 1200


@pytest.mark.asyncio
async def test_horde_submission_timeout_is_not_retried():
    calls=[]
    def route(request):
        calls.append(request)
        raise httpx.ReadTimeout('synthetic',request=request)
    with pytest.raises(httpx.ReadTimeout):
        await generate('auto','synthetic','auto','',httpx.MockTransport(route))
    assert len(calls)==1
