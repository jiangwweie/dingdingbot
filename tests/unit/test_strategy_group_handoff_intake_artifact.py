from __future__ import annotations

import json
from pathlib import Path

from scripts.build_strategy_group_handoff_intake_artifact import build_artifact


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _handoff(strategy_group_id: str, *, default_mode: str = "armed_observation") -> dict:
    return {
        "strategy_group_id": strategy_group_id,
        "version": "2026-06-14-r0",
        "name": f"{strategy_group_id} test handoff",
        "supported_symbols": ["BTCUSDT", "ETHUSDT"],
        "supported_sides": ["long"],
        "mode_recommendation": {
            "default": default_mode,
            "allowed": ["observe_only", "armed_observation"],
            "not_allowed_by_research_window": ["auto_execute_after_gate"],
        },
        "signal_ready_rule": {"requires_fresh_closed_candle": True},
        "required_facts": {
            "market": ["latest_price", "recent_1h_candles"],
            "account": ["active_position", "open_orders"],
            "exchange": ["symbol_availability", "min_notional"],
            "risk": ["protection_plan_state"],
        },
        "risk_defaults": {"max_notional_usdt": 8, "leverage": 1},
        "hard_stops": ["active_position", "open_order"],
        "sample_signal_artifact": {"status": "ready_for_shadow_candidate_prepare"},
        "sample_no_signal_artifact": {"status": "no_signal"},
        "sample_stale_signal_artifact": {"status": "stale_signal"},
        "sample_conflict_artifact": {"status": "signal_conflict"},
    }


def _write_supplements(base: Path) -> None:
    for name in [
        "main-control-admission-priority.md",
        "main-control-required-facts-map.md",
        "main-control-conflict-policy.md",
        "main-control-watcher-cadence.md",
        "main-control-handoff-index.md",
        "main-control-task-card.md",
    ]:
        (base / name).write_text(f"# {name}\n", encoding="utf-8")


def test_strategy_group_handoff_intake_artifact_builds_picker_and_readiness(tmp_path):
    base = tmp_path / "handoffs"
    _write_json(base / "MPG-001" / "handoff.json", _handoff("MPG-001"))
    _write_json(
        base / "PMR-001" / "handoff.json",
        _handoff("PMR-001", default_mode="observe_only"),
    )
    _write_supplements(base)

    artifact = build_artifact(
        handoff_dir=base,
        source_repo="/strategy-repo",
        source_branch="codex/strategy-research-20260613-goal",
        source_commit="05f616b0",
    )

    assert artifact["status"] == "ready_for_main_control_intake"
    assert artifact["source_anchor"]["commit"] == "05f616b0"
    assert artifact["counts"]["strategy_groups"] == 2
    assert artifact["counts"]["required_fact_rows"] == 14
    assert artifact["safety_invariants"]["places_order"] is False
    assert artifact["safety_invariants"]["creates_candidate"] is False
    assert artifact["safety_invariants"]["mutates_pg"] is False
    by_id = {item["strategy_group_id"]: item for item in artifact["strategy_picker"]}
    assert by_id["MPG-001"]["intake_status"] == "armed_observation_intake_ready"
    assert by_id["PMR-001"]["intake_status"] == "observe_only_intake_ready"
    assert by_id["MPG-001"]["sample_statuses"]["signal"] == (
        "ready_for_shadow_candidate_prepare"
    )
    assert by_id["MPG-001"]["watcher_scope"][
        "shadow_candidate_evidence_freshness_target_seconds"
    ] == 120
    assert "candidate_packet_freshness_seconds" not in by_id["MPG-001"]["watcher_scope"]
    account_rows = [
        item
        for item in artifact["required_facts_matrix"]
        if item["category"] == "account"
    ]
    assert account_rows
    assert {item["missing_behavior"] for item in account_rows} == {
        "block_candidate_prepare"
    }


def test_strategy_group_handoff_intake_artifact_warns_missing_supplements_by_default(
    tmp_path,
):
    base = tmp_path / "handoffs"
    _write_json(base / "MPG-001" / "handoff.json", _handoff("MPG-001"))

    artifact = build_artifact(
        handoff_dir=base,
        source_repo="/strategy-repo",
        source_branch="codex/strategy-research-20260613-goal",
        source_commit="05f616b0",
    )

    assert artifact["status"] == "ready_for_main_control_intake"
    assert "supplement_missing:admission_priority" in artifact["warnings"]
    assert artifact["blockers"] == []
    assert artifact["safety_invariants"]["places_order"] is False


def test_strategy_group_handoff_intake_artifact_can_require_supplements(tmp_path):
    base = tmp_path / "handoffs"
    _write_json(base / "MPG-001" / "handoff.json", _handoff("MPG-001"))

    artifact = build_artifact(
        handoff_dir=base,
        source_repo="/strategy-repo",
        source_branch="codex/strategy-research-20260613-goal",
        source_commit="05f616b0",
        require_supplements=True,
    )

    assert artifact["status"] == "blocked_strategy_intake_source"
    assert "supplement_missing:admission_priority" in artifact["blockers"]
    assert artifact["safety_invariants"]["places_order"] is False
