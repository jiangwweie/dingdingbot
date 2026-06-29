from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_strategygroup_owner_policy_package.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_strategygroup_owner_policy_package",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_owner_policy_package_default_output_paths_use_policy_identity():
    module = _load_module()

    assert module.DEFAULT_OUTPUT_JSON.name == "latest-strategygroup-owner-policy-package.json"
    assert module.DEFAULT_OUTPUT_MD.name == "latest-strategygroup-owner-policy-package.md"
    assert "owner-decision-package" not in module.DEFAULT_OUTPUT_JSON.name
    assert "owner-decision-package" not in module.DEFAULT_OUTPUT_MD.name


def _capture_gap_audit() -> dict:
    rows = [
        {
            "strategy_group_id": "BRF-001",
            "would_enter_count": 1,
            "no_action_count": 168,
            "high_priority_no_action_count": 168,
            "would_enter_forward_positive_count": 0,
            "missed_no_action_forward_positive_count": 136,
            "positive_forward_outcome_count": 136,
            "latest_event_time_utc": "2026-06-22T03:00:00+00:00",
        },
        {
            "strategy_group_id": "BTPC-001",
            "would_enter_count": 0,
            "no_action_count": 169,
            "high_priority_no_action_count": 169,
            "would_enter_forward_positive_count": 0,
            "missed_no_action_forward_positive_count": 152,
            "positive_forward_outcome_count": 152,
            "latest_event_time_utc": "2026-06-22T03:00:00+00:00",
        },
        {
            "strategy_group_id": "LSR-001",
            "would_enter_count": 2,
            "no_action_count": 167,
            "high_priority_no_action_count": 167,
            "would_enter_forward_positive_count": 2,
            "missed_no_action_forward_positive_count": 0,
            "positive_forward_outcome_count": 2,
            "latest_event_time_utc": "2026-06-22T03:00:00+00:00",
        },
        {
            "strategy_group_id": "MI-001",
            "would_enter_count": 23,
            "no_action_count": 315,
            "high_priority_no_action_count": 0,
            "would_enter_forward_positive_count": 22,
            "missed_no_action_forward_positive_count": 0,
            "positive_forward_outcome_count": 22,
            "latest_event_time_utc": "2026-06-22T03:00:00+00:00",
        },
        {
            "strategy_group_id": "CPM-RO-001",
            "would_enter_count": 18,
            "no_action_count": 151,
            "high_priority_no_action_count": 0,
            "would_enter_forward_positive_count": 13,
            "missed_no_action_forward_positive_count": 0,
            "positive_forward_outcome_count": 13,
            "latest_event_time_utc": "2026-06-22T03:00:00+00:00",
        },
        {"strategy_group_id": "MPG-001", "would_enter_count": 0},
        {
            "strategy_group_id": "RBR-001",
            "would_enter_count": 6,
            "would_enter_forward_positive_count": 6,
        },
        {
            "strategy_group_id": "VCB-001",
            "would_enter_count": 2,
            "would_enter_forward_positive_count": 2,
            "missed_no_action_forward_positive_count": 135,
        },
    ]
    return {
        "status": "strategy_capture_gap_audit_ready",
        "owner_visibility_state": {
            "p0_state": "waiting_for_market",
            "signal_observation_state": "review_needed",
            "observation_active": True,
        },
        "strategy_expectation_rows": rows,
    }


def _quality_closure_wave() -> dict:
    return {
        "status": "quality_closure_wave_ready",
        "wave_1_strategy_explainer": {
            "policy_items": [
                {
                    "strategy_group_id": group,
                    "why_not_live": "review-only artifact; no live authority",
                }
                for group in (
                    "BRF-001",
                    "BTPC-001",
                    "LSR-001",
                    "MI-001",
                    "CPM-RO-001",
                    "MPG-001",
                )
            ]
        },
        "wave_3_mpg_member_deepening": {
            "status": "ready_for_owner_review",
            "member_rows": [
                {
                    "member_id": "TSI-001",
                    "provisional_role": "core_member_candidate",
                    "review_focus": "right_tail_return_vs_drawdown_decay",
                    "recommended_action": "keep_core_candidate_but_require_decay_control",
                },
                {
                    "member_id": "MHI-001",
                    "provisional_role": "high_risk_member",
                    "review_focus": "high_return_high_drawdown_survivability",
                    "recommended_action": "downshift_or_park_review_before_live_expansion",
                },
                {
                    "member_id": "PPO-001",
                    "provisional_role": "support_member",
                    "review_focus": "middle_return_middle_drawdown_stability",
                    "recommended_action": "keep_observing_as_support_member",
                },
                {
                    "member_id": "DMI-001",
                    "provisional_role": "ignition_support_or_independent_observer",
                    "review_focus": "member_vs_independent_strategy_boundary",
                    "recommended_action": "identity_boundary_review",
                },
                {
                    "member_id": "WPR-001",
                    "provisional_role": "confirmation_member",
                    "review_focus": "conservative_momentum_confirmation_value",
                    "recommended_action": "keep_as_confirmation_candidate",
                },
                {
                    "member_id": "MFI-001",
                    "provisional_role": "risk_damper_or_scorer",
                    "review_focus": "low_drawdown_low_return_filter_value",
                    "recommended_action": "keep_as_scorer_not_primary_member",
                },
            ],
            "exit_decay_review": {
                "status": "needed_before_any_live_scope_expansion",
                "exit_horizons_to_review": ["6h", "12h", "24h", "72h"],
                "decay_controls_to_review": ["momentum_exhaustion_disable"],
            },
            "done_when": {"no_live_scope_expansion": True},
        },
    }


def _strategy_asset_state_source() -> dict:
    return _with_strategy_asset_state({
        "status": "strategy_asset_state_ready",
        "source_rows": [
            {
                "strategy_group_id": "BRF-001",
                "decision": "promote",
                "next_checkpoint": "BRF-001_forward_outcome_and_requiredfacts_review",
            },
            {
                "strategy_group_id": "BTPC-001",
                "decision": "revise",
                "next_checkpoint": "BTPC-001_classifier_fact_source_revision_review",
            },
            {
                "strategy_group_id": "LSR-001",
                "decision": "revise",
                "next_checkpoint": "LSR-001_classifier_fact_source_revision_review",
            },
            {
                "strategy_group_id": "MI-001",
                "decision": "revise",
                "next_checkpoint": "MI-001_registry_identity_review",
            },
            {
                "strategy_group_id": "CPM-RO-001",
                "decision": "revise",
                "next_checkpoint": "CPM-RO-001_registry_identity_review",
            },
            {
                "strategy_group_id": "MPG-001",
                "decision": "keep_observing",
                "next_checkpoint": "MPG-001_member_tiering_exit_decay_review",
            },
            {
                "strategy_group_id": "RBR-001",
                "decision": "park",
                "next_checkpoint": "park_until_material_new_edge_evidence",
            },
            {
                "strategy_group_id": "VCB-001",
                "decision": "keep_observing",
                "next_checkpoint": "VCB-001_true_false_breakout_classifier_review",
            },
        ],
    })


def _with_strategy_asset_state(strategy_asset_state_source: dict) -> dict:
    strategy_asset_state_source["strategy_asset_state"] = {
        "status": "strategy_asset_state_ready",
        "asset_rows": [
            {
                "strategy_group_id": row["strategy_group_id"],
                "current_tier": row.get("tier", "unknown"),
                "current_decision": row["decision"],
                "promotion_target": row.get("required_next_evidence", "not_applicable"),
                "required_next_evidence": row.get("required_next_evidence", ""),
                "next_checkpoint": row.get("next_checkpoint", ""),
            }
            for row in strategy_asset_state_source["source_rows"]
        ],
    }
    return strategy_asset_state_source


def _strategy_asset_state_source_with_conflicting_strategy_asset_state() -> dict:
    strategy_asset_state_source = _strategy_asset_state_source()
    for row in strategy_asset_state_source["strategy_asset_state"]["asset_rows"]:
        if row["strategy_group_id"] == "BTPC-001":
            row["current_decision"] = "park"
            row["next_checkpoint"] = "strategy_asset_state_checkpoint"
    return strategy_asset_state_source


def _strategy_asset_state_source_with_missing_strategy_asset_decision() -> dict:
    strategy_asset_state_source = _strategy_asset_state_source()
    for row in strategy_asset_state_source["strategy_asset_state"]["asset_rows"]:
        if row["strategy_group_id"] == "BTPC-001":
            row.pop("current_decision", None)
            row["next_checkpoint"] = "missing_decision_checkpoint"
    return strategy_asset_state_source


def _strategy_asset_state_source_with_missing_mpg_strategy_asset_decision() -> dict:
    strategy_asset_state_source = _strategy_asset_state_source()
    for row in strategy_asset_state_source["strategy_asset_state"]["asset_rows"]:
        if row["strategy_group_id"] == "MPG-001":
            row.pop("current_decision", None)
            row["next_checkpoint"] = "missing_mpg_decision_checkpoint"
    return strategy_asset_state_source


def _registry() -> dict:
    return {
        "status": "current_pilot_baseline",
        "rows": [
            {
                "strategy_group_id": "MPG-001",
                "owner_label": "动量延续",
                "default_tier": "L4",
                "actionable_now_reason": "runtime_state_only",
            },
            {
                "strategy_group_id": "BRF-001",
                "owner_label": "熊市反弹失败",
                "default_tier": "L1",
                "actionable_now_reason": "observe_only",
            },
            {
                "strategy_group_id": "BTPC-001",
                "owner_label": "熊市回抽延续",
                "default_tier": "L2",
                "actionable_now_reason": "shadow_only",
            },
            {
                "strategy_group_id": "LSR-001",
                "owner_label": "流动性扫盘",
                "default_tier": "L1",
                "actionable_now_reason": "observe_only",
            },
            {
                "strategy_group_id": "VCB-001",
                "owner_label": "波动压缩突破",
                "default_tier": "L1",
                "actionable_now_reason": "observe_only",
            },
            {
                "strategy_group_id": "RBR-001",
                "owner_label": "区间边界回归",
                "default_tier": "L1",
                "actionable_now_reason": "parked",
            },
        ],
    }


def _tier_policy() -> dict:
    return {
        "current_strategy_groups": {
            "MPG-001": {"tier": "L4"},
            "BTPC-001": {"tier": "L2"},
        },
        "new_strategy_group_defaults": {
            "known_new_groups": {"BRF": "L1", "LSR": "L1"}
        },
    }


def _btpc_fact_quality() -> dict:
    return {
        "status": "btpc_l2_shadow_fact_quality_review_ready",
        "counts": {"fact_gap_count": 5, "fact_source_pending_count": 4},
    }


def _btpc_source_mapping() -> dict:
    return {
        "status": "btpc_live_derivatives_fact_source_mapping_ready_without_live_authority",
        "counts": {
            "live_required_fact_gap_count": 8,
            "source_attachment_pending_count": 8,
        },
    }


def _btpc_classifier_review() -> dict:
    return {
        "status": "btpc_classifier_rule_review_recorded_without_live_authority",
        "counts": {"rule_review_count": 2},
    }


def _btpc_keep_revise() -> dict:
    return {
        "status": "btpc_l2_keep_revise_fact_source_review_ready",
        "review_outcome_state": {
            "state_family": "Review Outcome State",
            "source_role": "btpc_l2_keep_revise_fact_source_provenance",
            "tradeability_decision_source": False,
            "keep_l2_shadow_observation": True,
            "revise_fact_classifier_inputs_before_promotion": True,
        },
    }


def _btpc_proxy_replay() -> dict:
    return {
        "status": "btpc_proxy_replay_quality_review_ready",
        "counts": {
            "proxy_reviewable_would_enter_count": 2,
            "freshness_or_conflict_revision_count": 2,
        },
    }


def _opportunity_review_work_loop() -> dict:
    return {"status": "review_work_loop_ready"}


def _replay_corpus(strategy_group_id: str) -> dict:
    return {
        "strategy_group_id": strategy_group_id,
        "replay_samples": [
            {
                "review_recommendation": "keep_observing",
                "signal_status": "would_enter_observe_only",
                "required_facts_ready": True,
                "real_order_allowed": False,
            },
            {
                "review_recommendation": "revise",
                "signal_status": "rewrite_or_squeeze_review_needed",
                "required_facts_ready": True,
                "real_order_allowed": False,
            },
        ],
    }


def _build_policy_package(
    module,
    *,
    capture_gap_audit: dict | None = None,
    strategy_asset_state_source: dict | None = None,
):
    return module.build_owner_policy_package(
        capture_gap_audit=capture_gap_audit or _capture_gap_audit(),
        quality_closure_wave=_quality_closure_wave(),
        strategy_asset_state_source=(
            strategy_asset_state_source or _strategy_asset_state_source()
        ),
        registry=_registry(),
        tier_policy=_tier_policy(),
        btpc_fact_quality=_btpc_fact_quality(),
        btpc_source_mapping=_btpc_source_mapping(),
        btpc_classifier_review=_btpc_classifier_review(),
        btpc_keep_revise=_btpc_keep_revise(),
        btpc_proxy_replay=_btpc_proxy_replay(),
        opportunity_review_work_loop=_opportunity_review_work_loop(),
        mpg_replay_corpus=_replay_corpus("MPG-001"),
        brf_replay_corpus=_replay_corpus("BRF-001"),
        lsr_replay_corpus=_replay_corpus("LSR-001"),
    )


def test_owner_policy_package_builds_decision_ready_policy_items():
    module = _load_module()
    policy_package = _build_policy_package(module)

    assert policy_package["status"] == "owner_policy_package_ready"
    assert policy_package["schema"] == "brc.strategygroup_owner_policy_package.v1"
    assert "owner_decision_items" not in policy_package
    assert "owner_decision_summary" not in policy_package
    assert policy_package["source_ready"] is True
    assert policy_package["source_errors"] == []
    assert policy_package["owner_policy_summary"]["owner_policy_confirmation_required"] is True
    assert policy_package["owner_policy_summary"]["runtime_owner_intervention_required"] is False
    assert policy_package["owner_policy_summary"]["owner_policy_item_count"] == 6
    assert "decision_count" not in policy_package["owner_policy_summary"]
    assert policy_package["strategy_quality_snapshot"]["status"] == "ready"
    assert policy_package["strategy_quality_snapshot"]["p0_state"] == "waiting_for_market"
    assert policy_package["strategy_quality_snapshot"]["p0_state_source"] == (
        "capture_gap_audit.owner_visibility_state.p0_state"
    )

    policy_items = {row["policy_item_id"]: row for row in policy_package["owner_policy_items"]}
    expected = {
        "BRF-001:owner_policy_choice",
        "BTPC-001:owner_policy_choice",
        "LSR-001:owner_policy_choice",
        "MI-001:owner_policy_choice",
        "CPM-RO-001:owner_policy_choice",
        "MPG-001:member_policy_decision",
    }
    assert set(policy_items) == expected
    for policy_item in policy_items.values():
        assert policy_item["owner_policy_ready"] is True
        assert policy_item["owner_policy_confirmation_required"] is True
        assert policy_item["runtime_owner_intervention_required"] is False
        assert "decision_source" not in policy_item
        assert "decision_ready" not in policy_item
        assert "decision_type" not in policy_item
        assert "owner_decision_question" not in policy_item
        assert "decision_options" not in policy_item
        assert policy_item["default_recommendation"]
        assert policy_item["owner_policy_options"]
        assert policy_item["evidence_for"]
        assert policy_item["evidence_against"]
        assert "real_order" in policy_item["not_authorized"]

    assert policy_items["BRF-001:owner_policy_choice"]["default_recommendation"] == (
        "approve_promote_review_without_live_scope_change"
    )
    assert policy_items["BTPC-001:owner_policy_choice"]["specialized_evidence"]["fact_gap_count"] == 5
    assert policy_items["MI-001:owner_policy_choice"]["default_recommendation"] == (
        "open_formal_candidate_review_and_overlap_check"
    )
    assert policy_items["CPM-RO-001:owner_policy_choice"]["default_recommendation"] == (
        "keep_as_observation_asset_and_run_merge_review"
    )
    assert len(policy_items["MPG-001:member_policy_decision"]["member_decisions"]) == 6
    assert policy_items["MPG-001:member_policy_decision"]["strategy_asset_current_decision"] == (
        "keep_observing"
    )
    assert all(
        member["live_scope_allowed_now"] is False
        for member in policy_items["MPG-001:member_policy_decision"]["member_decisions"]
    )


def test_owner_policy_package_uses_strategy_asset_state_before_injected_legacy_rows():
    module = _load_module()
    policy_package = _build_policy_package(
        module,
        strategy_asset_state_source=(
            _strategy_asset_state_source_with_conflicting_strategy_asset_state()
        ),
    )

    assert policy_package["strategy_asset_state_source"] == {
        "source": "strategy_asset_state.asset_rows",
        "row_count": 8,
        "missing_strategy_asset_current_decision_row_count": 0,
    }
    policy_items = {row["policy_item_id"]: row for row in policy_package["owner_policy_items"]}
    btpc = policy_items["BTPC-001:owner_policy_choice"]
    assert btpc["strategy_asset_current_decision"] == "park"
    assert "ledger_decision" not in btpc
    assert "decision" not in btpc
    assert btpc["next_checkpoint"] == "strategy_asset_state_checkpoint"


def test_owner_policy_package_does_not_default_missing_strategy_asset_decision():
    module = _load_module()
    policy_package = _build_policy_package(
        module,
        strategy_asset_state_source=(
            _strategy_asset_state_source_with_missing_strategy_asset_decision()
        ),
    )

    assert policy_package["strategy_asset_state_source"] == {
        "source": "strategy_asset_state.asset_rows",
        "row_count": 8,
        "missing_strategy_asset_current_decision_row_count": 1,
    }
    policy_items = {row["policy_item_id"]: row for row in policy_package["owner_policy_items"]}
    btpc = policy_items["BTPC-001:owner_policy_choice"]
    assert btpc["strategy_asset_current_decision"] == "unknown"
    assert btpc["strategy_asset_current_decision"] != "keep_observing"
    assert "ledger_decision" not in btpc


def test_owner_policy_package_mpg_member_policy_item_does_not_default_missing_strategy_asset_decision():
    module = _load_module()
    policy_package = _build_policy_package(
        module,
        strategy_asset_state_source=(
            _strategy_asset_state_source_with_missing_mpg_strategy_asset_decision()
        ),
    )

    assert policy_package["strategy_asset_state_source"] == {
        "source": "strategy_asset_state.asset_rows",
        "row_count": 8,
        "missing_strategy_asset_current_decision_row_count": 1,
    }
    policy_items = {row["policy_item_id"]: row for row in policy_package["owner_policy_items"]}
    mpg = policy_items["MPG-001:member_policy_decision"]
    assert mpg["strategy_asset_current_decision"] == "unknown"
    assert mpg["strategy_asset_current_decision"] != "keep_observing"
    assert "ledger_decision" not in mpg


def test_owner_policy_package_does_not_default_missing_p0_state_to_waiting_for_market():
    module = _load_module()
    capture_gap = json.loads(json.dumps(_capture_gap_audit()))
    capture_gap.pop("owner_visibility_state", None)

    policy_package = _build_policy_package(module, capture_gap_audit=capture_gap)

    snapshot = policy_package["strategy_quality_snapshot"]
    assert snapshot["p0_state"] == "unknown_runtime_state"
    assert snapshot["p0_state"] != "waiting_for_market"
    assert snapshot["p0_state_source"] == (
        "missing_capture_gap_owner_visibility_state_p0_state"
    )


def test_owner_policy_package_fails_closed_without_strategy_asset_state():
    module = _load_module()
    strategy_asset_state_source = _strategy_asset_state_source()
    strategy_asset_state_source.pop("strategy_asset_state")
    policy_package = _build_policy_package(
        module,
        strategy_asset_state_source=strategy_asset_state_source,
    )

    assert policy_package["strategy_asset_state_source"] == {
        "source": "missing_strategy_asset_state",
        "row_count": 0,
        "missing_strategy_asset_current_decision_row_count": 0,
    }
    policy_items = {row["policy_item_id"]: row for row in policy_package["owner_policy_items"]}
    btpc = policy_items["BTPC-001:owner_policy_choice"]
    assert btpc["strategy_asset_current_decision"] == "unknown"
    assert "ledger_decision" not in btpc
    assert btpc["next_checkpoint"] != "BTPC-001_classifier_fact_source_revision_review"
    mpg = policy_items["MPG-001:member_policy_decision"]
    assert mpg["strategy_asset_current_decision"] == "unknown"
    assert mpg["strategy_asset_current_decision"] != "keep_observing"
    assert "ledger_decision" not in mpg


def test_owner_policy_package_safety_invariants_and_tracks():
    module = _load_module()
    policy_package = _build_policy_package(module)

    assert policy_package["interaction"]["remote_interaction_count"] == 0
    assert policy_package["interaction"]["approaches_real_order"] is False
    assert "real_order_authority" not in policy_package["safety_invariants"]
    assert policy_package["safety_invariants"]["tier_policy_changed"] is False
    assert policy_package["safety_invariants"]["live_profile_changed"] is False
    assert policy_package["safety_invariants"]["registry_authority_changed"] is False
    assert policy_package["safety_invariants"]["mpg_member_live_scope_expanded"] is False
    assert "execution_intent_created" not in policy_package["safety_invariants"]

    tracks = {row["track_id"]: row for row in policy_package["closure_tracks"]}
    assert set(tracks) == {
        "signal-observation-A",
        "signal-observation-B",
        "signal-observation-C",
        "signal-observation-D",
        "signal-observation-E",
        "signal-observation-F",
        "signal-observation-G",
    }
    assert policy_package["strategy_quality_snapshot"]["signal_observation_state"] == (
        "review_needed"
    )
    for track in tracks.values():
        assert track["status"] in {"ready", "ready_for_owner_policy"}


def test_owner_policy_package_cli_writes_json_and_markdown(tmp_path, capsys):
    module = _load_module()
    payloads = {
        "capture.json": _capture_gap_audit(),
        "wave.json": _quality_closure_wave(),
        "strategy-asset-state.json": _strategy_asset_state_source(),
        "registry.json": _registry(),
        "tier.json": _tier_policy(),
        "btpc_fact.json": _btpc_fact_quality(),
        "btpc_source.json": _btpc_source_mapping(),
        "btpc_classifier.json": _btpc_classifier_review(),
        "btpc_keep.json": _btpc_keep_revise(),
        "btpc_proxy.json": _btpc_proxy_replay(),
        "loop.json": _opportunity_review_work_loop(),
        "mpg_replay.json": _replay_corpus("MPG-001"),
        "brf_replay.json": _replay_corpus("BRF-001"),
        "lsr_replay.json": _replay_corpus("LSR-001"),
    }
    for name, payload in payloads.items():
        (tmp_path / name).write_text(json.dumps(payload), encoding="utf-8")
    output_json = tmp_path / "policy-package.json"
    output_md = tmp_path / "policy-package.md"

    exit_code = module.main(
        [
            "--capture-gap-audit-json",
            str(tmp_path / "capture.json"),
            "--quality-closure-wave-json",
            str(tmp_path / "wave.json"),
            "--strategy-asset-state-json",
            str(tmp_path / "strategy-asset-state.json"),
            "--registry-json",
            str(tmp_path / "registry.json"),
            "--tier-policy-json",
            str(tmp_path / "tier.json"),
            "--btpc-fact-quality-json",
            str(tmp_path / "btpc_fact.json"),
            "--btpc-source-mapping-json",
            str(tmp_path / "btpc_source.json"),
            "--btpc-classifier-review-json",
            str(tmp_path / "btpc_classifier.json"),
            "--btpc-keep-revise-json",
            str(tmp_path / "btpc_keep.json"),
            "--btpc-proxy-replay-json",
            str(tmp_path / "btpc_proxy.json"),
            "--opportunity-review-work-loop-json",
            str(tmp_path / "loop.json"),
            "--mpg-replay-corpus-json",
            str(tmp_path / "mpg_replay.json"),
            "--brf-replay-corpus-json",
            str(tmp_path / "brf_replay.json"),
            "--lsr-replay-corpus-json",
            str(tmp_path / "lsr_replay.json"),
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
        ]
    )

    assert exit_code == 0
    stdout_payload = json.loads(capsys.readouterr().out)
    policy_package = json.loads(output_json.read_text(encoding="utf-8"))
    md = output_md.read_text(encoding="utf-8")
    assert stdout_payload["status"] == "owner_policy_package_ready"
    assert policy_package["status"] == "owner_policy_package_ready"
    assert "Strategy Quality Snapshot" in md
    assert "Owner Policy Items" in md
    assert "Owner Confirmation Boundary" in md


def test_owner_policy_package_cli_omitted_generated_inputs_is_incomplete(
    tmp_path,
    capsys,
):
    module = _load_module()
    payloads = {
        "registry.json": _registry(),
        "tier.json": _tier_policy(),
        "mpg_replay.json": _replay_corpus("MPG-001"),
        "brf_replay.json": _replay_corpus("BRF-001"),
        "lsr_replay.json": _replay_corpus("LSR-001"),
    }
    for name, payload in payloads.items():
        (tmp_path / name).write_text(json.dumps(payload), encoding="utf-8")
    output_json = tmp_path / "policy-package.json"
    output_md = tmp_path / "policy-package.md"

    exit_code = module.main(
        [
            "--registry-json",
            str(tmp_path / "registry.json"),
            "--tier-policy-json",
            str(tmp_path / "tier.json"),
            "--mpg-replay-corpus-json",
            str(tmp_path / "mpg_replay.json"),
            "--brf-replay-corpus-json",
            str(tmp_path / "brf_replay.json"),
            "--lsr-replay-corpus-json",
            str(tmp_path / "lsr_replay.json"),
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
        ]
    )

    assert exit_code == 0
    stdout_payload = json.loads(capsys.readouterr().out)
    policy_package = json.loads(output_json.read_text(encoding="utf-8"))
    assert stdout_payload["status"] == "owner_policy_package_incomplete"
    assert policy_package["status"] == "owner_policy_package_incomplete"
    assert policy_package["source_ready"] is False
    assert policy_package["owner_policy_summary"]["ready_owner_policy_item_count"] == 0
    assert all(policy_item["owner_policy_ready"] is False for policy_item in policy_package["owner_policy_items"])
    assert policy_package["source_status"]["capture_gap_audit"] is None
    assert any(
        error.startswith("capture_gap_audit.unexpected_status")
        for error in policy_package["source_errors"]
    )
