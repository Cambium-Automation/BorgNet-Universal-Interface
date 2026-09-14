"""Check the cross-platform Debian archive without needing dpkg on macOS."""
import hashlib
import importlib.util
import io
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def test_debian_package(tmp_path):
    spec = importlib.util.spec_from_file_location('deb_build', ROOT / 'packaging/debian/build.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    package = module.build(tmp_path)
    raw = package.read_bytes()
    assert raw[:8] == b'!<arch>\n'
    offset, members = 8, {}
    while offset < len(raw):
        header = raw[offset:offset + 60]
        assert header[-2:] == b'`\n'
        size = int(header[48:58])
        members[header[:16].decode().strip().rstrip('/')] = raw[offset + 60:offset + 60 + size]
        offset += 60 + size + size % 2
    assert list(members) == ['debian-binary', 'control.tar.gz', 'data.tar.gz']
    assert members['debian-binary'] == b'2.0\n'
    with tarfile.open(fileobj=io.BytesIO(members['control.tar.gz'])) as archive:
        control = archive.extractfile('./control').read().decode()
        checksums = archive.extractfile('./md5sums').read().decode()
    assert 'Architecture: all\n' in control
    assert 'python3 (>= 3.11), python3-venv' in control
    with tarfile.open(fileobj=io.BytesIO(members['data.tar.gz'])) as archive:
        entries = {item.name.removeprefix('./'): item for item in archive.getmembers()}
        assert entries['usr/bin/borgnet'].mode == 0o755
        for item in entries.values():
            assert item.uid == item.gid == 0
            assert item.isfile()
            assert '..' not in Path(item.name).parts
            assert not {'.venv', '__pycache__', '.git'} & set(Path(item.name).parts)
        for line in checksums.splitlines():
            checksum, name = line.split('  ', 1)
            assert hashlib.md5(archive.extractfile(entries[name]).read()).hexdigest() == checksum
        assert 'usr/share/borgnet/source/borgnet/web/appearance.js' in entries
        for name in ['automation.py', 'desktop_adapter.py', 'adapter_setup.py']:
            assert 'usr/share/borgnet/source/borgnet/' + name in entries
        for name in ['requirements.txt', 'requirements-bootstrap.txt']:
            assert 'usr/share/borgnet/source/' + name in entries
        launcher = archive.extractfile(entries['usr/bin/borgnet']).read()
        compile(launcher, 'borgnet', 'exec')
        assert b'--require-hashes' in launcher and b'--only-binary=:all:' in launcher
        assert b'--no-build-isolation' in launcher and b'--no-deps' in launcher
        assert b"'adapters', 'install'" in launcher
        for name in entries:
            assert not name.endswith(('secrets.json', 'config.json', '.gguf', '.icns'))
    # Identical inputs produce identical distributable bytes.
    assert module.build(tmp_path).read_bytes() == raw
