import json
import os
import sys
from pathlib import Path
import httpx
import pytest
from tests.client import TestClient
from pydantic import ValidationError
from borgnet.config import Store, Connection, SSH, MCPSource
from borgnet.providers import Providers, Tunnels
from borgnet.server import create_app
from borgnet.mcp_bridge import inspect_source, fetch_context, shared_server


def fixture_response(request):
    path = request.url.path
    if request.method == 'GET':
        return httpx.Response(200,json={'models':[{'name':'fixture-chat','supportedGenerationMethods':['generateContent']}], 'data':[{'id':'fixture-chat'}]})
    payload=json.loads(request.content)
    if path == '/api/chat':
        if payload['stream'] is True:
            return httpx.Response(200,headers={'content-type':'application/x-ndjson'},content=json.dumps({'message':{'content':'Fixture answer'},'done':True})+'\n')
        assert payload['stream'] is False
        return httpx.Response(200,json={'message':{'content':'Fixture answer'}})
    if path.endswith('/chat/completions'):
        return httpx.Response(200,json={'choices':[{'message':{'content':'Fixture answer'}}]})
    if path.endswith('/messages'):
        assert request.headers['anthropic-version']=='2023-06-01'
        return httpx.Response(200,json={'content':[{'type':'text','text':'Fixture answer'}]})
    if ':generateContent' in path:
        return httpx.Response(200,json={'candidates':[{'content':{'parts':[{'text':'Hidden','thought':True},{'text':'Fixture answer'}]}}]})
    if path == '/api/pull':
        assert payload['model']=='fixture-download'
        return httpx.Response(200,json={'status':'success'})
    raise AssertionError(path)


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path, httpx.MockTransport(fixture_response))) as client:
        client.headers['X-BorgNet-Token']=client.get('/api/state').json()['token']
        yield client


def add(client, **kwargs):
    response=client.post('/api/connections',json={'kind':'ollama','url':'http://localhost:11434','model':'fixture-chat',**kwargs})
    assert response.status_code==200,response.text
    return response.json()['id']


def test_first_launch_is_empty_and_secrets_never_return(client,tmp_path):
    state=client.get('/api/state').json()
    assert state['connections']==state['mcp_sources']==state['context']==state['history']==[]
    identity=add(client,api_key='fixture-secret-value')
    state=client.get('/api/state')
    assert 'fixture-secret-value' not in state.text
    assert state.json()['connections'][0]['has_key'] is True
    assert (tmp_path/'secrets.json').stat().st_mode & 0o777 == 0o600
    client.post(f'/api/connections/{identity}/delete',json={})
    assert json.loads((tmp_path/'secrets.json').read_text())=={}


def test_origin_host_and_token_boundary(client):
    assert client.post('/api/settings',json={'theme':'dark'},headers={'Origin':'https://untrusted.example'}).status_code==403
    assert client.get('/api/state',headers={'Host':'untrusted.example'}).status_code==403
    assert client.post('/api/settings',json={'theme':'dark'},headers={'X-BorgNet-Token':'wrong'}).status_code==403
    assert client.post('/api/settings',json={'theme':'light'}).status_code==200
    assert client.get('/api/state').json()['theme']=='light'


@pytest.mark.parametrize('kind',['ollama','openai','anthropic','gemini'])
async def test_adapters_discover_and_chat(kind,tmp_path):
    item=Connection(id='fixture',kind=kind,url='http://localhost:1234',model='fixture-chat')
    adapter=Providers(Store(tmp_path),Tunnels(),httpx.MockTransport(fixture_response))
    assert await adapter.models(item)==['fixture-chat']
    assert await adapter.chat(item,[{'role':'user','content':'Fixture question'}],'Fixture purpose')=='Fixture answer'


async def test_auth_headers_and_no_error_secret_leak(tmp_path):
    store=Store(tmp_path);store.save_secret('fixture','fixture-secret-value')
    def upstream(request):
        assert request.headers['Authorization']=='Bearer fixture-secret-value'
        return httpx.Response(401,text='fixture-secret-value')
    adapter=Providers(store,Tunnels(),httpx.MockTransport(upstream))
    with pytest.raises(ValueError) as error:
        await adapter.models(Connection(id='fixture',url='http://localhost:1234'))
    assert 'fixture-secret-value' not in str(error.value)
    assert '401' in str(error.value)


async def test_blank_answer_is_error(tmp_path):
    adapter=Providers(Store(tmp_path),Tunnels(),httpx.MockTransport(lambda r:httpx.Response(200,json={'message':{'content':''}})))
    with pytest.raises(ValueError,match='no public text'):
        await adapter.chat(Connection(url='http://localhost:1234',model='fixture-chat'),[{'role':'user','content':'Hi'}])


def test_parallel_dispatch_and_history(client):
    one=add(client,purpose='Research');two=add(client,kind='openai',url='http://localhost:1234/v1',purpose='Review')
    response=client.post('/api/dispatch',json={'collaborate':False,'prompt':'Fixture question','connections':[one,two],'synthesize':two})
    assert response.status_code==200,response.text
    events=[json.loads(line) for line in response.text.splitlines()]
    results=[e for e in events if e['type']=='result']
    assert len(results)==3
    assert all(r['status']=='complete' for r in results)
    assert results[-1]['synthesis'] is True
    history=client.get('/api/state').json()['history']
    assert len(history)==1 and len(history[0]['results'])==3
    assert history[0]['conversation']==events[0]['conversation']


def test_discovery_pull_and_disabled_guard(client):
    identity=add(client)
    assert client.post(f'/api/connections/{identity}/discover',json={}).json()['models']==['fixture-chat']
    assert client.post(f'/api/connections/{identity}/pull',json={'model':'fixture-download'}).json()['status']=='success'
    add(client,id=identity,enabled=False)
    assert client.post('/api/dispatch',json={'collaborate':False,'prompt':'Hi','connections':[identity]}).status_code==400


def test_ssh_validation_and_no_shell():
    with pytest.raises(ValidationError):
        SSH(host='-oProxyCommand=anything')
    with pytest.raises(ValidationError):
        SSH(host='example.com;echo test')
    args=Tunnels.command(SSH(host='compute.example.com',user='operator'),23456)
    assert args[-1]=='operator@compute.example.com'
    assert '127.0.0.1:23456:127.0.0.1:11434' in args
    assert 'StrictHostKeyChecking=yes' in args and 'BatchMode=yes' in args
    with pytest.raises(ValidationError):
        Connection(url='http://api.example.com')
    with pytest.raises(ValidationError):
        Connection(url='https://secret@api.example.com')


async def test_real_stdio_mcp_and_sharing_boundary(tmp_path):
    store=Store(tmp_path)
    store.write('context',[{'id':'private','title':'Private','text':'private-text','shared':False},{'id':'public','title':'Shared fixture','text':'shared-text','shared':True}])
    source=MCPSource(name='Fixture MCP',transport='stdio',command=sys.executable,args=['-m','borgnet','--data-dir',str(tmp_path),'mcp'])
    discovery=await inspect_source(source,store)
    assert {t['name'] for t in discovery['tools']}=={'list_shared_context','read_shared_context'}
    assert discovery['resources'][0]['uri']=='borgnet://shared/context'
    text=await fetch_context(source,store,'tool','read_shared_context',{'context_id':'public'})
    assert text=='shared-text'
    index=await fetch_context(source,store,'resource','borgnet://shared/context',{})
    assert 'private' not in index and 'public' in index
    with pytest.raises(ValueError):
        await fetch_context(source,store,'tool','read_shared_context',{'context_id':'private'})


def test_context_is_opt_in_and_editable(client):
    result=client.post('/api/context',json={'title':'Reference','text':'A fixture reference'}).json()
    assert result['shared'] is False
    result['shared']=True
    assert client.post('/api/context',json=result).status_code==200
    assert client.get('/api/state').json()['context'][0]['shared'] is True
    client.post(f"/api/context/{result['id']}/delete",json={})
    assert client.get('/api/state').json()['context']==[]


async def test_real_streamable_http_mcp(tmp_path):
    import asyncio
    import socket
    with socket.socket() as listener:
        listener.bind(('127.0.0.1',0))
        port=listener.getsockname()[1]
    process=await asyncio.create_subprocess_exec(sys.executable,str(Path(__file__).with_name('mcp_fixture.py')),str(port),
        stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                reader,writer=await asyncio.open_connection('127.0.0.1',port)
                writer.close();await writer.wait_closed();break
            except OSError:
                await asyncio.sleep(.05)
        else:
            pytest.fail('HTTP MCP fixture failed to start')
        source=MCPSource(name='HTTP fixture',url=f'http://127.0.0.1:{port}/mcp')
        store=Store(tmp_path)
        listing=await inspect_source(source,store)
        assert listing['tools'][0]['name']=='read_fixture'
        assert await fetch_context(source,store,'tool','read_fixture',{})=='HTTP MCP fixture text'
        assert await fetch_context(source,store,'resource','fixture://reference',{})=='HTTP MCP fixture reference'
    finally:
        process.terminate()
        await process.wait()


def test_partial_failure_is_not_successful_consensus(tmp_path):
    def respond(request):
        if request.url.path.endswith('/chat/completions'):
            return httpx.Response(503,json={'error':'fixture error'})
        return fixture_response(request)
    with TestClient(create_app(tmp_path,httpx.MockTransport(respond))) as client:
        client.headers['X-BorgNet-Token']=client.get('/api/state').json()['token']
        first=add(client);second=add(client,kind='openai',url='http://localhost:1234/v1')
        response=client.post('/api/dispatch',json={'collaborate':False,'prompt':'Check failure','connections':[first,second],'synthesize':first})
        results=[e for e in map(json.loads,response.text.splitlines()) if e['type']=='result']
        assert [r['status'] for r in results].count('complete')==1
        assert results[-1]['synthesis'] and results[-1]['status']=='error'


def test_context_and_followup_reach_only_selected_provider(tmp_path):
    calls=[]
    def respond(request):
        calls.append(json.loads(request.content))
        return fixture_response(request)
    with TestClient(create_app(tmp_path,httpx.MockTransport(respond))) as client:
        client.headers['X-BorgNet-Token']=client.get('/api/state').json()['token']
        identity=add(client,purpose='Fixture purpose')
        context=client.post('/api/context',json={'title':'Selected context','text':'Selected reference text'}).json()
        client.post('/api/context',json={'title':'Private context','text':'Do not transmit this'})
        first=client.post('/api/dispatch',json={'collaborate':False,'prompt':'First question','connections':[identity],'contexts':[context['id']]}).text
        conversation=json.loads(first.splitlines()[0])['conversation']
        client.post('/api/dispatch',json={'collaborate':False,'prompt':'Follow up','connections':[identity],'conversation':conversation})
        assert 'Selected reference text' in json.dumps(calls[0])
        assert 'Do not transmit this' not in json.dumps(calls)
        assert calls[1]['messages'][0]=={'role':'system','content':'Fixture purpose'}
        assert any(m['role']=='assistant' and m['content']=='Fixture answer' for m in calls[1]['messages'])


def test_ssh_identity_and_remote_bind_address():
    settings=SSH(host='compute.example.com',remote_host='service.internal',remote_port=9000,identity_file='~/.ssh/example_key')
    args=Tunnels.command(settings,23456)
    assert '127.0.0.1:23456:service.internal:9000' in args
    assert str(Path('~/.ssh/example_key').expanduser()) in args
    assert 'IdentitiesOnly=yes' in args
    with pytest.raises(ValidationError):
        SSH(host='compute.example.com',remote_host='host:9000:other')


async def test_runtime_options_cannot_override_protocol_fields(tmp_path):
    payloads=[]
    def record(request):
        payloads.append(json.loads(request.content))
        return fixture_response(request)
    providers=Providers(Store(tmp_path),Tunnels(),httpx.MockTransport(record))
    item=Connection(kind='ollama',url='http://localhost:1234',model='fixture-chat',options={'num_ctx':4096,'num_predict':96,'think':False,'model':'invalid-override','messages':[]})
    await providers.chat(item,[{'role':'user','content':'Hi'}])
    assert payloads[0]['model']=='fixture-chat' and payloads[0]['messages']
    assert payloads[0]['options']=={'num_ctx':4096,'num_predict':96}
    assert payloads[0]['think'] is False
    item.kind='openai';item.options={'max_tokens':32,'temperature':.7,'model':'invalid-override'}
    await providers.chat(item,[{'role':'user','content':'Hi'}])
    assert payloads[1]['model']=='fixture-chat' and payloads[1]['max_tokens']==32


def test_synthesis_preference_is_persistent(client):
    identity=add(client)
    assert client.post('/api/settings',json={'synthesis':identity}).status_code==200
    assert client.get('/api/state').json()['synthesis']==identity
    assert client.post('/api/settings',json={'synthesis':'unknown'}).status_code==400


def test_discovered_models_persist_and_invalidate_when_endpoint_changes(client,tmp_path):
    identity=add(client)
    client.post(f'/api/connections/{identity}/discover',json={}).raise_for_status()
    assert client.get('/api/state').json()['model_catalog'][identity]==['fixture-chat']
    # A new server reading the same private data keeps the discovered choices.
    with TestClient(create_app(tmp_path,httpx.MockTransport(fixture_response))) as reopened:
        assert reopened.get('/api/state').json()['model_catalog'][identity]==['fixture-chat']
    add(client,id=identity,purpose='New role')
    assert identity in client.get('/api/state').json()['model_catalog']
    add(client,id=identity,url='http://localhost:11435')
    assert identity not in client.get('/api/state').json()['model_catalog']
    client.post(f'/api/connections/{identity}/discover',json={}).raise_for_status()
    client.post(f'/api/connections/{identity}/delete',json={}).raise_for_status()
    assert identity not in json.loads((tmp_path/'model-catalog.json').read_text())
    assert (tmp_path/'model-catalog.json').stat().st_mode & 0o777 == 0o600


async def test_provider_redirect_does_not_forward_credentials(tmp_path):
    store=Store(tmp_path);store.save_secret('fixture','fixture-secret-value')
    calls=[]
    def redirect(request):
        calls.append(str(request.url))
        return httpx.Response(302,headers={'Location':'https://untrusted.example/models'})
    providers=Providers(store,Tunnels(),httpx.MockTransport(redirect))
    with pytest.raises(ValueError,match='HTTP 302'):
        await providers.models(Connection(id='fixture',kind='openai',url='https://provider.example/v1'))
    assert calls==['https://provider.example/v1/models']


async def test_ollama_cpu_override_reaches_runtime_without_protocol_overrides(tmp_path):
    seen=[]
    def receive(request):
        data=json.loads(request.content);seen.append(data)
        return httpx.Response(200,json={'message':{'content':'READY'}})
    p=Providers(Store(tmp_path),Tunnels(),httpx.MockTransport(receive))
    assert await p.chat(Connection(url='http://localhost:11434',model='fixture-moe',options={'num_gpu':0,'num_ctx':8192,'model':'wrong','stream':True}),[{'role':'user','content':'Check'}])=='READY'
    assert seen[0]['options']=={'num_gpu':0,'num_ctx':8192}
    assert seen[0]['model']=='fixture-moe' and seen[0]['stream'] is False


def test_model_profiles_survive_config_save(client):
    identity=add(client,options={'num_gpu':0},model_options={'fixture-moe':{'num_gpu':0,'num_ctx':8192},'fixture-small':{'num_gpu':12}})
    c=next(x for x in client.get('/api/state').json()['connections'] if x['id']==identity)
    assert c['model_options']['fixture-moe']['num_gpu']==0
    assert c['model_options']['fixture-small']['num_gpu']==12


async def test_ollama_structured_output_uses_explicit_schema(tmp_path):
    schema={'type':'object','properties':{'answer':{'type':'string'}},'required':['answer']}
    seen=[]
    def receive(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200,json={'message':{'content':'{"answer":"four"}'}})
    p=Providers(Store(tmp_path),Tunnels(),httpx.MockTransport(receive));item=Connection(url='http://localhost:11434',model='fixture-chat')
    await p.chat(item,[{'role':'user','content':'Question'}],response_schema=schema)
    await p.chat(item,[{'role':'user','content':'Plain text'}])
    assert seen[0]['format']==schema and 'format' not in seen[1]
