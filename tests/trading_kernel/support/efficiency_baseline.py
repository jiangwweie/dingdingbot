"""Load the pinned pre-change Python module for local comparison only."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType

BASELINE = 'de73f2791a01a14ba77e842da0a3ecadbdbc1069'


def load_baseline(relative_path: str, name: str) -> ModuleType:
    root = Path(__file__).resolve().parents[3]
    source = subprocess.run(['git', 'show', f'{BASELINE}:{relative_path}'], cwd=root,
        check=True, capture_output=True, text=True).stdout
    with tempfile.TemporaryDirectory(prefix='brc-efficiency-') as directory:
        path = Path(directory) / 'baseline.py'
        path.write_text(source)
        spec = importlib.util.spec_from_file_location(name, path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return module
