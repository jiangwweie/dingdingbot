from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from scripts.trading_kernel.certify_readonly import _certify
from src.trading_kernel.application.certify_universe_instrument import (
    CertifyUniverseInstrumentRequest,
    certify_universe_instrument,
)
from src.trading_kernel.application.dispatch_exchange_command import (
    DispatchCommandRequest,
    DispatchCommandStatus,
    dispatch_one_command,
)
from src.trading_kernel.application.project_owner_state import (
    instrument_certification_monitor_key,
)
from src.trading_kernel.application.reconcile_ticket import (
    ReconcileTicketRequest,
    reconcile_ticket,
)
from src.trading_kernel.application.settle_ticket import (
    RecordTradeReviewRequest,
    SettleTicketRequest,
    SettleTicketStatus,
    record_trade_review,
    settle_ticket,
)
from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.position import PositionSnapshot
from src.trading_kernel.infrastructure.pg_models import strategy_universe_current
from src.trading_kernel.infrastructure.pg_unit_of_work import (
    PostgresKernelUnitOfWork,
)
from src.trading_kernel.interfaces.reconciliation_worker import (
    ReconciliationWorkerStatus,
    run_reconciliation_worker_once,
)
from tests.trading_kernel.full_chain.lifecycle_support import (
    dispatch_lifecycle_command,
    reach_runner_protected,
)
from tests.trading_kernel.integration import test_command_dispatch as _dispatch_fixture
from tests.trading_kernel.integration.test_command_dispatch import (
    CountingVenue,
    KindAwareAcceptingVenue,
    PreflightExitBarrierFactory,
    PreflightFacts,
    _issue,
    _seed_policy,
)
from tests.trading_kernel.integration.test_issue_ticket import (
    _seed_replacement_universe,
)
from tests.trading_kernel.integration.test_ticket_lifecycle_maintenance import (
    _registered_sor_long_ticket,
)
from tests.trading_kernel.integration.universe_certification_support import (
    NOW_MS,
    RecordingReadonlyCertificationSource,
    worker_request,
)
from tests.trading_kernel.integration.universe_certification_support import (
    certification_engine as _certification_engine,  # noqa: F401
)
from tests.trading_kernel.unit.test_ticket import _ticket

dispatch_engine = _dispatch_fixture.dispatch_engine


@pytest.mark.asyncio
async def test_network_timeout_is_retryable_and_readonly_visible(
    _certification_engine: AsyncEngine,  # noqa: F811
) -> None:
    """Catches timeout becoming Owner action or disappearing from certification."""

    source = RecordingReadonlyCertificationSource(
        _certification_engine,
        error=TimeoutError("authenticated read timeout"),
    )
    result = await run_reconciliation_worker_once(
        lambda: PostgresKernelUnitOfWork(_certification_engine),
        object(),
        object(),
        worker_request(NOW_MS),
        instrument_certification_source=source,
    )
    payload = await _certify(
        _certification_engine.url.render_as_string(hide_password=False),
        require_flat=True,
    )

    assert result.status is ReconciliationWorkerStatus.INSTRUMENT_CERTIFIED
    assert result.detail == "temporarily_unavailable"
    assert payload["status"] == "pass"
    assert payload["strategy_universe"][
        "temporarily_unavailable_certification_count"
    ] == 1


@pytest.mark.asyncio
async def test_worker_crash_claim_is_reclaimed_after_lease_expiry_without_signal(
    _certification_engine: AsyncEngine,  # noqa: F811
) -> None:
    """Catches a dead worker permanently stranding a warming instrument."""

    async with PostgresKernelUnitOfWork(_certification_engine) as uow:
        first = await uow.strategy_universes.claim_due_instrument_certification(
            worker_id="crashed-worker",
            now_ms=NOW_MS,
            lease_until_ms=NOW_MS + 60_000,
        )
        second = await uow.strategy_universes.claim_due_instrument_certification(
            worker_id="other-crashed-worker",
            now_ms=NOW_MS,
            lease_until_ms=NOW_MS + 60_000,
        )
    assert first is not None
    assert second is not None

    source = RecordingReadonlyCertificationSource(_certification_engine)
    recovered = await run_reconciliation_worker_once(
        lambda: PostgresKernelUnitOfWork(_certification_engine),
        object(),
        object(),
        worker_request(NOW_MS + 60_000),
        instrument_certification_source=source,
    )

    async with _certification_engine.connect() as connection:
        certification = (
            await connection.execute(
                sa.text(
                    "SELECT status, lease_owner, lease_expires_at_ms "
                    "FROM brc_instrument_certification_current "
                    "WHERE exchange_instrument_id = :instrument_id"
                ),
                {"instrument_id": recovered.exchange_instrument_id},
            )
        ).one()
        side_effect_counts = (
            await connection.execute(
                sa.text(
                    "SELECT "
                    "(SELECT count(*) FROM brc_signal_events), "
                    "(SELECT count(*) FROM brc_trade_tickets), "
                    "(SELECT count(*) FROM brc_exchange_commands)"
                )
            )
        ).one()

    assert recovered.status is ReconciliationWorkerStatus.INSTRUMENT_CERTIFIED
    assert recovered.exchange_instrument_id in {
        first.exchange_instrument_id,
        second.exchange_instrument_id,
    }
    assert certification == ("eligible", None, None)
    assert len(source.requests) == 1
    assert side_effect_counts == (0, 0, 0)
    assert source.mutation_calls == []


@pytest.mark.asyncio
async def test_monitor_deduplicates_same_blocker_then_records_resolution(
    _certification_engine: AsyncEngine,  # noqa: F811
) -> None:
    """Catches Monitor event storms or an Owner blocker that never resolves."""

    async with PostgresKernelUnitOfWork(_certification_engine) as uow:
        target = await uow.strategy_universes.claim_due_instrument_certification(
            worker_id="monitor-worker",
            now_ms=NOW_MS,
            lease_until_ms=NOW_MS + 60_000,
        )
        other_target = await uow.strategy_universes.claim_due_instrument_certification(
            worker_id="monitor-other-worker",
            now_ms=NOW_MS,
            lease_until_ms=NOW_MS + 60_000,
        )
    assert target is not None
    assert other_target is not None

    # Keep the unrelated member out of the retry selector.  This makes the
    # repeated owner blocker a real repeat of the same Monitor key.
    await certify_universe_instrument(
        lambda: PostgresKernelUnitOfWork(_certification_engine),
        RecordingReadonlyCertificationSource(_certification_engine),
        _certification_request(
            other_target,
            NOW_MS,
            eligible_check_interval_ms=1_000_000,
        ),
    )

    blocked_source = RecordingReadonlyCertificationSource(
        _certification_engine,
        changes={"configured_leverage": 3},
    )
    first = await certify_universe_instrument(
        lambda: PostgresKernelUnitOfWork(_certification_engine),
        blocked_source,
        _certification_request(target, NOW_MS),
    )

    # Reclaim the same target at its bounded deterministic recheck time.
    async with PostgresKernelUnitOfWork(_certification_engine) as uow:
        replay_target = await uow.strategy_universes.claim_due_instrument_certification(
            worker_id="monitor-worker-retry",
            now_ms=NOW_MS + 300_000,
            lease_until_ms=NOW_MS + 360_000,
        )
    assert replay_target is not None
    assert replay_target.exchange_instrument_id == target.exchange_instrument_id
    second = await certify_universe_instrument(
        lambda: PostgresKernelUnitOfWork(_certification_engine),
        blocked_source,
        _certification_request(replay_target, NOW_MS + 300_000),
    )

    async with PostgresKernelUnitOfWork(_certification_engine) as uow:
        resolved_target = await uow.strategy_universes.claim_due_instrument_certification(
            worker_id="monitor-worker-resolved",
            now_ms=NOW_MS + 600_000,
            lease_until_ms=NOW_MS + 660_000,
        )
    assert resolved_target is not None
    assert resolved_target.exchange_instrument_id == target.exchange_instrument_id
    resolved = await certify_universe_instrument(
        lambda: PostgresKernelUnitOfWork(_certification_engine),
        RecordingReadonlyCertificationSource(_certification_engine),
        _certification_request(resolved_target, NOW_MS + 600_000),
    )

    monitor_key = instrument_certification_monitor_key(target)
    async with _certification_engine.connect() as connection:
        current = (
            await connection.execute(
                sa.text(
                    "SELECT owner_status, summary, projection_version "
                    "FROM brc_monitor_current WHERE monitor_key = :monitor_key"
                ),
                {"monitor_key": monitor_key},
            )
        ).one()
        event_count = int(
            await connection.scalar(
                sa.text(
                    "SELECT count(*) FROM brc_monitor_events "
                    "WHERE monitor_key = :monitor_key"
                ),
                {"monitor_key": monitor_key},
            )
            or 0
        )

    assert first.certification.status == "owner_action_required"
    assert second.certification.status == "owner_action_required"
    assert resolved.certification.status == "eligible"
    assert current == ("running", "instrument_certification:resolved", 2)
    assert event_count == 2
    assert blocked_source.mutation_calls == []


def _certification_request(
    target,
    now_ms: int,
    *,
    eligible_check_interval_ms: int = 60_000,
) -> CertifyUniverseInstrumentRequest:
    return CertifyUniverseInstrumentRequest(
        target=target,
        now_ms=now_ms,
        timeout_seconds=1,
        required_leverage=5,
        required_margin_mode="cross",
        valid_for_ms=60_000,
        eligible_check_interval_ms=eligible_check_interval_ms,
        owner_action_check_interval_ms=300_000,
        transient_retry_interval_ms=30_000,
    )


@pytest.mark.asyncio
async def test_replaced_universe_keeps_old_runner_ticket_to_terminal_review(
    dispatch_engine: AsyncEngine,
) -> None:
    """Catches lifecycle or review reading the new Universe instead of the Ticket."""

    ticket = _registered_sor_long_ticket()
    await _seed_policy(dispatch_engine)
    await reach_runner_protected(dispatch_engine, ticket, seed_policy=False)
    await _seed_replacement_universe(dispatch_engine, ticket)
    async with dispatch_engine.begin() as connection:
        await connection.execute(
            sa.update(strategy_universe_current)
            .where(
                strategy_universe_current.c.event_spec_id
                == ticket.identity.runtime.event_spec_id
            )
            .values(
                universe_version_id="universe:sor-long:replacement",
                semantic_digest="sha256:" + ("b" * 64),
                activation_generation=2,
                activated_at_ms=3_000,
            )
        )

    venue = KindAwareAcceptingVenue()
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        external_flat = await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity=Decimal(0),
                    average_entry_price=None,
                    open_orders=(),
                    observed_at_ms=3_100,
                ),
            ),
        )
    assert external_flat.status.value == "external_flat_incident"
    assert (
        await dispatch_lifecycle_command(
            dispatch_engine,
            venue,
            ticket.identity.ticket_id,
            now_ms=3_200,
        )
    ).status.value == "accepted"
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        matched = await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity=Decimal(0),
                    average_entry_price=None,
                    open_orders=(),
                    observed_at_ms=3_300,
                ),
            ),
        )
        settled = await settle_ticket(
            uow,
            SettleTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                settled_at_ms=3_400,
            ),
        )
        reviewed = await record_trade_review(
            uow,
            RecordTradeReviewRequest(
                ticket_id=ticket.identity.ticket_id,
                review_id="review:old-universe-runner",
                outcome="closed",
                metrics={"realized_pnl": "1.25"},
                decision_impact={"strategy_action": "keep"},
                recorded_at_ms=3_500,
            ),
        )
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        persisted_ticket = await uow.tickets.get(ticket.identity.ticket_id)
        review = await uow.reviews.get_for_ticket(ticket.identity.ticket_id)

    assert matched.status.value == "matched"
    assert settled.status is SettleTicketStatus.BUDGET_SETTLED
    assert reviewed.status is SettleTicketStatus.REVIEW_RECORDED
    assert aggregate is not None and aggregate.status is AggregateStatus.TERMINAL
    assert persisted_ticket is not None
    assert persisted_ticket.universe_version_id == ticket.universe_version_id
    assert review is not None and review.review_id == "review:old-universe-runner"


@pytest.mark.asyncio
async def test_activation_cannot_cross_claimed_entry_dispatch_lane(
    dispatch_engine: AsyncEngine,
) -> None:
    """Catches a pointer switch that races an ENTRY venue write."""

    ticket = _ticket()
    await _seed_policy(dispatch_engine)
    await _issue(dispatch_engine, ticket)
    await _seed_replacement_universe(dispatch_engine, ticket)
    venue = CountingVenue()
    barrier_factory = PreflightExitBarrierFactory(dispatch_engine)
    dispatch_task = asyncio.create_task(
        dispatch_one_command(
            barrier_factory,
            venue,
            DispatchCommandRequest(
                worker_id="entry-dispatcher-failure-recovery",
                now_ms=1_100,
                lease_until_ms=6_100,
                timeout_seconds=1,
                runtime_commit="kernel-test-head",
                schema_revision="0002_crypto_strategy_universe",
                admission_snapshot_validity_ms=1_000,
            ),
            entry_facts_source=PreflightFacts(),
        )
    )
    await asyncio.wait_for(barrier_factory.preflight_closed.wait(), timeout=2)

    with pytest.raises(DBAPIError) as activation_error:
        async with dispatch_engine.begin() as connection:
            await connection.execute(
                sa.update(strategy_universe_current)
                .where(
                    strategy_universe_current.c.event_spec_id
                    == ticket.identity.runtime.event_spec_id
                )
                .values(
                    universe_version_id="universe:sor-long:replacement",
                    semantic_digest="sha256:" + ("b" * 64),
                    activation_generation=2,
                    activated_at_ms=1_101,
                )
            )
    barrier_factory.release_dispatch.set()
    dispatched = await dispatch_task

    assert getattr(activation_error.value.orig, "sqlstate", None) == "55000"
    assert dispatched.status is DispatchCommandStatus.ACCEPTED
    assert venue.calls == 1
    async with dispatch_engine.connect() as connection:
        current_version_id = await connection.scalar(
            sa.select(strategy_universe_current.c.universe_version_id).where(
                strategy_universe_current.c.event_spec_id
                == ticket.identity.runtime.event_spec_id
            )
        )
    assert current_version_id == ticket.universe_version_id
