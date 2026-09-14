"""One render per process, private stdin input, no retained model memory."""
import contextlib
import json
import os
from pathlib import Path
import secrets
import sys
import time


def main():
    data = json.load(sys.stdin)
    width, height = map(int, data['size'].split('x'))
    started = time.monotonic()
    with contextlib.redirect_stdout(sys.stderr):
        import mlx.core as mx
        from backend.pipeline import FluxPipeline, PipelineConfig
        mx.set_memory_limit(3 * 1024**3)
        mx.set_cache_limit(128 * 1024**2)
        mx.set_wired_limit(2 * 1024**3)
        variant = data['variant']
        paths = {'baked_binary_model_path' if variant == 'binary' else 'baked_model_path': data['model_path']}
        pipeline = FluxPipeline(PipelineConfig(backend='bonsai-'+variant+'-mlx', te_4bit=True,
            evict_text_encoder=True, evict_transformer=True, lazy_components=True,
            max_sequence_length=128, bucketed_seq_len=True, **paths))
        seed = data.get('seed', -1)
        if not isinstance(seed, int) or not 0 <= seed <= 2147483647:
            seed = secrets.randbits(31)
        png = pipeline.generate_png(prompt=data['prompt'], seed=seed, steps=4, height=height, width=width)
        peak = mx.get_peak_memory() / 1024**2
        with Path(data['output']).open('xb') as out:
            os.chmod(data['output'], 0o600)
            out.write(png)
    print(json.dumps({'seconds': round(time.monotonic()-started, 2), 'peak_memory_mb': round(peak, 1)}))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        import traceback
        traceback.print_exc(file=sys.stderr)
        print(json.dumps({'error': str(error)[:8000]}))
        raise SystemExit(1) from None
