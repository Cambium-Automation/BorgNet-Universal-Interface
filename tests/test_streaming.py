import asyncio
import json
import httpx
import pytest
from borgnet.providers import Providers, Tunnels
from borgnet.config import Store, Connection, SSH
from borgnet.streaming import public_delta, reasoning_eligible
from borgnet.collaboration import collaborate
from tests.test_collaboration import CouncilFixture


@pytest.mark.parametrize('stream', [False, True])
@pytest.mark.parametrize('detail', [
    'Context exceeds 2048 tokens: prompt=3456, reserved output=256. Reduce context/history or max_tokens; nothing was truncated.',
    'secret-key-do-not-reflect',
    'Context exceeds 2048 tokens: prompt=3456, reserved output=256. Reduce context/history or max_tokens; nothing was truncated. secret',
])
async def test_context_error_is_useful_without_reflecting_secrets(tmp_path, stream, detail):
    transport = httpx.MockTransport(lambda r: httpx.Response(400, json={'detail': detail}))
    providers = Providers(Store(tmp_path), Tunnels(), transport)
    async def delta(text): pass
    item = Connection(kind='openai', url='http://localhost:1', model='fixture')
    with pytest.raises(ValueError) as caught:
        if stream:
            await providers.stream_chat(item, [], on_delta=delta)
        else:
            await providers.chat(item, [])
    message = str(caught.value)
    assert 'secret' not in message
    if detail.endswith('truncated.'):
        assert 'prompt=3456' in message
    else:
        assert 'HTTP 400' in message


@pytest.mark.asyncio
@pytest.mark.parametrize('kind,events', [
 ('openai',[{'choices':[{'delta':{'content':'Hello '}}]},{'choices':[{'delta':{'reasoning_content':'private'}}]},{'choices':[{'delta':{'content':'world'},'finish_reason':'stop'}]}]),
 ('ollama',[{'message':{'content':'Hello '}},{'message':{'thinking':'private','content':'world'},'done':True}]),
 ('anthropic',[{'type':'content_block_delta','delta':{'type':'text_delta','text':'Hello '}},{'type':'content_block_delta','delta':{'type':'thinking_delta','thinking':'private'}},{'type':'content_block_delta','delta':{'type':'text_delta','text':'world'}},{'type':'message_stop'}]),
 ('gemini',[{'candidates':[{'content':{'parts':[{'text':'private','thought':True},{'text':'Hello '}]}}]},{'candidates':[{'content':{'parts':[{'text':'world'}]},'finishReason':'STOP'}]}]),
 ('responses',[{'type':'response.output_text.delta','delta':'Hello '},{'type':'response.reasoning_text.delta','delta':'private'},{'type':'response.output_text.delta','delta':'world'},{'type':'response.completed'}]),
 ('cohere',[{'type':'content-delta','delta':{'message':{'content':{'text':'Hello '}}}},{'type':'content-delta','delta':{'message':{'content':{'text':'world'}}}},{'type':'message-end'}]),
])
async def test_public_deltas_arrive_before_provider_finishes(tmp_path,kind,events):
    seen=[]
    class Chunks(httpx.AsyncByteStream):
        async def __aiter__(self):
            for i,event in enumerate(events):
                if i: assert seen, 'The first public chunk must arrive before the next upstream event'
                yield ((('' if kind=='ollama' else 'data: ') + json.dumps(event))+'\n\n').encode()
                await asyncio.sleep(0)
    def respond(request):
        if kind=='gemini':assert ':streamGenerateContent' in str(request.url)
        else:assert json.loads(request.content)['stream'] is True
        return httpx.Response(200,headers={'content-type':'application/x-ndjson' if kind=='ollama' else 'text/event-stream'},stream=Chunks())
    providers=Providers(Store(tmp_path),Tunnels(),httpx.MockTransport(respond))
    async def delta(text):seen.append(text)
    answer=await providers.stream_chat(Connection(kind=kind,url='http://localhost:1234',model='fixture'),[{'role':'user','content':'hi'}],on_delta=delta)
    assert answer=='Hello world' and ''.join(seen)=='Hello world'


@pytest.mark.asyncio
async def test_conference_streams_every_round():
    class StreamingCouncil(CouncilFixture):
        async def stream_chat(self,item,messages,system,response_schema=None,on_delta=None):
            result=await self.chat(item,messages,system,response_schema)
            await on_delta(result[:3]);await asyncio.sleep(0);await on_delta(result[3:])
            return result
    items=[Connection(id='a',url='http://localhost:1',model='fixture'),Connection(id='b',url='http://localhost:1',model='fixture')]
    events=[e async for e in collaborate(StreamingCouncil(),items,'Hi','',[],'',{'results':[]})]
    for phase in ['proposal','review','final']:
        delta_index=next(i for i,e in enumerate(events) if e['type']=='delta' and e['phase']==phase)
        result_index=next(i for i,e in enumerate(events) if e['type']=='result' and e['phase']==phase)
        assert delta_index<result_index


@pytest.mark.asyncio
async def test_interrupted_stream_is_not_success(tmp_path):
    transport=httpx.MockTransport(lambda r:httpx.Response(200,headers={'content-type':'text/event-stream'},content=b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'))
    async def delta(text):pass
    providers=Providers(Store(tmp_path),Tunnels(),transport)
    with pytest.raises(ValueError,match='before completion'):
        await providers.stream_chat(Connection(kind='openai',url='http://localhost:1',model='fixture'),[],on_delta=delta)


@pytest.mark.asyncio
@pytest.mark.parametrize('kind,url,options,expected', [
    ('openai', 'http://localhost:1234/v1', {'show_local_reasoning':True}, ['private thought']),
    ('openai', 'http://localhost:1234/v1', {}, []),
    ('ollama', 'http://localhost:11434', {}, ['private thought']),
    ('openai', 'https://example.com/v1', {'show_local_reasoning':True}, []),
])
async def test_reasoning_is_separate_and_only_local(tmp_path, kind, url, options, expected):
    events = ([{'choices':[{'delta':{'reasoning_content':'private thought'}}]},
               {'choices':[{'delta':{'content':'Public answer'},'finish_reason':'stop'}]}]
              if kind == 'openai' else
              [{'message':{'thinking':'private thought'}},
               {'message':{'content':'Public answer'},'done':True}])
    body = ''.join(('' if kind == 'ollama' else 'data: ') + json.dumps(e) + '\n\n' for e in events)
    transport = httpx.MockTransport(lambda r: httpx.Response(200,
        headers={'content-type':'application/x-ndjson' if kind == 'ollama' else 'text/event-stream'}, content=body))
    providers = Providers(Store(tmp_path), Tunnels(), transport)
    public, reasoning = [], []
    async def on_public(value): public.append(value)
    async def on_reasoning(value): reasoning.append(value)
    answer = await providers.stream_chat(Connection(kind=kind,url=url,model='fixture',options=options),
        [{'role':'user','content':'hi'}],on_delta=on_public,on_reasoning=on_reasoning)
    assert answer == 'Public answer'
    assert public == ['Public answer']
    assert reasoning == expected


@pytest.mark.asyncio
async def test_reasoning_excludes_tool_arguments_and_is_bounded(tmp_path):
    events = [{'choices':[{'delta':{'reasoning_content':'x'*50000,
                                    'tool_calls':[{'function':{'arguments':'SECRET'}}]}}]},
              {'choices':[{'delta':{'content':'done'},'finish_reason':'stop'}]}]
    body = ''.join('data: ' + json.dumps(e) + '\n\n' for e in events)
    transport = httpx.MockTransport(lambda r: httpx.Response(200,
        headers={'content-type':'text/event-stream'},content=body))
    providers = Providers(Store(tmp_path),Tunnels(),transport)
    public, reasoning = [], []
    async def emit(value): public.append(value)
    async def think(value): reasoning.append(value)
    assert await providers.stream_chat(Connection(kind='openai',url='http://localhost:1',model='fixture',
                                                   options={'show_local_reasoning':True}),
        [],on_delta=emit,on_reasoning=think) == 'done'
    assert ''.join(public) == 'done'
    assert 'SECRET' not in ''.join(reasoning)
    assert len(''.join(reasoning).replace('\n[Model reasoning display truncated.]', '')) == 48000


@pytest.mark.asyncio
async def test_local_json_fallback_exposes_only_explicit_reasoning(tmp_path):
    payload = {'choices':[{'message':{'content':'Answer','reasoning_content':'Thought',
                                      'tool_calls':[{'function':{'arguments':'SECRET'}}]}}]}
    transport=httpx.MockTransport(lambda r:httpx.Response(200,json=payload))
    providers=Providers(Store(tmp_path),Tunnels(),transport)
    reasoning=[]
    async def emit(_): pass
    async def think(value): reasoning.append(value)
    answer=await providers.stream_chat(Connection(kind='openai',url='http://localhost:1',model='fixture',
        options={'show_local_reasoning':True}),[],on_delta=emit,on_reasoning=think)
    assert answer=='Answer' and reasoning==['Thought']
    assert 'SECRET' not in ''.join(reasoning)


def test_dispatch_emits_reasoning_without_recording_it(tmp_path):
    from borgnet.server import create_app
    from tests.client import TestClient
    store = Store(tmp_path)
    item = Connection(id='local',kind='ollama',url='http://localhost:11434',model='fixture')
    cfg = store.config()
    cfg['connections'] = [item.model_dump()]
    store.write('config',cfg)
    body = '\n'.join(json.dumps(e) for e in [
        {'message':{'thinking':'internal thought'}},
        {'message':{'content':'Public answer'},'done':True}]) + '\n'
    transport = httpx.MockTransport(lambda r:httpx.Response(200,
        headers={'content-type':'application/x-ndjson'},content=body))
    with TestClient(create_app(tmp_path,transport)) as client:
        headers={'X-BorgNet-Token':client.get('/api/state').json()['token']}
        response=client.post('/api/dispatch',json={'prompt':'Hi','connections':['local']},headers=headers)
        events=[json.loads(line) for line in response.text.splitlines()]
    reason=next(e for e in events if e['type']=='reasoning')
    assert reason['connection']=='local' and reason['model']=='fixture'
    assert reason['text']=='internal thought'
    result=next(e for e in events if e['type']=='result')
    assert result['text']=='Public answer'
    assert 'internal thought' not in json.dumps(store.read('history',[]))


def test_ssh_reasoning_requires_remote_loopback_server():
    local = Connection(kind='openai',url='http://127.0.0.1:1234/v1',model='fixture',
                       ssh=SSH(host='remote-box',remote_host='127.0.0.1'))
    other = local.model_copy(update={'ssh':SSH(host='remote-box',remote_host='intranet.example')})
    assert reasoning_eligible(local)
    assert not reasoning_eligible(other)
