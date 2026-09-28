import json

import httpx
import pytest

from borgnet.config import Connection, Store
from borgnet.local_tools import LocalTools, chat_with_tools
from borgnet.permissions import Permissions, Policy


@pytest.mark.asyncio
async def test_local_model_function_call_executes_and_returns_observation(tmp_path):
    item = Connection(id='local', kind='openai', url='http://127.0.0.1:8110/v1', model='fixture')
    class FakeProvider:
        store = Store(tmp_path)
        def __init__(self): self.calls = []
        async def request(self, item, method, path, payload):
            self.calls.append(payload)
            if len(self.calls) == 1:
                return {'choices': [{'message': {'role': 'assistant', 'content': '', 'tool_calls': [{
                    'id': 'call1', 'type': 'function', 'function': {'name': 'run_command',
                    'arguments': json.dumps({'argv': ['/bin/pwd']})}}]}}]}
            assert payload['messages'][-1]['role'] == 'tool'
            assert payload['messages'][-1]['tool_call_id'] == 'call1'
            assert json.loads(payload['messages'][-1]['content'])['stdout'].strip() == str(tmp_path)
            return {'choices': [{'message': {'role': 'assistant', 'content': 'The working folder is ' + str(tmp_path)}}]}
    provider = FakeProvider()
    deltas, used = [], []
    async def emit(text): deltas.append(text)
    async def tool(name, ok): used.append((name, ok))
    answer = await chat_with_tools(provider, item, [{'role': 'user', 'content': 'Where am I?'}], '',
                                   Policy(workspace=str(tmp_path), full_access=True), emit, tool)
    assert answer == 'The working folder is ' + str(tmp_path)
    assert deltas == [answer]
    assert used == [('run_command', True)]


@pytest.mark.asyncio
async def test_tool_loop_continues_past_old_step_and_batch_caps(tmp_path):
    item = Connection(id='local', kind='openai', url='http://127.0.0.1:8110/v1', model='fixture')
    class FakeProvider:
        store = Store(tmp_path)
        def __init__(self): self.rounds = 0
        async def request(self, item, method, path, payload):
            self.rounds += 1
            if self.rounds == 2:
                assert [message['tool_call_id'] for message in payload['messages'][-5:]] == [
                    f'call-{number}' for number in range(5)]
            if self.rounds == 11:
                assert payload['messages'][-1]['tool_call_id'] == 'call-13'
                return {'choices': [{'message': {'role': 'assistant', 'content': 'Finished'}}]}
            count = 5 if self.rounds == 1 else 1
            start = 0 if self.rounds == 1 else self.rounds + 3
            calls = [{'id': f'call-{number}', 'type': 'function', 'function': {
                'name': 'run_command', 'arguments': json.dumps({'argv': ['/bin/pwd']})}}
                for number in range(start, start + count)]
            return {'choices': [{'message': {'role': 'assistant', 'content': '', 'tool_calls': calls}}]}
    provider = FakeProvider()
    used = []
    async def on_tool(name, ok): used.append((name, ok))
    answer = await chat_with_tools(provider, item, [{'role': 'user', 'content': 'Inspect the workspace'}], '',
                                   Policy(workspace=str(tmp_path), full_access=True), None, on_tool)
    assert answer == 'Finished'
    assert provider.rounds == 11
    assert used == [('run_command', True)] * 14


@pytest.mark.asyncio
async def test_local_tools_hide_ungranted_browser_and_mac(tmp_path):
    tools = LocalTools(Policy(workspace=str(tmp_path), full_access=True), Store(tmp_path))
    try:
        assert tools.names == {'run_command'}
        with pytest.raises(ValueError, match='not granted'):
            await tools.call('mac_open', {'name': 'Blender'})
        with pytest.raises(ValueError, match='non-empty'):
            await tools.call('run_command', {'argv': ['/bin/echo', '']})
    finally:
        await tools.close()


@pytest.mark.asyncio
async def test_browser_rejects_invalid_actions_before_launch(tmp_path, monkeypatch):
    tools = LocalTools(Policy(workspace=str(tmp_path), full_access=True, browser=True), Store(tmp_path))
    async def unexpected(): raise AssertionError('Browser must not launch for invalid input')
    monkeypatch.setattr(tools.browser, 'start', unexpected)
    try:
        assert {'browser_press', 'browser_scroll'} <= tools.names
        with pytest.raises(ValueError, match='Unsupported browser key'):
            await tools.call('browser_press', {'key': 'Meta+A'})
        with pytest.raises(ValueError, match='2,000'):
            await tools.call('browser_scroll', {'pixels': 9999})
    finally:
        await tools.close()


def test_dispatch_reports_tool_activity_before_final_result(tmp_path):
    from borgnet.server import create_app
    from tests.client import TestClient
    store = Store(tmp_path)
    item = Connection(id='local', kind='openai', url='http://127.0.0.1:8110/v1', model='fixture',
                      options={'reasoning_effort':'medium',
                               'quick_response':{'reasoning_effort':'low','thinking_budget_tokens':128}})
    cfg = store.config()
    cfg['connections'] = [item.model_dump()]
    cfg['permissions'] = Permissions(overrides={'local': Policy(workspace=str(tmp_path), full_access=True)}).model_dump()
    store.write('config', cfg)
    calls = 0
    def respond(request):
        nonlocal calls
        calls += 1
        body=json.loads(request.content)
        assert body['reasoning_effort']=='low' and body['thinking_budget_tokens']==128
        assert any(tool['function']['name']=='run_command' for tool in body['tools'])
        if calls == 1:
            return httpx.Response(200, json={'choices': [{'message': {'role':'assistant','content':'',
                'tool_calls':[{'id':'one','type':'function','function':{'name':'run_command',
                               'arguments':json.dumps({'argv':['/bin/pwd']})}}]}}]})
        assert json.loads(json.loads(request.content)['messages'][-1]['content'])['exit_code'] == 0
        return httpx.Response(200, json={'choices':[{'message':{'role':'assistant','content':'Checked'}}]})
    with TestClient(create_app(tmp_path, httpx.MockTransport(respond))) as client:
        headers={'X-BorgNet-Token':client.get('/api/state').json()['token']}
        response=client.post('/api/dispatch',json={'prompt':'Check the folder','connections':['local'],
                                                  'collaborate':False,'quick_response':True},headers=headers)
        events=[json.loads(line) for line in response.text.splitlines()]
        assert [event['type'] for event in events if event['type'] in {'stream-reset','tool','result'}] == ['stream-reset','tool','result']
        assert next(event for event in events if event['type']=='stream-reset')['mode']=='buffered-tools'
        assert next(event for event in events if event['type']=='tool')['name']=='run_command'
        assert next(event for event in events if event['type']=='result')['tools']==[{'name':'run_command','ok':True}]
