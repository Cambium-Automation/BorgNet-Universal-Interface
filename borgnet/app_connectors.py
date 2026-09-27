"""Mac application connectors with fixed argv and read-only inspection paths."""
import configparser
import json
import os
from pathlib import Path
import re
import subprocess


APP_DIRS = (Path('/Applications'), Path.home() / 'Applications', Path('/System/Applications'))
BLENDER = Path('/Applications/Blender.app/Contents/MacOS/Blender')
VSCODE = Path('/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code')
CURA_ENGINE = Path('/Applications/UltiMaker Cura.app/Contents/Frameworks/CuraEngine')
CURA_APP = Path('/Applications/UltiMaker Cura.app')
CURA_BINARY = CURA_APP / 'Contents/MacOS/UltiMaker-Cura'
CURA_USB_FILTER = 'CURA_DEVICENAMES=(?!)'


def applications():
    """Installed top-level apps; duplicate names are returned with distinct paths."""
    return sorted(({'name': item.stem, 'path': str(item)}
        for root in APP_DIRS if root.is_dir() for item in root.glob('*.app') if item.is_dir()),
        key=lambda item: (item['name'].casefold(), item['path']))[:250]


def _document(path):
    candidate = Path(path).expanduser().resolve(strict=True)
    if not candidate.is_file():
        raise ValueError('Document must be an existing regular file')
    return candidate


def _cura_usb_devices():
    """Conservatively detect serial devices Cura may auto-connect on launch."""
    root = Path('/dev')
    devices = [*root.glob('cu.usbmodem*'), *root.glob('cu.usbserial*')]
    pattern = os.environ.get('CURA_DEVICENAMES', '')
    if pattern:
        try:
            devices = [device for device in devices if re.search(pattern, device.name)]
        except re.error:
            pass
    return devices


def _cura_processes():
    result = subprocess.run(['/usr/bin/pgrep', '-x', 'UltiMaker-Cura'],
                            capture_output=True, text=True, timeout=5)
    if result.returncode not in (0, 1):
        raise ValueError('Could not check whether Cura is already running')
    return [int(line) for line in result.stdout.splitlines() if line.isdigit()]


def _cura_process_safe(pid):
    result = subprocess.run(['/bin/ps', 'eww', '-p', str(pid)],
                            capture_output=True, text=True, timeout=5)
    return result.returncode == 0 and CURA_USB_FILTER in result.stdout


def cura_open_available():
    """A filtered new launch or reuse of an already filtered Cura process is possible."""
    if not CURA_BINARY.is_file():
        return False
    return all(_cura_process_safe(pid) for pid in _cura_processes())


def open_application(name, document=''):
    if not isinstance(name, str) or not name or len(name) > 120:
        raise ValueError('Choose an installed application by its exact name')
    matches = [item for item in applications() if item['name'] == name]
    if len(matches) != 1:
        raise ValueError('Choose one exact, unambiguous application name from mac_apps')
    if name == 'UltiMaker Cura':
        if not cura_open_available():
            raise ValueError('Cura is already running without BorgNet’s USB-port filter. Close that Cura instance before opening a model through BorgNet.')
        running = _cura_processes()
        argv = ['/usr/bin/open', *(['-n'] if not running else []), '--env', CURA_USB_FILTER,
                '-a', matches[0]['path']]
    else:
        argv = ['/usr/bin/open', '-a', matches[0]['path']]
    target = _document(document) if document else None
    if target:
        argv.append(str(target))
    subprocess.run(argv, check=True, capture_output=True, timeout=20)
    return {'application': name, 'document': str(target) if target else None,
            'usb_printer_access': 'disabled for this Cura launch' if name == 'UltiMaker Cura' else None,
            'result': 'Open request sent to macOS; inspect the app before further actions.'}


def vscode_open(path, line=0, column=0):
    if not VSCODE.is_file():
        raise ValueError('Visual Studio Code CLI is not installed at the expected app path')
    target = Path(path).expanduser().resolve(strict=True)
    if not 0 <= line <= 1_000_000 or not 0 <= column <= 1_000_000:
        raise ValueError('Line and column must be between 0 and 1,000,000')
    if target.is_dir() and (line or column):
        raise ValueError('Line and column require a file')
    if not target.is_file() and not target.is_dir():
        raise ValueError('Choose an existing file or folder')
    location = str(target) + (f':{line}:{column or 1}' if line else '')
    subprocess.run([str(VSCODE), '--reuse-window', *(['--goto'] if line else []), location],
                   check=True, capture_output=True, timeout=20)
    return {'path': str(target), 'line': line or None, 'column': column or None,
            'result': 'Open request sent to VS Code.'}


def vscode_diff(left, right):
    if not VSCODE.is_file():
        raise ValueError('Visual Studio Code CLI is not installed at the expected app path')
    first, second = _document(left), _document(right)
    subprocess.run([str(VSCODE), '--reuse-window', '--diff', str(first), str(second)],
                   check=True, capture_output=True, timeout=20)
    return {'left': str(first), 'right': str(second), 'result': 'Diff open request sent to VS Code.'}


def vscode_extensions(query=''):
    if not VSCODE.is_file():
        raise ValueError('Visual Studio Code CLI is not installed at the expected app path')
    if not isinstance(query, str) or len(query) > 120:
        raise ValueError('Extension search is limited to 120 characters')
    result = subprocess.run([str(VSCODE), '--list-extensions', '--show-versions'],
                            check=True, capture_output=True, text=True, timeout=20)
    installed = sorted(line.strip() for line in result.stdout.splitlines() if line.strip())
    matches = [item for item in installed if query.casefold() in item.casefold()]
    return {'installed_count': len(installed), 'matches': matches[:40], 'truncated': len(matches) > 40}


def blender_scene(path):
    if not BLENDER.is_file():
        raise ValueError('Blender is not installed at the expected app path')
    target = _document(path)
    if target.suffix.lower() != '.blend':
        raise ValueError('Choose a .blend scene file')
    probe = Path(__file__).with_name('blender_probe.py')
    result = subprocess.run([str(BLENDER), '--background', '--factory-startup', '--disable-autoexec',
        str(target), '--python-exit-code', '9', '--python', str(probe)],
        check=True, capture_output=True, text=True, timeout=180)
    lines = [line.removeprefix('BORGNET_SCENE_JSON:') for line in result.stdout.splitlines()
             if line.startswith('BORGNET_SCENE_JSON:')]
    if len(lines) != 1:
        raise ValueError('Blender did not return a scene inventory')
    return json.loads(lines[0])


def cura_profile():
    if not CURA_ENGINE.is_file():
        raise ValueError('UltiMaker Cura is not installed at the expected app path')
    root = Path.home() / 'Library/Application Support/cura'
    versions = sorted((p for p in root.iterdir() if p.is_dir() and re.fullmatch(r'\d+(?:\.\d+)+', p.name)),
                      key=lambda p: tuple(int(x) for x in p.name.split('.'))) if root.is_dir() else []
    if not versions:
        return {'installed': True, 'profile': None, 'message': 'No saved Cura profile found'}
    version = versions[-1]
    settings = configparser.ConfigParser(interpolation=None)
    settings.read(version / 'cura.cfg')
    machine = settings.get('cura', 'active_machine', fallback='')
    explicit = []
    keys = {'layer_height', 'layer_height_0', 'adhesion_type', 'skirt_line_count',
            'brim_width', 'support_enable', 'infill_sparse_density', 'material_print_temperature'}
    for subdir in ('user', 'quality_changes', 'definition_changes'):
        for file in (version / subdir).glob('*.cfg'):
            profile = configparser.ConfigParser(interpolation=None)
            try: profile.read(file)
            except configparser.Error: continue
            if machine and profile.get('metadata', 'machine', fallback=machine) != machine:
                continue
            values = {key: profile.get('values', key) for key in keys if profile.has_option('values', key)}
            if values:
                explicit.append({'file': file.name, 'settings': values})
    return {'installed': True, 'cura_version': version.name, 'active_machine': machine or None,
            'explicit_overrides': explicit,
            'note': 'These are saved overrides, not resolved effective slice settings or a print-ready profile.'}


def cura_open_model(path):
    """Load a model in Cura's interface without slicing or sending printer commands."""
    if not CURA_ENGINE.is_file():
        raise ValueError('UltiMaker Cura is not installed at the expected app path')
    target = _document(path)
    if target.suffix.lower() not in {'.stl', '.obj', '.3mf'}:
        raise ValueError('Choose an existing STL, OBJ, or 3MF model file')
    return open_application('UltiMaker Cura', str(target))
