from __future__ import annotations

from decimal import Decimal

from scripts.runtime_post_submit_finalize_probe import (
    build_runtime_post_submit_finalize_probe_packet,
)
from src.application.runtime_post_submit_finalize_service import (
    RuntimePostSubmitFinalizeService,
)
from src.domain.models import Direction, Position
from src.domain.runtime_post_submit_finalize import RuntimePostSubmitFinalizeStatus
from tests.unit.test_runtime_post_submit_finalize import (
    _ExistingSettlementRepo,
    _ready_review_no_fill_cancelled,
)
from tests.unit.test_runtime_execution_submit_outcome_review import (
    NOW_MS,
    _ExecutionResultRepo,
    _RuntimeService,
    _SubmitOutcomeReviewRepo,
    _runtime,
    _settlement,
    _submitted_result,
)


class _PositionRepo:
    def __init__(self, positions=None) -> None:
        self.positions = list(positions or [])

    async def list_active(self, *, symbol=None, limit=100):
        return [
            position
            for position in self.positions[:limit]
            if symbol is None or position.symbol == symbol
        ]


class _AdapterShouldNotRecord:
    async def record_submit_outcome_review_for_authorization(self, *args, **kwargs):
        raise AssertionError("existing review should be reused")

    async def settle_first_real_submit_budget_for_authorization(self, *args, **kwargs):
        raise AssertionError("existing settlement should be reused")


async def test_finalize_probe_uses_pg_position_projection_for_next_gate():
    result = _submitted_result()
    review = _ready_review_no_fill_cancelled()
    settlement = _settlement()
    finalize_service = RuntimePostSubmitFinalizeService(
        adapter_service=_AdapterShouldNotRecord(),
        exchange_submit_execution_result_repository=_ExecutionResultRepo(result),
        submit_outcome_review_repository=_SubmitOutcomeReviewRepo([review]),
        post_submit_budget_settlement_repository=_ExistingSettlementRepo(settlement),
        runtime_service=_RuntimeService(_runtime(boundary={"budget_reserved": Decimal("0")})),
    )

    packet = await build_runtime_post_submit_finalize_probe_packet(
        authorization_id="auth-1",
        reservation_id="runtime-attempt-reservation-auth-1",
        position_repository=_PositionRepo([]),
        finalize_service=finalize_service,
        execution_result_repository=_ExecutionResultRepo(result),
    )

    assert packet["status"] == (
        RuntimePostSubmitFinalizeStatus.FINALIZED_READY_FOR_NEXT_ATTEMPT.value
    )
    assert packet["active_position_facts"]["source"] == "pg_position_projection"
    assert packet["active_position_facts"]["active_positions_count"] == 0
    assert packet["post_submit_finalize_packet"]["pre_submit_rehearsal_retry_allowed"] is False
    assert packet["safety_invariants"]["exchange_write_called"] is False


async def test_finalize_probe_blocks_when_symbol_has_active_position_projection():
    result = _submitted_result()
    review = _ready_review_no_fill_cancelled()
    settlement = _settlement()
    finalize_service = RuntimePostSubmitFinalizeService(
        adapter_service=_AdapterShouldNotRecord(),
        exchange_submit_execution_result_repository=_ExecutionResultRepo(result),
        submit_outcome_review_repository=_SubmitOutcomeReviewRepo([review]),
        post_submit_budget_settlement_repository=_ExistingSettlementRepo(settlement),
        runtime_service=_RuntimeService(_runtime()),
    )

    packet = await build_runtime_post_submit_finalize_probe_packet(
        authorization_id="auth-1",
        reservation_id="runtime-attempt-reservation-auth-1",
        position_repository=_PositionRepo([_position(runtime_instance_id="runtime-1")]),
        finalize_service=finalize_service,
        execution_result_repository=_ExecutionResultRepo(result),
    )

    assert packet["next_attempt_gate_status"] == "blocked"
    assert "runtime_active_position_slot_in_use" in packet["next_attempt_blockers"]
    assert packet["active_position_facts"]["runtime_owned_count"] == 1


async def test_finalize_probe_missing_submit_result_blocks_without_user_fact_override():
    finalize_service = RuntimePostSubmitFinalizeService(
        adapter_service=_AdapterShouldNotRecord(),
        exchange_submit_execution_result_repository=_ExecutionResultRepo(
            _submitted_result()
        ),
        submit_outcome_review_repository=_SubmitOutcomeReviewRepo([]),
        post_submit_budget_settlement_repository=_ExistingSettlementRepo(_settlement()),
        runtime_service=_RuntimeService(_runtime()),
    )

    packet = await build_runtime_post_submit_finalize_probe_packet(
        authorization_id="missing-auth",
        reservation_id="runtime-attempt-reservation-auth-1",
        position_repository=_PositionRepo([]),
        finalize_service=finalize_service,
        execution_result_repository=_ExecutionResultRepo(_submitted_result()),
    )

    assert packet["status"] == "blocked"
    assert packet["active_position_facts"]["active_positions_count"] is None
    assert "exchange_submit_execution_result_not_found" in packet["blockers"]
    assert "trusted_active_positions_count_missing" in packet["next_attempt_blockers"]


def _position(*, runtime_instance_id: str | None) -> Position:
    return Position(
        id="pos-1",
        signal_id="signal-eval-1",
        symbol="BNB/USDT:USDT",
        direction=Direction.LONG,
        entry_price=Decimal("300"),
        current_qty=Decimal("1"),
        watermark_price=Decimal("300"),
        realized_pnl=Decimal("0"),
        total_fees_paid=Decimal("0"),
        opened_at=NOW_MS,
        closed_at=None,
        is_closed=False,
        runtime_instance_id=runtime_instance_id,
        trial_binding_id="binding-1",
        strategy_family_id="CPM-001",
        strategy_family_version_id="CPM-001-v0",
        signal_evaluation_id="signal-eval-1",
        order_candidate_id="candidate-1",
    )
