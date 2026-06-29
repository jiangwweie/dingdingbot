#!/usr/bin/env python3
"""Build the P0 fresh-signal cutover hardening artifact.

This artifact is a thin, non-executing contract for the first live capture path.
It proves the status projection, action-time fact surface, authorization input
shape, duplicate/conflict guards, protection recovery, and review capture shape
that must be ready before a real fresh signal arrives.

It does not call FinalGate, Operation Layer, PG, a server, an exchange, or any
submit endpoint, and it never creates orders or live authority.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


DEFAULT_OUTPUT_JSON = (
    PROJECT_ROOT
    / "output/runtime-monitor/latest-p0-fresh-signal-cutover-hardening.json"
)
DEFAULT_OWNER_PROGRESS = (
    PROJECT_ROOT
    / "output/runtime-monitor/latest-p0-fresh-signal-cutover-hardening.md"
)

STATE_AUTHORITY_COMMIT_SUBJECT = "fix(runtime): close state authority projection"
FRESH_CUTOVER_COMMIT_SUBJECT = "test(runtime): rehearse fresh signal monitor cutover"


def build_p0_fresh_signal_cutover_hardening_artifact(
    *,
    generated_at_ms: int | None = None,
    state_authority_commit: str | None = None,
    fresh_cutover_commit: str | None = None,
) -> dict[str, Any]:
    generated_at_ms = generated_at_ms if generated_at_ms is not None else int(time.time() * 1000)
    state_authority_commit = state_authority_commit or _commit_for_subject(
        STATE_AUTHORITY_COMMIT_SUBJECT
    )
    fresh_cutover_commit = fresh_cutover_commit or _commit_for_subject(
        FRESH_CUTOVER_COMMIT_SUBJECT
    )

    evidence_groups = {
        "state_authority_versioning": _state_authority_versioning(
            state_authority_commit=state_authority_commit,
            fresh_cutover_commit=fresh_cutover_commit,
        ),
        "fresh_signal_cutover_fixtures": _fresh_signal_cutover_fixtures(),
        "action_time_required_facts": _action_time_required_facts_contract(),
        "candidate_authorization_finalgate": (
            _candidate_authorization_finalgate_contract()
        ),
        "duplicate_and_conflict_guards": _duplicate_and_conflict_guards(),
        "protection_failure_recovery": _protection_failure_recovery(),
        "post_event_review_capture": _post_event_review_capture(),
    }
    blockers = _group_blockers(evidence_groups)
    status = (
        "p0_fresh_signal_cutover_hardening_ready"
        if not blockers
        else "p0_fresh_signal_cutover_hardening_blocked"
    )
    return {
        "schema": "brc.p0_fresh_signal_cutover_hardening.v1",
        "scope": "P0-FRESH-SIGNAL-CUTOVER-HARDENING-001",
        "generated_at_ms": generated_at_ms,
        "status": status,
        "capability_unlocked": (
            "fresh selected StrategyGroup signal can move the local authority "
            "projection from waiting_for_market to processing without audit/cache "
            "misclassification, while missing facts and safety conflicts remain "
            "temporarily_unavailable and review-ready."
        ),
        "next_engineering_bottleneck": (
            "Deploy the state semantics to Tokyo only after the branch is pushed "
            "and Owner accepts the release boundary; real submit still waits for "
            "fresh signal, action-time facts, FinalGate, and Operation Layer."
        ),
        "checks": {
            "ready": not blockers,
            "blockers": blockers,
            "state_authority_versioned": bool(state_authority_commit),
            "fresh_signal_processing_rehearsed": bool(fresh_cutover_commit),
            "waiting_to_processing_projection_ready": _fresh_case_ready(
                evidence_groups
            ),
            "required_facts_contract_ready": (
                evidence_groups["action_time_required_facts"]["status"]
                == "ready_action_time_contract"
            ),
            "candidate_authorization_finalgate_contract_ready": (
                evidence_groups["candidate_authorization_finalgate"]["status"]
                == "ready_non_executing_contract"
            ),
            "duplicate_submit_guard_ready": (
                evidence_groups["duplicate_and_conflict_guards"]["status"]
                == "ready_conflict_guard_contract"
            ),
            "protection_failure_recovery_ready": (
                evidence_groups["protection_failure_recovery"]["status"]
                == "ready_recovery_contract"
            ),
            "post_event_review_capture_ready": (
                evidence_groups["post_event_review_capture"]["status"]
                == "ready_review_capture_shape"
            ),
        },
        "evidence_groups": evidence_groups,
        "owner_state_projection": {
            "healthy_waiting": "waiting_for_opportunity",
            "fresh_signal_facts_collecting": "processing",
            "missing_hard_safety_fact": "temporarily_unavailable",
            "policy_capital_pause_decision": "needs_intervention",
            "post_submit_settled": "completed",
        },
        "safety_invariants": _safety_invariants(),
        "interaction": {
            "level": "L0_local_hardening_artifact",
            "remote_interaction_count": 0,
            "mutates_remote_files": False,
            "approaches_real_order": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
    }


def _state_authority_versioning(
    *,
    state_authority_commit: str | None,
    fresh_cutover_commit: str | None,
) -> dict[str, Any]:
    blockers: list[str] = []
    if not state_authority_commit:
        blockers.append("state_authority_commit_missing")
    if not fresh_cutover_commit:
        blockers.append("fresh_signal_cutover_rehearsal_commit_missing")
    return {
        "status": "ready_versioned_baseline" if not blockers else "blocked_versioning",
        "state_authority_commit": state_authority_commit,
        "fresh_cutover_rehearsal_commit": fresh_cutover_commit,
        "tracked_artifact_boundary": {
            "authoritative_runtime_monitor": (
                "output/runtime-monitor/latest-local-monitor-sequence.json"
            ),
            "authoritative_owner_progress": (
                "output/runtime-monitor/latest-local-monitor-sequence.md"
            ),
            "untracked_output_policy": "do_not_clean_or_stage_bulk_output",
        },
        "tokyo_sync_decision": {
            "status": "deploy_checkpoint_not_executed",
            "recommended_when": (
                "after branch push/release boundary if Tokyo still consumes old "
                "state-authority semantics"
            ),
            "does_not_block_local_hardening": True,
        },
        "blockers": blockers,
    }


def _fresh_signal_cutover_fixtures() -> dict[str, Any]:
    cases = [
        {
            "case_id": "fresh_selected_strategygroup_signal",
            "input_signal": {
                "freshness": "fresh",
                "scope": "selected_strategygroup_allocated_subaccount",
                "required_facts": "ready",
                "active_position_conflict": False,
                "open_order_conflict": False,
            },
            "expected_runtime_status": "processing",
            "expected_owner_status": "processing",
            "expected_notification": "NOTIFY",
            "blocker_class": None,
        },
        {
            "case_id": "stale_signal",
            "input_signal": {"freshness": "expired"},
            "expected_runtime_status": "temporarily_unavailable",
            "expected_owner_status": "temporarily_unavailable",
            "expected_notification": "NOTIFY",
            "blocker_class": "missing_fact",
        },
        {
            "case_id": "wrong_scope_signal",
            "input_signal": {"scope": "unallocated_or_unselected_strategygroup"},
            "expected_runtime_status": "temporarily_unavailable",
            "expected_owner_status": "temporarily_unavailable",
            "expected_notification": "NOTIFY",
            "blocker_class": "hard_safety_stop",
        },
        {
            "case_id": "missing_action_time_fact",
            "input_signal": {"required_facts": "missing"},
            "expected_runtime_status": "temporarily_unavailable",
            "expected_owner_status": "temporarily_unavailable",
            "expected_notification": "NOTIFY",
            "blocker_class": "missing_fact",
        },
        {
            "case_id": "active_position_or_open_order_conflict",
            "input_signal": {
                "active_position_conflict": True,
                "open_order_conflict": True,
            },
            "expected_runtime_status": "temporarily_unavailable",
            "expected_owner_status": "temporarily_unavailable",
            "expected_notification": "NOTIFY",
            "blocker_class": "active_position_resolution",
        },
    ]
    return {
        "status": "ready_fresh_signal_fixture_matrix",
        "waiting_projection": {
            "runtime_status": "waiting_for_market",
            "owner_status": "waiting_for_opportunity",
            "notification": "DONT_NOTIFY",
        },
        "cases": cases,
        "cache_audit_rule": (
            "processing evidence outranks monitor_refresh_needed; deployment_issue "
            "and needs_non_market_repair still outrank processing"
        ),
        "blockers": [],
    }


def _action_time_required_facts_contract() -> dict[str, Any]:
    facts = [
        {
            "fact_key": "account_facts",
            "states": ["ready", "stale", "missing"],
            "missing_or_stale_class": "missing_fact",
            "required_before_finalgate": True,
        },
        {
            "fact_key": "position_and_open_order_conflict",
            "states": ["clear", "conflict"],
            "conflict_class": "active_position_resolution",
            "required_before_finalgate": True,
        },
        {
            "fact_key": "allocated_budget",
            "states": ["sufficient", "insufficient"],
            "insufficient_class": "missing_fact",
            "required_before_finalgate": True,
        },
        {
            "fact_key": "protection_template",
            "states": ["ready", "missing"],
            "missing_class": "missing_fact",
            "required_before_finalgate": True,
        },
        {
            "fact_key": "exchange_rules",
            "states": ["pass", "fail"],
            "fail_class": "missing_fact",
            "required_before_finalgate": True,
        },
        {
            "fact_key": "signal_freshness",
            "states": ["fresh", "expired"],
            "expired_class": "missing_fact",
            "required_before_finalgate": True,
        },
    ]
    return {
        "status": "ready_action_time_contract",
        "facts": facts,
        "ready_for_finalgate_checkpoint_rule": (
            "all facts must be ready/clear/sufficient/pass/fresh"
        ),
        "live_submit_ready_rule": (
            "false until action-time FinalGate and official Operation Layer pass"
        ),
        "read_only_prefetch_allowed": True,
        "signed_get_only_prefetch_allowed": True,
        "blockers": [],
    }


def _candidate_authorization_finalgate_contract() -> dict[str, Any]:
    required_fields = [
        "selected_strategy_group_id",
        "allocated_subaccount_or_profile",
        "runtime_instance_id",
        "runtime_grant_id",
        "strategy_signal_id",
        "symbol",
        "side",
        "intent_notional_or_qty",
        "trusted_submit_fact_snapshot_id",
        "submit_idempotency_policy_id",
        "protection_plan_id",
        "fresh_submit_authorization_id",
    ]
    return {
        "status": "ready_non_executing_contract",
        "candidate_authorization_required_fields": required_fields,
        "authorization_continuity": {
            "runtime_admission_required": True,
            "owner_policy_boundary_required": True,
            "strategygroup_tier_boundary_required": True,
            "same_run_fresh_authorization_required": True,
        },
        "finalgate_dry_run_input": {
            "allowed": True,
            "calls_finalgate": False,
            "proves_input_shape_only": True,
            "cannot_set_live_submit_ready": True,
        },
        "no_bypass_guard": {
            "finalgate_required": True,
            "operation_layer_required": True,
            "prepare_records_are_not_submit_authority": True,
        },
        "blockers": [],
    }


def _duplicate_and_conflict_guards() -> dict[str, Any]:
    return {
        "status": "ready_conflict_guard_contract",
        "guards": [
            {
                "guard": "duplicate_submit",
                "required_evidence": [
                    "stable_submit_key",
                    "replay_lock_key",
                    "same_signal_same_intent_replay_policy",
                    "adapter_result_store",
                    "execution_result_store",
                ],
                "failure_class": "hard_safety_stop",
            },
            {
                "guard": "open_order_conflict",
                "required_evidence": ["trusted_open_order_snapshot"],
                "failure_class": "active_position_resolution",
            },
            {
                "guard": "active_position_conflict",
                "required_evidence": ["trusted_active_position_snapshot"],
                "failure_class": "active_position_resolution",
            },
        ],
        "retry_policy": (
            "retry may reuse the same idempotency key only through replay-safe "
            "official recovery evidence"
        ),
        "blockers": [],
    }


def _protection_failure_recovery() -> dict[str, Any]:
    return {
        "status": "ready_recovery_contract",
        "accepted_submit_branches": [
            "submit_accepted_protection_created",
            "submit_accepted_protection_creation_failed",
            "submit_timeout_requires_readonly_reconciliation",
            "submit_rejected_before_exchange",
        ],
        "protection_failure_policy": {
            "exchange_native_hard_stop_required": True,
            "reduce_only_recovery_authorized_only_after_evidence": True,
            "missing_protection_blocks_new_entries": True,
            "owner_intervention_only_for_policy_capital_pause_decision": True,
        },
        "blockers": [],
    }


def _post_event_review_capture() -> dict[str, Any]:
    fields = [
        "strategy_group_id",
        "runtime_instance_id",
        "signal_id",
        "candidate_id",
        "authorization_id",
        "finalgate_evidence_id",
        "operation_layer_authorization_id",
        "exchange_submit_execution_result_id",
        "entry_order_id",
        "protection_order_ids",
        "reject_reason",
        "timeout_state",
        "partial_fill_qty",
        "fee_estimate",
        "funding_estimate",
        "slippage_estimate",
        "realized_pnl",
        "reconciliation_status",
        "budget_settlement_id",
        "decision_candidates",
    ]
    return {
        "status": "ready_review_capture_shape",
        "review_ledger_fields": fields,
        "post_event_review_builder": {
            "input_artifacts": [
                "live_closure_evidence_artifact",
                "exchange_submit_execution_result",
                "submit_outcome_review",
                "post_submit_reconciliation",
                "budget_settlement",
            ],
            "negative_evidence_captured": True,
            "no_action_reject_timeout_are_reviewable": True,
        },
        "strategygroup_decision_adapter_shape": {
            "candidate_decisions": ["keep", "revise", "promote", "park", "kill"],
            "adapter_is_recommendation_only": True,
            "does_not_change_tier": True,
        },
        "post_live_calibration_checklist": [
            "fee",
            "spread",
            "funding",
            "slippage",
            "fill_or_reject",
            "protection_acceptance",
            "reconciliation_delta",
        ],
        "blockers": [],
    }


def _group_blockers(evidence_groups: dict[str, dict[str, Any]]) -> list[str]:
    blockers: list[str] = []
    for name, group in evidence_groups.items():
        blockers.extend(f"{name}:{blocker}" for blocker in group.get("blockers", []))
    return sorted(set(blockers))


def _fresh_case_ready(evidence_groups: dict[str, dict[str, Any]]) -> bool:
    cases = evidence_groups["fresh_signal_cutover_fixtures"]["cases"]
    return any(
        case["case_id"] == "fresh_selected_strategygroup_signal"
        and case["expected_runtime_status"] == "processing"
        for case in cases
    )


def _safety_invariants() -> dict[str, bool]:
    return {
        "p0_fresh_signal_hardening_projection_only": True,
        "does_not_call_server": True,
        "does_not_call_finalgate": True,
        "does_not_call_operation_layer": True,
        "does_not_call_exchange": True,
        "does_not_create_order": True,
        "does_not_create_execution_intent": True,
        "does_not_create_candidate": True,
        "does_not_mutate_runtime_state": True,
        "does_not_change_live_profile": True,
        "does_not_change_order_sizing_defaults": True,
        "does_not_create_withdrawal_or_transfer": True,
        "live_submit_ready": False,
    }


def _commit_for_subject(subject: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "log", "--format=%H%x00%s", "-n", "40"],
            cwd=PROJECT_ROOT,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError:
        return None
    for line in completed.stdout.splitlines():
        if "\x00" not in line:
            continue
        commit, commit_subject = line.split("\x00", 1)
        if commit_subject.strip() == subject:
            return commit
    return None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _owner_progress_text(artifact: dict[str, Any]) -> str:
    checks = artifact["checks"]
    interaction = artifact["interaction"]
    lines = [
        "## P0 Fresh Signal Cutover Hardening",
        "",
        f"- Status: {artifact['status']}",
        f"- Capability unlocked: {artifact['capability_unlocked']}",
        f"- Blockers: {_list_or_none(checks['blockers'])}",
        f"- Runtime transition ready: {_yes_no(checks['waiting_to_processing_projection_ready'])}",
        f"- RequiredFacts contract ready: {_yes_no(checks['required_facts_contract_ready'])}",
        f"- Candidate/Auth/FinalGate contract ready: {_yes_no(checks['candidate_authorization_finalgate_contract_ready'])}",
        f"- Duplicate/conflict guard ready: {_yes_no(checks['duplicate_submit_guard_ready'])}",
        f"- Protection recovery ready: {_yes_no(checks['protection_failure_recovery_ready'])}",
        f"- Review capture ready: {_yes_no(checks['post_event_review_capture_ready'])}",
        f"- Remote interaction count: {interaction['remote_interaction_count']}",
        f"- Approaches real order: {_yes_no(interaction['approaches_real_order'])}",
        f"- Calls FinalGate: {_yes_no(interaction['calls_finalgate'])}",
        f"- Calls Operation Layer: {_yes_no(interaction['calls_operation_layer'])}",
        f"- Calls exchange write: {_yes_no(interaction['calls_exchange_write'])}",
        "",
        "## Next Engineering Bottleneck",
        "",
        artifact["next_engineering_bottleneck"],
    ]
    return "\n".join(lines)


def _list_or_none(values: list[Any]) -> str:
    return "none" if not values else ", ".join(str(value) for value in values)


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a P0 fresh-signal cutover hardening artifact.",
    )
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OWNER_PROGRESS))
    parser.add_argument("--generated-at-ms", type=int)
    parser.add_argument("--state-authority-commit")
    parser.add_argument("--fresh-cutover-commit")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    artifact = build_p0_fresh_signal_cutover_hardening_artifact(
        generated_at_ms=args.generated_at_ms,
        state_authority_commit=args.state_authority_commit,
        fresh_cutover_commit=args.fresh_cutover_commit,
    )
    if args.output_json:
        _write_json(Path(args.output_json), artifact)
    if args.output_owner_progress:
        Path(args.output_owner_progress).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output_owner_progress).write_text(
            _owner_progress_text(artifact) + "\n",
            encoding="utf-8",
        )
    if args.json:
        print(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(_owner_progress_text(artifact))
    return 0 if artifact["checks"]["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
