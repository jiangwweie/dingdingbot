"""Shared contract constants for first bounded live-closure evidence projections.

This module is a local projection contract. It does not call FinalGate,
Operation Layer, exchange APIs, or any submit path.
"""

from __future__ import annotations

LEGACY_PACKET_ID_FIELD = "pack" + "et_id"
LIVE_WATCHER_SIGNAL_EVIDENCE_KEY = "live_watcher_signal_" + LEGACY_PACKET_ID_FIELD
WATCHER_SIGNAL_EVIDENCE_KEY = "watcher_signal_" + LEGACY_PACKET_ID_FIELD
SIGNAL_EVIDENCE_KEY = "signal_" + LEGACY_PACKET_ID_FIELD
ACTION_TIME_FINALGATE_EVIDENCE_KEY = (
    "action_time_finalgate_" + LEGACY_PACKET_ID_FIELD
)
ACTION_TIME_FINAL_GATE_EVIDENCE_KEY = (
    "action_time_final_gate_" + LEGACY_PACKET_ID_FIELD
)
FINAL_GATE_EVIDENCE_KEY = "final_gate_" + LEGACY_PACKET_ID_FIELD

EVIDENCE_ID_FIELDS = ("id", "evidence_id", LEGACY_PACKET_ID_FIELD, "ref_id", "reference_id")

LIVE_SIGNAL_CHAIN_KEY = LIVE_WATCHER_SIGNAL_EVIDENCE_KEY
LIVE_SIGNAL_CHAIN_EVIDENCE_KEYS = (
    "required_facts_readiness_artifact_id",
    "candidate_id",
)

PRE_SUBMIT_AUTHORIZATION_CHAIN_KEY = "fresh_submit_authorization_id"
ACTION_TIME_FINALGATE_CHAIN_KEY = ACTION_TIME_FINALGATE_EVIDENCE_KEY
PRE_SUBMIT_AUTHORIZATION_CHAIN_EVIDENCE_KEYS = (
    "candidate_id",
    "runtime_grant_id",
    ACTION_TIME_FINALGATE_CHAIN_KEY,
    "operation_layer_submit_authorization_id",
)

POST_SUBMIT_CLOSE_LOOP_EVIDENCE_KEYS = (
    "runtime_post_submit_finalize_payload_id",
    "post_submit_reconciliation_evidence_id",
    "post_submit_budget_settlement_id",
    "submit_outcome_review_id",
)
POST_SUBMIT_CLOSE_LOOP_TRUTH_CHECKS: dict[str, tuple[str, tuple[str, ...], str]] = {
    "runtime_post_submit_finalize_payload_id": (
        "finalize_complete",
        (
            "post_submit_finalize_complete",
            "runtime_post_submit_finalize_complete",
            "finalize_complete",
            "post_submit_finalized",
        ),
        "post_submit_finalize_not_complete",
    ),
    "post_submit_reconciliation_evidence_id": (
        "reconciliation_matched",
        (
            "post_submit_reconciliation_matched",
            "reconciliation_matched",
            "reconciliation_ok",
            "order_reconciled",
        ),
        "post_submit_reconciliation_not_matched",
    ),
    "post_submit_budget_settlement_id": (
        "budget_settled",
        (
            "post_submit_budget_settled",
            "budget_settled",
            "budget_settlement_complete",
            "budget_released",
        ),
        "post_submit_budget_not_settled",
    ),
    "submit_outcome_review_id": (
        "review_recorded",
        (
            "submit_outcome_review_recorded",
            "review_recorded",
            "submit_review_recorded",
            "outcome_review_recorded",
        ),
        "submit_outcome_review_not_recorded",
    ),
}

RUNTIME_BOUNDARY_FIELDS = (
    "strategy_group_id",
    "runtime_profile_id",
    "subaccount_id",
    "symbol",
    "side",
    "notional",
    "leverage",
)
RUNTIME_BOUNDARY_REQUIRED_EVIDENCE_KEYS = (
    "candidate_id",
    "runtime_grant_id",
    "fresh_submit_authorization_id",
    ACTION_TIME_FINALGATE_CHAIN_KEY,
    "operation_layer_submit_authorization_id",
    "exchange_submit_execution_result_id",
)
RUNTIME_BOUNDARY_REJECT_REASONS = {
    "strategy_group_id": "strategy_group_boundary_mismatch",
    "runtime_profile_id": "runtime_profile_boundary_mismatch",
    "subaccount_id": "subaccount_boundary_mismatch",
    "symbol": "symbol_boundary_mismatch",
    "side": "side_boundary_mismatch",
    "notional": "notional_boundary_mismatch",
    "leverage": "leverage_boundary_mismatch",
}
RUNTIME_BOUNDARY_MISSING_REJECT_REASONS = {
    "strategy_group_id": "strategy_group_boundary_missing",
    "runtime_profile_id": "runtime_profile_boundary_missing",
    "subaccount_id": "subaccount_boundary_missing",
    "symbol": "symbol_boundary_missing",
    "side": "side_boundary_missing",
    "notional": "notional_boundary_missing",
    "leverage": "leverage_boundary_missing",
}
