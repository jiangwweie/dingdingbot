from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "run_strategygroup_signal_coverage_diagnostic.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "run_strategygroup_signal_coverage_diagnostic",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _runtime_summary(*, ready: bool = False, forbidden: bool = False) -> dict:
    return {
        "status": "waiting_for_signal",
        "order_created": forbidden,
        "exchange_write_called": False,
        "runtime_signal_summaries": [
            {
                "runtime_instance_id": "runtime-mpg",
                "strategy_family_id": "MPG-001",
                "strategy_family_version_id": "MPG-001-v0",
                "symbol": "MSTR/USDT:USDT",
                "side": "long",
                "status": "waiting_for_signal",
                "signal_summary": {
                    "signal_type": "would_enter" if ready else "no_action",
                    "confidence": "0.81" if ready else "0.25",
                    "reason_codes": (
                        ["mpg_momentum_confirmed"]
                        if ready
                        else ["mpg_no_action_momentum_persistence_not_confirmed"]
                    ),
                    "human_summary": "MPG summary",
                },
            },
            {
                "runtime_instance_id": "runtime-sor",
                "strategy_family_id": "SOR-001",
                "strategy_family_version_id": "SOR-001-v0",
                "symbol": "XAG/USDT:USDT",
                "side": "short",
                "status": "waiting_for_signal",
                "signal_type": "no_action",
                "confidence": "0.25",
                "reason_codes": ["sor_no_action_session_breakout_not_confirmed"],
                "human_summary": "SOR summary",
            },
        ],
    }


def _preview(*, would_enter: bool = True, forbidden: bool = False) -> dict:
    would_enter_rows = [
        {
            "candidate_id": "BTPC-001-AVAX-SHORT",
            "strategy_group_id": "BTPC-001",
            "strategy_family_version_id": "BTPC-001-v0",
            "symbol": "AVAX/USDT:USDT",
            "side": "short",
            "signal_type": "would_enter",
            "confidence": "0.62",
            "reason_codes": ["btpc_structure_loss_confirmed"],
            "human_summary": "BTPC would enter",
            "not_order": True,
            "not_execution_intent": True,
            "no_execution_permission": True,
            "no_order_permission": True,
            "no_runtime_start": True,
        }
    ] if would_enter else []
    no_action_rows = [
        {
            "candidate_id": "BRF-001-BTC",
            "strategy_group_id": "BRF-001",
            "strategy_family_version_id": "BRF-001-v0",
            "symbol": "BTC/USDT:USDT",
            "side": "long",
            "signal_type": "no_action",
            "confidence": "0.20",
            "reason_codes": ["brf_no_action_no_rejection_close"],
            "human_summary": "BRF no action",
            "not_order": True,
            "not_execution_intent": True,
            "no_execution_permission": True,
            "no_order_permission": True,
            "no_runtime_start": True,
        }
    ]
    return {
        "status": "preview_built",
        "market_source": "sample_strategy_group_market_bar_source_v1",
        "checks": {
            "candidate_count": 2,
            "current_signal_count": len(would_enter_rows) + len(no_action_rows),
            "would_enter_signal_count": len(would_enter_rows),
            "no_action_signal_count": len(no_action_rows),
            "invalid_signal_count": 0,
            "forbidden_effects": [],
        },
        "would_enter_signals": would_enter_rows,
        "no_action_signals": no_action_rows,
        "invalid_signals": [],
        "interaction": {
            "preview_only": True,
            "not_execution_authority": True,
            "places_order": forbidden,
            "calls_order_lifecycle": False,
            "withdrawal_or_transfer_requested": False,
        },
        "safety_invariants": {
            "database_connected": False,
            "pg_observation_written": False,
            "runtime_resolver_called": False,
            "shadow_candidate_created": False,
            "execution_intent_created": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "exchange_write_called": False,
            "runtime_started": False,
            "attempt_counter_mutated": False,
            "runtime_budget_mutated": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def _expansion_policy() -> dict:
    return {
        "strategy_groups": {
            "BTPC-001": {
                "coverage_review_priority": "P0_5",
                "l2_readiness": "l2_shadow_candidate_observation_enabled",
                "recommended_action": "continue_l2_shadow_candidate_observation_without_l4_scope_change",
            },
            "BRF-001": {
                "coverage_review_priority": "P0_5",
                "l2_readiness": "blocked_requiredfacts_and_squeeze_classifier_needed",
                "recommended_action": "keep_l1_observe_only_until_rally_failure_context_and_short_squeeze_classifier_are_attached",
            },
            "LSR-001": {
                "coverage_review_priority": "P1",
                "l2_readiness": "blocked_rewrite_required",
                "recommended_action": "keep_l1_observe_only_until_side_specific_rewrite_handoff_exists",
            },
            "VCB-001": {
                "coverage_review_priority": "P1",
                "l2_readiness": "blocked_classifier_redesign_required",
                "recommended_action": "keep_l1_observe_only_until_false_breakout_disable",
            },
            "RBR-001": {
                "coverage_review_priority": "P2",
                "l2_readiness": "blocked_parked_negative_evidence",
                "recommended_action": "keep_l1_or_park_as_range_vocabulary_until_materially_new_classifier_exists",
            },
        }
    }


def test_diagnostic_surfaces_broader_would_enter_without_execution_authority():
    module = _load_module()

    artifact = module.build_signal_coverage_diagnostic_artifact(
        runtime_summary_artifact=_runtime_summary(),
        broader_preview_artifact=_preview(would_enter=True),
        source_name="sample",
        expansion_policy=_expansion_policy(),
    )

    assert artifact["status"] == "mainline_no_signal_broader_would_enter"
    assert artifact["owner_state"] == "coverage_review_needed"
    assert artifact["checks"]["runtime_ready_signal_count"] == 0
    assert artifact["checks"]["broader_would_enter_signal_count"] == 1
    assert artifact["checks"]["broader_actionable_would_enter_signal_count"] == 1
    assert artifact["checks"]["broader_low_priority_would_enter_signal_count"] == 0
    assert artifact["checks"]["broader_high_priority_no_action_signal_count"] == 1
    assert artifact["checks"]["coverage_gap"] is True
    assert artifact["interaction"]["level"] == "L0_local_signal_coverage"
    assert artifact["interaction"]["remote_interaction_count"] == 0
    assert artifact["interaction"]["mutates_remote_files"] is False
    assert artifact["interaction"]["approaches_real_order"] is False
    assert artifact["diagnosis"]["broader_signals_are_observe_only"] is True
    assert artifact["diagnosis"]["does_not_authorize_real_order"] is True
    assert artifact["interaction"]["places_order"] is False
    assert artifact["interaction"]["calls_finalgate"] is False
    assert artifact["interaction"]["calls_operation_layer"] is False
    assert "operator_command_plan" not in artifact
    assert artifact["safety_invariants"]["exchange_write_called"] is False
    assert "execution_intent_created" not in artifact["safety_invariants"]
    assert artifact["safety_invariants"][
        "broader_signals_are_not_execution_authority"
    ] is True


def test_diagnostic_enriches_high_priority_no_action_rows_for_review():
    module = _load_module()

    artifact = module.build_signal_coverage_diagnostic_artifact(
        runtime_summary_artifact=_runtime_summary(),
        broader_preview_artifact=_preview(would_enter=False),
        source_name="sample",
        expansion_policy=_expansion_policy(),
    )

    assert artifact["status"] == "mainline_and_broader_no_signal"
    assert artifact["checks"]["broader_high_priority_no_action_signal_count"] == 1
    assert artifact["diagnosis"]["broader_high_priority_no_action_review_available"] is True
    rows = artifact["broader_observation"]["high_priority_no_action_signals"]
    assert [row["strategy_group_id"] for row in rows] == ["BRF-001"]
    assert rows[0]["coverage_review_priority"] == "P0_5"
    assert rows[0]["policy_l2_readiness"] == (
        "blocked_requiredfacts_and_squeeze_classifier_needed"
    )
    assert rows[0]["reason_codes"] == ["brf_no_action_no_rejection_close"]
    assert rows[0]["not_order"] is True


def test_diagnostic_records_low_priority_broader_would_enter_without_coverage_gap():
    module = _load_module()
    preview = _preview(would_enter=True)
    preview["would_enter_signals"] = [
        {
            "candidate_id": "RBR-001-ADA-SHORT",
            "strategy_group_id": "RBR-001",
            "strategy_family_version_id": "RBR-001-v0",
            "symbol": "ADA/USDT:USDT",
            "side": "short",
            "signal_type": "would_enter",
            "confidence": "0.55",
            "reason_codes": ["rbr_range_boundary_reversion"],
            "human_summary": "RBR would enter",
            "not_order": True,
            "not_execution_intent": True,
            "no_execution_permission": True,
            "no_order_permission": True,
            "no_runtime_start": True,
        }
    ]

    artifact = module.build_signal_coverage_diagnostic_artifact(
        runtime_summary_artifact=_runtime_summary(),
        broader_preview_artifact=preview,
        source_name="sample",
        expansion_policy=_expansion_policy(),
    )

    assert artifact["status"] == "mainline_no_signal_low_priority_broader_would_enter"
    assert artifact["owner_state"] == "waiting_for_opportunity"
    assert artifact["checks"]["broader_would_enter_signal_count"] == 1
    assert artifact["checks"]["broader_actionable_would_enter_signal_count"] == 0
    assert artifact["checks"]["broader_low_priority_would_enter_signal_count"] == 1
    assert artifact["checks"]["coverage_gap"] is False
    assert artifact["diagnosis"]["broader_observation_has_would_enter"] is True
    assert (
        artifact["diagnosis"]["broader_observation_has_actionable_would_enter"] is False
    )
    row = artifact["broader_observation"]["would_enter_signals"][0]
    assert row["coverage_review_priority"] == "P2"
    assert row["policy_l2_readiness"] == "blocked_parked_negative_evidence"
    assert row["not_order"] is True


def test_diagnostic_reports_waiting_when_mainline_and_broader_have_no_signal():
    module = _load_module()

    artifact = module.build_signal_coverage_diagnostic_artifact(
        runtime_summary_artifact=_runtime_summary(),
        broader_preview_artifact=_preview(would_enter=False),
        source_name="sample",
    )

    assert artifact["status"] == "mainline_and_broader_no_signal"
    assert artifact["owner_state"] == "waiting_for_opportunity"
    assert artifact["checks"]["coverage_gap"] is False
    assert artifact["diagnosis"]["mainline_runtime_is_waiting"] is True
    assert artifact["diagnosis"]["broader_observation_has_would_enter"] is False


def test_diagnostic_defers_to_mainline_ready_signal():
    module = _load_module()

    artifact = module.build_signal_coverage_diagnostic_artifact(
        runtime_summary_artifact=_runtime_summary(ready=True),
        broader_preview_artifact=_preview(would_enter=True),
        source_name="sample",
    )

    assert artifact["status"] == "mainline_runtime_signal_ready"
    assert artifact["owner_state"] == "processing"
    assert artifact["checks"]["runtime_ready_signal_count"] == 1
    assert artifact["diagnosis"]["next_step"] == (
        "pause_lower_priority_work_and_continue_official_runtime_chain"
    )


def test_diagnostic_blocks_forbidden_source_effects():
    module = _load_module()

    artifact = module.build_signal_coverage_diagnostic_artifact(
        runtime_summary_artifact=_runtime_summary(forbidden=True),
        broader_preview_artifact=_preview(would_enter=True, forbidden=True),
        source_name="sample",
    )

    assert artifact["status"] == "blocked_forbidden_effect"
    assert artifact["interaction"]["places_order"] is False
    assert artifact["safety_invariants"]["order_created"] is False
    assert "runtime.order_created" in artifact["checks"]["forbidden_effects"]
    assert "preview.interaction.places_order" in artifact["checks"][
        "forbidden_effects"
    ]


def test_cli_writes_artifact_and_owner_progress(tmp_path, capsys):
    module = _load_module()
    runtime_path = tmp_path / "runtime.json"
    preview_path = tmp_path / "preview.json"
    output_path = tmp_path / "diagnostic.json"
    owner_path = tmp_path / "owner.md"
    runtime_path.write_text(json.dumps(_runtime_summary()), encoding="utf-8")
    preview_path.write_text(json.dumps(_preview(would_enter=True)), encoding="utf-8")

    exit_code = module.main(
        [
            "--runtime-summary-json",
            str(runtime_path),
            "--broader-preview-json",
            str(preview_path),
            "--source",
            "sample",
            "--output-json",
            str(output_path),
            "--output-owner-progress",
            str(owner_path),
        ]
    )

    assert exit_code == 0
    stdout_payload = json.loads(capsys.readouterr().out)
    file_payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert stdout_payload == file_payload
    assert file_payload["scope"] == "strategygroup_signal_coverage_diagnostic"
    owner_text = owner_path.read_text(encoding="utf-8")
    assert "策略机会覆盖诊断" in owner_text
    assert "宽观察 Would-Enter 信号" in owner_text
    assert "当前判断" in owner_text


def test_cli_treats_missing_runtime_summary_as_non_executing_no_signal(
    tmp_path, capsys
):
    module = _load_module()
    runtime_path = tmp_path / "missing-runtime.json"
    preview_path = tmp_path / "preview.json"
    output_path = tmp_path / "diagnostic.json"
    owner_path = tmp_path / "owner.md"
    preview_path.write_text(json.dumps(_preview(would_enter=False)), encoding="utf-8")

    exit_code = module.main(
        [
            "--runtime-summary-json",
            str(runtime_path),
            "--broader-preview-json",
            str(preview_path),
            "--source",
            "sample",
            "--output-json",
            str(output_path),
            "--output-owner-progress",
            str(owner_path),
        ]
    )

    assert exit_code == 0
    artifact = json.loads(capsys.readouterr().out)
    assert artifact["source"]["runtime_summary_status"] == "runtime_summary_missing"
    assert artifact["checks"]["runtime_ready_signal_count"] == 0
    assert artifact["diagnosis"]["mainline_runtime_is_waiting"] is True
    assert artifact["interaction"]["places_order"] is False
    assert artifact["interaction"]["calls_finalgate"] is False
    assert artifact["interaction"]["calls_operation_layer"] is False
    assert "operator_command_plan" not in artifact
    assert artifact["safety_invariants"]["exchange_write_called"] is False
    assert "execution_intent_created" not in artifact["safety_invariants"]
