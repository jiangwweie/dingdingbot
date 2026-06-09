from __future__ import annotations

from decimal import Decimal

from src.domain.live_lifecycle_review import BrcLiveLifecycleReviewRecord
from src.domain.runtime_semantic_review_packet import (
    build_runtime_semantic_review_packet,
    summarize_runtime_semantic_review_packets,
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


def test_runtime_semantic_review_packet_reviews_explicit_right_tail_path() -> None:
    packet = build_runtime_semantic_review_packet(_record())

    assert packet.packet_id == "runtime-semantic-review-packet:live-review-1"
    assert packet.semantic_trace_complete is True
    assert packet.missing_semantic_ids == []
    assert packet.right_tail_review_status == "reviewed"
    assert packet.right_tail_review is not None
    assert packet.right_tail_review.classification.value == "right_tail_win"
    assert packet.right_tail_review.r_multiple == Decimal("5.0000")
    assert packet.strategy_family_id == "CPM-001"
    assert packet.strategy_family_version_id == "CPM-001-v0"
    assert packet.runtime_instance_id == "runtime-1"
    assert packet.trial_binding_id == "trial-binding-1"
    assert packet.signal_evaluation_id == "signal-evaluation-1"
    assert packet.order_candidate_id == "order-candidate-1"
    assert packet.execution_intent_id == "intent-1"
    assert packet.not_order is True
    assert packet.not_execution_intent is True
    assert packet.not_trading_authority is True
    assert packet.places_order is False
    assert packet.creates_execution_intent is False
    assert packet.calls_exchange is False
    assert packet.mutates_exchange is False
    assert packet.mutates_runtime_budget is False
    assert packet.mutates_strategy_pnl is False
    assert packet.creates_withdrawal_instruction is False


def test_runtime_semantic_review_packet_requires_explicit_trade_path_metadata() -> None:
    packet = build_runtime_semantic_review_packet(_record(metadata={}))

    assert packet.right_tail_review_status == "review_inputs_required"
    assert packet.right_tail_review is None
    assert packet.required_inputs == [
        "live_lifecycle_review.metadata.right_tail_trade_path"
    ]
    assert "right_tail_trade_path_missing" in packet.warnings
    assert packet.places_order is False
    assert packet.creates_execution_intent is False
    assert packet.calls_exchange is False


def test_runtime_semantic_review_packet_marks_missing_semantic_trace() -> None:
    packet = build_runtime_semantic_review_packet(
        _record(
            strategy_family_version_id=None,
            runtime_instance_id=None,
            trial_binding_id=None,
            signal_evaluation_id=None,
            order_candidate_id=None,
            execution_intent_id=None,
        )
    )

    assert packet.semantic_trace_complete is False
    assert set(packet.missing_semantic_ids) == {
        "strategy_family_version_id",
        "runtime_instance_id",
        "trial_binding_id",
        "signal_evaluation_id",
        "order_candidate_id",
        "execution_intent_id",
    }
    assert "runtime_semantic_trace_incomplete" in packet.warnings


def test_runtime_semantic_review_packet_summary_is_non_executing() -> None:
    summary = summarize_runtime_semantic_review_packets([_record(), _record(metadata={})])

    assert summary.status == "review_inputs_required"
    assert summary.packet_count == 2
    assert summary.reviewed_packet_count == 1
    assert summary.missing_input_packet_count == 1
    assert summary.semantic_trace_complete_count == 2
    assert summary.no_action_guarantee["places_order"] is False
    assert summary.no_action_guarantee["creates_execution_intent"] is False
    assert summary.no_action_guarantee["calls_exchange"] is False
    assert summary.no_action_guarantee["mutates_exchange"] is False
    assert summary.no_action_guarantee["mutates_runtime_budget"] is False
    assert summary.no_action_guarantee["mutates_strategy_pnl"] is False
    assert summary.no_action_guarantee["creates_withdrawal_instruction"] is False
