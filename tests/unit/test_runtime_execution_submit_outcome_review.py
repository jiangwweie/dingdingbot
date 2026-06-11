from __future__ import annotations

import importlib.util
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.application.runtime_execution_intent_adapter_service import (
    RuntimeExecutionIntentAdapterService,
)
from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.models import Direction, Order, OrderRole, OrderStatus, OrderType
from src.domain.runtime_execution_attempt_outcome_policy import (
    RuntimeExecutionAttemptOutcomeKind,
    RuntimeExecutionAttemptOutcomePolicyStatus,
)
from src.domain.runtime_execution_attempt_mutation import (
    RuntimeExecutionAttemptMutation,
    RuntimeExecutionAttemptMutationStatus,
)
from src.domain.runtime_execution_attempt_reservation import (
    RuntimeExecutionAttemptReservation,
    RuntimeExecutionAttemptReservationStatus,
)
from src.domain.runtime_execution_exchange_submit_execution_result import (
    RuntimeExecutionExchangeSubmitExecutionMode,
    RuntimeExecutionExchangeSubmitExecutionResult,
    RuntimeExecutionExchangeSubmitExecutionStatus,
    RuntimeExecutionSubmittedExchangeOrder,
)
from src.domain.runtime_execution_first_real_submit_outcome_accounting import (
    RuntimeExecutionFirstRealSubmitOutcomeAccountingStatus,
)
from src.domain.runtime_execution_submit_outcome_review import (
    RuntimeExecutionSubmitObservedOutcome,
    RuntimeExecutionSubmitOutcomeReviewStatus,
    build_runtime_execution_submit_outcome_review,
)
from src.infrastructure.pg_models import PGRuntimeExecutionSubmitOutcomeReviewORM
from src.infrastructure.pg_runtime_execution_submit_outcome_review_repository import (
    PgRuntimeExecutionSubmitOutcomeReviewRepository,
)
from src.interfaces import api_trading_console as trading_console_api


NOW_MS = 1781090000000


class _DraftRepo:
    async def get(self, draft_id: str):
        raise AssertionError("draft repository should not be used")


class _ExecutionResultRepo:
    def __init__(self, result) -> None:
        self.result = result

    async def get_by_authorization_id(self, authorization_id):
        if self.result.authorization_id == authorization_id:
            return self.result
        return None

    async def acquire_exchange_submit_execution_lock(self, result):
        raise AssertionError("lock should not be acquired by outcome review")

    async def complete_exchange_submit_execution_result(self, result):
        raise AssertionError("result should not be mutated by outcome review")


class _Lifecycle:
    def __init__(self, orders) -> None:
        self.orders = {order.id: order for order in orders}
        self.submit_calls = []

    async def register_created_order(self, order, *, metadata=None):
        raise AssertionError("orders should not be registered by outcome review")

    async def get_order(self, order_id: str):
        return self.orders.get(order_id)

    async def submit_order(self, order_id: str, exchange_order_id=None):
        self.submit_calls.append((order_id, exchange_order_id))
        raise AssertionError("orders should not be submitted by outcome review")


class _SubmitOutcomeReviewRepo:
    def __init__(self, items=None) -> None:
        self.created = list(items or [])

    async def create(self, review):
        self.created.append(review)
        return review

    async def get(self, review_id):
        return next(
            (review for review in self.created if review.review_id == review_id),
            None,
        )

    async def get_by_authorization_id(self, authorization_id):
        return next(
            (
                review
                for review in self.created
                if review.authorization_id == authorization_id
            ),
            None,
        )


class _AttemptReservationRepo:
    def __init__(self, reservation) -> None:
        self.reservation = reservation

    async def get(self, reservation_id):
        if self.reservation.reservation_id == reservation_id:
            return self.reservation
        return None

    async def create(self, reservation):
        self.reservation = reservation
        return reservation


class _AttemptMutationRepo:
    def __init__(self, mutation) -> None:
        self.mutation = mutation

    async def get(self, mutation_id):
        if self.mutation.mutation_id == mutation_id:
            return self.mutation
        return None

    async def create(self, mutation):
        self.mutation = mutation
        return mutation


class _AttemptOutcomePolicyRepo:
    def __init__(self) -> None:
        self.created = []

    async def create(self, policy):
        self.created.append(policy)
        return policy

    async def get(self, policy_id):
        return next(
            (policy for policy in self.created if policy.policy_id == policy_id),
            None,
        )


def test_submit_outcome_review_maps_entry_submit_failure_without_order_facts():
    result = _execution_result(
        RuntimeExecutionExchangeSubmitExecutionStatus.ENTRY_SUBMIT_FAILED,
        submitted_orders=[],
        failed_local_order_id="entry-1",
        failed_order_role="ENTRY",
        failed_reason="TEST_REJECT",
        exchange_call_count=1,
        order_lifecycle_submit_call_count=0,
        exchange_called=True,
        exchange_order_submitted=False,
        order_lifecycle_submit_called=False,
        blockers=["entry_submit_failed"],
    )

    review = build_runtime_execution_submit_outcome_review(
        exchange_submit_execution_result=result,
        local_orders=[],
        now_ms=NOW_MS,
    )

    assert review.status == (
        RuntimeExecutionSubmitOutcomeReviewStatus
        .CLASSIFIED_READY_FOR_ATTEMPT_OUTCOME_POLICY
    )
    assert review.observed_outcome == (
        RuntimeExecutionSubmitObservedOutcome
        .ENTRY_SUBMIT_REJECTED_BEFORE_EXCHANGE
    )
    assert review.recommended_attempt_outcome_kind == (
        RuntimeExecutionAttemptOutcomeKind.SUBMIT_REJECTED_BEFORE_EXCHANGE
    )
    assert review.no_fill is True
    assert review.any_fill is False
    assert review.exchange_called is False
    assert review.order_lifecycle_called is False


def test_submit_outcome_review_blocks_open_no_fill_until_resolved():
    result = _submitted_result()
    entry = _order("entry-1", OrderRole.ENTRY, OrderStatus.OPEN, Decimal("0"))
    sl = _order("sl-1", OrderRole.SL, OrderStatus.OPEN, Decimal("0"))

    review = build_runtime_execution_submit_outcome_review(
        exchange_submit_execution_result=result,
        local_orders=[entry, sl],
        now_ms=NOW_MS,
    )

    assert review.status == RuntimeExecutionSubmitOutcomeReviewStatus.BLOCKED
    assert review.observed_outcome == (
        RuntimeExecutionSubmitObservedOutcome.SUBMITTED_NO_FILL_OPEN
    )
    assert review.recommended_attempt_outcome_kind is None
    assert "entry_order_still_open_no_fill_unresolved" in review.blockers
    assert review.blocks_attempt_outcome_policy_until_resolved is True
    assert review.attempt_outcome_policy_ready is False


def test_submit_outcome_review_maps_no_fill_cancel_to_release_policy_kind():
    result = _submitted_result()
    entry = _order("entry-1", OrderRole.ENTRY, OrderStatus.CANCELED, Decimal("0"))
    sl = _order("sl-1", OrderRole.SL, OrderStatus.CANCELED, Decimal("0"))

    review = build_runtime_execution_submit_outcome_review(
        exchange_submit_execution_result=result,
        local_orders=[entry, sl],
        now_ms=NOW_MS,
    )

    assert review.status == (
        RuntimeExecutionSubmitOutcomeReviewStatus
        .CLASSIFIED_READY_FOR_ATTEMPT_OUTCOME_POLICY
    )
    assert review.observed_outcome == (
        RuntimeExecutionSubmitObservedOutcome.SUBMITTED_NO_FILL_CANCELLED
    )
    assert review.recommended_attempt_outcome_kind == (
        RuntimeExecutionAttemptOutcomeKind.SUBMITTED_NO_FILL_CANCELLED
    )
    assert review.no_fill is True
    assert review.requires_reconciliation_before_retry is True
    assert review.runtime_state_mutated is False
    assert review.budget_released is False


@pytest.mark.parametrize(
    ("filled_qty", "expected_outcome", "expected_kind", "partial", "full"),
    [
        (
            Decimal("0.4"),
            RuntimeExecutionSubmitObservedOutcome.SUBMITTED_PARTIAL_FILL,
            RuntimeExecutionAttemptOutcomeKind.SUBMITTED_PARTIAL_FILL,
            True,
            False,
        ),
        (
            Decimal("1"),
            RuntimeExecutionSubmitObservedOutcome.SUBMITTED_FULL_FILL,
            RuntimeExecutionAttemptOutcomeKind.SUBMITTED_FULL_FILL,
            False,
            True,
        ),
    ],
)
def test_submit_outcome_review_maps_fill_states_to_attempt_outcome_kind(
    filled_qty,
    expected_outcome,
    expected_kind,
    partial,
    full,
):
    result = _submitted_result()
    status = OrderStatus.PARTIALLY_FILLED if partial else OrderStatus.FILLED
    entry = _order("entry-1", OrderRole.ENTRY, status, filled_qty)
    sl = _order("sl-1", OrderRole.SL, OrderStatus.OPEN, Decimal("0"))

    review = build_runtime_execution_submit_outcome_review(
        exchange_submit_execution_result=result,
        local_orders=[entry, sl],
        now_ms=NOW_MS,
    )

    assert review.status == (
        RuntimeExecutionSubmitOutcomeReviewStatus
        .CLASSIFIED_READY_FOR_ATTEMPT_OUTCOME_POLICY
    )
    assert review.observed_outcome == expected_outcome
    assert review.recommended_attempt_outcome_kind == expected_kind
    assert review.any_fill is True
    assert review.partial_fill is partial
    assert review.full_fill is full
    assert review.exchange_order_submitted is False


def test_submit_outcome_review_maps_filled_entry_protection_failure():
    result = _execution_result(
        RuntimeExecutionExchangeSubmitExecutionStatus.PROTECTION_SUBMIT_FAILED,
        submitted_orders=[
            _submitted_order("entry-1", "ENTRY", "ex-entry", lifecycle_called=True),
        ],
        failed_local_order_id="sl-1",
        failed_order_role="SL",
        failed_reason="TEST_PROTECTION_REJECT",
        exchange_call_count=2,
        order_lifecycle_submit_call_count=1,
        exchange_called=True,
        exchange_order_submitted=True,
        order_lifecycle_submit_called=True,
        blockers=["protection_submit_failed_after_entry_submit"],
    )
    entry = _order("entry-1", OrderRole.ENTRY, OrderStatus.FILLED, Decimal("1"))
    sl = _order("sl-1", OrderRole.SL, OrderStatus.CREATED, Decimal("0"))

    review = build_runtime_execution_submit_outcome_review(
        exchange_submit_execution_result=result,
        local_orders=[entry, sl],
        now_ms=NOW_MS,
    )

    assert review.status == (
        RuntimeExecutionSubmitOutcomeReviewStatus
        .CLASSIFIED_READY_FOR_ATTEMPT_OUTCOME_POLICY
    )
    assert review.observed_outcome == (
        RuntimeExecutionSubmitObservedOutcome
        .ENTRY_FILLED_PROTECTION_CREATION_FAILED
    )
    assert review.recommended_attempt_outcome_kind == (
        RuntimeExecutionAttemptOutcomeKind
        .ENTRY_FILLED_PROTECTION_CREATION_FAILED
    )
    assert review.protection_creation_failed is True
    assert review.requires_reconciliation_before_retry is True
    assert review.owner_bounded_execution_called is False


async def test_submit_outcome_review_service_reads_existing_result_and_orders_only():
    result = _submitted_result()
    entry = _order("entry-1", OrderRole.ENTRY, OrderStatus.FILLED, Decimal("1"))
    sl = _order("sl-1", OrderRole.SL, OrderStatus.OPEN, Decimal("0"))
    lifecycle = _Lifecycle([entry, sl])
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftRepo(),
        exchange_submit_execution_result_repository=_ExecutionResultRepo(result),
        order_lifecycle_service=lifecycle,
    )

    review = await service.submit_outcome_review_for_authorization("auth-1")

    assert review.recommended_attempt_outcome_kind == (
        RuntimeExecutionAttemptOutcomeKind.SUBMITTED_FULL_FILL
    )
    assert lifecycle.submit_calls == []
    assert review.order_lifecycle_called is False
    assert review.exchange_called is False


async def test_submit_outcome_review_service_blocks_when_order_facts_missing():
    result = _submitted_result()
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftRepo(),
        exchange_submit_execution_result_repository=_ExecutionResultRepo(result),
        order_lifecycle_service=_Lifecycle([]),
    )

    review = await service.submit_outcome_review_for_authorization("auth-1")

    assert review.status == RuntimeExecutionSubmitOutcomeReviewStatus.BLOCKED
    assert "entry_order_fact_missing" in review.blockers
    assert "protection_order_fact_missing" in review.blockers
    assert review.missing_order_ids == ["entry-1", "sl-1"]


async def test_submit_outcome_review_service_records_pg_style_evidence_only():
    result = _submitted_result()
    entry = _order("entry-1", OrderRole.ENTRY, OrderStatus.FILLED, Decimal("1"))
    sl = _order("sl-1", OrderRole.SL, OrderStatus.OPEN, Decimal("0"))
    review_repo = _SubmitOutcomeReviewRepo()
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftRepo(),
        exchange_submit_execution_result_repository=_ExecutionResultRepo(result),
        order_lifecycle_service=_Lifecycle([entry, sl]),
        submit_outcome_review_repository=review_repo,
    )

    review = await service.record_submit_outcome_review_for_authorization("auth-1")

    assert review_repo.created == [review]
    assert review.status == (
        RuntimeExecutionSubmitOutcomeReviewStatus
        .CLASSIFIED_READY_FOR_ATTEMPT_OUTCOME_POLICY
    )
    assert review.recommended_attempt_outcome_kind == (
        RuntimeExecutionAttemptOutcomeKind.SUBMITTED_FULL_FILL
    )
    assert review.exchange_called is False
    assert review.exchange_order_submitted is False
    assert review.order_lifecycle_called is False


async def test_attempt_outcome_policy_records_from_submit_outcome_review():
    result = _submitted_result()
    review = build_runtime_execution_submit_outcome_review(
        exchange_submit_execution_result=result,
        local_orders=[
            _order("entry-1", OrderRole.ENTRY, OrderStatus.FILLED, Decimal("1")),
            _order("sl-1", OrderRole.SL, OrderStatus.OPEN, Decimal("0")),
        ],
        now_ms=NOW_MS,
    )
    reservation = _reservation()
    mutation = _mutation(reservation)
    policy_repo = _AttemptOutcomePolicyRepo()
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftRepo(),
        attempt_reservation_repository=_AttemptReservationRepo(reservation),
        attempt_mutation_repository=_AttemptMutationRepo(mutation),
        attempt_outcome_policy_repository=policy_repo,
        submit_outcome_review_repository=_SubmitOutcomeReviewRepo([review]),
    )

    policy = await (
        service.record_attempt_outcome_policy_from_submit_outcome_review(
            reservation.reservation_id
        )
    )

    assert policy_repo.created == [policy]
    assert policy.status == (
        RuntimeExecutionAttemptOutcomePolicyStatus
        .READY_FOR_ATTEMPT_BUDGET_OUTCOME_ACCOUNTING
    )
    assert policy.outcome_kind == RuntimeExecutionAttemptOutcomeKind.SUBMITTED_FULL_FILL
    assert policy.budget_consumption_confirmed is True
    assert policy.metadata["submit_outcome_review_id"] == review.review_id
    assert policy.metadata["submit_observed_outcome"] == "submitted_full_fill"
    assert any(
        warning.startswith("derived_from_submit_outcome_review:")
        for warning in policy.warnings
    )
    assert policy.budget_released is False
    assert policy.exchange_called is False
    assert policy.order_lifecycle_called is False


async def test_attempt_outcome_policy_from_submit_outcome_review_blocks_unresolved():
    result = _submitted_result()
    review = build_runtime_execution_submit_outcome_review(
        exchange_submit_execution_result=result,
        local_orders=[
            _order("entry-1", OrderRole.ENTRY, OrderStatus.OPEN, Decimal("0")),
            _order("sl-1", OrderRole.SL, OrderStatus.OPEN, Decimal("0")),
        ],
        now_ms=NOW_MS,
    )
    reservation = _reservation()
    policy_repo = _AttemptOutcomePolicyRepo()
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftRepo(),
        attempt_reservation_repository=_AttemptReservationRepo(reservation),
        attempt_mutation_repository=_AttemptMutationRepo(_mutation(reservation)),
        attempt_outcome_policy_repository=policy_repo,
        submit_outcome_review_repository=_SubmitOutcomeReviewRepo([review]),
    )

    with pytest.raises(ValueError) as exc:
        await service.record_attempt_outcome_policy_from_submit_outcome_review(
            reservation.reservation_id
        )

    assert "submit_outcome_review_not_policy_ready" in str(exc.value)
    assert policy_repo.created == []


async def test_first_real_submit_outcome_accounting_records_review_and_policy():
    result = _submitted_result()
    entry = _order("entry-1", OrderRole.ENTRY, OrderStatus.FILLED, Decimal("1"))
    sl = _order("sl-1", OrderRole.SL, OrderStatus.OPEN, Decimal("0"))
    reservation = _reservation()
    mutation = _mutation(reservation)
    review_repo = _SubmitOutcomeReviewRepo()
    policy_repo = _AttemptOutcomePolicyRepo()
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftRepo(),
        exchange_submit_execution_result_repository=_ExecutionResultRepo(result),
        order_lifecycle_service=_Lifecycle([entry, sl]),
        submit_outcome_review_repository=review_repo,
        attempt_reservation_repository=_AttemptReservationRepo(reservation),
        attempt_mutation_repository=_AttemptMutationRepo(mutation),
        attempt_outcome_policy_repository=policy_repo,
    )

    accounting = await (
        service.record_first_real_submit_outcome_accounting_for_authorization(
            "auth-1",
            reservation_id=reservation.reservation_id,
        )
    )

    assert accounting.status == (
        RuntimeExecutionFirstRealSubmitOutcomeAccountingStatus
        .READY_FOR_ATTEMPT_BUDGET_OUTCOME_ACCOUNTING
    )
    assert accounting.submit_outcome_review_id == review_repo.created[0].review_id
    assert accounting.attempt_outcome_policy_id == policy_repo.created[0].policy_id
    assert accounting.outcome_kind == (
        RuntimeExecutionAttemptOutcomeKind.SUBMITTED_FULL_FILL
    )
    assert accounting.attempt_should_be_consumed is True
    assert accounting.budget_consumption_confirmed is True
    assert accounting.runtime_state_mutated is False
    assert accounting.budget_released is False
    assert accounting.exchange_called is False
    assert accounting.order_lifecycle_called is False


async def test_first_real_submit_outcome_accounting_blocks_unresolved_review():
    result = _submitted_result()
    entry = _order("entry-1", OrderRole.ENTRY, OrderStatus.OPEN, Decimal("0"))
    sl = _order("sl-1", OrderRole.SL, OrderStatus.OPEN, Decimal("0"))
    reservation = _reservation()
    policy_repo = _AttemptOutcomePolicyRepo()
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftRepo(),
        exchange_submit_execution_result_repository=_ExecutionResultRepo(result),
        order_lifecycle_service=_Lifecycle([entry, sl]),
        submit_outcome_review_repository=_SubmitOutcomeReviewRepo(),
        attempt_reservation_repository=_AttemptReservationRepo(reservation),
        attempt_mutation_repository=_AttemptMutationRepo(_mutation(reservation)),
        attempt_outcome_policy_repository=policy_repo,
    )

    accounting = await (
        service.record_first_real_submit_outcome_accounting_for_authorization(
            "auth-1",
            reservation_id=reservation.reservation_id,
        )
    )

    assert (
        accounting.status
        == RuntimeExecutionFirstRealSubmitOutcomeAccountingStatus.BLOCKED
    )
    assert "submit_outcome_review_not_policy_ready" in accounting.blockers
    assert "entry_order_still_open_no_fill_unresolved" in accounting.blockers
    assert accounting.attempt_outcome_policy is None
    assert policy_repo.created == []
    assert accounting.runtime_state_mutated is False
    assert accounting.exchange_called is False


async def test_submit_outcome_review_repository_roundtrips_by_authorization():
    engine, session_maker = await _repo_engine(
        PGRuntimeExecutionSubmitOutcomeReviewORM.__table__
    )
    repo = PgRuntimeExecutionSubmitOutcomeReviewRepository(
        session_maker=session_maker
    )
    try:
        review = build_runtime_execution_submit_outcome_review(
            exchange_submit_execution_result=_submitted_result(),
            local_orders=[
                _order("entry-1", OrderRole.ENTRY, OrderStatus.FILLED, Decimal("1")),
                _order("sl-1", OrderRole.SL, OrderStatus.OPEN, Decimal("0")),
            ],
            now_ms=NOW_MS,
        )

        saved = await repo.create(review)
        loaded = await repo.get(saved.review_id)
        by_authorization = await repo.get_by_authorization_id("auth-1")

        assert loaded is not None
        assert loaded.review_id == review.review_id
        assert loaded.entry_filled_qty == Decimal("1")
        assert loaded.recommended_attempt_outcome_kind == (
            RuntimeExecutionAttemptOutcomeKind.SUBMITTED_FULL_FILL
        )
        assert by_authorization is not None
        assert by_authorization.review_id == review.review_id
        assert by_authorization.exchange_called is False
    finally:
        await engine.dispose()


async def test_submit_outcome_review_migration_creates_and_downgrades_table():
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/2026-06-11-079_create_runtime_submit_outcome_reviews.py"
    )
    spec = importlib.util.spec_from_file_location(
        "runtime_submit_outcome_review_migration",
        migration_path,
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:

        def upgrade(sync_conn):
            old_op = migration.op
            migration.op = Operations(MigrationContext.configure(sync_conn))
            try:
                migration.upgrade()
                inspector = inspect(sync_conn)
                assert inspector.has_table(
                    "runtime_execution_submit_outcome_reviews"
                )
                columns = {
                    column["name"]
                    for column in inspector.get_columns(
                        "runtime_execution_submit_outcome_reviews"
                    )
                }
                unique_constraints = {
                    constraint["name"]
                    for constraint in inspector.get_unique_constraints(
                        "runtime_execution_submit_outcome_reviews"
                    )
                }
                migration.downgrade()
                inspector = inspect(sync_conn)
                assert not inspector.has_table(
                    "runtime_execution_submit_outcome_reviews"
                )
                return columns, unique_constraints
            finally:
                migration.op = old_op

        columns, unique_constraints = await conn.run_sync(upgrade)
    await engine.dispose()

    assert "review_id" in columns
    assert "observed_outcome" in columns
    assert "exchange_called" in columns
    assert "exchange_order_submitted" in columns
    assert "uq_rt_submit_outcome_review_authorization" in unique_constraints


async def test_trading_console_records_submit_outcome_review_without_gateway(
    monkeypatch,
):
    factory_calls = []

    class FakeService:
        async def record_submit_outcome_review_for_authorization(
            self,
            authorization_id,
        ):
            return SimpleNamespace(
                authorization_id=authorization_id,
                exchange_called=False,
                order_lifecycle_called=False,
            )

    async def fake_factory(*, include_runtime_exchange_gateway=False):
        factory_calls.append(include_runtime_exchange_gateway)
        return FakeService()

    monkeypatch.setattr(
        trading_console_api,
        "_runtime_execution_intent_adapter_service",
        fake_factory,
    )

    review = await (
        trading_console_api
        .record_runtime_execution_submit_outcome_review_for_authorization(
            "auth-1"
        )
    )

    assert factory_calls == [False]
    assert review.authorization_id == "auth-1"
    assert review.exchange_called is False
    assert review.order_lifecycle_called is False


async def test_trading_console_records_attempt_outcome_from_submit_review_without_gateway(
    monkeypatch,
):
    factory_calls = []

    class FakeService:
        async def record_attempt_outcome_policy_from_submit_outcome_review(
            self,
            reservation_id,
            *,
            submit_outcome_review_id=None,
        ):
            return SimpleNamespace(
                reservation_id=reservation_id,
                submit_outcome_review_id=submit_outcome_review_id,
                exchange_called=False,
                order_lifecycle_called=False,
            )

    async def fake_factory(*, include_runtime_exchange_gateway=False):
        factory_calls.append(include_runtime_exchange_gateway)
        return FakeService()

    monkeypatch.setattr(
        trading_console_api,
        "_runtime_execution_intent_adapter_service",
        fake_factory,
    )

    policy = await (
        trading_console_api
        .record_runtime_execution_attempt_outcome_policy_from_submit_outcome_review(
            "reservation-1",
            submit_outcome_review_id="review-1",
        )
    )

    assert factory_calls == [False]
    assert policy.reservation_id == "reservation-1"
    assert policy.submit_outcome_review_id == "review-1"
    assert policy.exchange_called is False
    assert policy.order_lifecycle_called is False


async def test_trading_console_records_first_real_submit_accounting_without_gateway(
    monkeypatch,
):
    factory_calls = []

    class FakeService:
        async def record_first_real_submit_outcome_accounting_for_authorization(
            self,
            authorization_id,
            *,
            reservation_id,
        ):
            return SimpleNamespace(
                authorization_id=authorization_id,
                reservation_id=reservation_id,
                exchange_called=False,
                order_lifecycle_called=False,
                runtime_state_mutated=False,
            )

    async def fake_factory(*, include_runtime_exchange_gateway=False):
        factory_calls.append(include_runtime_exchange_gateway)
        return FakeService()

    monkeypatch.setattr(
        trading_console_api,
        "_runtime_execution_intent_adapter_service",
        fake_factory,
    )

    accounting = await (
        trading_console_api
        .record_runtime_execution_first_real_submit_outcome_accounting(
            "auth-1",
            reservation_id="reservation-1",
        )
    )

    assert factory_calls == [False]
    assert accounting.authorization_id == "auth-1"
    assert accounting.reservation_id == "reservation-1"
    assert accounting.exchange_called is False
    assert accounting.order_lifecycle_called is False
    assert accounting.runtime_state_mutated is False


def _submitted_result() -> RuntimeExecutionExchangeSubmitExecutionResult:
    return _execution_result(
        RuntimeExecutionExchangeSubmitExecutionStatus.EXCHANGE_SUBMIT_ORDERS_SUBMITTED,
        submitted_orders=[
            _submitted_order("entry-1", "ENTRY", "ex-entry", lifecycle_called=True),
            _submitted_order("sl-1", "SL", "ex-sl", lifecycle_called=True),
        ],
        exchange_call_count=2,
        order_lifecycle_submit_call_count=2,
        exchange_called=True,
        exchange_order_submitted=True,
        order_lifecycle_submit_called=True,
    )


def _execution_result(
    status: RuntimeExecutionExchangeSubmitExecutionStatus,
    *,
    submitted_orders: list[RuntimeExecutionSubmittedExchangeOrder],
    exchange_call_count: int,
    order_lifecycle_submit_call_count: int,
    exchange_called: bool,
    exchange_order_submitted: bool,
    order_lifecycle_submit_called: bool,
    failed_local_order_id: str | None = None,
    failed_order_role: str | None = None,
    failed_reason: str | None = None,
    blockers: list[str] | None = None,
) -> RuntimeExecutionExchangeSubmitExecutionResult:
    entry_exchange_order_id = next(
        (
            order.exchange_order_id
            for order in submitted_orders
            if order.order_role == "ENTRY"
        ),
        None,
    )
    protection_exchange_order_ids = [
        order.exchange_order_id
        for order in submitted_orders
        if order.order_role != "ENTRY" and order.exchange_order_id is not None
    ]
    return RuntimeExecutionExchangeSubmitExecutionResult(
        execution_result_id="exchange-submit-result-1",
        enablement_decision_id="exchange-submit-enable-1",
        packet_preview_id="packet-preview-1",
        binding_id="binding-1",
        authorization_id="auth-1",
        execution_intent_id="intent-1",
        runtime_instance_id="runtime-1",
        source_type="brc_runtime_order_candidate",
        source_id="candidate-1",
        semantic_ids=BrcSemanticIds(
            runtime_instance_id="runtime-1",
            trial_binding_id="binding-1",
            strategy_family_id="CPM-001",
            strategy_family_version_id="CPM-001-v0",
            signal_evaluation_id="signal-eval-1",
            order_candidate_id="candidate-1",
        ),
        status=status,
        symbol="BNB/USDT:USDT",
        exchange_submit_action_authorization_id="exchange-submit-action-1",
        local_order_ids=["entry-1", "sl-1"],
        execution_mode=RuntimeExecutionExchangeSubmitExecutionMode.IN_MEMORY_SIMULATION,
        entry_order_id="entry-1",
        protection_order_ids=["sl-1"],
        submitted_orders=submitted_orders,
        submitted_local_order_ids=[order.local_order_id for order in submitted_orders],
        submitted_exchange_order_ids=[
            order.exchange_order_id
            for order in submitted_orders
            if order.exchange_order_id is not None
        ],
        entry_exchange_order_id=entry_exchange_order_id,
        protection_exchange_order_ids=protection_exchange_order_ids,
        failed_local_order_id=failed_local_order_id,
        failed_order_role=failed_order_role,
        failed_reason=failed_reason,
        exchange_submit_execution_enabled=True,
        exchange_call_count=exchange_call_count,
        order_lifecycle_submit_call_count=order_lifecycle_submit_call_count,
        blockers=blockers or [],
        warnings=[],
        real_exchange_submit_adapter_executed=True,
        exchange_order_submitted=exchange_order_submitted,
        exchange_called=exchange_called,
        order_lifecycle_submit_called=order_lifecycle_submit_called,
        execution_intent_status_changed=False,
        owner_bounded_execution_called=False,
        withdrawal_or_transfer_created=False,
        created_at_ms=NOW_MS,
        metadata={"scope": "test"},
    )


def _submitted_order(
    local_order_id: str,
    role: str,
    exchange_order_id: str | None,
    *,
    lifecycle_called: bool,
) -> RuntimeExecutionSubmittedExchangeOrder:
    return RuntimeExecutionSubmittedExchangeOrder(
        local_order_id=local_order_id,
        order_role=role,
        exchange_order_id=exchange_order_id,
        exchange_status="OPEN",
        amount="1",
        filled_qty="0",
        average_exec_price=None,
        reduce_only=role != "ENTRY",
        order_lifecycle_submit_called=lifecycle_called,
    )


def _order(
    order_id: str,
    role: OrderRole,
    status: OrderStatus,
    filled_qty: Decimal,
) -> Order:
    return Order(
        id=order_id,
        signal_id="signal-eval-1",
        exchange_order_id=f"ex-{order_id}",
        symbol="BNB/USDT:USDT",
        direction=Direction.LONG,
        order_type=(
            OrderType.MARKET
            if role == OrderRole.ENTRY
            else OrderType.STOP_MARKET
        ),
        order_role=role,
        price=None,
        trigger_price=Decimal("280") if role == OrderRole.SL else None,
        requested_qty=Decimal("1"),
        filled_qty=filled_qty,
        average_exec_price=Decimal("300") if filled_qty > Decimal("0") else None,
        status=status,
        created_at=NOW_MS,
        updated_at=NOW_MS,
        reduce_only=role != OrderRole.ENTRY,
        runtime_instance_id="runtime-1",
        trial_binding_id="binding-1",
        strategy_family_id="CPM-001",
        strategy_family_version_id="CPM-001-v0",
        signal_evaluation_id="signal-eval-1",
        order_candidate_id="candidate-1",
    )


def _reservation() -> RuntimeExecutionAttemptReservation:
    return RuntimeExecutionAttemptReservation(
        reservation_id="runtime-attempt-reservation-auth-1",
        reservation_preview_id="runtime-attempt-reservation-preview-auth-1",
        preflight_id="runtime-controlled-submit-preflight-auth-1",
        authorization_id="auth-1",
        execution_intent_id="intent-1",
        runtime_instance_id="runtime-1",
        source_id="candidate-1",
        semantic_ids=BrcSemanticIds(
            runtime_instance_id="runtime-1",
            trial_binding_id="binding-1",
            strategy_family_id="CPM-001",
            strategy_family_version_id="CPM-001-v0",
            signal_evaluation_id="signal-eval-1",
            order_candidate_id="candidate-1",
        ),
        status=RuntimeExecutionAttemptReservationStatus.PENDING_RUNTIME_MUTATION,
        symbol="BNB/USDT:USDT",
        side="long",
        proposed_quantity=Decimal("1"),
        intended_notional=Decimal("300"),
        attempts_used_before=0,
        attempts_remaining_before=3,
        attempts_remaining_after=2,
        max_attempts=3,
        budget_remaining_before=Decimal("30"),
        budget_remaining_after=Decimal("24"),
        max_notional_per_attempt=Decimal("300"),
        total_budget=Decimal("30"),
        max_active_positions=1,
        blockers=[],
        warnings=[],
        created_at_ms=NOW_MS,
        metadata={
            "scope": "runtime_execution_attempt_reservation",
            "budget_reservation_basis": "max_loss_reference",
            "budget_reservation_amount": "6",
        },
    )


def _mutation(
    reservation: RuntimeExecutionAttemptReservation,
) -> RuntimeExecutionAttemptMutation:
    return RuntimeExecutionAttemptMutation(
        mutation_id=f"runtime-attempt-mutation-{reservation.reservation_id}",
        reservation_id=reservation.reservation_id,
        reservation_preview_id=reservation.reservation_preview_id,
        authorization_id=reservation.authorization_id,
        execution_intent_id=reservation.execution_intent_id,
        runtime_instance_id=reservation.runtime_instance_id,
        source_id=reservation.source_id,
        semantic_ids=reservation.semantic_ids,
        status=RuntimeExecutionAttemptMutationStatus.APPLIED,
        runtime_status_before="active",
        runtime_status_after="active",
        symbol=reservation.symbol,
        side=reservation.side,
        proposed_quantity=reservation.proposed_quantity,
        intended_notional=reservation.intended_notional,
        attempts_used_before=0,
        attempts_used_after=1,
        attempts_remaining_before=3,
        attempts_remaining_after=2,
        max_attempts=3,
        budget_reserved_before=Decimal("0"),
        budget_reserved_after=Decimal("6"),
        budget_remaining_before=Decimal("30"),
        budget_remaining_after=Decimal("24"),
        reservation_budget_remaining_after=Decimal("24"),
        max_notional_per_attempt=Decimal("300"),
        total_budget=Decimal("30"),
        max_active_positions=1,
        blockers=[],
        warnings=[],
        reservation_status=RuntimeExecutionAttemptReservationStatus
        .PENDING_RUNTIME_MUTATION,
        runtime_budget_mutated=True,
        attempt_consumed=True,
        created_at_ms=NOW_MS + 1,
        metadata={
            "scope": "runtime_execution_attempt_mutation",
            "budget_reservation_basis": "max_loss_reference",
            "budget_reservation_amount": "6",
        },
    )


async def _repo_engine(*tables):
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        for table in tables:
            await conn.run_sync(table.create)
    return engine, async_sessionmaker(engine, expire_on_commit=False)
