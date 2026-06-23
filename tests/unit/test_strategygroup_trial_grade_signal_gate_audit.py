from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = (
    REPO_ROOT / "scripts" / "build_strategygroup_trial_grade_signal_gate_audit.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_strategygroup_trial_grade_signal_gate_audit",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _brf_replay_corpus() -> dict:
    return {
        "replay_samples": [
            {
                "event_id": "brf2-ok",
                "fixture_case": "bear_rally_failure_short_would_enter",
                "signal_status": "would_enter_observe_only",
                "required_facts_ready": True,
                "blocker_class": "review_only_warning",
                "review_recommendation": "keep_observing",
            },
            {
                "event_id": "brf2-squeeze",
                "fixture_case": "short_squeeze_risk_revision_needed",
                "signal_status": "would_enter_squeeze_risk_revision_needed",
                "required_facts_ready": True,
                "blocker_class": "review_only_warning",
                "review_recommendation": "revise",
            },
        ]
    }


def _mpg_replay_corpus() -> dict:
    return {
        "replay_samples": [
            {
                "event_id": "mpg-ok",
                "fixture_case": "trend_continuation",
                "signal_status": "fresh_signal_replay",
                "required_facts_ready": True,
                "blocker_class": "none",
                "review_recommendation": "keep_observing",
            },
            {
                "event_id": "mpg-false",
                "fixture_case": "false_breakout",
                "signal_status": "fresh_signal_replay_false_breakout",
                "required_facts_ready": True,
                "blocker_class": "review_only_warning",
                "review_recommendation": "revise",
            },
        ]
    }


def _live_preview() -> dict:
    return {
        "status": "preview_built",
        "would_enter_signals": [
            {
                "candidate_id": "BRF-001-BTC-SHORT",
                "strategy_group_id": "BRF-001",
                "strategy_family_version_id": "BRF-001-v0",
                "signal_type": "would_enter",
                "symbol": "BTC/USDT:USDT",
                "side": "short",
                "market_bar_timestamp_ms": 1782097200000,
                "reason_codes": [
                    "brf_bear_rally_extended",
                    "brf_rally_high_rejected",
                    "brf_short_squeeze_risk_reviewed",
                ],
                "not_execution_intent": True,
            }
        ],
        "no_action_signals": [
            {
                "candidate_id": "SOR-001-XAG-NO-ACTION",
                "strategy_group_id": "SOR-001",
                "signal_type": "no_action",
                "symbol": "XAG/USDT:USDT",
                "side": "none",
                "market_bar_timestamp_ms": 1782097200000,
            }
        ],
        "invalid_signals": [],
        "preview": {"current_signals": [], "signal_history": [], "candidates": []},
    }


def _brf2_policy() -> dict:
    return {
        "policy": {
            "capital_scope": {
                "amount": "30",
                "currency": "USDT",
                "type": "isolated_subaccount_full_allocation",
            },
            "loss_unit": {"amount": "10", "currency": "USDT"},
            "attempt_cap": 3,
            "max_consecutive_losses": 2,
            "pause_conditions": ["two_consecutive_losses"],
        }
    }


def _brf2_capture() -> dict:
    return {
        "signal_detector_preview": {
            "missing_required_fact_keys": [
                "rally_context",
                "rally_failure_trigger_state",
            ]
        }
    }


def _sor_replay_corpus() -> dict:
    return {
        "replay_samples": [
            {
                "event_id": "sor-ok",
                "fixture_case": "session_range_breakdown_trial_would_enter",
                "signal_status": "would_enter_trial_grade_review",
                "required_facts_ready": True,
                "blocker_class": "review_only_warning",
                "review_recommendation": "keep_observing",
            },
            {
                "event_id": "sor-false",
                "fixture_case": "session_false_breakout_decay_review_needed",
                "signal_status": "would_enter_decay_risk_revision_needed",
                "required_facts_ready": True,
                "blocker_class": "review_only_warning",
                "review_recommendation": "revise",
            },
        ]
    }


def test_trial_grade_signal_catalog_and_brf2_proxy_boundary() -> None:
    module = _load_module()

    packet = module.build_trial_grade_signal_gate_audit(
        mpg_replay_corpus=_mpg_replay_corpus(),
        brf_replay_corpus=_brf_replay_corpus(),
        sor_handoff={"risk_defaults": {"requires_sl": True}},
        live_preview=_live_preview(),
        local_preview={},
        brf2_policy=_brf2_policy(),
        brf2_capture=_brf2_capture(),
        three_strategy_portfolio={},
        generated_at_utc="2026-06-23T00:00:00+00:00",
    )

    assert packet["schema"] == "brc.strategygroup_trial_grade_signal_gate_audit.v1"
    assert set(packet["signal_grade_catalog"]) == {
        "observe_only_signal",
        "trial_grade_signal",
        "production_grade_signal",
        "invalid_signal",
    }
    assert packet["summary"]["trial_grade_observation_count_30d"] == 1
    assert packet["summary"]["action_time_trial_submit_count_30d"] == 0
    assert packet["summary"]["hard_safety_gates_relaxed"] is False
    assert packet["checks"]["hard_safety_gates_not_relaxed"] is True
    assert packet["checks"]["actionable_now"] is False
    assert packet["checks"]["real_order_authority"] is False

    brf2 = packet["strategy_group_rows"]["BRF2-001"]
    counts_30d = brf2["verified_recent_window_counts"]["windows_days"]["30"]
    assert counts_30d["trial_grade_observation_count"] == 1
    assert counts_30d["action_time_trial_submit_count"] == 0
    assert counts_30d["evidence_level"] == (
        "timestamped_proxy_or_preview_observation_not_action_time_submit"
    )
    assert brf2["fixture_replay_projection"]["trial_grade_trigger_case_count"] == 1
    assert brf2["fixture_replay_projection"]["would_trigger_cases"] == [
        "bear_rally_failure_short_would_enter"
    ]
    assert brf2["risk_envelope"]["path_risk_treatment"] == (
        "known_path_risk_enters_envelope_not_trade_denial"
    )
    assert brf2["risk_envelope"]["attempt_cap"] == 3
    assert brf2["risk_envelope"]["loss_unit"]["amount"] == "10"
    assert brf2["tomorrow_same_structure_assessment"]["would_enter_30u_trial"] is True
    assert brf2["authority_boundary"]["trial_grade_signal_can_bypass_hard_safety_gates"] is False


def test_sor_trial_grade_audit_exposes_missing_replay_source() -> None:
    module = _load_module()

    packet = module.build_trial_grade_signal_gate_audit(
        mpg_replay_corpus=_mpg_replay_corpus(),
        brf_replay_corpus=_brf_replay_corpus(),
        sor_handoff={"risk_defaults": {"requires_sl": True}},
        live_preview=_live_preview(),
        local_preview={},
        brf2_policy=_brf2_policy(),
        brf2_capture=_brf2_capture(),
        three_strategy_portfolio={},
        generated_at_utc="2026-06-23T00:00:00+00:00",
    )

    sor = packet["strategy_group_rows"]["SOR-001"]
    assert sor["fixture_replay_projection"]["source"] == (
        "missing_strategy_specific_replay_source"
    )
    assert sor["tomorrow_same_structure_assessment"]["would_enter_30u_trial"] is False
    assert sor["false_positive_review_pack"][0]["case"] == "sor_replay_source_missing"
    assert any(
        row["recommendation"] == "needs_replay_source"
        for row in sor["trial_grade_trigger_diff"]
    )


def test_sor_replay_source_calibrates_trial_grade_without_live_authority() -> None:
    module = _load_module()

    packet = module.build_trial_grade_signal_gate_audit(
        mpg_replay_corpus=_mpg_replay_corpus(),
        brf_replay_corpus=_brf_replay_corpus(),
        sor_handoff={"risk_defaults": {"requires_sl": True}},
        sor_replay_corpus=_sor_replay_corpus(),
        live_preview=_live_preview(),
        local_preview={},
        brf2_policy=_brf2_policy(),
        brf2_capture=_brf2_capture(),
        three_strategy_portfolio={},
        generated_at_utc="2026-06-23T00:00:00+00:00",
    )

    sor = packet["strategy_group_rows"]["SOR-001"]
    assert sor["fixture_replay_projection"]["trial_grade_trigger_case_count"] == 1
    assert sor["fixture_replay_projection"]["would_trigger_cases"] == [
        "session_range_breakdown_trial_would_enter"
    ]
    assert sor["tomorrow_same_structure_assessment"]["would_enter_30u_trial"] is True
    assert sor["verified_recent_window_counts"]["windows_days"]["30"][
        "trial_grade_observation_count"
    ] == 0
    assert any(
        item["case"] == "session_false_breakout_decay_review_needed"
        for item in sor["false_positive_review_pack"]
    )
    assert packet["checks"]["calls_finalgate"] is False
    assert packet["checks"]["calls_operation_layer"] is False
    assert packet["checks"]["calls_exchange_write"] is False


def test_trial_grade_signal_gate_audit_cli_writes_json_and_markdown(tmp_path: Path) -> None:
    output_json = tmp_path / "trial-grade-audit.json"
    output_md = tmp_path / "trial-grade-audit.md"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
        ],
        cwd=REPO_ROOT,
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    packet = json.loads(output_json.read_text(encoding="utf-8"))
    markdown = output_md.read_text(encoding="utf-8")
    assert packet["status"] == "trial_grade_signal_gate_audit_ready"
    assert packet["checks"]["calls_finalgate"] is False
    assert packet["checks"]["calls_operation_layer"] is False
    assert packet["checks"]["calls_exchange_write"] is False
    assert packet["checks"]["places_order"] is False
    assert "Trial-Grade Signal Gate Audit" in markdown
