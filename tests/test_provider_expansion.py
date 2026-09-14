import json
import httpx
import pytest
from borgnet.config import Connection, Store
from borgnet.providers import Providers, Tunnels

@pytest.mark.parametrize('kind', ['responses', 'cohere'])
async def test_new_protocol_history_auth_and_public_text(tmp_path, kind):
    store=Store(tmp_path); store.save_secret('fixture', 'fixture-key')
    messages=[{'role':'user','content':'First'},{'role':'assistant','content':'Prior'},{'role':'user','content':'Next'}]
    def handle(request):
        assert request.headers['Authorization']=='Bearer fixture-key'
        data=json.loads(request.content)
        assert data['model']=='fixture-model' and data['stream'] is False
        if kind=='responses':
            assert request.url.path=='/responses'
            assert data['store'] is False and data['input']==messages and data['instructions']=='Purpose'
            assert data['max_output_tokens']==200
            return httpx.Response(200,json={'status':'completed','output':[{'type':'reasoning','summary':[]},{'type':'message','content':[{'type':'output_text','text':'Answer'}]}]})
        assert request.url.path=='/v2/chat'
        assert data['messages']==[{'role':'system','content':'Purpose'}]+messages
        assert data['max_tokens']==200 and 'store' not in data
        return httpx.Response(200,json={'finish_reason':'COMPLETE','message':{'content':[{'type':'thinking','text':'Hidden'},{'type':'text','text':'Answer'}]}})
    p=Providers(store,Tunnels(),httpx.MockTransport(handle))
    c=Connection(id='fixture',kind=kind,url='http://localhost:1234',model='fixture-model',options={'store':True,'model':'wrong','stream':True,'max_tokens':200,'max_output_tokens':200})
    assert await p.chat(c,messages,'Purpose')=='Answer'

@pytest.mark.parametrize('kind,data', [('responses',{'status':'incomplete','output':[]}),('cohere',{'finish_reason':'MAX_TOKENS','message':{'content':[{'type':'text','text':'partial'}]}})])
async def test_incomplete_not_accepted(tmp_path,kind,data):
    p=Providers(Store(tmp_path),Tunnels(),httpx.MockTransport(lambda r:httpx.Response(200,json=data)))
    with pytest.raises(ValueError,match='did not complete'):
        await p.chat(Connection(kind=kind,url='http://localhost:1234',model='fixture'),[])

async def test_cohere_discovery_pagination(tmp_path):
    def handle(request):
        assert request.url.path=='/v1/models' and request.url.params['endpoint']=='chat'
        if 'page_token' not in request.url.params:
            return httpx.Response(200,json={'models':[{'name':'a'},{'name':'old','is_deprecated':True}], 'next_page_token':'next/+'})
        assert request.url.params['page_token']=='next/+'
        return httpx.Response(200,json={'models':[{'name':'b'}]})
    p=Providers(Store(tmp_path),Tunnels(),httpx.MockTransport(handle))
    assert await p.models(Connection(kind='cohere',url='http://localhost:1234'))==['a','b']

@pytest.mark.parametrize('kind,options', [('anthropic',{'max_tokens':800,'temperature':.4}),('gemini',{'maxOutputTokens':800,'temperature':.4})])
async def test_generation_options(tmp_path,kind,options):
    def handle(request):
        data=json.loads(request.content)
        target=data['generationConfig'] if kind=='gemini' else data
        assert all(target[k]==v for k,v in options.items())
        return httpx.Response(200,json={'content':[{'type':'text','text':'Answer'}], 'candidates':[{'content':{'parts':[{'text':'Answer'}]}}]})
    p=Providers(Store(tmp_path),Tunnels(),httpx.MockTransport(handle))
    assert await p.chat(Connection(kind=kind,url='http://localhost:1234',model='fixture',options=options),[])=='Answer'
