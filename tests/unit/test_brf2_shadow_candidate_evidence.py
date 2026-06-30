from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_brf2_shadow_candidate_evidence.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_brf2_shadow_candidate_evidence",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _capture(*, fresh_signal_present: bool) -> dict:
    required_state = "satisfied" if fresh_signal_present else "missing"
    return {
        "status": "brf2_runtime_signal_capture_ready",
        "strategy_group_id": "BRF2-001",
        "watcher_scope": {
            "signal_id": "brf2_short_rally_failure_fresh_signal_v1",
            "side_scope": ["short"],
        },
        "source_signal_context": {
            "signal_observation_id": "brf2-signal-001",
            "runtime_instance_id": "runtime-brf2-001",
            "symbol": "ADA/USDT:USDT",
            "timeframe": "5m_closed",
            "closed_at_utc": "2026-06-23T00:00:00+00:00",
            "source_strategy_group_id": "BRF-001",
            "source_candidate_id": "BRF-001-BTC-SHORT",
            "source_signal_type": "would_enter",
        },
        "fact_authority": "readonly_proxy_not_action_time_required_fact",
        "fact_authority_boundary": {
            "usable_for_armed_observation": True,
            "action_time_required_facts_satisfied": False,
            "usable_for_finalgate": False,
            "usable_for_operation_layer": False,
        },
        "signal_detector_preview": {
            "current_signal_state": (
                "fresh_signal_present"
                if fresh_signal_present
                else "fresh_signal_absent"
            ),
            "fresh_signal_present": fresh_signal_present,
            "first_blocker_class": (
                "brf2_fresh_short_signal_present_non_executing"
                if fresh_signal_present
                else "fresh_brf2_short_signal_absent"
            ),
            "first_blocker_owner": "runtime" if fresh_signal_present else "market",
            "signal_capture_checkpoint": (
                "build_brf2_shadow_candidate_evidence"
                if fresh_signal_present
                else "continue_brf2_armed_observation_until_fresh_signal"
            ),
            "required_fact_status": [
                {
                    "fact_key": "closed_1h_ohlcv",
                    "state": required_state,
                    "raw_state": "ready" if fresh_signal_present else "",
                    "fresh": fresh_signal_present,
                },
                {
                    "fact_key": "rally_failure_trigger_state",
                    "state": required_state,
                    "raw_state": "confirmed" if fresh_signal_present else "",
                    "fresh": fresh_signal_present,
                },
            ],
            "disable_fact_status": [
                {
                    "fact_key": "short_squeeze_risk_state",
                    "state": "clear",
                    "raw_state": "clear",
                    "fresh": True,
                },
            ],
        },
    }


def _missing_fact_input_capture() -> dict:
    artifact = _capture(fresh_signal_present=False)
    artifact["fact_input_present"] = False
    artifact["watcher_tick_present"] = False
    artifact["fact_input_status"] = "brf2_runtime_signal_facts_missing_watcher_input"
    artifact["signal_detector_preview"] = {
        **artifact["signal_detector_preview"],
        "current_signal_state": "fact_input_missing",
        "first_blocker_class": "brf2_watcher_fact_input_missing",
        "first_blocker_owner": "engineering",
        "signal_capture_checkpoint": "attach_brf2_watcher_fact_input_producer",
    }
    return artifact


def _assert_checks_do_not_mirror_execution_authority(artifact: dict) -> None:
    for key in (
        "actionable_now",
        "real_order_authority",
        "action_time_required_facts_satisfied",
        "calls_finalgate",
        "calls_operation_layer",
        "calls_exchange_write",
        "places_order",
    ):
        assert key not in artifact["checks"]


def _assert_safety_keeps_shadow_boundary_without_execution_intent(artifact: dict) -> None:
    assert artifact["safety_invariants"]["authorization_evidence_created"] is False
    assert artifact["safety_invariants"]["execution_attempt_created"] is False
    assert "execution_intent_created" not in artifact["safety_invariants"]


def test_brf2_shadow_candidate_evidence_waits_without_fresh_signal():
    module = _load_module()

    artifact = module.build_brf2_shadow_candidate_evidence(
        runtime_signal_capture=_capture(fresh_signal_present=False),
        generated_at_utc="2026-06-23T00:00:00+00:00",
    )

    assert artifact["schema"] == module.SCHEMA
    assert artifact["status"] == module.WAITING_STATUS
    assert artifact["shadow_candidate_evidence_ready"] is False
    assert artifact["shadow_candidate_evidence"]["shadow_candidate_evidence_id"] == ""
    assert (
        artifact["shadow_candidate_evidence"]["source_signal_observation_id"]
        == "brf2-signal-001"
    )
    assert artifact["shadow_candidate_evidence"]["symbol"] == "ADA/USDT:USDT"
    assert artifact["first_blocker"]["class"] == "fresh_brf2_short_signal_absent"
    assert artifact["first_blocker"]["owner"] == "market"
    _assert_checks_do_not_mirror_execution_authority(artifact)
    assert "runtime_signal_capture_ready" not in artifact["checks"]
    assert "fresh_signal_present" not in artifact["checks"]
    assert "shadow_candidate_evidence_created" not in artifact["safety_invariants"]
    assert "actionable_now" not in artifact["safety_invariants"]
    assert "real_order_authority" not in artifact["safety_invariants"]
    _assert_safety_keeps_shadow_boundary_without_execution_intent(artifact)
    assert artifact["safety_invariants"]["calls_finalgate"] is False
    assert artifact["safety_invariants"]["calls_operation_layer"] is False
    assert artifact["safety_invariants"]["calls_exchange_write"] is False
    assert artifact["safety_invariants"]["places_order"] is False
    assert artifact["interaction"]["calls_finalgate"] is False
    assert artifact["interaction"]["calls_operation_layer"] is False
    assert artifact["interaction"]["calls_exchange_write"] is False
    assert artifact["interaction"]["places_order"] is False


def test_brf2_shadow_candidate_evidence_mirrors_missing_fact_input_blocker():
    module = _load_module()

    artifact = module.build_brf2_shadow_candidate_evidence(
        runtime_signal_capture=_missing_fact_input_capture(),
        generated_at_utc="2026-06-23T00:00:00+00:00",
    )

    assert artifact["status"] == module.WAITING_STATUS
    assert artifact["shadow_candidate_evidence_ready"] is False
    assert artifact["shadow_candidate_evidence"]["signal_state"] == "fact_input_missing"
    assert artifact["first_blocker"]["class"] == "brf2_watcher_fact_input_missing"
    assert artifact["first_blocker"]["owner"] == "engineering"
    assert "next_action" not in artifact["first_blocker"]
    assert artifact["first_blocker"]["repair_checkpoint"] == (
        "attach_brf2_watcher_fact_input_producer"
    )
    _assert_checks_do_not_mirror_execution_authority(artifact)
    assert "actionable_now" not in artifact["safety_invariants"]
    assert "real_order_authority" not in artifact["safety_invariants"]
    _assert_safety_keeps_shadow_boundary_without_execution_intent(artifact)


def test_brf2_shadow_candidate_evidence_ready_from_fresh_signal_without_authority():
    module = _load_module()

    artifact = module.build_brf2_shadow_candidate_evidence(
        runtime_signal_capture=_capture(fresh_signal_present=True),
        generated_at_utc="2026-06-23T00:00:00+00:00",
    )

    candidate = artifact["shadow_candidate_evidence"]
    assert artifact["status"] == module.READY_STATUS
    assert artifact["shadow_candidate_evidence_ready"] is True
    assert candidate["shadow_candidate_evidence_id"] == (
        "brf2-shadow-evidence:brf2-signal-001"
    )
    assert candidate["symbol"] == "ADA/USDT:USDT"
    assert candidate["source_strategy_group_id"] == "BRF-001"
    assert candidate["source_candidate_id"] == "BRF-001-BTC-SHORT"
    assert candidate["source_signal_type"] == "would_enter"
    assert candidate["side"] == "short"
    assert candidate["fact_authority"] == "readonly_proxy_not_action_time_required_fact"
    assert candidate["fact_authority_boundary"][
        "action_time_required_facts_satisfied"
    ] is False
    assert artifact["first_blocker"]["class"] == (
        "candidate_authorization_evidence_not_created"
    )
    assert artifact["next_runtime_step"] == "prepare_fresh_candidate_authorization_evidence"
    assert "required_next_chain" not in candidate
    assert "forbidden_until_action_time" not in candidate
    assert "shadow_candidate_evidence_ready" not in artifact["checks"]
    assert artifact["shadow_candidate_evidence_ready"] is True
    _assert_checks_do_not_mirror_execution_authority(artifact)
    assert "actionable_now" not in artifact["safety_invariants"]
    assert "real_order_authority" not in artifact["safety_invariants"]
    _assert_safety_keeps_shadow_boundary_without_execution_intent(artifact)
    assert "runtime_signal_capture_ready" not in artifact["checks"]
    assert "fresh_signal_present" not in artifact["checks"]
    assert artifact["safety_invariants"]["calls_finalgate"] is False
    assert artifact["safety_invariants"]["calls_operation_layer"] is False
    assert artifact["safety_invariants"]["calls_exchange_write"] is False
    assert artifact["safety_invariants"]["places_order"] is False


def test_brf2_shadow_candidate_evidence_cli_writes_artifacts(tmp_path: Path):
    module = _load_module()
    capture_json = tmp_path / "capture.json"
    output_json = tmp_path / "candidate.json"
    output_md = tmp_path / "candidate.md"
    capture_json.write_text(
        json.dumps(_capture(fresh_signal_present=True)),
        encoding="utf-8",
    )

    exit_code = module.main(
        [
            "--runtime-signal-capture-json",
            str(capture_json),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
        ]
    )

    assert exit_code == 0
    artifact = json.loads(output_json.read_text(encoding="utf-8"))
    assert artifact["status"] == module.READY_STATUS
    assert artifact["shadow_candidate_evidence_ready"] is True
    _assert_safety_keeps_shadow_boundary_without_execution_intent(artifact)
    assert "BRF2 Shadow Candidate Evidence" in output_md.read_text(
        encoding="utf-8"
    )
