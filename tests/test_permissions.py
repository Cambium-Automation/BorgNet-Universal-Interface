from pathlib import Path
import pytest
from borgnet.config import Store, Connection
from borgnet.permissions import Policy, Permissions, effective
from borgnet.cli_text import command


def item(provider='codex', kind='cli'):
    return Connection(id='test', kind=kind, cli_provider=provider, url='http://localhost', model='default')


def test_inheritance_and_api_limits(tmp_path):
    store = Store(tmp_path)
    config = store.config()
    config['permissions'] = Permissions(defaults=Policy(full_access=True)).model_dump()
    store.write('config', config)
    assert effective(store, item()).full_access
    assert not effective(store, item(kind='openai')).full_access
    assert not effective(store, item('gemini')).full_access
    config['permissions']['overrides']['test'] = Policy().model_dump()
    store.write('config', config)
    assert not effective(store, item()).full_access


def test_workspace_validation(tmp_path):
    assert Policy(workspace=str(tmp_path)).workspace == str(tmp_path.resolve())
    with pytest.raises(ValueError): Policy(workspace=str(tmp_path/'missing'))
    with pytest.raises(ValueError): Policy(network='false')


@pytest.mark.parametrize('provider', ['codex','grok','copilot'])
def test_opt_in_flags(tmp_path, monkeypatch, provider):
    monkeypatch.setattr('borgnet.cli_text.executable', lambda p: p)
    safe, _ = command(item(provider), tmp_path, 'test')
    full, _ = command(item(provider), tmp_path, 'test', Policy(full_access=True))
    if provider == 'codex':
        assert 'shell_tool' in safe and 'shell_tool' not in full
        assert '--dangerously-bypass-approvals-and-sandbox' in full
    elif provider == 'grok':
        assert safe[safe.index('--tools')+1] == ''
        assert '--tools' not in full and 'bypassPermissions' in full
        assert 'MCPTool' in full
    else:
        assert '--available-tools=' in safe and '--available-tools=' not in full
        assert '--allow-all' in full


def test_web_only_keeps_shell_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr('borgnet.cli_text.executable', lambda p: p)
    argv, _ = command(item(), tmp_path, 'test', Policy(network=True))
    assert '--search' in argv and 'shell_tool' in argv
    argv, _ = command(item('grok'), tmp_path, 'test', Policy(network=True))
    assert argv[argv.index('--tools')+1] == 'web_search,web_fetch'
    assert '--disable-web-search' not in argv


def test_permissions_endpoint_roundtrip(tmp_path):
    from tests.client import TestClient
    from borgnet.server import create_app
    with TestClient(create_app(tmp_path)) as client:
        headers = {'X-BorgNet-Token': client.get('/api/state').json()['token']}
        settings = client.get('/api/permissions').json()
        assert settings['defaults']['full_access'] is False
        settings['defaults']['workspace'] = str(tmp_path)
        assert client.post('/api/permissions', json=settings, headers=headers).status_code == 200
        assert client.get('/api/permissions').json() == settings
        settings['overrides']['missing'] = settings['defaults']
        assert client.post('/api/permissions', json=settings, headers=headers).status_code == 400


def test_deleted_connection_cannot_leave_stale_access(tmp_path):
    from tests.client import TestClient
    from borgnet.server import create_app
    app = create_app(tmp_path)
    with TestClient(app) as client:
        headers = {'X-BorgNet-Token': client.get('/api/state').json()['token']}
        connection = item().model_dump()
        assert client.post('/api/connections', json=connection, headers=headers).status_code == 200
        policy = Permissions(overrides={'test': Policy(full_access=True)}).model_dump()
        assert client.post('/api/permissions', json=policy, headers=headers).status_code == 200
        assert client.post('/api/connections/test/delete', headers=headers).status_code == 200
        assert client.get('/api/permissions').json()['overrides'] == {}
        assert client.post('/api/connections', json=connection, headers=headers).status_code == 200
        assert not effective(app.state.store, item()).full_access
