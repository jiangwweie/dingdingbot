from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "validate_strategy_group_handoffs.py"

spec = importlib.util.spec_from_file_location("validate_strategy_group_handoffs", SCRIPT_PATH)
validator = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = validator
spec.loader.exec_module(validator)


def test_current_strategy_group_handoffs_are_valid() -> None:
    base_dir = ROOT / "docs" / "strategy-research" / "strategy-group-handoffs"
    results = [validator.validate_handoff(path) for path in validator.discover_handoffs(base_dir)]

    assert len(results) >= 5
    assert all(result.ok for result in results), [(result.group_id, result.errors) for result in results]


def test_validator_rejects_missing_required_field(tmp_path: Path) -> None:
    group_dir = tmp_path / "BAD-001"
    group_dir.mkdir()
    (group_dir / "handoff.md").write_text("# bad\n", encoding="utf-8")
    payload = {
        "strategy_group_id": "BAD-001",
        "version": "2026-06-14-r0",
        "supported_symbols": ["BTCUSDT"],
        "supported_sides": ["long"],
        "signal_ready_rule": {
            "status_name": "ready",
            "freshness_window_seconds": 120,
            "must_include": ["direction"],
            "stale_behavior": "block",
            "conflict_behavior": "block",
        },
        "required_facts": {"market": ["latest_price"]},
        "risk_defaults": {"interpretation": "research_proposal_only_not_live_order_sizing_default"},
        "hard_stops": ["stale_market_facts"],
        "sample_signal_packet": {
            "packet_type": "strategy_signal",
            "strategy_group_id": "BAD-001",
            "strategy_group_version": "2026-06-14-r0",
            "status": "ready",
            "generated_at": "2026-06-14T00:00:00Z",
            "symbol": "BTCUSDT",
            "direction": "long",
            "candidate_prepare_allowed_by_research": True,
            "execution_allowed_by_research": False,
        },
    }
    (group_dir / "handoff.json").write_text(json.dumps(payload), encoding="utf-8")

    result = validator.validate_handoff(group_dir / "handoff.json")

    assert not result.ok
    assert "missing required field: sample_no_signal_packet" in result.errors
