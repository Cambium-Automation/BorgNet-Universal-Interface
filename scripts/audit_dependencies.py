"""Check every locked platform/version against advisories, including inactive markers."""
from pathlib import Path
import re
import subprocess
import sys
import tempfile


def main():
    root = Path(__file__).resolve().parents[1]
    pins = set()
    for name in ('requirements.txt', 'requirements-bootstrap.txt', 'requirements-dev.txt'):
        pins.update(re.findall(r'^([A-Za-z0-9_.-]+==[^ ;\\\n]+)', (root / name).read_text(), re.MULTILINE))
    if not pins:
        raise SystemExit('No locked dependencies found; refusing an empty audit')
    with tempfile.TemporaryDirectory(prefix='borgnet-audit-') as directory:
        requirements = Path(directory) / 'all-platforms.txt'
        requirements.write_text('\n'.join(sorted(pins)) + '\n')
        # No package install/resolution occurs: every exact version is queried, including Windows-only packages on Linux.
        result = subprocess.run([sys.executable, '-m', 'pip_audit', '--disable-pip', '--no-deps', '-r', str(requirements)], check=False)
        raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
