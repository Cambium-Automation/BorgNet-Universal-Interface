import json
from pathlib import Path
import subprocess
import sys

import pytest

from borgnet import app_connectors as apps
from borgnet.automation import Grant, create_server
from tests.test_automation import grant_file


def test_app_open_uses_exact_installed_app_without_shell(tmp_path, monkeypatch):
    app = tmp_path / 'Blender.app'
    app.mkdir()
    scene = tmp_path / 'scene.blend'
    scene.write_bytes(b'fixture')
    calls = []
    monkeypatch.setattr(apps, 'applications', lambda: [{'name': 'Blender', 'path': str(app)}])
    monkeypatch.setattr(apps.subprocess, 'run', lambda argv, **kwargs: calls.append((argv, kwargs)))
    result = apps.open_application('Blender', str(scene))
    assert result['application'] == 'Blender'
    assert calls[0][0] == ['/usr/bin/open', '-a', str(app), str(scene)]
    with pytest.raises(ValueError, match='exact'):
        apps.open_application('Terminal')


@pytest.mark.asyncio
async def test_mac_connectors_obey_request_grant(tmp_path):
    if sys.platform != 'darwin':
        pytest.skip('Mac connector tools are exposed on macOS only')
    no_grant = create_server(Grant(tmp_path / 'missing'))
    assert not any(tool.name == 'mac_open' for tool in await no_grant.list_tools())
    allowed = create_server(Grant(grant_file(tmp_path, computer=True)))
    names = {tool.name for tool in await allowed.list_tools()}
    assert {'mac_apps', 'mac_open', 'vscode_open', 'vscode_diff', 'vscode_extensions',
            'blender_scene', 'cura_profile', 'cura_open_model'} <= names


def test_cura_model_open_rejects_non_model_files(tmp_path, monkeypatch):
    model = tmp_path / 'part.stl'
    model.write_text('solid part\nendsolid part\n')
    other = tmp_path / 'instructions.gcode'
    other.write_text('G1 X0')
    monkeypatch.setattr(apps, 'CURA_ENGINE', model)
    calls = []
    monkeypatch.setattr(apps, 'open_application', lambda name, document='': calls.append((name, document)) or {'application':name})
    assert apps.cura_open_model(str(model)) == {'application':'UltiMaker Cura'}
    assert calls == [('UltiMaker Cura', str(model))]
    with pytest.raises(ValueError, match='STL, OBJ, or 3MF'):
        apps.cura_open_model(str(other))


def test_cura_launch_filters_usb_discovery(tmp_path, monkeypatch):
    app = tmp_path / 'UltiMaker Cura.app'
    app.mkdir()
    binary = tmp_path / 'UltiMaker-Cura'
    binary.write_text('fixture')
    monkeypatch.setattr(apps, 'CURA_BINARY', binary)
    monkeypatch.setattr(apps, 'applications', lambda: [{'name':'UltiMaker Cura','path':str(app)}])
    monkeypatch.setattr(apps, '_cura_processes', lambda: [])
    calls=[]
    monkeypatch.setattr(apps.subprocess, 'run', lambda argv, **kwargs: calls.append(argv))
    result=apps.open_application('UltiMaker Cura')
    assert calls==[['/usr/bin/open','-n','--env','CURA_DEVICENAMES=(?!)','-a',str(app)]]
    assert result['usb_printer_access']=='disabled for this Cura launch'


def test_cura_refuses_unsafe_existing_instance(tmp_path, monkeypatch):
    app=tmp_path/'UltiMaker Cura.app';app.mkdir()
    binary=tmp_path/'UltiMaker-Cura';binary.write_text('fixture')
    monkeypatch.setattr(apps,'CURA_BINARY',binary)
    monkeypatch.setattr(apps,'applications',lambda: [{'name':'UltiMaker Cura','path':str(app)}])
    monkeypatch.setattr(apps,'_cura_processes',lambda: [123])
    monkeypatch.setattr(apps,'_cura_process_safe',lambda pid: False)
    def unexpected(*args, **kwargs):raise AssertionError('Unsafe Cura must not receive a file')
    monkeypatch.setattr(apps.subprocess,'run',unexpected)
    with pytest.raises(ValueError,match='already running'):
        apps.open_application('UltiMaker Cura')


def test_cura_reuses_only_filtered_instance(tmp_path, monkeypatch):
    app=tmp_path/'UltiMaker Cura.app';app.mkdir()
    binary=tmp_path/'UltiMaker-Cura';binary.write_text('fixture')
    model=tmp_path/'part.stl';model.write_text('solid part\nendsolid part\n')
    monkeypatch.setattr(apps,'CURA_BINARY',binary)
    monkeypatch.setattr(apps,'applications',lambda: [{'name':'UltiMaker Cura','path':str(app)}])
    monkeypatch.setattr(apps,'_cura_processes',lambda: [123])
    monkeypatch.setattr(apps,'_cura_process_safe',lambda pid: True)
    calls=[]
    monkeypatch.setattr(apps.subprocess,'run',lambda argv,**kwargs:calls.append(argv))
    apps.open_application('UltiMaker Cura',str(model))
    assert calls==[['/usr/bin/open','--env','CURA_DEVICENAMES=(?!)','-a',str(app),str(model)]]


@pytest.mark.skipif(not apps.BLENDER.is_file(), reason='Blender is not installed')
def test_blender_probe_reads_scene_without_autorun(tmp_path):
    scene = tmp_path / 'fixture.blend'
    subprocess.run([str(apps.BLENDER), '--background', '--factory-startup', '--disable-autoexec',
                    '--python-expr', f"import bpy; bpy.ops.wm.save_as_mainfile(filepath={str(scene)!r})"],
                   check=True, capture_output=True, timeout=60)
    report = apps.blender_scene(str(scene))
    assert report['scene'] == 'Scene'
    assert any(item['name'] == 'Cube' and item['type'] == 'MESH' for item in report['objects'])
    assert report['auto_execute_enabled'] is False
