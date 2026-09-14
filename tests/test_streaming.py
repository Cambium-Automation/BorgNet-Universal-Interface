import asyncio
import json
import httpx
import pytest
from borgnet.providers import Providers, Tunnels
from borgnet.config import Store, Connection
from borgnet.streaming import public_delta
from borgnet.collaboration import collaborate
from tests.test_collaboration import CouncilFixture


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
