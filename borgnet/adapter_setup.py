"""Install browser binaries and register the gated Grok stdio connector."""
import importlib.util
import importlib.resources
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib

SERVER = 'borgnet_automation'


def entrypoint():
    return str(Path(__file__).with_name('automation.py').resolve())


def grok_registered():
    try:
        root=Path(os.environ.get('GROK_HOME','~/.grok')).expanduser()
        config=tomllib.loads((root/'config.toml').read_text())
        item=config.get('mcp_servers',{}).get(SERVER,{})
        return item.get('command')==sys.executable and item.get('args')==[entrypoint()]
    except (OSError,ValueError):return False


def status():
    from .desktop_adapter import status as desktop_status
    installed=importlib.util.find_spec('playwright') is not None
    browser_ready=False
    if installed:
        package=Path(str(importlib.resources.files('playwright')))
        manifest=json.loads((package/'driver/package/browsers.json').read_text())
        revision=next(item['revision'] for item in manifest['browsers'] if item['name']=='chromium')
        override=os.environ.get('PLAYWRIGHT_BROWSERS_PATH')
        if override=='0':cache=package/'driver/package/.local-browsers'
        elif override:cache=Path(override).expanduser()
        elif sys.platform=='darwin':cache=Path.home()/'Library/Caches/ms-playwright'
        elif sys.platform=='win32':cache=Path(os.environ.get('LOCALAPPDATA',''))/'ms-playwright'
        else:cache=Path(os.environ.get('XDG_CACHE_HOME',str(Path.home()/'.cache')))/'ms-playwright'
        directory=cache/('chromium-'+str(revision))
        browser_ready=directory.is_dir() and any(p.is_file() and p.name in {'chrome','chrome.exe','Chromium','Google Chrome for Testing'} for p in directory.rglob('*'))
    return {'browser':{'installed':installed,'ready':browser_ready,
                       'message':'Isolated Chromium; browser pages can send data to websites.'},
            'computer':desktop_status(), 'grok_registered':grok_registered(),
            'requires_full_access':True}


def install():
    subprocess.run([sys.executable,'-m','playwright','install','chromium'],check=True)
    grok=shutil.which('grok')
    if grok:
        root=Path(os.environ.get('GROK_HOME','~/.grok')).expanduser()
        config=tomllib.loads((root/'config.toml').read_text()) if (root/'config.toml').exists() else {}
        marker=root/'borgnet-automation-registration.json'
        previous=json.loads(marker.read_text()) if marker.exists() else {}
        entry=config.get('mcp_servers',{}).get(SERVER)
        current={'command':sys.executable,'args':[entrypoint()]}
        if not grok_registered():
            if entry and {'command':entry.get('command'),'args':entry.get('args')} != previous:
                raise ValueError('An existing borgnet_automation Grok server is not owned by this installer. Rename it before installing this adapter.')
            subprocess.run([grok,'mcp','add','--scope','user','-e',
                            'BORGNET_AUTOMATION_GRANT=${BORGNET_AUTOMATION_GRANT:-}',SERVER,'--',sys.executable,entrypoint()],check=True)
        marker.write_text(json.dumps(current))
        marker.chmod(0o600)
    print(json.dumps(status(),indent=2))
