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


def _assert_output_paths_absent(*paths: str) -> None:
    assert [path for path in paths if (REPO_ROOT / path).exists()] == []


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
    _assert_output_paths_absent(
        "output/runtime-monitor/strategy-capture-gap-audit-20260622.json",
        "output/runtime-monitor/latest-opportunity-review-work-loop.md",
        "output/runtime-monitor/latest-strategygroup-regime-role-coverage-map.json",
    )


def test_current_d4_strategy_asset_projections_have_no_authority_mirror_fields():
    _assert_output_paths_absent(
        "output/runtime-monitor/latest-strategygroup-research-intake-review.json",
    )
    handoff_boundary = _read_json(
        "docs/current/strategy-group-handoffs/strategygroup-handoff-boundary-closure-current.json"
    )
    quality_wave = _read_json(
        "docs/current/strategy-group-handoffs/strategygroup-quality-wave-current.json"
    )

    for packet in (handoff_boundary, quality_wave):
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
    _assert_output_paths_absent(
        "output/runtime-monitor/latest-strategygroup-trial-asset-admission-proposal.json",
        "output/runtime-monitor/latest-strategygroup-trial-asset-admission-proposal.md",
    )


def test_current_capital_trial_envelope_projection_has_no_authority_mirrors():
    _assert_output_paths_absent(
        "output/runtime-monitor/latest-strategygroup-capital-trial-envelope-projection.json",
        "output/runtime-monitor/latest-strategygroup-capital-trial-envelope-projection.md",
        "output/runtime-monitor/latest-strategygroup-capital-trial-envelope-v0.json",
        "output/runtime-monitor/latest-strategygroup-capital-trial-envelope-v0.md",
    )


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
    _assert_output_paths_absent(
        "output/runtime-monitor/latest-strategygroup-owner-decision-package.json",
        "output/runtime-monitor/latest-strategygroup-owner-decision-package.md",
        "output/runtime-monitor/latest-strategy-asset-state.json",
        "output/runtime-monitor/latest-strategy-asset-state.md",
        "output/runtime-monitor/latest-strategygroup-quality-closure-wave.json",
        "output/runtime-monitor/latest-strategygroup-quality-closure-wave.md",
        "output/runtime-monitor/latest-strategygroup-owner-policy-package.json",
        "output/runtime-monitor/latest-strategygroup-owner-policy-package.md",
    )


def test_current_review_only_deep_dive_does_not_expose_real_order_mirrors():
    _assert_output_paths_absent(
        "output/runtime-monitor/latest-strategygroup-review-only-deep-dive-wave.json",
        "output/runtime-monitor/latest-strategygroup-review-only-deep-dive-wave.md",
        "output/runtime-monitor/latest-strategygroup-review-only-deep-dive-owner-policy.md",
    )


def test_current_review_only_evidence_closure_does_not_expose_real_order_mirrors():
    _assert_output_paths_absent(
        "output/runtime-monitor/latest-strategygroup-review-only-evidence-closure-wave.json",
        "output/runtime-monitor/latest-strategygroup-review-only-evidence-closure-wave.md",
        "output/runtime-monitor/latest-strategygroup-review-only-owner-progress.md",
    )


def test_current_review_only_policy_confirmation_does_not_expose_real_order_mirrors():
    _assert_output_paths_absent(
        "output/runtime-monitor/latest-strategygroup-review-only-policy-confirmation.json",
        "output/runtime-monitor/latest-strategygroup-review-only-policy-confirmation.md",
    )


def test_current_brf2_owner_trial_policy_scope_artifact_is_complete():
    _assert_output_paths_absent(
        "output/runtime-monitor/latest-brf2-owner-trial-policy-scope.json",
        "output/runtime-monitor/latest-brf2-owner-trial-policy-scope.md",
    )
    docs_policy_packet = _read_json(
        "docs/current/strategy-group-handoffs/brf2-owner-trial-policy-scope-v0.json"
    )
    policy = docs_policy_packet.get("policy") or {}

    assert docs_policy_packet["schema"] == "brc.brf2_owner_trial_policy_scope.v0"
    assert (
        docs_policy_packet["scope"]
        == "final_owned_brf2_owner_trial_policy_scope_non_executing"
    )
    assert docs_policy_packet["status"] == "brf2_owner_trial_policy_scope_recorded"
    assert policy["strategy_group_id"] == "BRF2-001"
    assert policy["trial_identity"] == "BRF2_CONTROLLED_SHORT_TRIAL_V0"
    assert policy["capital_scope"]["amount_source"] == (
        "action_time_exchange_available_balance"
    )
    assert policy["capital_scope"]["allocation_mode"] == (
        "full_available_isolated_subaccount"
    )
    assert policy["capital_scope"]["currency"] == "USDT"
    assert policy["capital_scope"]["loss_capable"] is True
    assert policy["side_scope"] == ["short"]
    assert policy["leverage_scenario"] == "5x_scenario_not_authority"
    assert policy["max_notional"]["balance_source"] == (
        "action_time_exchange_available_balance"
    )
    assert policy["attempt_cap"] == 3
    assert policy["loss_unit"]["balance_source"] == (
        "action_time_exchange_available_balance"
    )
    for authority_mirror in (
        "actionable_now",
        "real_order_authority",
        "calls_finalgate",
        "calls_operation_layer",
        "calls_exchange_write",
        "places_order",
    ):
        assert authority_mirror not in docs_policy_packet["checks"]
    assert "actionable_now" not in policy["authority_boundary"]
    assert "real_order_authority" not in policy["authority_boundary"]
    assert "actionable_now" not in docs_policy_packet["safety_invariants"]
    assert "real_order_authority" not in docs_policy_packet["safety_invariants"]
    assert docs_policy_packet["safety_invariants"]["calls_finalgate"] is False
    assert docs_policy_packet["safety_invariants"]["calls_operation_layer"] is False
    assert docs_policy_packet["safety_invariants"]["calls_exchange_write"] is False
    assert docs_policy_packet["safety_invariants"]["places_order"] is False


def test_current_brf2_required_facts_mapping_artifact_is_complete():
    _assert_output_paths_absent(
        "output/runtime-monitor/latest-brf2-required-facts-mapping.json",
        "output/runtime-monitor/latest-brf2-required-facts-mapping.md",
    )


def test_current_brf2_runtime_signal_capture_artifact_is_complete():
    facts = _read_json("output/runtime-monitor/latest-brf2-runtime-signal-facts.json")
    _assert_output_paths_absent(
        "output/runtime-monitor/latest-brf2-runtime-signal-capture.json",
        "output/runtime-monitor/latest-brf2-runtime-signal-capture.md",
    )

    assert facts["schema"] == "brc.brf2_runtime_signal_facts.v1"
    assert facts["status"] == "brf2_runtime_signal_facts_ready"
    assert facts["fact_authority"] == "readonly_proxy_not_action_time_required_fact"
    assert facts["fact_authority_boundary"]["usable_for_armed_observation"] is True
    assert facts["fact_authority_boundary"][
        "action_time_required_facts_satisfied"
    ] is False
    assert facts["fact_authority_boundary"]["usable_for_finalgate"] is False


def test_current_brf2_shadow_candidate_evidence_artifact_is_complete():
    _assert_output_paths_absent(
        "output/runtime-monitor/latest-brf2-shadow-candidate-evidence.json",
        "output/runtime-monitor/latest-brf2-shadow-candidate-evidence.md",
    )


def test_current_trial_grade_signal_gate_audit_does_not_expose_authority_mirrors():
    _assert_output_paths_absent(
        "output/runtime-monitor/latest-strategygroup-trial-grade-signal-gate-audit.json",
        "output/runtime-monitor/latest-strategygroup-trial-grade-signal-gate-audit.md",
    )


def test_current_three_strategy_live_trial_portfolio_artifact_is_complete():
    _assert_output_paths_absent(
        "output/runtime-monitor/latest-three-strategy-live-trial-portfolio.json",
        "output/runtime-monitor/latest-three-strategy-live-trial-portfolio.md",
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
    assert brf2["first_blocker_class"] == "computed_not_satisfied"
    assert brf2["legacy_blocker_raw"] == "short_squeeze_risk_state_disable_active"
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
