from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "fetch_binance_usdm_public_facts.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "fetch_binance_usdm_public_facts",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_public_facts_rejects_legacy_fallback_json_arg(tmp_path: Path):
    module = _load_module()
    fallback = tmp_path / "fallback.json"

    with pytest.raises(SystemExit):
        module.main(["--fallback-json", str(fallback)])

    assert not hasattr(module, "_fallback_public_facts")


def test_public_facts_requires_pg_database_url_before_fetching():
    module = _load_module()

    assert module.main(["--symbols", "ETHUSDT"]) == 2
