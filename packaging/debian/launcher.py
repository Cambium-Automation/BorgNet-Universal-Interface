#!/usr/bin/python3
"""Per-user Debian launcher; never installs into the system Python."""
import fcntl
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import webbrowser

SOURCE = Path('/usr/share/borgnet')


def main():
    if os.getuid() == 0:
        sys.exit('Run BorgNet as your normal desktop user, without sudo.')
    if sys.version_info < (3, 11):
        sys.exit('BorgNet requires Python 3.11 or newer.')
    os.umask(0o077)
    cache = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))) / 'borgnet'
    cache.mkdir(parents=True, exist_ok=True)
    revision = (SOURCE / 'VERSION').read_text().strip()
    runtime = cache / ('runtime-' + revision)
    python = runtime / 'bin/python'
    with (cache / 'setup.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not (runtime / '.ready').exists():
            print('Setting up BorgNet. First launch requires Internet access to PyPI.', flush=True, file=sys.stderr)
            subprocess.run(['/usr/bin/python3', '-m', 'venv', str(runtime)], check=True, stdout=sys.stderr)
            subprocess.run([str(python), '-m', 'pip', '--isolated', 'install', '--index-url', 'https://pypi.org/simple', '--upgrade', 'pip>=26.2'], check=True, stdout=sys.stderr)
            with tempfile.TemporaryDirectory(prefix='borgnet-install-') as temp:
                source = Path(temp) / 'source'
                shutil.copytree(SOURCE / 'source', source)
                subprocess.run([str(python), '-m', 'pip', '--isolated', 'install', '--index-url', 'https://pypi.org/simple', '--disable-pip-version-check', str(source)], check=True, stdout=sys.stderr)
            (runtime / '.ready').touch()
    args = sys.argv[1:]
    if args:
        os.execv(str(python), [str(python), '-m', 'borgnet', *args])
    # Fail explicitly if another application already owns the port.
    with socket.socket() as probe:
        try:
            probe.bind(('127.0.0.1', 7337))
        except OSError:
            sys.exit('Port 7337 is already in use. If BorgNet is running, open http://127.0.0.1:7337; otherwise use borgnet serve --port 7338.')
    process = subprocess.Popen([str(python), '-m', 'borgnet', 'serve'])

    def open_when_ready():
        for _ in range(100):
            if process.poll() is not None:
                return
            try:
                with urllib.request.urlopen('http://127.0.0.1:7337/', timeout=0.5) as response:
                    if response.status == 200:
                        data_root = Path(os.environ.get('BORGNET_DATA_DIR', '~/.borgnet')).expanduser()
                        session = json.loads((data_root / 'browser-session.json').read_text())['token']
                        webbrowser.open('http://127.0.0.1:7337/#session=' + session)
                        return
            except (OSError, urllib.error.URLError):
                time.sleep(0.1)
        print('Browser launch timed out. Check the server messages in this terminal.', flush=True)

    threading.Thread(target=open_when_ready, daemon=True).start()
    print('Keep this terminal open while using BorgNet. Ctrl+C stops the server.', flush=True)
    try:
        raise SystemExit(process.wait())
    except KeyboardInterrupt:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


if __name__ == '__main__':
    try:
        main()
    except subprocess.CalledProcessError as error:
        sys.exit(f'BorgNet setup failed (exit {error.returncode}). Check Internet access and python3-venv, then launch again.')
