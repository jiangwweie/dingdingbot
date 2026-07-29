from __future__ import annotations

import asyncio

import pytest
import sqlalchemy as sa
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine

from src.trading_kernel.application.advance_strategy_universe import (
    UniverseActivationRequest,
    UniverseActivationStatus,
    advance_strategy_universe,
)
from src.trading_kernel.infrastructure.pg_models import (
    comparative_projection_current,
    instrument_certification_current,
    runtime_scopes_current,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import (
    PostgresKernelUnitOfWork,
)
from tests.trading_kernel.integration.universe_activation_support import (
    COMPARATIVE_CONTRACT,
    DIRECT_CONTRACT,
    NOW_MS,
    REPLACEMENT_MEMBERS,
    activation_snapshot,
    make_warming_ready,
    prepare_active_and_warming,
    save_complete_comparative_projection,
)


@pytest.mark.asyncio
async def test_fully_ready_replacement_activates_atomically_without_chain_writes(
    activation_engine: AsyncEngine,
) -> None:
    """Catches a split pointer/scope/version switch or execution-chain mutation."""

    old_version_id, new_version_id = await prepare_active_and_warming(
        activation_engine
    )
    await make_warming_ready(
        activation_engine,
        universe_version_id=new_version_id,
    )
    before = await activation_snapshot(
        activation_engine,
        event_spec_id=DIRECT_CONTRACT.event_spec_id,
    )

    async with PostgresKernelUnitOfWork(activation_engine) as uow:
        result = await advance_strategy_universe(
            uow,
            UniverseActivationRequest(
                universe_version_id=new_version_id,
                attempted_at_ms=NOW_MS,
            ),
        )

    assert result.status is UniverseActivationStatus.ACTIVATED
    assert result.reason_code is None
    assert result.event_spec_id == DIRECT_CONTRACT.event_spec_id
    assert result.universe_version_id == new_version_id
    assert result.previous_universe_version_id == old_version_id
    assert result.activation_generation == 2
    assert result.activated_at_ms == NOW_MS

    after = await activation_snapshot(
        activation_engine,
        event_spec_id=DIRECT_CONTRACT.event_spec_id,
    )
    assert after["current"] == {
        "event_spec_id": DIRECT_CONTRACT.event_spec_id,
        "universe_version_id": new_version_id,
        "semantic_digest": after["current"]["semantic_digest"],
        "lifecycle_state": "active",
        "activation_generation": 2,
        "activated_at_ms": NOW_MS,
    }
    assert after["versions"] == (
        (old_version_id, "retired", NOW_MS - 800_000, NOW_MS),
        (new_version_id, "active", NOW_MS, None),
    )
    assert {
        (row[0], row[2], row[3], row[4], row[5])
        for row in after["scopes"]
    } == {
        (old_version_id, "retired", False, False, 3),
        (new_version_id, "active", True, True, 2),
    }
    async with activation_engine.connect() as connection:
        new_due_times = set(
            (
                await connection.scalars(
                    sa.select(
                        runtime_scopes_current.c.next_observation_due_at_ms
                    ).where(
                        runtime_scopes_current.c.universe_version_id
                        == new_version_id
                    )
                )
            ).all()
        )
    expected_next_close_ms = (
        NOW_MS - (NOW_MS % 900_000) + 900_000
    )
    assert new_due_times == {expected_next_close_ms}
    assert before["side_effect_counts"] == (0, 0, 0, 0, 0)
    assert after["side_effect_counts"] == before["side_effect_counts"]


@pytest.mark.parametrize(
    ("blocked_fact", "expected_reason"),
    (
        ("certification_missing", "CERTIFICATION_MISSING"),
        ("certification_owner_action", "CERTIFICATION_NOT_ELIGIBLE"),
        ("certification_expired", "CERTIFICATION_STALE"),
        ("warm_readiness_missing", "WARM_READINESS_MISSING"),
        ("warm_readiness_expired", "WARM_READINESS_STALE"),
    ),
)
@pytest.mark.asyncio
async def test_incomplete_or_stale_readiness_keeps_old_universe_fully_active(
    activation_engine: AsyncEngine,
    blocked_fact: str,
    expected_reason: str,
) -> None:
    """Catches activation from missing, blocked, or stale readiness authority."""

    _, new_version_id = await prepare_active_and_warming(
        activation_engine
    )
    await make_warming_ready(
        activation_engine,
        universe_version_id=new_version_id,
    )
    async with activation_engine.begin() as connection:
        if blocked_fact == "certification_missing":
            await connection.execute(
                sa.delete(instrument_certification_current).where(
                    instrument_certification_current.c.exchange_instrument_id
                    == REPLACEMENT_MEMBERS[0]
                )
            )
        elif blocked_fact == "certification_owner_action":
            await connection.execute(
                sa.update(instrument_certification_current)
                .where(
                    instrument_certification_current.c.exchange_instrument_id
                    == REPLACEMENT_MEMBERS[0]
                )
                .values(
                    status="owner_action_required",
                    blocker_code="instrument_leverage_mismatch",
                )
            )
        elif blocked_fact == "certification_expired":
            await connection.execute(
                sa.update(instrument_certification_current)
                .where(
                    instrument_certification_current.c.exchange_instrument_id
                    == REPLACEMENT_MEMBERS[0]
                )
                .values(valid_until_ms=NOW_MS)
            )
        elif blocked_fact == "warm_readiness_missing":
            await connection.execute(
                sa.update(runtime_scopes_current)
                .where(
                    runtime_scopes_current.c.universe_version_id
                    == new_version_id,
                    runtime_scopes_current.c.exchange_instrument_id
                    == REPLACEMENT_MEMBERS[0],
                )
                .values(
                    warm_closed_bar_time_ms=None,
                    warm_completed_at_ms=None,
                    warm_readiness_digest=None,
                    warm_valid_until_ms=None,
                )
            )
        else:
            await connection.execute(
                sa.update(runtime_scopes_current)
                .where(
                    runtime_scopes_current.c.universe_version_id
                    == new_version_id,
                    runtime_scopes_current.c.exchange_instrument_id
                    == REPLACEMENT_MEMBERS[0],
                )
                .values(warm_valid_until_ms=NOW_MS)
            )
    before = await activation_snapshot(
        activation_engine,
        event_spec_id=DIRECT_CONTRACT.event_spec_id,
    )

    async with PostgresKernelUnitOfWork(activation_engine) as uow:
        result = await advance_strategy_universe(
            uow,
            UniverseActivationRequest(
                universe_version_id=new_version_id,
                attempted_at_ms=NOW_MS,
            ),
        )

    after = await activation_snapshot(
        activation_engine,
        event_spec_id=DIRECT_CONTRACT.event_spec_id,
    )
    assert result.status is UniverseActivationStatus.NOT_READY
    assert result.reason_code == expected_reason
    assert result.activated_at_ms is None
    assert after == before


@pytest.mark.asyncio
async def test_comparative_activation_requires_one_complete_exact_projection(
    activation_engine: AsyncEngine,
) -> None:
    """Catches activation that bypasses the shared comparative projection."""

    old_version_id, new_version_id = await prepare_active_and_warming(
        activation_engine,
        contract=COMPARATIVE_CONTRACT,
    )
    await make_warming_ready(
        activation_engine,
        universe_version_id=new_version_id,
    )
    before = await activation_snapshot(
        activation_engine,
        event_spec_id=COMPARATIVE_CONTRACT.event_spec_id,
    )

    async with PostgresKernelUnitOfWork(activation_engine) as uow:
        blocked = await advance_strategy_universe(
            uow,
            UniverseActivationRequest(
                universe_version_id=new_version_id,
                attempted_at_ms=NOW_MS,
            ),
        )

    still_blocked = await activation_snapshot(
        activation_engine,
        event_spec_id=COMPARATIVE_CONTRACT.event_spec_id,
    )
    assert blocked.status is UniverseActivationStatus.NOT_READY
    assert blocked.reason_code == "COMPARATIVE_PROJECTION_INCOMPLETE"
    assert still_blocked == before

    await save_complete_comparative_projection(
        activation_engine,
        contract=COMPARATIVE_CONTRACT,
        universe_version_id=new_version_id,
    )
    async with PostgresKernelUnitOfWork(activation_engine) as uow:
        activated = await advance_strategy_universe(
            uow,
            UniverseActivationRequest(
                universe_version_id=new_version_id,
                attempted_at_ms=NOW_MS,
            ),
        )

    assert activated.status is UniverseActivationStatus.ACTIVATED
    assert activated.previous_universe_version_id == old_version_id
    assert activated.activation_generation == 2


@pytest.mark.asyncio
async def test_incomplete_current_universe_identity_blocks_replacement(
    activation_engine: AsyncEngine,
) -> None:
    """Catches activation that retires a structurally incomplete current pool."""

    old_version_id, new_version_id = await prepare_active_and_warming(
        activation_engine
    )
    await make_warming_ready(
        activation_engine,
        universe_version_id=new_version_id,
    )
    async with activation_engine.begin() as connection:
        old_scope_id = await connection.scalar(
            sa.select(runtime_scopes_current.c.runtime_scope_id)
            .where(
                runtime_scopes_current.c.universe_version_id
                == old_version_id
            )
            .order_by(runtime_scopes_current.c.runtime_scope_id)
            .limit(1)
        )
        await connection.execute(
            sa.delete(runtime_scopes_current).where(
                runtime_scopes_current.c.runtime_scope_id == old_scope_id
            )
        )
    before = await activation_snapshot(
        activation_engine,
        event_spec_id=DIRECT_CONTRACT.event_spec_id,
    )

    async with PostgresKernelUnitOfWork(activation_engine) as uow:
        result = await advance_strategy_universe(
            uow,
            UniverseActivationRequest(
                universe_version_id=new_version_id,
                attempted_at_ms=NOW_MS,
            ),
        )

    after = await activation_snapshot(
        activation_engine,
        event_spec_id=DIRECT_CONTRACT.event_spec_id,
    )
    assert result.status is UniverseActivationStatus.NOT_READY
    assert result.reason_code == "CURRENT_UNIVERSE_IDENTITY_CONFLICT"
    assert after == before


@pytest.mark.parametrize(
    ("authority_field", "wrong_value"),
    (
        ("strategy_group_id", "strategy-group:wrong"),
        ("strategy_version_id", "strategy-version:wrong"),
        ("runtime_profile_id", "runtime-profile:wrong"),
        ("owner_policy_id", "owner-policy:wrong"),
        ("position_side", "short"),
    ),
)
@pytest.mark.asyncio
async def test_warming_scope_authority_mismatch_blocks_activation_without_mutation(
    activation_engine: AsyncEngine,
    authority_field: str,
    wrong_value: str,
) -> None:
    """Catches activation that trusts only member and lifecycle identities."""

    _, new_version_id = await prepare_active_and_warming(
        activation_engine
    )
    await make_warming_ready(
        activation_engine,
        universe_version_id=new_version_id,
    )
    async with activation_engine.begin() as connection:
        target_scope_id = await connection.scalar(
            sa.select(runtime_scopes_current.c.runtime_scope_id)
            .where(
                runtime_scopes_current.c.universe_version_id
                == new_version_id
            )
            .order_by(runtime_scopes_current.c.runtime_scope_id)
            .limit(1)
        )
        await connection.execute(
            sa.update(runtime_scopes_current)
            .where(
                runtime_scopes_current.c.runtime_scope_id
                == target_scope_id
            )
            .values(**{authority_field: wrong_value})
        )
    before = await activation_snapshot(
        activation_engine,
        event_spec_id=DIRECT_CONTRACT.event_spec_id,
    )

    async with PostgresKernelUnitOfWork(activation_engine) as uow:
        result = await advance_strategy_universe(
            uow,
            UniverseActivationRequest(
                universe_version_id=new_version_id,
                attempted_at_ms=NOW_MS,
            ),
        )

    after = await activation_snapshot(
        activation_engine,
        event_spec_id=DIRECT_CONTRACT.event_spec_id,
    )
    assert result.status is UniverseActivationStatus.NOT_READY
    assert result.reason_code == "WARMING_SCOPE_IDENTITY_CONFLICT"
    assert after == before


@pytest.mark.parametrize("corruption", ("missing_scope", "wrong_binding"))
@pytest.mark.asyncio
async def test_already_active_revalidates_complete_scope_authority(
    activation_engine: AsyncEngine,
    corruption: str,
) -> None:
    """Catches an active-pointer shortcut accepting damaged active authority."""

    _, new_version_id = await prepare_active_and_warming(
        activation_engine
    )
    await make_warming_ready(
        activation_engine,
        universe_version_id=new_version_id,
    )
    async with PostgresKernelUnitOfWork(activation_engine) as uow:
        activated = await advance_strategy_universe(
            uow,
            UniverseActivationRequest(
                universe_version_id=new_version_id,
                attempted_at_ms=NOW_MS,
            ),
        )
    assert activated.status is UniverseActivationStatus.ACTIVATED

    async with activation_engine.begin() as connection:
        target_scope_id = await connection.scalar(
            sa.select(runtime_scopes_current.c.runtime_scope_id)
            .where(
                runtime_scopes_current.c.universe_version_id
                == new_version_id
            )
            .order_by(runtime_scopes_current.c.runtime_scope_id)
            .limit(1)
        )
        if corruption == "missing_scope":
            await connection.execute(
                sa.delete(runtime_scopes_current).where(
                    runtime_scopes_current.c.runtime_scope_id
                    == target_scope_id
                )
            )
        else:
            await connection.execute(
                sa.update(runtime_scopes_current)
                .where(
                    runtime_scopes_current.c.runtime_scope_id
                    == target_scope_id
                )
                .values(owner_policy_id="owner-policy:wrong")
            )
    before = await activation_snapshot(
        activation_engine,
        event_spec_id=DIRECT_CONTRACT.event_spec_id,
    )

    async with PostgresKernelUnitOfWork(activation_engine) as uow:
        repeated = await advance_strategy_universe(
            uow,
            UniverseActivationRequest(
                universe_version_id=new_version_id,
                attempted_at_ms=NOW_MS + 1,
            ),
        )

    after = await activation_snapshot(
        activation_engine,
        event_spec_id=DIRECT_CONTRACT.event_spec_id,
    )
    assert repeated.status is UniverseActivationStatus.NOT_READY
    assert repeated.reason_code == "CURRENT_UNIVERSE_IDENTITY_CONFLICT"
    assert after == before


@pytest.mark.asyncio
async def test_already_active_revalidates_exact_comparative_projection(
    activation_engine: AsyncEngine,
) -> None:
    """Catches an active-pointer shortcut accepting lost projection authority."""

    _, new_version_id = await prepare_active_and_warming(
        activation_engine,
        contract=COMPARATIVE_CONTRACT,
    )
    await make_warming_ready(
        activation_engine,
        universe_version_id=new_version_id,
    )
    await save_complete_comparative_projection(
        activation_engine,
        contract=COMPARATIVE_CONTRACT,
        universe_version_id=new_version_id,
    )
    async with PostgresKernelUnitOfWork(activation_engine) as uow:
        activated = await advance_strategy_universe(
            uow,
            UniverseActivationRequest(
                universe_version_id=new_version_id,
                attempted_at_ms=NOW_MS,
            ),
        )
    assert activated.status is UniverseActivationStatus.ACTIVATED
    async with activation_engine.begin() as connection:
        await connection.execute(
            sa.delete(comparative_projection_current).where(
                comparative_projection_current.c.universe_version_id
                == new_version_id
            )
        )
    before = await activation_snapshot(
        activation_engine,
        event_spec_id=COMPARATIVE_CONTRACT.event_spec_id,
    )

    async with PostgresKernelUnitOfWork(activation_engine) as uow:
        repeated = await advance_strategy_universe(
            uow,
            UniverseActivationRequest(
                universe_version_id=new_version_id,
                attempted_at_ms=NOW_MS + 1,
            ),
        )

    after = await activation_snapshot(
        activation_engine,
        event_spec_id=COMPARATIVE_CONTRACT.event_spec_id,
    )
    assert repeated.status is UniverseActivationStatus.NOT_READY
    assert repeated.reason_code == "COMPARATIVE_PROJECTION_INCOMPLETE"
    assert after == before


@pytest.mark.asyncio
async def test_two_workers_activate_one_generation_and_retry_is_idempotent(
    activation_engine: AsyncEngine,
) -> None:
    """Catches a CAS loser creating a second generation or repeat activation."""

    _, new_version_id = await prepare_active_and_warming(
        activation_engine
    )
    await make_warming_ready(
        activation_engine,
        universe_version_id=new_version_id,
    )

    async def activate():
        async with PostgresKernelUnitOfWork(activation_engine) as uow:
            return await advance_strategy_universe(
                uow,
                UniverseActivationRequest(
                    universe_version_id=new_version_id,
                    attempted_at_ms=NOW_MS,
                ),
            )

    first, second = await asyncio.gather(activate(), activate())
    repeated = await activate()
    snapshot = await activation_snapshot(
        activation_engine,
        event_spec_id=DIRECT_CONTRACT.event_spec_id,
    )

    assert {first.status, second.status} == {
        UniverseActivationStatus.ACTIVATED,
        UniverseActivationStatus.ALREADY_ACTIVE,
    }
    assert repeated.status is UniverseActivationStatus.ALREADY_ACTIVE
    assert first.activation_generation == 2
    assert second.activation_generation == 2
    assert repeated.activation_generation == 2
    assert snapshot["current"]["activation_generation"] == 2


@pytest.mark.asyncio
async def test_activation_sql_never_enters_signal_ticket_or_entry_lane_tables(
    activation_engine: AsyncEngine,
) -> None:
    """Catches activation crossing into Signal, Ticket, command, or lane state."""

    _, new_version_id = await prepare_active_and_warming(
        activation_engine
    )
    await make_warming_ready(
        activation_engine,
        universe_version_id=new_version_id,
    )
    statements: list[str] = []
    recording = False

    def record_statement(
        _connection,
        _cursor,
        statement: str,
        _parameters,
        _context,
        _executemany,
    ) -> None:
        if recording:
            statements.append(statement.lower())

    event.listen(
        activation_engine.sync_engine,
        "before_cursor_execute",
        record_statement,
    )
    try:
        recording = True
        async with PostgresKernelUnitOfWork(activation_engine) as uow:
            result = await advance_strategy_universe(
                uow,
                UniverseActivationRequest(
                    universe_version_id=new_version_id,
                    attempted_at_ms=NOW_MS,
                ),
            )
        recording = False
    finally:
        event.remove(
            activation_engine.sync_engine,
            "before_cursor_execute",
            record_statement,
        )

    assert result.status is UniverseActivationStatus.ACTIVATED
    observed_sql = "\n".join(statements)
    assert statements
    for forbidden_table in (
        "brc_signal_events",
        "brc_readiness_current",
        "brc_capacity_claims",
        "brc_trade_tickets",
        "brc_exchange_commands",
        "brc_trade_events",
        "brc_trade_aggregates",
        "brc_entry_lane_current",
    ):
        assert forbidden_table not in observed_sql
