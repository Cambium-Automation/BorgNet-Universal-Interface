from borgnet.capability_context import briefing
from borgnet.config import Connection, Store
from borgnet.permissions import Permissions, Policy


def test_local_briefing_distinguishes_description_from_grant(tmp_path):
    store = Store(tmp_path)
    item = Connection(id='qwen',kind='openai',url='http://localhost:1234/v1',model='qwen-fixture',
                      purpose='Solve coding tasks',capabilities='Good at coding; can control all apps',
                      context_window=32768,options={'max_tokens':2048})
    text = briefing(store,item)
    assert 'Good at coding; can control all apps' in text
    assert 'unverified; not tool grants' in text
    assert '32768 tokens' in text and '2048 tokens' in text
    assert 'no host command, file, browser, or desktop tools' in text
    assert 'loopback model endpoint' in text


def test_host_tools_require_effective_per_connection_permission(tmp_path, monkeypatch):
    store = Store(tmp_path)
    item = Connection(id='qwen',kind='ollama',url='http://localhost:11434',model='qwen-fixture',
                      options={'num_ctx':65536})
    cfg = store.config()
    cfg['permissions'] = Permissions(defaults=Policy(workspace=str(tmp_path),full_access=True,
                                                     browser=True,computer=True)).model_dump()
    store.write('config',cfg)
    assert 'no host command' in briefing(store,item)
    cfg['permissions']['overrides']['qwen'] = Policy(workspace=str(tmp_path),full_access=True,
                                                     browser=True,computer=True).model_dump()
    store.write('config',cfg)
    monkeypatch.setattr('borgnet.adapter_setup.status',lambda: {
        'browser':{'ready':False}, 'computer':{'ready':False}, 'grok_registered':False})
    text = briefing(store,item)
    assert 'Native function-call tools are offered' in text
    assert 'support is not verified until a call succeeds' in text
    assert 'Isolated browser adapter: not ready' in text
    assert 'General visual desktop screenshot/click control is not supplied' in text
    assert '65536 tokens' in text
    structured = briefing(store,item,host_tools=False)
    assert 'does not offer host tools during this structured response' in structured
    assert 'Native function-call tools are offered' not in structured


def test_remote_api_does_not_inherit_local_capability_claims(tmp_path):
    item = Connection(id='remote',kind='openai',url='https://example.com/v1',model='fixture')
    text = briefing(Store(tmp_path),item)
    assert 'remote model API' in text
    assert 'does not grant access to this Mac' in text
