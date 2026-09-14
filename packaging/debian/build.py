#!/usr/bin/env python3
"""Build an architecture-independent .deb on macOS or Linux using stdlib only."""
import argparse
import gzip
import hashlib
import io
from pathlib import Path
import tarfile
import tomllib

ROOT = Path(__file__).resolve().parents[2]


def tarball(files):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w', format=tarfile.USTAR_FORMAT) as archive:
        for name, (data, mode) in sorted(files.items()):
            entry = tarfile.TarInfo('./' + name)
            entry.size, entry.mode, entry.mtime = len(data), mode, 0
            entry.uid = entry.gid = 0
            entry.uname = entry.gname = 'root'
            archive.addfile(entry, io.BytesIO(data))
    return gzip.compress(buffer.getvalue(), mtime=0)


def build(output):
    version = tomllib.loads((ROOT / 'pyproject.toml').read_text())['project']['version'] + '-1'
    files = {}
    for path in sorted((ROOT / 'borgnet').rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts and path.suffix in {'.py', '.html', '.css', '.js'}:
            files['usr/share/borgnet/source/' + str(path.relative_to(ROOT))] = (path.read_bytes(), 0o644)
    files['usr/share/borgnet/source/pyproject.toml'] = ((ROOT / 'pyproject.toml').read_bytes(), 0o644)
    digest = hashlib.sha256(b''.join(data for data, _ in files.values())).hexdigest()[:16]
    files['usr/share/borgnet/VERSION'] = ((version + '-' + digest + '\n').encode(), 0o644)
    files['usr/bin/borgnet'] = ((ROOT / 'packaging/debian/launcher.py').read_bytes(), 0o755)
    files['usr/share/icons/hicolor/512x512/apps/borgnet.png'] = ((ROOT / 'native/AppIcon.png').read_bytes(), 0o644)
    files['usr/share/applications/borgnet.desktop'] = (b'''[Desktop Entry]
Type=Application
Name=BorgNet Universal Interface
Comment=Local AI workspace
Exec=/usr/bin/borgnet
Icon=borgnet
Terminal=true
Categories=Development;Utility;
StartupNotify=false
''', 0o644)
    files['usr/share/doc/borgnet/README.md'] = ((ROOT / 'packaging/debian/README.md').read_bytes(), 0o644)
    control = f'''Package: borgnet
Version: {version}
Section: utils
Priority: optional
Architecture: all
Maintainer: Cambium Automation <noreply@github.com>
Depends: python3 (>= 3.11), python3-venv, ca-certificates, xdg-utils
Recommends: openssh-client
Installed-Size: {(sum(len(data) for data, _ in files.values()) + 1023) // 1024}
Homepage: https://github.com/Cambium-Automation/BorgNet-Universal-Interface
Description: Local AI workspace with customizable appearance
 Browser interface for local models, cloud APIs, CLI assistants and MCP.
 First launch downloads Python dependencies into a per-user virtualenv.
 Requires Internet access for initial setup; models are installed separately.
'''.encode()
    md5sums = ''.join(f'{hashlib.md5(data).hexdigest()}  {name}\n' for name, (data, _) in sorted(files.items())).encode()
    members = [('debian-binary', b'2.0\n'), ('control.tar.gz', tarball({'control': (control, 0o644), 'md5sums': (md5sums, 0o644)})), ('data.tar.gz', tarball(files))]
    output.mkdir(parents=True, exist_ok=True)
    target = output / f'borgnet_{version}_all.deb'
    with target.open('wb') as stream:
        stream.write(b'!<arch>\n')
        for name, data in members:
            stream.write(f'{name + "/":<16}{0:<12}{0:<6}{0:<6}{"100644":<8}{len(data):<10}`\n'.encode('ascii'))
            stream.write(data)
            if len(data) % 2:
                stream.write(b'\n')
    print(target)
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist')
    build(parser.parse_args().output)
