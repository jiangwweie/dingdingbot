from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
import sys
from pathlib import Path


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


def test_public_facts_fallback_requires_fresh_ready_artifact(tmp_path: Path):
    module = _load_module()
    fallback = tmp_path / "fallback.json"
    generated_at = datetime.now(timezone.utc).isoformat()
    fallback.write_text(
        json.dumps(
            {
                "status": "binance_usdm_public_facts_ready",
                "generated_at_utc": generated_at,
                "summary": {"ready_symbol_count": 1, "errors": []},
                "symbols": [{"symbol": "ETHUSDT", "public_facts_ready": True}],
                "checks": {"public_facts_ready": True},
            }
        ),
        encoding="utf-8",
    )
    current = {
        "status": "binance_usdm_public_facts_unavailable",
        "summary": {"errors": ["network_down"]},
    }

    artifact = module._fallback_public_facts(
        current,
        fallback_path=fallback,
        symbols=["ETHUSDT"],
    )

    assert artifact["status"] == "binance_usdm_public_facts_ready_from_fallback"
    assert artifact["checks"]["public_facts_ready"] is True
    assert artifact["checks"]["used_fallback_after_fetch_failure"] is True
    assert artifact["interaction"]["calls_exchange_write"] is False
    assert artifact["safety_invariants"]["order_created"] is False


def test_public_facts_fallback_rejects_missing_symbol(tmp_path: Path):
    module = _load_module()
    fallback = tmp_path / "fallback.json"
    generated_at = datetime.now(timezone.utc).isoformat()
    fallback.write_text(
        json.dumps(
            {
                "status": "binance_usdm_public_facts_ready",
                "generated_at_utc": generated_at,
                "symbols": [{"symbol": "ETHUSDT", "public_facts_ready": True}],
                "checks": {"public_facts_ready": True},
            }
        ),
        encoding="utf-8",
    )
    current = {"status": "binance_usdm_public_facts_unavailable", "summary": {}}

    artifact = module._fallback_public_facts(
        current,
        fallback_path=fallback,
        symbols=["ETHUSDT", "SOLUSDT"],
    )

    assert artifact is current
