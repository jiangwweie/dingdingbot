from __future__ import annotations

from decimal import Decimal

import pytest

from src.application.runtime_post_submit_finalize_service import (
    RuntimePostSubmitFinalizeService,
)
from src.domain.runtime_execution_post_submit_budget_settlement import (
    RuntimeExecutionPostSubmitBudgetSettlementStatus,
)
from src.domain.runtime_post_submit_finalize import (
    RuntimeNextAttemptGateStatus,
    RuntimePostSubmitFinalizePayload,
    RuntimePostSubmitFinalizeStatus,
    build_runtime_post_submit_finalize_payload,
)
from tests.unit.test_runtime_execution_submit_outcome_review import (
    NOW_MS,
    _AttemptMutationRepo,
    _AttemptOutcomePolicyRepo,
    _AttemptReservationRepo,
    _ExecutionResultRepo,
    _Lifecycle,
    _PostSubmitBudgetSettlementRepo,
    _ReconciliationReadModelRepo,
    _RuntimeService,
    _SubmitOutcomeReviewRepo,
    _DraftRepo,
    _clean_reconciliation_report,
    _order,
    _reservation,
    _runtime,
    _settlement,
    _submitted_result,
    _mutation,
)
from src.application.runtime_execution_intent_adapter_service import (
    RuntimeExecutionIntentAdapterService,
)
from src.domain.models import OrderRole, OrderStatus


def test_post_submit_finalize_ready_after_no_fill_settlement():
    runtime = _runtime(boundary={"budget_reserved": Decimal("0")})
    result = _submitted_result()
    review = _ready_review_no_fill_cancelled()
    settlement = _settlement(
        status=RuntimeExecutionPostSubmitBudgetSettlementStatus
        .RELEASED_RESERVED_BUDGET,
        budget_reserved_after=Decimal("0"),
        budget_remaining_after=Decimal("30"),
        budget_released=True,
        reserved_budget_remains_held=False,
        requires_reconciliation_before_retry=True,
        blocks_new_entries_until_resolved=False,
    )

    packet = build_runtime_post_submit_finalize_payload(
        authorization_id="auth-1",
        runtime=runtime,
        exchange_submit_execution_result=result,
        submit_outcome_review=review,
        post_submit_budget_settlement=settlement,
        active_positions_count=0,
        closed_review_required=False,
        now_ms=NOW_MS,
    )

    assert packet.status == (
        RuntimePostSubmitFinalizeStatus.FINALIZED_READY_FOR_NEXT_ATTEMPT
    )
    assert packet.consumed_authorization_replay_only is True
    assert packet.pre_submit_rehearsal_retry_allowed is False
    assert packet.local_created_order_requirement_retired is True
    assert packet.next_attempt_gate.status == (
        RuntimeNextAttemptGateStatus.READY_FOR_FRESH_SIGNAL
    )
    assert packet.next_attempt_gate.requires_fresh_strategy_signal is True
    assert packet.next_attempt_gate.requires_fresh_authorization is True
    assert packet.post_submit_reconciliation_evidence_id
    assert packet.post_submit_finalize_complete is True
    assert packet.post_submit_reconciliation_matched is True
    assert packet.post_submit_budget_settled is True
    assert packet.submit_outcome_review_recorded is True
    payload = packet.model_dump(mode="python")
    assert payload["runtime_state_mutated_by_payload"] is False
    assert "runtime_state_mutated_by_packet" not in payload
    assert packet.exchange_called is False
    assert packet.order_lifecycle_called is False


def test_post_submit_finalize_rejects_legacy_packet_mutation_flag():
    payload = build_runtime_post_submit_finalize_payload(
        authorization_id="auth-1",
        runtime=_runtime(boundary={"budget_reserved": Decimal("0")}),
        exchange_submit_execution_result=_submitted_result(),
        submit_outcome_review=_ready_review_no_fill_cancelled(),
        post_submit_budget_settlement=_settlement(
            status=RuntimeExecutionPostSubmitBudgetSettlementStatus
            .RELEASED_RESERVED_BUDGET,
            budget_reserved_after=Decimal("0"),
            budget_remaining_after=Decimal("30"),
            budget_released=True,
            reserved_budget_remains_held=False,
            requires_reconciliation_before_retry=True,
            blocks_new_entries_until_resolved=False,
        ),
        active_positions_count=0,
        closed_review_required=False,
        now_ms=NOW_MS,
    ).model_dump(mode="python")
    payload["runtime_state_mutated_by_packet"] = False
    payload.pop("runtime_state_mutated_by_payload")

    with pytest.raises(ValueError):
        RuntimePostSubmitFinalizePayload.model_validate(payload)


def test_post_submit_finalize_blocks_next_attempt_when_active_position_slot_used():
    runtime = _runtime()
    result = _submitted_result()
    review = _ready_review_full_fill()
    settlement = _settlement(
        status=RuntimeExecutionPostSubmitBudgetSettlementStatus
        .RECORDED_RESERVED_BUDGET_CONSUMED,
        budget_action="confirm_reserved_budget_consumed",
        outcome_kind="submitted_full_fill",
        budget_release_amount=Decimal("0"),
        budget_released=False,
        budget_consumption_recorded=True,
        reserved_budget_remains_held=False,
        runtime_budget_mutated=False,
        blocks_new_entries_until_resolved=False,
    )

    packet = build_runtime_post_submit_finalize_payload(
        authorization_id="auth-1",
        runtime=runtime,
        exchange_submit_execution_result=result,
        submit_outcome_review=review,
        post_submit_budget_settlement=settlement,
        active_positions_count=1,
        closed_review_required=False,
        now_ms=NOW_MS,
    )

    assert packet.status == (
        RuntimePostSubmitFinalizeStatus.FINALIZED_NEXT_ATTEMPT_BLOCKED
    )
    assert packet.blockers == []
    assert packet.post_submit_reconciliation_evidence_id
    assert packet.post_submit_finalize_complete is True
    assert packet.post_submit_reconciliation_matched is True
    assert packet.post_submit_budget_settled is True
    assert packet.submit_outcome_review_recorded is True
    assert "runtime_active_position_slot_in_use" in (
        packet.next_attempt_gate.blockers
    )
    assert packet.old_authorization_submit_retry_allowed is False


def test_post_submit_finalize_blocks_missing_trusted_active_position_fact():
    packet = build_runtime_post_submit_finalize_payload(
        authorization_id="auth-1",
        runtime=_runtime(),
        exchange_submit_execution_result=_submitted_result(),
        submit_outcome_review=_ready_review_no_fill_cancelled(),
        post_submit_budget_settlement=_settlement(),
        active_positions_count=None,
        closed_review_required=False,
        now_ms=NOW_MS,
    )

    assert packet.status == (
        RuntimePostSubmitFinalizeStatus.FINALIZED_NEXT_ATTEMPT_BLOCKED
    )
    assert "trusted_active_positions_count_missing" in (
        packet.next_attempt_gate.blockers
    )


async def test_post_submit_finalize_service_reuses_existing_review_and_settlement():
    result = _submitted_result()
    review = _ready_review_no_fill_cancelled()
    settlement = _settlement()
    adapter = _AdapterShouldNotRecord()
    service = RuntimePostSubmitFinalizeService(
        adapter_service=adapter,
        exchange_submit_execution_result_repository=_ExecutionResultRepo(result),
        submit_outcome_review_repository=_SubmitOutcomeReviewRepo([review]),
        post_submit_budget_settlement_repository=_ExistingSettlementRepo(
            settlement
        ),
        runtime_service=_RuntimeService(
            _runtime(boundary={"budget_reserved": Decimal("0")})
        ),
    )

    packet = await service.finalize_authorization(
        "auth-1",
        reservation_id="runtime-attempt-reservation-auth-1",
        active_positions_count=0,
    )

    assert packet.status == (
        RuntimePostSubmitFinalizeStatus.FINALIZED_READY_FOR_NEXT_ATTEMPT
    )
    assert adapter.review_record_calls == 0
    assert adapter.settlement_record_calls == 0
    assert "submit_outcome_review_existing_reused" in packet.warnings
    assert "post_submit_budget_settlement_existing_reused" in packet.warnings


async def test_post_submit_finalize_service_records_missing_post_submit_facts_once():
    result = _submitted_result()
    entry = _order("entry-1", OrderRole.ENTRY, OrderStatus.CANCELED, Decimal("0"))
    sl = _order("sl-1", OrderRole.SL, OrderStatus.CANCELED, Decimal("0"))
    reservation = _reservation()
    mutation = _mutation(reservation)
    review_repo = _SubmitOutcomeReviewRepo()
    settlement_repo = _PostSubmitBudgetSettlementRepoWithLookup()
    runtime_service = _RuntimeService(_runtime())
    adapter = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftRepo(),
        exchange_submit_execution_result_repository=_ExecutionResultRepo(result),
        order_lifecycle_service=_Lifecycle([entry, sl]),
        submit_outcome_review_repository=review_repo,
        attempt_reservation_repository=_AttemptReservationRepo(reservation),
        attempt_mutation_repository=_AttemptMutationRepo(mutation),
        attempt_outcome_policy_repository=_AttemptOutcomePolicyRepo(),
        post_submit_budget_settlement_repository=settlement_repo,
        runtime_service=runtime_service,
        reconciliation_read_model_repository=_ReconciliationReadModelRepo(
            [_clean_reconciliation_report()]
        ),
    )
    service = RuntimePostSubmitFinalizeService(
        adapter_service=adapter,
        exchange_submit_execution_result_repository=_ExecutionResultRepo(result),
        submit_outcome_review_repository=review_repo,
        post_submit_budget_settlement_repository=settlement_repo,
        runtime_service=runtime_service,
    )

    packet = await service.finalize_authorization(
        "auth-1",
        reservation_id=reservation.reservation_id,
        active_positions_count=0,
    )

    assert packet.status == (
        RuntimePostSubmitFinalizeStatus.FINALIZED_READY_FOR_NEXT_ATTEMPT
    )
    assert len(review_repo.created) == 1
    assert len(settlement_repo.created) == 1
    assert runtime_service.runtime.boundary.budget_reserved == Decimal("0")
    assert packet.exchange_order_submitted is False
    assert packet.order_created is False


async def test_post_submit_finalize_service_resolves_latest_runtime_submit_result():
    result = _submitted_result()
    review = _ready_review_no_fill_cancelled()
    settlement = _settlement()
    service = RuntimePostSubmitFinalizeService(
        adapter_service=_AdapterShouldNotRecord(),
        exchange_submit_execution_result_repository=_LatestExecutionResultRepo(
            result
        ),
        submit_outcome_review_repository=_SubmitOutcomeReviewRepo([review]),
        post_submit_budget_settlement_repository=_ExistingSettlementRepo(
            settlement
        ),
        runtime_service=_RuntimeService(
            _runtime(boundary={"budget_reserved": Decimal("0")})
        ),
    )

    packet = await service.finalize_latest_for_runtime(
        "runtime-1",
        reservation_id="runtime-attempt-reservation-auth-1",
        active_positions_count=0,
    )

    assert packet.status == (
        RuntimePostSubmitFinalizeStatus.FINALIZED_READY_FOR_NEXT_ATTEMPT
    )
    assert packet.authorization_id == "auth-1"
    assert packet.exchange_submit_execution_result_id == "exchange-submit-result-1"
    assert packet.pre_submit_rehearsal_retry_allowed is False
    assert packet.next_attempt_gate.requires_fresh_strategy_signal is True


async def test_post_submit_finalize_service_resolves_reservation_id_for_latest_runtime_submit():
    result = _submitted_result()
    review = _ready_review_no_fill_cancelled()
    reservation = _reservation()
    settlement_repo = _PostSubmitBudgetSettlementRepoWithLookup()
    adapter = _AdapterRecordsSettlement(_settlement())
    service = RuntimePostSubmitFinalizeService(
        adapter_service=adapter,
        exchange_submit_execution_result_repository=_LatestExecutionResultRepo(
            result
        ),
        submit_outcome_review_repository=_SubmitOutcomeReviewRepo([review]),
        post_submit_budget_settlement_repository=settlement_repo,
        attempt_reservation_repository=_AttemptReservationByAuthorizationRepo(
            reservation
        ),
        runtime_service=_RuntimeService(
            _runtime(boundary={"budget_reserved": Decimal("0")})
        ),
    )

    packet = await service.finalize_latest_for_runtime(
        "runtime-1",
        active_positions_count=0,
    )

    assert packet.status == (
        RuntimePostSubmitFinalizeStatus.FINALIZED_READY_FOR_NEXT_ATTEMPT
    )
    assert adapter.settlement_calls == [
        {
            "authorization_id": "auth-1",
            "reservation_id": "runtime-attempt-reservation-auth-1",
        }
    ]
    assert "reservation_id_resolved_from_attempt_reservation" in packet.warnings
    assert packet.pre_submit_rehearsal_retry_allowed is False


async def test_post_submit_finalize_service_blocks_missing_reservation_resolution():
    result = _submitted_result()
    review = _ready_review_no_fill_cancelled()
    service = RuntimePostSubmitFinalizeService(
        adapter_service=_AdapterRecordsSettlement(_settlement()),
        exchange_submit_execution_result_repository=_LatestExecutionResultRepo(
            result
        ),
        submit_outcome_review_repository=_SubmitOutcomeReviewRepo([review]),
        post_submit_budget_settlement_repository=(
            _PostSubmitBudgetSettlementRepoWithLookup()
        ),
        runtime_service=_RuntimeService(
            _runtime(boundary={"budget_reserved": Decimal("0")})
        ),
    )

    packet = await service.finalize_latest_for_runtime(
        "runtime-1",
        active_positions_count=0,
    )

    assert packet.status == RuntimePostSubmitFinalizeStatus.BLOCKED
    assert "attempt_reservation_repository_unavailable" in packet.blockers
    assert packet.pre_submit_rehearsal_retry_allowed is False


async def test_post_submit_finalize_service_blocks_expected_runtime_mismatch():
    result = _submitted_result().model_copy(update={"runtime_instance_id": "other"})
    review = _ready_review_no_fill_cancelled()
    settlement = _settlement()
    service = RuntimePostSubmitFinalizeService(
        adapter_service=_AdapterShouldNotRecord(),
        exchange_submit_execution_result_repository=_ExecutionResultRepo(result),
        submit_outcome_review_repository=_SubmitOutcomeReviewRepo([review]),
        post_submit_budget_settlement_repository=_ExistingSettlementRepo(
            settlement
        ),
        runtime_service=_RuntimeService(_runtime()),
    )

    packet = await service.finalize_authorization(
        "auth-1",
        reservation_id="runtime-attempt-reservation-auth-1",
        active_positions_count=0,
        expected_runtime_instance_id="runtime-1",
    )

    assert packet.status == RuntimePostSubmitFinalizeStatus.BLOCKED
    assert "exchange_submit_execution_result_runtime_mismatch" in packet.blockers
    assert packet.pre_submit_rehearsal_retry_allowed is False


def test_post_submit_finalize_payload_requires_fresh_authorization_after_no_fill():
    packet = build_runtime_post_submit_finalize_payload(
        authorization_id="auth-1",
        runtime=_runtime(boundary={"budget_reserved": Decimal("0")}),
        exchange_submit_execution_result=_submitted_result(),
        submit_outcome_review=_ready_review_no_fill_cancelled(),
        post_submit_budget_settlement=_settlement(),
        active_positions_count=0,
        closed_review_required=False,
        now_ms=NOW_MS,
    )

    assert packet.status == (
        RuntimePostSubmitFinalizeStatus.FINALIZED_READY_FOR_NEXT_ATTEMPT
    )
    assert packet.next_attempt_gate.requires_fresh_authorization is True


def _ready_review_no_fill_cancelled():
    result = _submitted_result()
    from src.domain.runtime_execution_submit_outcome_review import (
        build_runtime_execution_submit_outcome_review,
    )

    return build_runtime_execution_submit_outcome_review(
        exchange_submit_execution_result=result,
        local_orders=[
            _order("entry-1", OrderRole.ENTRY, OrderStatus.CANCELED, Decimal("0")),
            _order("sl-1", OrderRole.SL, OrderStatus.CANCELED, Decimal("0")),
        ],
        post_submit_reconciliation_report=_clean_reconciliation_report(),
        now_ms=NOW_MS,
    )


def _ready_review_full_fill():
    result = _submitted_result()
    from src.domain.runtime_execution_submit_outcome_review import (
        build_runtime_execution_submit_outcome_review,
    )

    return build_runtime_execution_submit_outcome_review(
        exchange_submit_execution_result=result,
        local_orders=[
            _order("entry-1", OrderRole.ENTRY, OrderStatus.FILLED, Decimal("1")),
            _order("sl-1", OrderRole.SL, OrderStatus.OPEN, Decimal("0")),
        ],
        post_submit_reconciliation_report=_clean_reconciliation_report(),
        now_ms=NOW_MS,
    )


class _ExistingSettlementRepo:
    def __init__(self, settlement) -> None:
        self.settlement = settlement

    async def get_by_authorization_id(self, authorization_id):
        if self.settlement.authorization_id == authorization_id:
            return self.settlement
        return None


class _PostSubmitBudgetSettlementRepoWithLookup(_PostSubmitBudgetSettlementRepo):
    async def get_by_authorization_id(self, authorization_id):
        return next(
            (
                settlement
                for settlement in self.created
                if settlement.authorization_id == authorization_id
            ),
            None,
        )


class _LatestExecutionResultRepo(_ExecutionResultRepo):
    async def get_latest_by_runtime_instance_id(self, runtime_instance_id):
        if self.result.runtime_instance_id == runtime_instance_id:
            return self.result
        return None


class _AttemptReservationByAuthorizationRepo:
    def __init__(self, reservation) -> None:
        self.reservation = reservation

    async def get_by_authorization_id(self, authorization_id):
        if self.reservation.authorization_id == authorization_id:
            return self.reservation
        return None


class _AdapterRecordsSettlement:
    def __init__(self, settlement) -> None:
        self.settlement = settlement
        self.settlement_calls = []

    async def record_submit_outcome_review_for_authorization(self, *args, **kwargs):
        raise AssertionError("existing review should be reused")

    async def settle_first_real_submit_budget_for_authorization(
        self,
        authorization_id,
        *,
        reservation_id,
    ):
        self.settlement_calls.append(
            {
                "authorization_id": authorization_id,
                "reservation_id": reservation_id,
            }
        )
        return self.settlement


class _AdapterShouldNotRecord:
    def __init__(self) -> None:
        self.review_record_calls = 0
        self.settlement_record_calls = 0

    async def record_submit_outcome_review_for_authorization(self, *args, **kwargs):
        self.review_record_calls += 1
        raise AssertionError("existing review should be reused")

    async def settle_first_real_submit_budget_for_authorization(self, *args, **kwargs):
        self.settlement_record_calls += 1
        raise AssertionError("existing settlement should be reused")
