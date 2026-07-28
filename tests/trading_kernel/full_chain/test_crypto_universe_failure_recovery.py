from __future__ import annotations

from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from scripts.trading_kernel.certify_readonly import _certify
from src.trading_kernel.application.advance_strategy_universe import (
    UniverseActivationRequest,
    UniverseActivationStatus,
    advance_strategy_universe,
)
from src.trading_kernel.application.certify_universe_instrument import (
    CertifyUniverseInstrumentRequest,
    certify_universe_instrument,
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
from src.trading_kernel.application.strategy_authority import (
    strategy_authority_matches_ticket,
)
from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.position import PositionSnapshot
from src.trading_kernel.domain.ticket import build_ticket_id
from src.trading_kernel.infrastructure.pg_models import (
    instrument_certification_current,
    owner_policy_current,
    runtime_profiles,
    runtime_scopes_current,
    strategy_universe_versions,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import (
    PostgresKernelUnitOfWork,
)
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    ArmAcceptancePolicyRequest,
    arm_acceptance_policy,
)
from src.trading_kernel.interfaces.reconciliation_worker import (
    ReconciliationWorkerStatus,
    run_reconciliation_worker_once,
)
from tests.trading_kernel.full_chain.lifecycle_support import (
    dispatch_lifecycle_command,
    reach_runner_protected,
)
from tests.trading_kernel.integration.test_command_dispatch import (
    KindAwareAcceptingVenue,
    _issue,
)
from tests.trading_kernel.integration.test_ticket_lifecycle_maintenance import (
    _registered_sor_long_ticket,
)
from tests.trading_kernel.integration.universe_activation_support import (
    NOW_MS as ACTIVATION_NOW_MS,
)
from tests.trading_kernel.integration.universe_activation_support import (
    activation_engine as _activation_engine,  # noqa: F401
)
from tests.trading_kernel.integration.universe_activation_support import (
    activation_snapshot,
    make_warming_ready,
    prepare_active_and_warming,
)
from tests.trading_kernel.integration.universe_certification_support import (
    NOW_MS,
    RecordingReadonlyCertificationSource,
    worker_request,
)
from tests.trading_kernel.integration.universe_certification_support import (
    certification_engine as _certification_engine,  # noqa: F401
)


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
async def test_readonly_timeout_count_excludes_retired_and_other_profile_facts(
    _certification_engine: AsyncEngine,  # noqa: F811
) -> None:
    """Catches a global certification scan being reported as runtime readiness."""

    source = RecordingReadonlyCertificationSource(
        _certification_engine,
        error=TimeoutError("authenticated read timeout"),
    )
    await run_reconciliation_worker_once(
        lambda: PostgresKernelUnitOfWork(_certification_engine),
        object(),
        object(),
        worker_request(NOW_MS),
        instrument_certification_source=source,
    )
    async with _certification_engine.begin() as connection:
        await connection.execute(
            sa.insert(runtime_profiles).values(
                runtime_profile_id="foreign-runtime-profile",
                venue_id="binance-usdm",
                account_id="foreign-account",
                environment="production",
                position_mode="independent_sides",
                status="active",
                updated_at_ms=NOW_MS,
            )
        )
        await connection.execute(
            sa.insert(instrument_certification_current).values(
                runtime_profile_id="foreign-runtime-profile",
                exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
                status="temporarily_unavailable",
                blocker_code="readonly_facts_unavailable",
                facts_digest="sha256:" + ("f" * 64),
                product_rules_digest=None,
                configured_leverage=None,
                margin_mode=None,
                position_mode=None,
                observed_at_ms=NOW_MS,
                valid_until_ms=NOW_MS + 30_000,
                next_check_at_ms=NOW_MS + 30_000,
                lease_owner=None,
                lease_expires_at_ms=None,
                projection_version=1,
            )
        )

    current = await _certify(
        _certification_engine.url.render_as_string(hide_password=False),
        require_flat=True,
    )
    assert current["strategy_universe"][
        "temporarily_unavailable_certification_count"
    ] == 1

    async with _certification_engine.begin() as connection:
        await connection.execute(
            sa.update(strategy_universe_versions)
            .values(
                lifecycle_state="retired",
                activated_at_ms=NOW_MS,
                retired_at_ms=NOW_MS + 1,
            )
        )
        await connection.execute(
            sa.update(runtime_scopes_current).values(
                lifecycle_state="retired",
                observation_enabled=False,
                entry_enabled=False,
                updated_at_ms=NOW_MS + 1,
            )
        )
    retired = await _certify(
        _certification_engine.url.render_as_string(hide_password=False),
        require_flat=True,
    )
    assert retired["strategy_universe"][
        "temporarily_unavailable_certification_count"
    ] == 0


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
async def test_official_replacement_keeps_old_runner_ticket_to_terminal_review(
    _activation_engine: AsyncEngine,  # noqa: F811
) -> None:
    """Catches lifecycle or review reading the new Universe instead of the Ticket."""

    old_version_id, new_version_id = await prepare_active_and_warming(
        _activation_engine
    )
    await make_warming_ready(
        _activation_engine,
        universe_version_id=old_version_id,
    )
    await _arm_entry(_activation_engine)
    ticket = await _ticket_for_active_universe(
        _activation_engine,
        old_version_id=old_version_id,
    )
    frozen_authority = _frozen_ticket_authority(ticket)
    await _assert_ticket_authority(_activation_engine, ticket)
    await reach_runner_protected(_activation_engine, ticket, seed_policy=False)
    await make_warming_ready(
        _activation_engine,
        universe_version_id=new_version_id,
    )
    async with PostgresKernelUnitOfWork(_activation_engine) as uow:
        activated = await advance_strategy_universe(
            uow,
            UniverseActivationRequest(
                universe_version_id=new_version_id,
                attempted_at_ms=ACTIVATION_NOW_MS,
            ),
        )
    assert activated.status is UniverseActivationStatus.ACTIVATED
    assert activated.previous_universe_version_id == old_version_id

    venue = KindAwareAcceptingVenue()
    async with PostgresKernelUnitOfWork(_activation_engine) as uow:
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
            _activation_engine,
            venue,
            ticket.identity.ticket_id,
            now_ms=3_200,
        )
    ).status.value == "accepted"
    async with PostgresKernelUnitOfWork(_activation_engine) as uow:
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
    assert _frozen_ticket_authority(persisted_ticket) == frozen_authority
    assert review is not None and review.review_id == "review:old-universe-runner"


@pytest.mark.asyncio
async def test_official_activation_rolls_back_while_entry_lane_is_claimed(
    _activation_engine: AsyncEngine,  # noqa: F811
) -> None:
    """Catches official activation splitting projections under claimed ENTRY."""

    old_version_id, new_version_id = await prepare_active_and_warming(
        _activation_engine
    )
    await make_warming_ready(
        _activation_engine,
        universe_version_id=old_version_id,
    )
    await _arm_entry(_activation_engine)
    ticket = await _ticket_for_active_universe(
        _activation_engine,
        old_version_id=old_version_id,
    )
    await _assert_ticket_authority(_activation_engine, ticket)
    await _issue(_activation_engine, ticket)
    await make_warming_ready(
        _activation_engine,
        universe_version_id=new_version_id,
    )
    before = await activation_snapshot(
        _activation_engine,
        event_spec_id=ticket.identity.runtime.event_spec_id,
    )
    assert all(
        {
            "next_observation_due_at_ms",
            "lease_owner",
            "lease_expires_at_ms",
            "observation_generation",
            "updated_at_ms",
        }.issubset(scope)
        for scope in before["scope_projections"]
    )

    with pytest.raises(DBAPIError) as activation_error:
        async with PostgresKernelUnitOfWork(_activation_engine) as uow:
            await advance_strategy_universe(
                uow,
                UniverseActivationRequest(
                    universe_version_id=new_version_id,
                    attempted_at_ms=ACTIVATION_NOW_MS,
                ),
            )
    after = await activation_snapshot(
        _activation_engine,
        event_spec_id=ticket.identity.runtime.event_spec_id,
    )
    assert getattr(activation_error.value.orig, "sqlstate", None) == "55000"
    assert after == before


async def _arm_entry(engine: AsyncEngine) -> None:
    async with PostgresKernelUnitOfWork(engine) as uow:
        await arm_acceptance_policy(
            uow,
            ArmAcceptancePolicyRequest(armed_at_ms=1_000),
        )


async def _assert_ticket_authority(engine: AsyncEngine, ticket) -> None:
    async with PostgresKernelUnitOfWork(engine) as uow:
        universe = await uow.signals.get_active_universe_member(
            event_spec_id=ticket.identity.runtime.event_spec_id,
            exchange_instrument_id=(
                ticket.identity.netting_domain.exchange_instrument_id
            ),
            for_update=False,
        )
        scope = await uow.signals.get_runtime_scope(
            ticket.runtime_scope_id,
            for_update=False,
        )
        group = await uow.signals.get_strategy_group(
            ticket.identity.runtime.strategy_group_id
        )
        version = await uow.signals.get_strategy_version(
            ticket.identity.runtime.strategy_version_id
        )
        event = await uow.signals.get_event_spec(ticket.identity.runtime.event_spec_id)
    assert universe is not None
    assert universe.universe_version_id == ticket.universe_version_id
    assert universe.semantic_digest == ticket.universe_semantic_digest
    assert scope is not None
    assert scope.runtime_scope_id == ticket.runtime_scope_id
    assert scope.scope_version == ticket.runtime_scope_version
    assert scope.owner_policy_id == ticket.owner_policy_id
    assert strategy_authority_matches_ticket(group, version, event, ticket)


def _frozen_ticket_authority(ticket) -> tuple[object, ...]:
    return (
        ticket.universe_version_id,
        ticket.universe_semantic_digest,
        ticket.runtime_scope_id,
        ticket.runtime_scope_version,
        ticket.owner_policy_id,
        ticket.owner_policy_version,
        ticket.identity.runtime,
        ticket.identity.netting_domain,
    )


async def _ticket_for_active_universe(
    engine: AsyncEngine,
    *,
    old_version_id: str,
):
    async with engine.connect() as connection:
        scope = (
            await connection.execute(
                sa.select(runtime_scopes_current)
                .where(
                    runtime_scopes_current.c.universe_version_id == old_version_id,
                    runtime_scopes_current.c.exchange_instrument_id
                    == "binance-usdm:BTCUSDT:perpetual",
                    runtime_scopes_current.c.position_side == "long",
                )
                .limit(1)
            )
        ).mappings().one()
        account_id = str(
            await connection.scalar(
                sa.select(runtime_profiles.c.account_id).where(
                    runtime_profiles.c.runtime_profile_id
                    == scope["runtime_profile_id"]
                )
            )
        )
        policy_version = int(
            await connection.scalar(
                sa.select(owner_policy_current.c.policy_version).where(
                    owner_policy_current.c.owner_policy_id == scope["owner_policy_id"]
                )
            )
        )

    original = _registered_sor_long_ticket()
    domain = original.identity.netting_domain.model_copy(
        update={"account_id": account_id}
    )
    signal_event_id = "signal:active-universe-runner"
    identity = original.identity.model_copy(
        update={
            "ticket_id": build_ticket_id(
                signal_event_id=signal_event_id,
                runtime=original.identity.runtime,
                netting_domain=domain,
            ),
            "signal_event_id": signal_event_id,
            "exposure_episode_id": "episode:active-universe-runner",
            "netting_domain": domain,
        }
    )
    return original.model_copy(
        update={
            "identity": identity,
            "runtime_scope_id": str(scope["runtime_scope_id"]),
            "runtime_scope_version": int(scope["scope_version"]),
            "universe_version_id": old_version_id,
            "universe_semantic_digest": str(scope["universe_semantic_digest"]),
            "owner_policy_id": str(scope["owner_policy_id"]),
            "owner_policy_version": policy_version,
        }
    )
