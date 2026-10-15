"""Opt-in historical experiment; release regressions need no old Git objects."""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType

BASELINE = 'de73f2791a01a14ba77e842da0a3ecadbdbc1069'


def benchmark_variants() -> tuple[bool, ...]:
    """Always test current behavior; historical A/B requires explicit invocation."""
    return (True, False) if os.getenv("BRC_OBS_HISTORICAL_BENCHMARK") == "1" else (False,)


def load_baseline(relative_path: str, name: str) -> ModuleType:
    if os.getenv("BRC_OBS_HISTORICAL_BENCHMARK") != "1":
        raise RuntimeError("historical experiment requires BRC_OBS_HISTORICAL_BENCHMARK=1")
    root = Path(__file__).resolve().parents[3]
    result = subprocess.run(['git', 'show', f'{BASELINE}:{relative_path}'], cwd=root,
        capture_output=True, text=True, timeout=10, check=False)
    if result.returncode:
        raise RuntimeError(f"historical experiment requires Git baseline {BASELINE}; "
                           "use a checkout containing that commit (no automatic fetch or skipped regression)")
    source = result.stdout
    with tempfile.TemporaryDirectory(prefix='brc-efficiency-') as directory:
        path = Path(directory) / 'baseline.py'
        path.write_text(source)
        spec = importlib.util.spec_from_file_location(name, path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return module
