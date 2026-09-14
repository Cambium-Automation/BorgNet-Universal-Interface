from contextlib import asynccontextmanager
from types import SimpleNamespace
import pytest
from borgnet import mcp_bridge

@pytest.mark.parametrize('capability', ['tools','resources'])
async def test_discovery_only_calls_advertised_capability(monkeypatch,capability):
    class Client:
        async def list_tools(self,cursor=None):
            assert capability=='tools'
            return SimpleNamespace(tools=[],nextCursor=None)
        async def list_resources(self,cursor=None):
            assert capability=='resources'
            return SimpleNamespace(resources=[],nextCursor=None)
    @asynccontextmanager
    async def fake_session(source,store,with_capabilities=False):
        assert with_capabilities
        yield Client(),SimpleNamespace(**{capability:object()})
    monkeypatch.setattr(mcp_bridge,'session',fake_session)
    assert await mcp_bridge.inspect_source(None,None)=={'tools':[],'resources':[]}
