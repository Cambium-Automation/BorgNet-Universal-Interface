"""Local emergency stop for BorgNet, SSH sessions, and Mac AI agents.

The native app supplies a password over stdin. No network call is made here.
Preview is deliberately read-only and does not require authentication.
"""
import argparse
import getpass
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time


LAUNCH_LABELS = {
    'org.borgnet.workspace', 'org.borgnet.advisors',
    'com.frankencluster.relay', 'com.frankencluster.junior-runner',
    'homebrew.mxcl.ollama', 'com.openssh.ssh-agent',
}
AGENT_EXECUTABLES = {
    'codex', 'claude', 'grok', 'gemini', 'copilot', 'ollama',
    'llama-server', 'llama-cli', 'vllm', 'openclaw', 'aider',
    'chatgpt', 'frankencluster workshop',
}
SSH_EXECUTABLES = {'ssh', 'scp', 'sftp', 'sshfs', 'autossh', 'mosh-client',
                   'ssh-agent', 'sshd', 'sshd-session', 'sftp-server'}
KNOWN_AGENT_MARKERS = (
    '/Application Support/BorgNet/cli_bridge.py',
    '/Application Support/Frankencluster Relay/relay_server.py',
    '/Application Support/Frankencluster Services/frankencluster-',
    '/frankencluster-junior-devs/', '/frankencluster-handoff/',
    '/frankencluster-sim/', '/frankencluster-security-mcp/',
    '/signal-chat/claude_bridge',
)


def run(argv, **kwargs):
    return subprocess.run(argv, check=False, text=True, capture_output=True,
                          timeout=kwargs.pop('timeout', 10), **kwargs)


def process_rows():
    result = run(['/bin/ps', '-axo', 'pid=,ppid=,uid=,command='])
    if result.returncode:
        raise RuntimeError('Cannot list processes')
    rows = []
    for line in result.stdout.splitlines():
        match = re.match(r'^\s*(\d+)\s+(\d+)\s+(\d+)\s+(.+)$', line)
        if match:
            pid, ppid, uid = map(int, match.group(1, 2, 3))
            rows.append({'pid': pid, 'ppid': ppid, 'uid': uid,
                         'command': match.group(4)})
    return rows


def executable_name(command):
    """ps command can begin with a path containing spaces; use known app paths first."""
    if command.startswith('/Applications/ChatGPT.app/'):
        return 'chatgpt'
    if '/BorgNet Universal Interface.app/' in command and command.startswith('/'):
        return 'borgnet'
    if '/Frankencluster Workshop.app/' in command and command.startswith('/'):
        return 'frankencluster workshop'
    if command.startswith('/Applications/') and '.app/' in command:
        return command.split('/Applications/', 1)[1].split('.app/', 1)[0].lower()
    first = command.split(' ', 1)[0]
    return Path(first).name.lower()


def category(row):
    command = row['command']
    lower = command.lower()
    if 'borgnet e-stop.app/' in lower or '/estop/stop.py' in lower:
        return None
    name = executable_name(command)
    if name in SSH_EXECUTABLES:
        return 'ssh'
    if name in AGENT_EXECUTABLES:
        return 'agent'
    if name == 'borgnet' or re.search(r'\s-m\s+borgnet(?:\s|$)', lower):
        return 'borgnet'
    if any(marker.lower() in lower for marker in KNOWN_AGENT_MARKERS):
        return 'agent'
    return None


def launch_labels():
    result = run(['/bin/launchctl', 'list'])
    if result.returncode:
        raise RuntimeError('Cannot list launch agents')
    found = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[-1] in LAUNCH_LABELS:
            found.append(parts[-1])
    return sorted(set(found))


def snapshot(rows=None, labels=None, self_pid=None):
    rows = process_rows() if rows is None else rows
    labels = launch_labels() if labels is None else labels
    self_pid = os.getpid() if self_pid is None else self_pid
    by_pid = {row['pid']: row for row in rows}
    protected = {self_pid}
    current = self_pid
    while current in by_pid:
        current = by_pid[current]['ppid']
        if current in protected or current <= 1:
            break
        protected.add(current)
    targets = []
    for row in rows:
        kind = category(row)
        if kind and row['pid'] not in protected:
            targets.append({**row, 'category': kind})
    return {'jobs': sorted(set(labels) & LAUNCH_LABELS),
            'processes': sorted(targets, key=lambda item: (item['category'], item['pid']))}


def authenticate(password):
    if not password or '\n' in password or '\x00' in password or len(password) > 1024:
        raise ValueError('Enter the current macOS account password')
    run(['/usr/bin/sudo', '-k'])
    result = run(['/usr/bin/sudo', '-S', '-p', '', '-v'], input=password + '\n', timeout=25)
    if result.returncode:
        run(['/usr/bin/sudo', '-k'])
        raise ValueError('macOS password verification failed')


def kill_pid(pid, uid):
    try:
        os.kill(pid, signal.SIGKILL)
        return True
    except ProcessLookupError:
        return True
    except PermissionError:
        result = run(['/usr/bin/sudo', '-n', '/bin/kill', '-KILL', str(pid)])
        return result.returncode == 0


def execute(password, rows=None, labels=None):
    authenticate(password)
    try:
        before = snapshot(rows, labels)
        report = {'started_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                  'planned': before, 'disabled_jobs': [], 'booted_out_jobs': [],
                  'killed_pids': [], 'errors': []}
        domain = f'gui/{os.getuid()}'
        signalled = set()

        def stop_process(row):
            # Re-read the command to avoid signalling a PID reused since preview.
            current = next((item for item in process_rows() if item['pid'] == row['pid']), None)
            if current is None:
                return
            if current['command'] != row['command'] or category(current) != row['category']:
                report['errors'].append(f'PID {row["pid"]} changed before stop')
                return
            if kill_pid(row['pid'], row['uid']):
                report['killed_pids'].append(row['pid'])
                signalled.add(row['pid'])
            else:
                report['errors'].append(f'Could not stop PID {row["pid"]} (different owner)')

        # Sever established SSH sessions before slower launchd cleanup.
        for row in before['processes']:
            if row['category'] == 'ssh':
                stop_process(row)
        # Disable before bootout so KeepAlive jobs cannot immediately respawn.
        for label in before['jobs']:
            target = f'{domain}/{label}'
            disabled = run(['/bin/launchctl', 'disable', target])
            if disabled.returncode == 0:
                report['disabled_jobs'].append(label)
            else:
                report['errors'].append(f'Could not disable {label}')
            stopped = run(['/bin/launchctl', 'bootout', target])
            if stopped.returncode == 0:
                report['booted_out_jobs'].append(label)
            else:
                report['errors'].append(f'Could not boot out {label}')
        # Refresh after stopping jobs; kill SSH first and then all agent processes.
        try:
            remaining = snapshot()['processes']
        except RuntimeError as error:
            report['errors'].append(str(error))
            remaining = before['processes']
        order = {'ssh': 0, 'borgnet': 1, 'agent': 2}
        pending = [row for row in {row['pid']: row for row in before['processes'] + remaining}.values()
                   if row['pid'] not in signalled]
        for attempt in range(3):
            for row in sorted(pending, key=lambda item: (order[item['category']], item['pid'])):
                stop_process(row)
            # Catch new processes spawned while the launch jobs wind down.
            time.sleep(0.2)
            try:
                report['remaining'] = snapshot()
            except RuntimeError as error:
                report['errors'].append(str(error))
                report['remaining'] = {'jobs': [], 'processes': []}
            pending = [row for row in report['remaining']['processes']
                       if row['pid'] not in signalled]
            if not pending:
                break
        return report
    finally:
        run(['/usr/bin/sudo', '-k'])


def save_report(report):
    directory = Path.home() / 'Library/Application Support/BorgNet E-Stop'
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = directory / 'last-run.json'
    temporary = directory / f'last-run-{os.getpid()}.tmp'
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'w') as file:
            json.dump(report, file, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def main():
    parser = argparse.ArgumentParser(description='BorgNet Mac emergency stop')
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--preview', action='store_true')
    action.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    try:
        if args.preview:
            print(json.dumps(snapshot()))
            return 0
        password = (getpass.getpass('Mac account password: ') if sys.stdin.isatty()
                    else sys.stdin.readline(1025).rstrip('\n'))
        report = execute(password)
        path = save_report(report)
        report['report_path'] = str(path)
        print(json.dumps(report))
        return 0 if not report['errors'] and not any(report['remaining'].values()) else 2
    except (ValueError, RuntimeError, OSError) as error:
        print(json.dumps({'error': str(error)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
