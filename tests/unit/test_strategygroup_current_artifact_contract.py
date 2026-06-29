from __future__ import annotations

import json
from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[2]

PRIMARY_JUDGMENT_TRUE_RE = re.compile(
    r"primary_judgment_source.*(?:true|True)", re.IGNORECASE
)
PRIMARY_JUDGMENT_TRUE_ALLOWED_PATHS = {
    "scripts/build_strategygroup_strategy_asset_state.py",
    "scripts/build_strategygroup_runtime_safety_state.py",
    "output/runtime-monitor/latest-strategy-asset-state.json",
    "output/runtime-monitor/latest-runtime-safety-state.json",
}
RETIRED_CURRENT_ARTIFACT_PATH_TOKENS = {
    "latest-strategygroup-owner-decision-package",
    "latest-strategygroup-tradeability-verdict",
    "latest-strategygroup-capital-trial-readiness-bridge",
    "latest-strategygroup-live-submit-readiness-bridge",
    "latest-strategygroup-decision-ledger",
}


def _read_json(path: str) -> dict:
    return json.loads((REPO_ROOT / path).read_text(encoding="utf-8"))


def _read_text(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_primary_judgment_source_true_is_allowlisted_to_core_states():
    violations: list[str] = []
    scanned_roots = (
        REPO_ROOT / "scripts",
        REPO_ROOT / "src",
        REPO_ROOT / "docs/current",
        REPO_ROOT / "output/runtime-monitor",
    )

    for root in scanned_roots:
        for path in root.rglob("*"):
            if path.suffix not in {".py", ".json", ".md"}:
                continue
            relative = path.relative_to(REPO_ROOT).as_posix()
            for line_number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if not PRIMARY_JUDGMENT_TRUE_RE.search(line):
                    continue
                if relative not in PRIMARY_JUDGMENT_TRUE_ALLOWED_PATHS:
                    violations.append(f"{relative}:{line_number}:{line.strip()}")

    assert violations == []


def test_current_artifact_contract_blocks_retired_generated_artifact_paths():
    violations: list[str] = []
    scanned_roots = (
        REPO_ROOT / "scripts",
        REPO_ROOT / "docs/current",
        REPO_ROOT / "output/runtime-monitor",
    )

    for root in scanned_roots:
        for path in root.rglob("*"):
            if path.suffix not in {".py", ".json", ".md"}:
                continue
            relative = path.relative_to(REPO_ROOT).as_posix()
            text = path.read_text(encoding="utf-8")
            for token in RETIRED_CURRENT_ARTIFACT_PATH_TOKENS:
                if token in text:
                    violations.append(f"{relative}:{token}")

    assert violations == []


def test_current_lifecycle_rehearsal_has_no_authority_mirror_fields():
    packet = _read_json(
        "docs/current/strategy-group-handoffs/strategygroup-lifecycle-rehearsal-current.json"
    )
    markdown = _read_text(
        "docs/current/strategy-group-handoffs/strategygroup-lifecycle-rehearsal-current.md"
    )

    runtime_safety = packet["runtime_safety_state"]
    assert runtime_safety["source_role"] == "lifecycle_rehearsal_evidence"
    assert runtime_safety["primary_judgment_source"] is False
    assert runtime_safety["tradeability_decision_source"] is False
    assert runtime_safety["execution_attempt_source"] is False
    assert "actionable_now" not in runtime_safety
    assert "real_order_authority" not in runtime_safety
    assert "actionable_now" not in packet["safety_invariants"]
    assert "real_order_authority" not in packet["safety_invariants"]
    for row in packet["scenario_rows"]:
        assert "real_order_authority" not in row
    assert "Real order authority" not in markdown
    assert "| Real order |" not in markdown


def test_current_d3_review_projections_have_no_authority_mirror_fields():
    capture_gap = _read_json("output/runtime-monitor/strategy-capture-gap-audit-20260622.json")
    opportunity_md = _read_text(
        "output/runtime-monitor/latest-opportunity-review-work-loop.md"
    )
    regime_role = _read_json(
        "output/runtime-monitor/latest-strategygroup-regime-role-coverage-map.json"
    )

    assert "real_order_authority" not in capture_gap["safety_invariants"]
    assert "Real order authority" not in opportunity_md
    assert "actionable_now" not in regime_role["safety_invariants"]
    assert "real_order_authority" not in regime_role["safety_invariants"]


def test_current_d4_strategy_asset_projections_have_no_authority_mirror_fields():
    research_intake = _read_json(
        "output/runtime-monitor/latest-strategygroup-research-intake-review.json"
    )
    handoff_boundary = _read_json(
        "docs/current/strategy-group-handoffs/strategygroup-handoff-boundary-closure-current.json"
    )
    quality_wave = _read_json(
        "docs/current/strategy-group-handoffs/strategygroup-quality-wave-current.json"
    )

    for packet in (research_intake, handoff_boundary, quality_wave):
        assert "actionable_now" not in packet["safety_invariants"]
        assert "real_order_authority" not in packet["safety_invariants"]


def test_current_tradeability_artifact_matches_monitor_sequence_contract():
    decision_artifact = _read_json(
        "output/runtime-monitor/latest-strategygroup-tradeability-decision.json"
    )
    monitor = _read_json("output/runtime-monitor/latest-local-monitor-sequence.json")

    decision_rows = decision_artifact.get("decision_rows") or []
    monitor_checks = monitor.get("checks") or {}
    monitor_issues = monitor.get("owner_runtime_issues") or {}
    monitor_tradeability = monitor.get("tradeability_decision") or {}
    decision_row_count = decision_artifact.get("summary", {}).get("row_count")

    assert "checks" not in monitor
    assert set(monitor_issues) == {
        "blockers",
        "non_market_gaps",
        "blocker_count",
        "non_market_gap_count",
    }
    assert decision_artifact["schema"] == "brc.strategygroup_tradeability_decision.v1"
    assert decision_artifact["scope"] == "strategygroup_tradeability_decision_read_model"
    assert decision_artifact["generated_at_utc"]
    assert decision_artifact["owner_summary"]
    assert "actionable_now" not in decision_artifact["owner_summary"]
    assert "real_order_authority" not in decision_artifact["owner_summary"]
    assert decision_rows
    assert decision_artifact.get("summary", {}).get("top_decision")
    assert decision_row_count == len(decision_rows)
    assert decision_artifact.get("checks", {}).get("row_count_matches_decision_rows") is True
    assert decision_artifact.get("checks", {}).get("row_count_matches_decision_rows") is True
    assert monitor_tradeability.get("row_count") == decision_row_count
    assert monitor_tradeability.get("decision_rows_count") == len(decision_rows)
    assert monitor_tradeability.get("row_count_matches_decision_rows") is True
    assert monitor_tradeability.get("projection_role") == (
        "tradeability_decision_projection"
    )
    assert monitor_tradeability.get("decision_result_counts", {}).get(
        "runtime_trade_allowed_rows"
    ) == decision_artifact.get("summary", {}).get("tradable_now_count")
    assert "decision_value_counts" not in monitor_tradeability
    assert "authority_true_row_counts" not in monitor_tradeability
    assert "runtime_authority_row_counts" not in monitor_tradeability
    assert "tradable_now_count" not in monitor_tradeability
    assert "actionable_now_count" not in monitor_tradeability
    assert "real_order_authority_count" not in monitor_tradeability
    decision_md = _read_text(
        "output/runtime-monitor/latest-strategygroup-tradeability-decision.md"
    )
    assert "Real order authority" not in decision_md
    for removed_check in (
        "tradeability_row_count",
        "tradeability_decision_rows_count",
        "tradeability_row_count_matches_decision_rows",
    ):
        assert removed_check not in monitor_checks


def test_current_trial_asset_admission_proposal_artifact_is_complete():
    proposal_packet = _read_json(
        "output/runtime-monitor/latest-strategygroup-trial-asset-admission-proposal.json"
    )
    proposal_md = (
        REPO_ROOT
        / "output/runtime-monitor/latest-strategygroup-trial-asset-admission-proposal.md"
    ).read_text(encoding="utf-8")
    proposal = proposal_packet.get("proposal") or {}

    assert (
        proposal_packet["schema"]
        == "brc.strategygroup_trial_asset_admission_proposal.v1"
    )
    assert (
        proposal_packet["scope"]
        == "strategygroup_trial_asset_admission_proposal_non_applying"
    )
    assert proposal_packet["generated_at_utc"]
    assert proposal["owner_policy_defaults"]
    assert proposal["owner_policy_required"] is False
    assert proposal["owner_policy_recorded"] is True
    assert proposal["owner_policy_scope_missing"] is False
    assert "next_action" not in proposal
    assert proposal["non_authority_checkpoint"] == (
        "close_brf2_required_facts_mapping_for_armed_observation"
    )
    assert proposal["proposed_registry_row"]
    assert proposal["proposed_tier_policy_row"]
    assert proposal["runtime_admission_plan"]
    assert "actionable_now" not in proposal
    assert "real_order_authority" not in proposal
    assert "actionable_now=false" not in proposal["proposed_registry_row"][
        "authority_boundary"
    ]
    assert "real_order_authority=false" not in proposal["proposed_registry_row"][
        "authority_boundary"
    ]
    assert "actionable_now=false" not in proposal["owner_policy_defaults"][
        "authority_boundary"
    ]
    assert "real_order_authority=false" not in proposal["owner_policy_defaults"][
        "authority_boundary"
    ]
    assert "actionable_now" not in proposal_packet["checks"]
    assert "real_order_authority" not in proposal_packet["checks"]
    assert "actionable_now" not in proposal_packet["safety_invariants"]
    assert "real_order_authority" not in proposal_packet["safety_invariants"]
    assert "Real order authority" not in proposal_md


def test_current_capital_trial_envelope_projection_has_no_authority_mirrors():
    projection = _read_json(
        "output/runtime-monitor/latest-strategygroup-capital-trial-envelope-projection.json"
    )
    trial_envelope = _read_json(
        "output/runtime-monitor/latest-strategygroup-capital-trial-envelope-v0.json"
    )
    projection_md = (
        REPO_ROOT
        / "output/runtime-monitor/latest-strategygroup-capital-trial-envelope-projection.md"
    ).read_text(encoding="utf-8")
    trial_md = (
        REPO_ROOT
        / "output/runtime-monitor/latest-strategygroup-capital-trial-envelope-v0.md"
    ).read_text(encoding="utf-8")

    assert projection["schema"] == (
        "brc.strategygroup_capital_trial_envelope_projection.v1"
    )
    assert projection["projection_metadata"]["tradeability_decision_source"] is False
    assert projection["projection_metadata"]["runtime_truth_source"] is False
    assert "actionable_now" not in projection["capital_trial_summary"]
    assert "real_order_authority" not in projection["capital_trial_summary"]
    assert "actionable_now_count" not in projection["capital_trial_summary"]
    assert "real_order_authority_count" not in projection["capital_trial_summary"]
    selected = projection["selected_non_mpg_trial_candidate"]
    assert "actionable_now" not in selected
    assert "real_order_authority" not in selected
    assert "actionable_now" not in projection["safety_invariants"]
    assert "real_order_authority" not in projection["safety_invariants"]
    assert "Actionable now" not in projection_md
    assert "Real order authority" not in projection_md

    assert trial_envelope["schema"] == "brc.strategygroup_capital_trial_envelope.v0"
    assert "actionable_now" not in trial_envelope
    assert "real_order_authority" not in trial_envelope
    assert "actionable_now" not in trial_envelope["authority_boundary"]
    assert "real_order_authority" not in trial_envelope["authority_boundary"]
    assert trial_envelope["authority_boundary"]["calls_finalgate"] is False
    assert trial_envelope["authority_boundary"]["calls_operation_layer"] is False
    assert trial_envelope["authority_boundary"]["calls_exchange_write"] is False
    assert "Actionable now" not in trial_md
    assert "Real order authority" not in trial_md


def test_current_pre_live_rehearsal_readiness_has_no_authority_mirrors():
    packet = _read_json(
        "docs/current/strategy-group-handoffs/strategygroup-pre-live-rehearsal-readiness-current.json"
    )
    markdown = (
        REPO_ROOT
        / "docs/current/strategy-group-handoffs/strategygroup-pre-live-rehearsal-readiness-current.md"
    ).read_text(encoding="utf-8")
    readiness = packet["runtime_readiness_state"]

    assert packet["schema"] == "brc.strategygroup_pre_live_rehearsal_readiness.v1"
    assert packet["status"] == "pre_live_rehearsal_ready"
    assert readiness["state_family"] == "Runtime Readiness State"
    assert readiness["source_role"] == "pre_live_rehearsal_readiness_evidence"
    assert readiness["primary_judgment_source"] is False
    assert readiness["tradeability_decision_source"] is False
    assert readiness["execution_attempt_source"] is False
    assert "actionable_now" not in readiness
    assert "real_order_authority" not in readiness
    assert "actionable_now" not in packet["safety_invariants"]
    assert "real_order_authority" not in packet["safety_invariants"]
    assert "Actionable now" not in markdown
    assert "Real order authority" not in markdown


def test_current_strategy_decision_owner_outputs_have_no_real_order_mirrors():
    assert not (
        REPO_ROOT / "output/runtime-monitor/latest-strategygroup-owner-decision-package.json"
    ).exists()
    assert not (
        REPO_ROOT / "output/runtime-monitor/latest-strategygroup-owner-decision-package.md"
    ).exists()

    strategy_asset_state = _read_json(
        "output/runtime-monitor/latest-strategy-asset-state.json"
    )
    quality_closure = _read_json(
        "output/runtime-monitor/latest-strategygroup-quality-closure-wave.json"
    )
    owner_package = _read_json(
        "output/runtime-monitor/latest-strategygroup-owner-policy-package.json"
    )
    decision_md = (
        REPO_ROOT / "output/runtime-monitor/latest-strategy-asset-state.md"
    ).read_text(encoding="utf-8")
    quality_md = (
        REPO_ROOT
        / "output/runtime-monitor/latest-strategygroup-quality-closure-wave.md"
    ).read_text(encoding="utf-8")
    owner_md = (
        REPO_ROOT
        / "output/runtime-monitor/latest-strategygroup-owner-policy-package.md"
    ).read_text(encoding="utf-8")

    assert "real_order_authorized_count" not in strategy_asset_state["counts"]
    for packet in (strategy_asset_state, quality_closure, owner_package):
        assert "real_order_authority" not in packet["safety_invariants"]
    assert "Real order authority" not in decision_md
    assert "Real order authority" not in quality_md
    assert "Real order authority" not in owner_md


def test_current_review_only_deep_dive_does_not_expose_real_order_mirrors():
    packet = _read_json(
        "output/runtime-monitor/latest-strategygroup-review-only-deep-dive-wave.json"
    )
    markdown = _read_text(
        "output/runtime-monitor/latest-strategygroup-review-only-deep-dive-wave.md"
    )
    owner_markdown = _read_text(
        "output/runtime-monitor/latest-strategygroup-review-only-deep-dive-owner-policy.md"
    )

    assert "real_order_authority" not in packet
    assert "deep_dive_packets" not in packet
    assert packet["owner_progress_projection"]["deep_dive_artifact_count"] == len(
        packet["deep_dive_artifacts"]
    )
    assert "real_order_authority" not in packet["safety_invariants"]
    for row in packet["deep_dive_artifacts"]:
        assert "real_order_authority" not in row
        assert "real_order_authority" not in row["safety_invariants"]
    assert "Real order authority" not in markdown
    assert "Real order authority" not in owner_markdown


def test_current_review_only_evidence_closure_does_not_expose_real_order_mirrors():
    packet = _read_json(
        "output/runtime-monitor/latest-strategygroup-review-only-evidence-closure-wave.json"
    )
    markdown = _read_text(
        "output/runtime-monitor/latest-strategygroup-review-only-evidence-closure-wave.md"
    )
    owner_progress = _read_text(
        "output/runtime-monitor/latest-strategygroup-review-only-owner-progress.md"
    )

    assert "real_order_authority" not in packet["safety_invariants"]
    assert "evidence_closure_packets" not in packet
    assert packet["owner_progress_projection"]["evidence_artifact_count"] == len(
        packet["evidence_closure_artifacts"]
    )
    for row in packet["evidence_closure_artifacts"]:
        assert "real_order_authority" not in row
        assert "real_order_authority" not in row["safety_invariants"]
    assert "real_order_authority" not in packet["next_owner_policy_package"][
        "safety_invariants"
    ]
    assert "Real order authority" not in markdown
    assert "Real order authority" not in owner_progress


def test_current_review_only_policy_confirmation_does_not_expose_real_order_mirrors():
    packet = _read_json(
        "output/runtime-monitor/latest-strategygroup-review-only-policy-confirmation.json"
    )
    markdown = _read_text(
        "output/runtime-monitor/latest-strategygroup-review-only-policy-confirmation.md"
    )

    assert "real_order_authority" not in packet["safety_invariants"]
    assert "Real order authority" not in markdown
    assert "| `real_order_authority` | `false` |" not in markdown


def test_current_brf2_owner_trial_policy_scope_artifact_is_complete():
    policy_packet = _read_json(
        "output/runtime-monitor/latest-brf2-owner-trial-policy-scope.json"
    )
    docs_policy_packet = _read_json(
        "docs/current/strategy-group-handoffs/brf2-owner-trial-policy-scope-v0.json"
    )
    policy = policy_packet.get("policy") or {}

    assert policy_packet["schema"] == "brc.brf2_owner_trial_policy_scope.v0"
    assert (
        policy_packet["scope"]
        == "final_owned_brf2_owner_trial_policy_scope_non_executing"
    )
    assert policy_packet["status"] == "brf2_owner_trial_policy_scope_recorded"
    assert docs_policy_packet["schema"] == policy_packet["schema"]
    assert policy_packet["view_mode"] == "monitor_view_from_final_owned_policy"
    assert policy_packet["source_policy_json"].endswith(
        "docs/current/strategy-group-handoffs/brf2-owner-trial-policy-scope-v0.json"
    )
    assert policy_packet["brf2_policy_scope_recorded"] is True
    assert policy_packet["owner_policy_scope_missing"] is False
    assert policy["strategy_group_id"] == "BRF2-001"
    assert policy["trial_identity"] == "BRF2_TINY_SHORT_TRIAL_30U_V0"
    assert policy["capital_scope"]["amount"] == "30"
    assert policy["capital_scope"]["currency"] == "USDT"
    assert policy["capital_scope"]["loss_capable"] is True
    assert policy["side_scope"] == ["short"]
    assert policy["leverage_scenario"] == "5x_scenario_not_authority"
    assert policy["max_notional"]["amount"] == "150"
    assert policy["attempt_cap"] == 3
    assert policy["loss_unit"]["amount"] == "10"
    for authority_mirror in (
        "actionable_now",
        "real_order_authority",
        "calls_finalgate",
        "calls_operation_layer",
        "calls_exchange_write",
        "places_order",
    ):
        assert authority_mirror not in policy_packet["checks"]
    assert "actionable_now" not in policy["authority_boundary"]
    assert "real_order_authority" not in policy["authority_boundary"]
    assert "actionable_now" not in policy_packet["safety_invariants"]
    assert "real_order_authority" not in policy_packet["safety_invariants"]
    assert policy_packet["safety_invariants"]["calls_finalgate"] is False
    assert policy_packet["safety_invariants"]["calls_operation_layer"] is False
    assert policy_packet["safety_invariants"]["calls_exchange_write"] is False
    assert policy_packet["safety_invariants"]["places_order"] is False


def test_current_brf2_required_facts_mapping_artifact_is_complete():
    mapping = _read_json("output/runtime-monitor/latest-brf2-required-facts-mapping.json")

    assert mapping["schema"] == "brc.brf2_required_facts_mapping.v1"
    assert mapping["scope"] == "brf2_required_facts_mapping_for_armed_observation"
    assert mapping["status"] == "brf2_required_facts_mapping_ready"
    assert mapping["generated_at_utc"]
    assert mapping["strategy_group_id"] == "BRF2-001"
    assert mapping["required_facts_mapping_ready"] is True
    assert mapping["after_next_state"] == "armed_observation"
    assert mapping["fresh_signal_rule"]["signal_id"] == (
        "brf2_short_rally_failure_fresh_signal_v1"
    )
    specs = {
        row["fact_key"]: row["accepted_statuses"]
        for row in mapping["required_fact_observation_specs"]
    }
    assert {
        "closed_1h_ohlcv",
        "closed_5m_ohlcv",
        "rally_context",
        "rally_failure_trigger_state",
        "short_squeeze_risk_state",
        "strong_reclaim_disable_state",
        "liquidity_downshift_state",
        "spread_liquidity_state",
    }.issubset(set(specs))
    assert "required_fact_keys" not in mapping
    disable_specs = {
        row["fact_key"]: row
        for row in mapping["disable_fact_observation_specs"]
    }
    assert {
        "short_squeeze_risk_state",
        "strong_reclaim_disable_state",
        "rally_extension_invalidates_failure_state",
        "liquidity_downshift_state",
        "spread_liquidity_state",
    }.issubset(set(disable_specs))
    assert "disable_fact_keys" not in mapping
    for authority_mirror in (
        "actionable_now",
        "real_order_authority",
        "calls_finalgate",
        "calls_operation_layer",
        "calls_exchange_write",
        "places_order",
    ):
        assert authority_mirror not in mapping["checks"]


def test_current_brf2_runtime_signal_capture_artifact_is_complete():
    facts = _read_json("output/runtime-monitor/latest-brf2-runtime-signal-facts.json")
    capture = _read_json("output/runtime-monitor/latest-brf2-runtime-signal-capture.json")
    monitor = _read_json("output/runtime-monitor/latest-local-monitor-sequence.json")
    monitor_facts = monitor["brf2_runtime_signal_facts"]
    monitor_capture = monitor["brf2_runtime_signal_capture"]
    preview = capture["signal_detector_preview"]
    candidate = capture["shadow_candidate_shape"]

    assert capture["schema"] == "brc.brf2_runtime_signal_capture.v1"
    assert capture["scope"] == "brf2_runtime_signal_capture_read_model"
    assert capture["status"] == "brf2_runtime_signal_capture_ready"
    assert capture["generated_at_utc"]
    assert capture["strategy_group_id"] == "BRF2-001"
    assert "would_bind_required_facts" not in candidate
    assert "would_bind_disable_facts" not in candidate
    assert facts["schema"] == "brc.brf2_runtime_signal_facts.v1"
    assert facts["status"] == "brf2_runtime_signal_facts_ready"
    assert facts["fact_authority"] == "readonly_proxy_not_action_time_required_fact"
    assert facts["fact_authority_boundary"]["usable_for_armed_observation"] is True
    assert facts["fact_authority_boundary"][
        "action_time_required_facts_satisfied"
    ] is False
    assert facts["fact_authority_boundary"]["usable_for_finalgate"] is False
    assert capture["fact_input_present"] == facts["fact_input_present"]
    assert capture["watcher_tick_present"] == facts["watcher_tick_present"]
    assert capture["fact_authority"] == facts["fact_authority"]
    assert capture["fact_authority_boundary"] == facts["fact_authority_boundary"]
    assert capture["source_signal_context"]["signal_observation_id"] == (
        facts["source_signal_context"]["signal_observation_id"]
    )
    assert capture["source_signal_context"]["symbol"] == (
        facts["source_signal_context"]["symbol"]
    )
    assert capture["source_signal_context"]["source_strategy_group_id"] == "BRF-001"
    assert capture["watcher_scope"]["signal_id"] == (
        "brf2_short_rally_failure_fresh_signal_v1"
    )
    assert capture["watcher_scope"]["side_scope"] == ["short"]
    assert preview["detector_ready"] is True
    assert preview["current_signal_state"] == "blocked_by_disable_fact"
    assert preview["first_blocker_class"] == (
        "short_squeeze_risk_state_disable_active"
    )
    assert preview["first_blocker_owner"] == "market"
    assert capture["no_action_attribution"]["attribution_ready"] is True
    assert candidate["shadow_candidate_type"] == (
        "brf2_non_executing_short_signal_candidate_evidence"
    )
    assert "required_next_chain" not in candidate
    assert "forbidden_until_action_time" not in candidate
    for removed_check in (
        "fact_input_status_ready",
        "watcher_scope_ready",
        "signal_detector_preview_ready",
        "no_action_attribution_ready",
        "shadow_candidate_shape_ready",
    ):
        assert removed_check not in capture["checks"]
    assert candidate["fact_authority"] == facts["fact_authority"]
    assert candidate["fact_authority_boundary"] == facts["fact_authority_boundary"]
    for authority_mirror in (
        "actionable_now",
        "real_order_authority",
        "action_time_required_facts_satisfied",
        "calls_finalgate",
        "calls_operation_layer",
        "calls_exchange_write",
        "places_order",
    ):
        assert authority_mirror not in capture["checks"]
    assert monitor_capture["ready"] is True
    assert monitor_facts["fact_input_present"] == facts["fact_input_present"]
    assert monitor_facts["watcher_tick_present"] == facts["watcher_tick_present"]
    assert monitor_capture["current_signal_state"] == preview["current_signal_state"]
    assert monitor_capture["shadow_candidate_shape_ready"] == candidate[
        "shadow_candidate_ready"
    ]


def test_current_brf2_shadow_candidate_evidence_artifact_is_complete():
    packet = _read_json(
        "output/runtime-monitor/latest-brf2-shadow-candidate-evidence.json"
    )
    monitor = _read_json("output/runtime-monitor/latest-local-monitor-sequence.json")
    monitor_candidate = monitor["brf2_shadow_candidate_evidence"]
    candidate = packet["shadow_candidate_evidence"]

    assert packet["schema"] == "brc.brf2_shadow_candidate_evidence.v1"
    assert packet["scope"] == "brf2_shadow_candidate_evidence_read_model"
    assert packet["status"] in {
        "brf2_shadow_candidate_evidence_ready",
        "brf2_shadow_candidate_evidence_waiting_for_fresh_signal",
    }
    assert packet["generated_at_utc"]
    assert packet["strategy_group_id"] == "BRF2-001"
    assert "candidate_packet_ready" not in packet
    assert "candidate_packet" not in packet
    assert candidate["shadow_candidate_evidence_type"] == (
        "brf2_non_executing_short_signal_candidate_evidence"
    )
    assert candidate["side"] == "short"
    assert candidate["symbol"]
    assert candidate["source_signal_observation_id"]
    assert candidate["source_strategy_group_id"] == "BRF-001"
    assert candidate["fact_authority"] == "readonly_proxy_not_action_time_required_fact"
    assert candidate["fact_authority_boundary"][
        "action_time_required_facts_satisfied"
    ] is False
    assert "required_next_chain" not in candidate
    assert "forbidden_until_action_time" not in candidate
    assert "runtime_signal_capture_ready" not in packet["checks"]
    assert "fresh_signal_present" not in packet["checks"]
    assert "actionable_now" not in packet["checks"]
    assert "real_order_authority" not in packet["checks"]
    assert "action_time_required_facts_satisfied" not in packet["checks"]
    assert "calls_finalgate" not in packet["checks"]
    assert "calls_operation_layer" not in packet["checks"]
    assert "calls_exchange_write" not in packet["checks"]
    assert "places_order" not in packet["checks"]
    assert "actionable_now" not in packet["safety_invariants"]
    assert "real_order_authority" not in packet["safety_invariants"]
    assert packet["safety_invariants"]["calls_finalgate"] is False
    assert packet["safety_invariants"]["calls_operation_layer"] is False
    assert packet["safety_invariants"]["calls_exchange_write"] is False
    assert packet["safety_invariants"]["places_order"] is False
    assert packet["interaction"]["calls_finalgate"] is False
    assert packet["interaction"]["calls_operation_layer"] is False
    assert packet["interaction"]["calls_exchange_write"] is False
    assert packet["interaction"]["places_order"] is False
    assert monitor_candidate["status"] == packet["status"]
    assert "candidate_packet_ready" not in monitor_candidate
    assert monitor_candidate["shadow_candidate_evidence_ready"] == (
        packet["shadow_candidate_evidence_ready"]
    )


def test_current_trial_grade_signal_gate_audit_does_not_expose_authority_mirrors():
    packet = _read_json(
        "output/runtime-monitor/latest-strategygroup-trial-grade-signal-gate-audit.json"
    )
    markdown = _read_text(
        "output/runtime-monitor/latest-strategygroup-trial-grade-signal-gate-audit.md"
    )

    assert "actionable_now" not in packet["safety_invariants"]
    assert "real_order_authority" not in packet["safety_invariants"]
    for row in packet["strategy_group_rows"].values():
        authority_boundary = row.get("authority_boundary") or {}
        assert "actionable_now" not in authority_boundary
        assert "real_order_authority" not in authority_boundary
    assert "Actionable now" not in markdown
    assert "Real order authority" not in markdown


def test_current_three_strategy_live_trial_portfolio_artifact_is_complete():
    portfolio = _read_json(
        "output/runtime-monitor/latest-three-strategy-live-trial-portfolio.json"
    )
    monitor = _read_json("output/runtime-monitor/latest-local-monitor-sequence.json")
    checks = monitor.get("checks") or {}
    assert "checks" not in monitor
    monitor_portfolio = monitor["three_strategy_live_trial_portfolio"]
    monitor_facts = monitor["brf2_runtime_signal_facts"]
    monitor_capture = monitor["brf2_runtime_signal_capture"]
    monitor_signal_observation = monitor["signal_observation_grade"]
    monitor_research_intake = monitor["strategy_research_intake"]
    monitor_trial_admission = monitor["strategy_trial_asset_admission"]
    monitor_trial_grade_audit = monitor["strategy_trial_grade_signal_gate_audit"]

    assert portfolio["schema"] == "brc.three_strategy_live_trial_portfolio.v1"
    assert portfolio["scope"] == "three_strategy_live_trial_portfolio_read_model"
    assert portfolio["status"] == "three_strategy_live_trial_portfolio_ready"
    assert portfolio["selected_strategy_groups"] == ["MPG-001", "BRF2-001", "SOR-001"]
    assert portfolio["seat_count"] == 3
    assert portfolio["objective_met"] is True
    assert portfolio["checks"]["all_seats_have_first_blocker"] is True
    assert portfolio["checks"]["all_seats_have_required_facts"] is True
    assert portfolio["checks"]["all_seats_have_review_hooks"] is True
    for authority_mirror in (
        "actionable_now",
        "real_order_authority",
        "trial_envelope_actionable_now",
        "trial_envelope_real_order_authority",
    ):
        assert authority_mirror not in portfolio["checks"]
    trial_envelope = portfolio["trial_envelope"]
    assert trial_envelope["primary_policy_source"] is True
    assert trial_envelope["tradeability_decision_source"] is False
    assert trial_envelope["runtime_truth_source"] is False
    assert "actionable_now" not in trial_envelope
    assert "real_order_authority" not in trial_envelope
    brf2 = portfolio["seat_readiness"]["BRF2-001"]
    assert brf2["stage"] == "armed_observation"
    assert brf2["armed_observation_plan_ready"] is True
    assert brf2["required_facts_mapping_ready"] is True
    assert brf2["runtime_readiness"]["armed_observation_plan_ready"] is True
    assert brf2["runtime_readiness"]["armed_observation_ready"] is True
    assert brf2["runtime_readiness"]["blocked_by"] == (
        "short_squeeze_risk_state_disable_active"
    )
    assert brf2["runtime_readiness"]["tiny_live_ready"] is False
    assert brf2["runtime_readiness"]["live_submit_ready"] is False
    assert "readiness_separation" not in brf2["runtime_readiness"]
    readiness_stage = brf2["runtime_readiness"]["readiness_stage_evidence"]
    assert readiness_stage["trial_eligible"] is True
    assert readiness_stage["live_submit_ready"] is False
    assert readiness_stage["can_create_execution_attempt"] is False
    assert "actionable_now" not in readiness_stage
    assert "real_order_authority" not in readiness_stage
    for seat in portfolio["seat_readiness"].values():
        assert "can_trade" not in seat["tradeability_decision_evidence"]
    stage_5 = portfolio["stage_5_live_opportunity_standby"]
    for removed_projection_field in (
        "live_submit_ready_now",
        "actionable_now",
        "real_order_authority",
    ):
        assert removed_projection_field not in stage_5
    for seat in portfolio["seat_readiness"].values():
        assert "actionable_now" not in seat["trial_grade_signal_status"]
        assert "real_order_authority" not in seat["trial_grade_signal_status"]
    assert brf2["first_blocker"]["blocker_owner"] == "market"
    assert "next_action" not in brf2["first_blocker"]
    assert brf2["first_blocker"]["repair_checkpoint"] == (
        "continue_brf2_armed_observation_until_disable_clears"
    )
    assert "actionable_now" not in portfolio["safety_invariants"]
    assert "real_order_authority" not in portfolio["safety_invariants"]
    assert portfolio["safety_invariants"]["calls_finalgate"] is False
    assert portfolio["safety_invariants"]["calls_operation_layer"] is False
    assert portfolio["safety_invariants"]["calls_exchange_write"] is False
    assert portfolio["safety_invariants"]["places_order"] is False
    evidence = portfolio["final_portfolio_evidence"]
    assert "final_evidence_packet" not in portfolio
    assert evidence["closed_engineering_problem"]
    assert evidence["capability_unlocked"]
    assert evidence["three_strategy_portfolio_status"] == portfolio["status"]
    assert "strategy_seat_table" not in evidence
    assert evidence["remaining_first_blockers"] == portfolio["first_blockers"]
    assert evidence["next_live_submit_condition"]
    assert evidence["tests_run"]
    assert evidence["files_changed"]
    assert evidence["deploy_recommendation"]

    assert monitor_portfolio["ready"] is True
    assert monitor_portfolio["seat_count"] == 3
    assert "readiness_separation" not in monitor_portfolio
    assert "actionable_now" not in monitor_portfolio["readiness_stage_evidence"]
    assert "real_order_authority" not in monitor_portfolio["readiness_stage_evidence"]
    assert monitor_portfolio["selected_strategy_groups"] == [
        "MPG-001",
        "BRF2-001",
        "SOR-001",
    ]
    assert monitor_portfolio["owner_policy_gap_count"] == 0
    assert monitor_portfolio["engineering_gap_count"] == 0
    assert monitor_portfolio["market_wait_count"] == 3
    assert "actionable_now" not in monitor_research_intake
    assert "actionable_now" not in monitor["owner_summary"]["strategy_research_intake"]
    for removed_projection_field in ("actionable_now", "real_order_authority"):
        assert removed_projection_field not in monitor_signal_observation
        assert (
            removed_projection_field
            not in monitor["owner_summary"]["signal_observation_grade"]
        )
        assert removed_projection_field not in monitor_trial_admission
        assert (
            removed_projection_field
            not in monitor["owner_summary"]["trial_asset_admission"]
        )
        assert removed_projection_field not in monitor_trial_grade_audit
        assert (
            removed_projection_field
            not in monitor["owner_summary"]["trial_grade_signal_gate_audit"]
        )
    assert monitor["brf2_owner_trial_policy"]["owner_policy_recorded"] is True
    assert monitor["brf2_owner_trial_policy"]["owner_policy_scope_missing"] is False
    assert monitor["brf2_owner_trial_policy"]["brf2_stage_after_policy"] == (
        "admitted_trial_asset"
    )
    assert monitor["brf2_owner_trial_policy"]["brf2_new_first_blocker"] == (
        "required_facts_mapping_gap"
    )
    for removed_projection_field in ("actionable_now", "real_order_authority"):
        assert removed_projection_field not in monitor["brf2_owner_trial_policy"]
        assert (
            removed_projection_field
            not in monitor["owner_summary"]["brf2_owner_trial_policy"]
        )
    for removed_check in (
        "brf2_owner_policy_recorded",
        "brf2_owner_policy_scope_missing",
        "brf2_stage_after_policy",
        "brf2_new_first_blocker",
    ):
        assert removed_check not in checks
    assert monitor["brf2_required_facts_mapping"]["ready"] is True
    assert monitor["brf2_required_facts_mapping"]["after_next_state"] == (
        "armed_observation"
    )
    assert monitor["brf2_required_facts_mapping"]["fresh_signal_rule_id"] == (
        "brf2_short_rally_failure_fresh_signal_v1"
    )
    for removed_projection_field in ("actionable_now", "real_order_authority"):
        assert removed_projection_field not in monitor["brf2_required_facts_mapping"]
    for removed_check in (
        "brf2_required_facts_mapping_ready",
        "brf2_after_required_facts_mapping_state",
        "brf2_fresh_signal_rule_id",
    ):
        assert removed_check not in checks
    assert monitor_facts["fact_input_present"] is True
    assert monitor_facts["watcher_tick_present"] is True
    assert monitor_capture["current_signal_state"] == "blocked_by_disable_fact"
    assert monitor_capture["first_blocker_class"] == (
        "short_squeeze_risk_state_disable_active"
    )


def test_current_tradeability_brf2_resolves_old_owner_policy_blockers():
    decision_artifact = _read_json(
        "output/runtime-monitor/latest-strategygroup-tradeability-decision.json"
    )
    rows = {row["strategy_group_id"]: row for row in decision_artifact["decision_rows"]}
    brf2 = rows["BRF2-001"]
    secondary = {row["blocker"] for row in brf2["secondary_blockers"]}
    resolved = {row["blocker"] for row in brf2["resolved_blockers"]}

    assert brf2["runtime_scope_status"]["owner_policy_recorded"] is True
    assert brf2["runtime_scope_status"]["owner_policy_scope_missing"] is False
    assert brf2["stage"] == "armed_observation"
    assert brf2["decision"] == "not_tradable_market_wait"
    assert brf2["first_blocker_class"] == (
        "short_squeeze_risk_state_disable_active"
    )
    assert brf2["blocker_owner"] == "market"
    assert brf2["next_action"] == (
        "continue_brf2_armed_observation_until_disable_clears"
    )
    assert brf2["runtime_scope_status"]["brf2_runtime_signal_capture_status"] == (
        "brf2_runtime_signal_capture_ready"
    )
    assert brf2["runtime_scope_status"]["brf2_current_signal_state"] == (
        "blocked_by_disable_fact"
    )
    assert "brf2_shadow_candidate_evidence_status" not in (
        brf2["runtime_scope_status"]
    )
    assert "brf2_shadow_candidate_evidence_ready" not in (
        brf2["runtime_scope_status"]
    )
    candidate_provenance = brf2["brf2_shadow_candidate_evidence_provenance"]
    assert candidate_provenance["projection_role"] == (
        "shadow_candidate_evidence_provenance"
    )
    assert candidate_provenance["primary_judgment_source"] is False
    assert candidate_provenance["non_executing_evidence"] is True
    for removed_projection_field in (
        "live_submit_authority",
        "operation_layer_authority",
        "actionable_now",
        "real_order_authority",
    ):
        assert removed_projection_field not in candidate_provenance
    assert "owner_capital_scope_not_confirmed" not in secondary
    assert "owner_trial_identity_not_confirmed" not in secondary
    assert "owner_capital_scope_not_confirmed" in resolved
    assert "owner_trial_identity_not_confirmed" in resolved
