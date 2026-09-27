"""E-stop targeting tests never signal real processes or change launchd."""
from types import SimpleNamespace
import signal

import pytest

from estop import stop


def row(pid, command, ppid=1, uid=501):
    return {'pid': pid, 'ppid': ppid, 'uid': uid, 'command': command}


def test_targets_ssh_agents_and_borgnet_without_matching_unrelated_apps():
    assert stop.category(row(1, '/usr/bin/ssh -N remote-box')) == 'ssh'
    assert stop.category(row(2, '/usr/bin/ssh-agent -l')) == 'ssh'
    assert stop.category(row(21, '/usr/sbin/sshd -i')) == 'ssh'
    assert stop.category(row(3, '/opt/homebrew/bin/ollama serve')) == 'agent'
    assert stop.category(row(4, '/Applications/ChatGPT.app/Contents/MacOS/ChatGPT')) == 'agent'
    assert stop.category(row(5, '/opt/homebrew/bin/python -m borgnet serve')) == 'borgnet'
    assert stop.category(row(51, '/Users/example/Applications/BorgNet Universal Interface.app/Contents/MacOS/BorgNet')) == 'borgnet'
    assert stop.category(row(6, '/Applications/Gemini 2.app/Contents/MacOS/Gemini 2')) is None
    assert stop.category(row(7, '/Applications/Visual Studio Code.app/Contents/MacOS/Code')) is None
    assert stop.category(row(8, '/Applications/BorgNet E-Stop.app/Contents/MacOS/BorgNetEStop')) is None
    assert stop.category(row(9, '/usr/libexec/UserEventAgent (System)')) is None


def test_snapshot_excludes_estop_and_its_parent_chain():
    rows = [row(10, '/Applications/ChatGPT.app/Contents/MacOS/ChatGPT'),
            row(11, '/usr/bin/python3 estop/stop.py', ppid=10),
            row(12, '/usr/bin/ssh -N remote-box'),
            row(13, '/opt/homebrew/bin/ollama serve')]
    result = stop.snapshot(rows, ['org.borgnet.workspace', 'com.apple.finder'], self_pid=11)
    assert result['jobs'] == ['org.borgnet.workspace']
    assert [item['pid'] for item in result['processes']] == [13, 12]


def test_empty_password_refuses_before_any_side_effect(monkeypatch):
    monkeypatch.setattr(stop, 'run', lambda *_a, **_kw: pytest.fail('should not run'))
    with pytest.raises(ValueError, match='password'):
        stop.authenticate('')


def test_borgnet_interface_is_force_quit(monkeypatch):
    sent = []
    monkeypatch.setattr(stop.os, 'kill', lambda pid, sig: sent.append((pid, sig)))
    assert stop.kill_pid(51, 501)
    assert sent == [(51, signal.SIGKILL)]


def test_execute_disables_jobs_and_kills_ssh_first(monkeypatch):
    ssh = {**row(20, '/usr/bin/ssh -N remote-box'), 'category': 'ssh'}
    agent = {**row(30, '/opt/homebrew/bin/ollama serve'), 'category': 'agent'}
    before = {'jobs': ['org.borgnet.workspace'], 'processes': [agent, ssh]}
    empty = {'jobs': [], 'processes': []}
    snapshots = iter([before, before, empty])
    monkeypatch.setattr(stop, 'snapshot', lambda *_a, **_kw: next(snapshots))
    monkeypatch.setattr(stop, 'process_rows', lambda: [ssh, agent])
    monkeypatch.setattr(stop.time, 'sleep', lambda _seconds: None)
    calls = []

    def fake_run(argv, **_kwargs):
        calls.append(tuple(argv))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(stop, 'run', fake_run)
    monkeypatch.setattr(stop, 'kill_pid', lambda pid, uid: calls.append(('kill', pid)) or True)
    report = stop.execute('test-password', rows=[], labels=[])
    assert report['errors'] == []
    assert report['disabled_jobs'] == ['org.borgnet.workspace']
    assert report['killed_pids'] == [20, 30]
    assert calls.index(('/bin/launchctl', 'disable', f'gui/{stop.os.getuid()}/org.borgnet.workspace')) < calls.index(
        ('/bin/launchctl', 'bootout', f'gui/{stop.os.getuid()}/org.borgnet.workspace'))
    assert calls.index(('kill', 20)) < calls.index(
        ('/bin/launchctl', 'disable', f'gui/{stop.os.getuid()}/org.borgnet.workspace'))
    assert calls.index(('kill', 20)) < calls.index(('kill', 30))
    assert calls[-1] == ('/usr/bin/sudo', '-k')


def test_changed_pid_is_not_signalled(monkeypatch):
    initial = {**row(20, '/usr/bin/ssh -N remote-box'), 'category': 'ssh'}
    snapshots = iter([{'jobs': [], 'processes': [initial]},
                      {'jobs': [], 'processes': [initial]},
                      {'jobs': [], 'processes': []}])
    monkeypatch.setattr(stop, 'snapshot', lambda *_a, **_kw: next(snapshots))
    monkeypatch.setattr(stop, 'process_rows', lambda: [row(20, '/usr/bin/python3 unrelated.py')])
    monkeypatch.setattr(stop.time, 'sleep', lambda _seconds: None)
    monkeypatch.setattr(stop, 'run', lambda *_a, **_kw: SimpleNamespace(returncode=0))
    monkeypatch.setattr(stop, 'kill_pid', lambda *_a: pytest.fail('changed PID was signalled'))
    report = stop.execute('test-password', rows=[], labels=[])
    assert 'PID 20 changed before stop' in report['errors']
