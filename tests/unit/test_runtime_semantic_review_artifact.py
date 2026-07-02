from __future__ import annotations

from decimal import Decimal

from src.domain.live_lifecycle_review import BrcLiveLifecycleReviewRecord
from src.domain.runtime_semantic_review_artifact import (
    build_runtime_semantic_review_artifact,
    summarize_runtime_semantic_review_artifacts,
)


def _record(**overrides) -> BrcLiveLifecycleReviewRecord:
    values = {
        "review_id": "live-review-1",
        "authorization_id": "auth-1",
        "carrier_id": "CPM-001-live-readonly-v0",
        "strategy_family_id": "CPM-001",
        "strategy_family_version_id": "CPM-001-v0",
        "runtime_instance_id": "runtime-1",
        "trial_binding_id": "trial-binding-1",
        "signal_evaluation_id": "signal-evaluation-1",
        "order_candidate_id": "order-candidate-1",
        "execution_intent_id": "intent-1",
        "symbol": "BNB/USDT:USDT",
        "side": "long",
        "quantity": "0.01",
        "lifecycle_status": "closed_reviewed",
        "review_status": "closed_reviewed",
        "final_gate_result": "passed",
        "protection_status": "tp_filled_sibling_sl_canceled",
        "evidence_refs": ["evidence://review/1"],
        "metadata": {
            "right_tail_trade_path": {
                "entry_price": "100",
                "exit_price": "115",
                "mfe_price": "118",
                "mae_price": "98",
                "realized_pnl": "15",
                "max_loss_budget": "3",
                "opened_at_ms": 1780496600000,
                "closed_at_ms": 1780497600000,
                "runner_preserved": True,
            }
        },
        "created_at_ms": 1780496600000,
        "updated_at_ms": 1780497600000,
    }
    values.update(overrides)
    return BrcLiveLifecycleReviewRecord(**values)


def test_runtime_semantic_review_artifact_reviews_explicit_right_tail_path() -> None:
    artifact = build_runtime_semantic_review_artifact(_record())

    assert artifact.artifact_id == "runtime-semantic-review-artifact:live-review-1"
    assert artifact.semantic_trace_complete is True
    assert artifact.missing_semantic_ids == []
    assert artifact.right_tail_review_status == "reviewed"
    assert artifact.right_tail_review is not None
    assert artifact.right_tail_review.classification.value == "right_tail_win"
    assert artifact.right_tail_review.r_multiple == Decimal("5.0000")
    assert artifact.strategy_family_id == "CPM-001"
    assert artifact.strategy_family_version_id == "CPM-001-v0"
    assert artifact.runtime_instance_id == "runtime-1"
    assert artifact.trial_binding_id == "trial-binding-1"
    assert artifact.signal_evaluation_id == "signal-evaluation-1"
    assert artifact.order_candidate_id == "order-candidate-1"
    assert artifact.execution_intent_id == "intent-1"
    assert artifact.not_order is True
    assert artifact.not_execution_intent is True
    assert artifact.not_trading_authority is True
    assert artifact.not_future_live_authorization is True
    assert artifact.cannot_authorize_future_live_action is True
    assert artifact.cannot_authorize_fresh_submit is True
    assert artifact.creates_runtime_authorization is False
    assert artifact.places_order is False
    assert artifact.creates_execution_intent is False
    assert artifact.calls_exchange is False
    assert artifact.mutates_exchange is False
    assert artifact.mutates_runtime_budget is False
    assert artifact.mutates_strategy_pnl is False
    assert artifact.creates_withdrawal_instruction is False
    assert "packet_id" not in artifact.model_dump(mode="json")


def test_runtime_semantic_review_artifact_requires_explicit_trade_path_metadata() -> None:
    artifact = build_runtime_semantic_review_artifact(_record(metadata={}))

    assert artifact.right_tail_review_status == "review_inputs_required"
    assert artifact.right_tail_review is None
    assert artifact.required_inputs == [
        "live_lifecycle_review.metadata.right_tail_trade_path"
    ]
    assert "right_tail_trade_path_missing" in artifact.warnings
    assert artifact.places_order is False
    assert artifact.creates_execution_intent is False
    assert artifact.calls_exchange is False


def test_runtime_semantic_review_artifact_marks_missing_semantic_trace() -> None:
    artifact = build_runtime_semantic_review_artifact(
        _record(
            strategy_family_version_id=None,
            runtime_instance_id=None,
            trial_binding_id=None,
            signal_evaluation_id=None,
            order_candidate_id=None,
            execution_intent_id=None,
        )
    )

    assert artifact.semantic_trace_complete is False
    assert set(artifact.missing_semantic_ids) == {
        "strategy_family_version_id",
        "runtime_instance_id",
        "trial_binding_id",
        "signal_evaluation_id",
        "order_candidate_id",
        "execution_intent_id",
    }
    assert "runtime_semantic_trace_incomplete" in artifact.warnings


def test_runtime_semantic_review_artifact_summary_is_non_executing() -> None:
    summary = summarize_runtime_semantic_review_artifacts([_record(), _record(metadata={})])

    assert summary.status == "review_inputs_required"
    assert summary.artifact_count == 2
    assert summary.reviewed_artifact_count == 1
    assert summary.missing_input_artifact_count == 1
    assert summary.semantic_trace_complete_count == 2
    assert summary.no_action_guarantee["places_order"] is False
    assert summary.no_action_guarantee["creates_execution_intent"] is False
    assert summary.no_action_guarantee["calls_exchange"] is False
    assert summary.no_action_guarantee["creates_runtime_authorization"] is False
    assert summary.no_action_guarantee["authorizes_future_live_action"] is False
    assert summary.no_action_guarantee["authorizes_fresh_submit"] is False
    assert summary.no_action_guarantee["mutates_exchange"] is False
    assert summary.no_action_guarantee["mutates_runtime_budget"] is False
    assert summary.no_action_guarantee["mutates_strategy_pnl"] is False
    assert summary.no_action_guarantee["creates_withdrawal_instruction"] is False
    dumped = summary.model_dump(mode="json")
    assert "packets" not in dumped
    assert "packet_count" not in dumped
