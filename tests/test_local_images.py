import asyncio
from pathlib import Path
import sys
import pytest
from borgnet.config import Store
from borgnet.local_images import LocalImages, model_gate


def test_model_gate_excludes_second_process(tmp_path):
    import subprocess
    gate = tmp_path/'gate'
    with model_gate(gate):
        result = subprocess.run([sys.executable, '-c', 'from borgnet.local_images import model_gate;\nwith model_gate('+repr(str(gate))+'): pass'],capture_output=True)
        assert result.returncode != 0 and b'Another local model' in result.stderr
    with model_gate(gate): pass


@pytest.mark.asyncio
async def test_bonsai_stops_bitnet_before_runner_and_releases_gate(tmp_path):
    store=Store(tmp_path/'state')
    script=tmp_path/'runner.py'
    marker=tmp_path/'stopped'
    script.write_text('import json,sys\nfrom pathlib import Path\nd=json.load(sys.stdin)\nassert Path('+repr(str(marker))+').exists()\nPath(d["output"]).write_bytes(b"\\x89PNG\\r\\n\\x1a\\nfixture")\nprint(json.dumps({"seconds":1,"peak_memory_mb":20}))\n')
    cfg={'ready':True,'variant':'ternary','python':sys.executable,'runner':str(script),'model_path':str(tmp_path),'lock_path':str(tmp_path/'gate')}
    store.write('local-image-runtime',cfg)
    service=LocalImages(store.root,store)
    async def stop(action):
        assert action=='stop'
        with pytest.raises(ValueError):
            with model_gate(cfg['lock_path']): pass
        marker.write_text('stopped')
    service.bitnet=stop
    result=await service.generate({'model_id':'local::bonsai','prompt':'synthetic','size':'512x512'})
    assert result['peak_memory_mb']==20
    assert len(store.read('api-image-history',[]))==1
    with model_gate(cfg['lock_path']):pass
    with pytest.raises(ValueError,match='preview size'):
        await service.generate({'model_id':'local::bonsai','prompt':'synthetic','size':'4096x4096'})


@pytest.mark.asyncio
async def test_bonsai_never_loads_if_bitnet_stop_fails(tmp_path):
    store=Store(tmp_path)
    store.write('local-image-runtime',{'ready':True,'variant':'ternary','lock_path':str(tmp_path/'gate')})
    service=LocalImages(tmp_path,store)
    async def fail(action):raise ValueError('stop failed')
    service.bitnet=fail
    with pytest.raises(ValueError,match='stop failed'):
        await service.generate({'model_id':'local::bonsai','prompt':'synthetic'})
    with model_gate(tmp_path/'gate'):pass
    assert not store.read('api-image-history',[])


@pytest.mark.asyncio
async def test_bitnet_chat_holds_same_gate(tmp_path, monkeypatch):
    from borgnet.config import Connection
    from borgnet.providers import Providers, Tunnels
    store=Store(tmp_path)
    gate=tmp_path/'gate'
    store.write('local-image-runtime',{'ready':True,'lock_path':str(gate)})
    async def start(self, action):assert action=='start'
    monkeypatch.setattr(LocalImages,'bitnet',start)
    service=Providers(store,Tunnels())
    async def chat(*args):
        with pytest.raises(ValueError):
            with model_gate(gate):pass
        return 'synthetic'
    service._chat=chat
    assert await service.chat(Connection(url='http://127.0.0.1:18081/v1',kind='openai',model='bitnet-b1.58-2b-4t'),[])=='synthetic'
