import json
import sys
import httpx
import pytest
from borgnet.config import Connection, Store
from borgnet.providers import Providers, Tunnels
from borgnet.routing import choose
from borgnet.permissions import Permissions, Policy
from borgnet.server import create_app
from tests.client import TestClient


def setup(tmp_path, backend='connection'):
    store = Store(tmp_path)
    candidates = [Connection(id=i,kind='ollama',url='http://localhost:11434',model=i) for i in ['a','b']]
    store.write('config', {'connections':[c.model_dump() for c in candidates], 'mcp_sources':[],
                          'routing':{'backend':backend,'selector':'a'}})
    return store,candidates


@pytest.mark.asyncio
@pytest.mark.parametrize('choice',['b','unknown','uncertain'])
async def test_validated_selection(tmp_path, choice):
    store, candidates = setup(tmp_path)
    calls=[]
    def respond(r):
        body=json.loads(r.content);calls.append(body)
        assert body['format']['properties']['connection']['enum']==['a','b','uncertain']
        return httpx.Response(200,json={'message':{'content':json.dumps({'connection':choice,'reason':'Domain fit'})}})
    providers=Providers(store,Tunnels(),httpx.MockTransport(respond))
    if choice=='b':
        chosen,route=await choose(providers,store,candidates,'Explain recursion')
        assert chosen.id=='b' and route['reason']=='Domain fit'
    else:
        with pytest.raises(ValueError):await choose(providers,store,candidates,'Explain recursion')
    assert len(calls)==1


@pytest.mark.asyncio
async def test_native_jev_contract(tmp_path):
    store,candidates=setup(tmp_path,'jev');store.save_secret('__jev_router__','fixture-secret')
    candidates[0].capabilities='Text reasoning; no tool execution'
    candidates[0].context_window=4096
    candidates[1].capabilities='Long text and code analysis'
    candidates[1].context_window=32768
    def respond(r):
        assert str(r.url)=='https://api.typesafe.ai/v1/systemone'
        assert r.headers['Authorization']=='Bearer fixture-secret'
        request=json.loads(r.content)
        assert request['questions']['route']['type']=='choice'
        assert request['questions']['route']['criteria']['b']['capabilities']=='Long text and code analysis'
        assert request['questions']['route']['criteria']['a']['context_window_tokens']==4096
        assert request['questions']['route']['criteria']['a']['tool_access']['command_execution'] is False
        assert request['state']['reference_characters']==12000
        assert request['state']['prior_content_characters']==9000
        return httpx.Response(200,json={'model':'jev-fixture','answers':{'route':{'type':'choice','choice':'b','confidence':.8,'probabilities':{'a':.1,'b':.8,'uncertain':.1}}}})
    chosen,route=await choose(Providers(store,Tunnels(),httpx.MockTransport(respond)),store,candidates,'Question','r'*12000,
        [{'prompt':'p'*3000,'results':[{'text':'a'*6000}]}])
    assert chosen.id=='b' and route['selector']=='jev-fixture'


@pytest.mark.asyncio
async def test_selector_sees_real_grants_and_os_readiness(tmp_path, monkeypatch):
    store, candidates = setup(tmp_path)
    cfg = store.config()
    cfg['permissions'] = Permissions(overrides={'b': Policy(workspace=str(tmp_path), full_access=True,
                                                            browser=True, computer=True)}).model_dump()
    store.write('config', cfg)
    monkeypatch.setattr('borgnet.adapter_setup.status', lambda: {
        'browser': {'ready': True}, 'computer': {'ready': False}, 'grok_registered': False})
    monkeypatch.setattr('borgnet.app_connectors._cura_processes', lambda: [123])
    monkeypatch.setattr('borgnet.app_connectors._cura_process_safe', lambda pid: False)
    def respond(request):
        body = json.loads(request.content)
        evidence = json.loads(body['messages'][-1]['content'])
        assert evidence['candidates']['a']['tool_access']['command_execution'] is False
        tools = evidence['candidates']['b']['tool_access']
        assert tools['command_execution'] is True
        assert tools['browser_interaction'] is True
        assert tools['visual_desktop_control'] is False
        assert tools['tool_protocol'] == 'native function calls'
        if sys.platform == 'darwin':
            assert tools['app_workflows']['cura_model_open'] is False
        return httpx.Response(200, json={'message': {'content': json.dumps({'connection':'b','reason':'Browser grant'})}})
    chosen, _ = await choose(Providers(store, Tunnels(), httpx.MockTransport(respond)), store, candidates, 'Open a website')
    assert chosen.id == 'b'


def test_dispatch_routes_only_one_and_preserves_context(tmp_path):
    store,candidates=setup(tmp_path)
    store.write('context',[{'id':'reference','title':'Test','text':'full reference'}])
    seen=[]
    def respond(r):
        body=json.loads(r.content);seen.append(body)
        if body.get('format'):
            return httpx.Response(200,json={'message':{'content':json.dumps({'connection':'b','reason':'Best fit'})}})
        assert body['model']=='b' and 'full reference' in body['messages'][-1]['content']
        return httpx.Response(200,headers={'content-type':'application/x-ndjson'},text=json.dumps({'message':{'content':'answer'},'done':True})+'\n')
    app=create_app(tmp_path,httpx.MockTransport(respond))
    with TestClient(app) as client:
        token=client.get('/api/state').json()['token']
        response=client.post('/api/dispatch',headers={'X-BorgNet-Token':token},json={'prompt':'Question','connections':['a','b'],'contexts':['reference'],'auto_select':True})
        assert response.status_code==200,response.text
        events=[json.loads(x) for x in response.text.splitlines()]
        assert events[0]['type']=='routing'
        assert [x['connection'] for x in events if x['type']=='result']==['b']
        assert store.read('history',[])[0]['routing']['connection']=='b'
        assert len(seen)==2
        assert client.post('/api/routing',headers={'X-BorgNet-Token':token},json={'backend':'connection','selector':'a'}).status_code==200


@pytest.mark.asyncio
async def test_forced_tool_call(tmp_path):
    store,candidates=setup(tmp_path)
    cfg=store.config();cfg['connections'][0]['kind']='openai';store.write('config',cfg)
    def respond(r):
        body=json.loads(r.content)
        assert body['tool_choice']['function']['name']=='select_model'
        return httpx.Response(200,json={'choices':[{'message':{'tool_calls':[{'function':{'name':'select_model','arguments':json.dumps({'connection':'b','reason':'fit'})}}]}}]})
    chosen,_=await choose(Providers(store,Tunnels(),httpx.MockTransport(respond)),store,candidates,'Question')
    assert chosen.id=='b'


def test_failed_route_releases_reservation_and_does_not_answer(tmp_path):
    store,_=setup(tmp_path)
    seen=[]
    def respond(r):
        seen.append(r)
        return httpx.Response(200,json={'message':{'content':'{"connection":"not-allowed","reason":"bad"}'}})
    app=create_app(tmp_path,httpx.MockTransport(respond))
    with TestClient(app) as client:
        token=client.get('/api/state').json()['token'];headers={'X-BorgNet-Token':token}
        for _ in range(2):
            response=client.post('/api/dispatch',headers=headers,json={'prompt':'test','connections':['a','b'],'auto_select':True})
            assert response.status_code==400 and 'invalid candidate' in response.text
        assert len(seen)==2 and store.read('history',[])==[]
        assert client.post('/api/routing',headers=headers,json={'backend':'jev','api_key':'private-fixture'}).status_code==200
        assert 'private-fixture' not in client.get('/api/state').text
