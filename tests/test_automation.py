import json
import os
import sys
import time
from types import SimpleNamespace
import pytest
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from borgnet.automation import Grant,create_server
from borgnet.permissions import Policy,effective,discussion_only
from borgnet.config import Store,Connection
from borgnet.cli_text import automation_command,command
from borgnet.desktop_adapter import Desktop
from borgnet.adapter_setup import entrypoint


def grant_file(tmp_path,**values):
    path=tmp_path/'grant.json'
    path.write_text(json.dumps({'expires':time.time()+60,**values}));path.chmod(0o600)
    return path


def test_grant_is_fail_closed_and_revocable(tmp_path):
    path=grant_file(tmp_path,browser=True,computer=False)
    grant=Grant(path)
    assert grant.allows('browser') and not grant.allows('computer')
    path.chmod(0o644)
    if os.name=='posix':assert not grant.allows('browser')
    path.chmod(0o600)
    path.write_text(json.dumps({'browser':True,'expires':0}))
    assert not grant.allows('browser')
    path.unlink()
    assert not grant.allows('browser')


async def test_stdio_discovery_and_revocation(tmp_path):
    path=grant_file(tmp_path,browser=True,computer=True)
    async with stdio_client(StdioServerParameters(command=sys.executable,args=[entrypoint()],env={'BORGNET_AUTOMATION_GRANT':str(path)})) as streams:
        async with ClientSession(*streams) as client:
            await client.initialize()
            names={t.name for t in (await client.list_tools()).tools}
            assert {'browser_navigate','browser_click','computer_screenshot','computer_type'}<=names
            path.unlink()
            assert (await client.call_tool('browser_snapshot')).isError
            assert (await client.call_tool('computer_click',{'x':1,'y':1})).isError


async def test_no_grant_exposes_no_control_tools(tmp_path):
    server=create_server(Grant(tmp_path/'missing'))
    assert [t.name for t in await server.list_tools()]==['automation_status']


async def test_browser_only_has_no_desktop_tools(tmp_path):
    server=create_server(Grant(grant_file(tmp_path,browser=True)))
    names=[t.name for t in await server.list_tools()]
    assert 'browser_click' in names and not any(n.startswith('computer_') for n in names)
    with pytest.raises(Exception,match='HTTP'):
        await server.call_tool('browser_navigate',{'url':'file:///etc/passwd'})


def test_grants_require_full_cli_and_are_removed_for_discussion(tmp_path):
    store=Store(tmp_path);config=store.config();config['permissions']={'defaults':{'browser':True,'computer':True}}
    store.write('config',config)
    item=Connection(id='c',kind='cli',url='http://localhost',model='default')
    assert not effective(store,item).browser
    config['permissions']['defaults']['full_access']=True;store.write('config',config)
    assert effective(store,item).computer
    marker=discussion_only.set(True)
    try:assert not effective(store,item).computer
    finally:discussion_only.reset(marker)


@pytest.mark.parametrize('provider',['codex','copilot','grok'])
def test_request_scoped_mcp_configuration(tmp_path,monkeypatch,provider):
    from borgnet import cli_text
    monkeypatch.setattr(cli_text,'executable',lambda p:p)
    monkeypatch.setattr('borgnet.adapter_setup.grok_registered',lambda:True)
    monkeypatch.setattr(cli_text.subprocess,'run',lambda *a,**k:SimpleNamespace(stdout='[{"name":"borgnet_automation"},{"name":"other"}]'))
    item=Connection(id='c',kind='cli',cli_provider=provider,url='http://localhost',model='default')
    policy=Policy(full_access=True,browser=True)
    argv,_=command(item,tmp_path,'test',policy)
    argv,env=automation_command(item,tmp_path,argv,{},policy)
    grant=Grant(env['BORGNET_AUTOMATION_GRANT'])
    assert grant.allows('browser') and not grant.allows('computer')
    if provider=='codex':assert any('mcp_servers.borgnet_automation' in a for a in argv)
    if provider=='copilot':assert '--additional-mcp-config' in argv
    if provider=='grok':assert 'MCPTool(other__*)' in argv and 'MCPTool' not in argv


def test_desktop_rejects_actions_without_observation(monkeypatch):
    monkeypatch.setattr('borgnet.desktop_adapter.status',lambda:{'ready':True})
    with pytest.raises(ValueError,match='fresh'):Desktop().click(0,0)


def test_adapter_status_endpoint_requires_session(tmp_path):
    from borgnet.server import create_app
    from fastapi.testclient import TestClient
    app=create_app(tmp_path)
    with TestClient(app,base_url='http://127.0.0.1') as client:
        assert client.get('/api/adapters').status_code==401
        assert client.post('/api/adapters/browser-test').status_code==401
