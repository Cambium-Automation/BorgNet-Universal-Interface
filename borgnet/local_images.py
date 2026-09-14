"""Isolated Bonsai generation with an interprocess BitNet memory gate."""
import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import signal
import uuid

from .media_responses import capture


@contextmanager
def model_gate(path):
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'r+') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Another local model is active. Wait for it to finish before switching.') from None
        yield


class LocalImages:
    def __init__(self, root, store):
        self.root, self.store = Path(root), store

    def settings(self):
        return self.store.read('local-image-runtime', {})

    def catalog(self):
        cfg = self.settings()
        if not cfg.get('ready'):
            return []
        return [{'id': 'local::bonsai', 'label': 'Bonsai Image 4B · '+cfg['variant']+' · this Mac',
                 'backend': 'local_cli', 'installed': True, 'ready': True,
                 'status': 'Exclusive memory mode: unloads BitNet before rendering; releases Bonsai afterward. BitNet reloads when next used.',
                 'sizes': ['512x512', '576x384', '384x576'], 'default_size': '512x512',
                 'modes': [['auto', '4 steps · memory-safe preview']], 'min_steps': 4, 'max_steps': 4, 'default_steps': 4}]

    async def bitnet(self, action):
        cfg = self.settings()
        process = await asyncio.create_subprocess_exec(cfg['bitnet_python'], cfg['bitnet_runtime'], action,
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        try:
            await asyncio.wait_for(process.wait(), 75)
        except BaseException:
            if process.returncode is None:
                process.kill()
            await process.wait()
            raise
        if process.returncode:
            raise ValueError('Could not '+action+' the managed BitNet runtime. The local runtime may be busy.')

    async def monitor_memory(self, process):
        # MLX's allocator limit is advisory; enforce a separate process RSS cap.
        while process.returncode is None:
            check = await asyncio.create_subprocess_exec('/bin/ps', '-p', str(process.pid), '-o', 'rss=',
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            output, _ = await check.communicate()
            if output.strip() and int(output.strip()) > 4 * 1024**2:
                raise ValueError('Bonsai reached its 4 GB process memory cap and was stopped. BitNet remains unloaded.')
            await asyncio.sleep(1)

    async def generate(self, body):
        cfg = self.settings()
        if not self.catalog() or body.get('model_id') != 'local::bonsai':
            raise ValueError('Bonsai is not installed and verified on this computer.')
        prompt = str(body.get('prompt', '')).strip()
        size = body.get('size', '512x512')
        if not prompt or len(prompt) > 4000 or size not in self.catalog()[0]['sizes']:
            raise ValueError('Enter a prompt and choose a supported preview size.')
        if body.get('negative_prompt'):
            raise ValueError('Bonsai does not support negative prompts. Include desired details in the main prompt.')
        identity = datetime.now().strftime('%Y%m%d-%H%M%S-')+uuid.uuid4().hex[:8]
        directory = self.root/'api-images'
        directory.mkdir(mode=0o700, exist_ok=True)
        target = directory/identity
        with model_gate(cfg['lock_path']):
            # Confirm the managed process exits before importing MLX or loading weights.
            await self.bitnet('stop')
            env = {k: os.environ[k] for k in ('HOME', 'PATH', 'TMPDIR', 'LANG') if k in os.environ}
            env.update(HF_HUB_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1', TOKENIZERS_PARALLELISM='false')
            process = await asyncio.create_subprocess_exec(cfg['python'], cfg['runner'],
                      stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                      stderr=asyncio.subprocess.DEVNULL, env=env, start_new_session=True)
            payload = {'model_path': cfg['model_path'], 'variant': cfg['variant'], 'prompt': prompt,
                       'size': size, 'seed': body.get('seed', -1), 'output': str(target)}
            communication = asyncio.create_task(process.communicate(json.dumps(payload).encode()))
            monitor = asyncio.create_task(self.monitor_memory(process))
            try:
                done, _ = await asyncio.wait([communication, monitor], timeout=600, return_when=asyncio.FIRST_COMPLETED)
                if not done:
                    raise ValueError('Bonsai exceeded the ten-minute render limit and was unloaded.')
                if monitor in done:
                    await monitor
                output, _ = await communication
                if process.returncode or not target.is_file():
                    try:
                        failure = json.loads(output)
                        capture({'error': failure.get('error', '')})
                    except (ValueError, AttributeError):
                        pass
                    target.unlink(missing_ok=True)
                    raise ValueError('Bonsai generation failed or exceeded its memory allowance. BitNet remains unloaded; try again after closing other apps.')
                metrics = json.loads(output)
            except BaseException:
                target.unlink(missing_ok=True)
                raise
            finally:
                monitor.cancel()
                if process.returncode is None:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                await process.wait()
                await asyncio.gather(communication, monitor, return_exceptions=True)
                if process.returncode:
                    target.unlink(missing_ok=True)
                # Release all model memory before dropping the gate.
        result = {'id': identity, 'model_id': 'local::bonsai', 'prompt': prompt,
                  'created_at': datetime.now(timezone.utc).isoformat(), 'url': '/api/imagegen/images/'+identity,
                  'mime': 'image/png', 'seconds': metrics.get('seconds'), 'peak_memory_mb': metrics.get('peak_memory_mb')}
        with self.store.lock:
            history = self.store.read('api-image-history', [])
            history.append(result)
            self.store.write('api-image-history', history)
        return result
