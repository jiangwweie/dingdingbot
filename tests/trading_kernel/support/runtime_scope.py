"""Current runtime-scope authority seed used by PostgreSQL tests."""

from __future__ import annotations

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine

from src.trading_kernel.domain.instrument_identity import (
    parse_binance_usdm_instrument_id,
)
from src.trading_kernel.infrastructure.pg_models import (
    event_product_compatibility,
    event_specs,
    instrument_product_profiles,
    instruments,
    owner_authorizations,
    runtime_scopes_current,
    strategy_entry_control_events,
    strategy_entry_controls_current,
    strategy_groups,
    strategy_universe_current,
    strategy_universe_members,
    strategy_universe_versions,
    strategy_versions,
)


async def seed_replacement_universe(engine: AsyncEngine, ticket) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            pg_insert(strategy_universe_versions)
            .values(
                universe_version_id="universe:sor-long:replacement",
                strategy_group_id=ticket.identity.runtime.strategy_group_id,
                event_spec_id=ticket.identity.runtime.event_spec_id,
                universe_version=2,
                semantic_digest="sha256:" + "b" * 64,
                lifecycle_state="active",
                installed_at_ms=1_000,
                activated_at_ms=1_001,
            )
            .on_conflict_do_nothing(
                index_elements=[strategy_universe_versions.c.universe_version_id]
            )
        )
        await connection.execute(
            pg_insert(strategy_universe_members)
            .values(
                universe_version_id="universe:sor-long:replacement",
                exchange_instrument_id=ticket.identity.netting_domain.exchange_instrument_id,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    strategy_universe_members.c.universe_version_id,
                    strategy_universe_members.c.exchange_instrument_id,
                ]
            )
        )


async def seed_ticket_runtime_scope(engine: AsyncEngine, ticket) -> None:
    """Give direct Ticket tests the same current Scope authority as production."""

    identity = ticket.identity
    values = {
        "runtime_scope_id": ticket.runtime_scope_id,
        "strategy_group_id": identity.runtime.strategy_group_id,
        "strategy_version_id": identity.runtime.strategy_version_id,
        "event_spec_id": identity.runtime.event_spec_id,
        "runtime_profile_id": identity.runtime.runtime_profile_id,
        "owner_policy_id": ticket.owner_policy_id,
        "exchange_instrument_id": identity.netting_domain.exchange_instrument_id,
        "position_side": identity.netting_domain.position_side,
        "universe_version_id": ticket.universe_version_id,
        "universe_semantic_digest": ticket.universe_semantic_digest,
        "lifecycle_state": "active",
        "observation_enabled": True,
        "entry_enabled": True,
        "scope_version": ticket.runtime_scope_version,
        "warm_closed_bar_time_ms": ticket.created_at_ms,
        "warm_completed_at_ms": ticket.created_at_ms,
        "warm_readiness_digest": ticket.universe_semantic_digest,
        "warm_valid_until_ms": ticket.expires_at_ms,
        "updated_at_ms": ticket.created_at_ms,
    }
    async with engine.begin() as connection:
        await seed_ticket_registry(connection, ticket)
        await connection.execute(
            pg_insert(runtime_scopes_current)
            .values(**values)
            .on_conflict_do_update(
                index_elements=[runtime_scopes_current.c.runtime_scope_id],
                set_=values,
            )
        )


async def seed_ticket_registry(connection, ticket) -> None:
    identity = ticket.identity
    runtime = identity.runtime
    instrument = parse_binance_usdm_instrument_id(
        identity.netting_domain.exchange_instrument_id
    )
    await connection.execute(
        pg_insert(instruments)
        .values(
            exchange_instrument_id=identity.netting_domain.exchange_instrument_id,
            venue_id=identity.netting_domain.venue_id,
            asset_class="crypto",
            venue_symbol=instrument.symbol,
            contract_kind="perpetual",
            status="active",
        )
        .on_conflict_do_nothing(index_elements=[instruments.c.exchange_instrument_id])
    )
    await connection.execute(
        pg_insert(strategy_groups)
        .values(
            strategy_group_id=runtime.strategy_group_id,
            display_name=runtime.strategy_group_id,
            active_version_id=runtime.strategy_version_id,
            status="active",
            updated_at_ms=ticket.created_at_ms,
        )
        .on_conflict_do_update(
            index_elements=[strategy_groups.c.strategy_group_id],
            set_={
                "active_version_id": runtime.strategy_version_id,
                "status": "active",
                "updated_at_ms": ticket.created_at_ms,
            },
        )
    )
    authorization_id = f"owner-authorization:seed:{runtime.strategy_group_id}"
    event_id = f"strategy-control-event:seed:{runtime.strategy_group_id}"
    await connection.execute(
        pg_insert(owner_authorizations)
        .values(
            authorization_id=authorization_id,
            purpose="strategy_resume",
            owner_identity="system-seed",
            authentication_strength="session",
            request_digest="sha256:" + "0" * 64,
            target_scope={"seed": True},
            idempotency_key=f"owner-request:seed:{runtime.strategy_group_id}",
            authorized_at_ms=ticket.created_at_ms,
        )
        .on_conflict_do_nothing(
            index_elements=[owner_authorizations.c.authorization_id]
        )
    )
    await connection.execute(
        pg_insert(strategy_entry_control_events)
        .values(
            strategy_entry_control_event_id=event_id,
            strategy_group_id=runtime.strategy_group_id,
            control_version=1,
            operation="resume",
            target_state="enabled",
            authorization_id=authorization_id,
            reason="seed_enabled",
            payload={},
            created_at_ms=ticket.created_at_ms,
        )
        .on_conflict_do_nothing(
            index_elements=[
                strategy_entry_control_events.c.strategy_entry_control_event_id
            ]
        )
    )
    await connection.execute(
        pg_insert(strategy_entry_controls_current)
        .values(
            strategy_group_id=runtime.strategy_group_id,
            entry_state="enabled",
            control_version=1,
            last_event_id=event_id,
            reason="seed_enabled",
            updated_at_ms=ticket.created_at_ms,
        )
        .on_conflict_do_nothing(
            index_elements=[strategy_entry_controls_current.c.strategy_group_id]
        )
    )
    await connection.execute(
        pg_insert(strategy_versions)
        .values(
            strategy_version_id=runtime.strategy_version_id,
            strategy_group_id=runtime.strategy_group_id,
            version=1,
            semantics={},
            status="active",
            created_at_ms=ticket.created_at_ms,
        )
        .on_conflict_do_update(
            index_elements=[strategy_versions.c.strategy_version_id],
            set_={"strategy_group_id": runtime.strategy_group_id, "status": "active"},
        )
    )
    await connection.execute(
        pg_insert(event_specs)
        .values(
            event_spec_id=runtime.event_spec_id,
            strategy_version_id=runtime.strategy_version_id,
            event_id=f"event:{runtime.event_spec_id}",
            position_side=identity.netting_domain.position_side,
            timeframe="1h",
            freshness_window_ms=1_000,
            event_time_authority="close_time",
            entry_order_type=ticket.entry_order_type.value,
            protection_reference_fact_definition_id="fact:protection",
            exit_policy_id=f"exit:{runtime.event_spec_id}",
            execution_semantics={},
            status="active",
            created_at_ms=ticket.created_at_ms,
        )
        .on_conflict_do_update(
            index_elements=[event_specs.c.event_spec_id],
            set_={
                "strategy_version_id": runtime.strategy_version_id,
                "position_side": identity.netting_domain.position_side,
                "entry_order_type": ticket.entry_order_type.value,
                "status": "active",
            },
        )
    )
    await connection.execute(
        pg_insert(event_product_compatibility)
        .values(
            event_spec_id=runtime.event_spec_id,
            product_family="crypto_perpetual",
            asset_class="crypto",
            contract_type="PERPETUAL",
            underlying_type="CRYPTO",
            margin_asset="USDT",
            semantic_digest="sha256:" + "f" * 64,
            created_at_ms=ticket.created_at_ms,
        )
        .on_conflict_do_nothing(
            index_elements=[event_product_compatibility.c.event_spec_id]
        )
    )
    await connection.execute(
        pg_insert(instrument_product_profiles)
        .values(
            exchange_instrument_id=identity.netting_domain.exchange_instrument_id,
            product_family="crypto_perpetual",
            asset_class="crypto",
            contract_type="PERPETUAL",
            underlying_type="CRYPTO",
            margin_asset="USDT",
            entry_session_policy="continuous",
            status="candidate",
            max_entry_spread_bps=None,
            max_mark_index_deviation_bps=None,
            semantic_digest="sha256:" + "e" * 64,
            updated_at_ms=ticket.created_at_ms,
        )
        .on_conflict_do_nothing(
            index_elements=[instrument_product_profiles.c.exchange_instrument_id]
        )
    )
    await connection.execute(
        pg_insert(strategy_universe_versions)
        .values(
            universe_version_id=ticket.universe_version_id,
            strategy_group_id=runtime.strategy_group_id,
            event_spec_id=runtime.event_spec_id,
            universe_version=1,
            semantic_digest=ticket.universe_semantic_digest,
            lifecycle_state="active",
            installed_at_ms=ticket.created_at_ms,
            activated_at_ms=ticket.created_at_ms,
        )
        .on_conflict_do_nothing(
            index_elements=[strategy_universe_versions.c.universe_version_id]
        )
    )
    await connection.execute(
        pg_insert(strategy_universe_members)
        .values(
            universe_version_id=ticket.universe_version_id,
            exchange_instrument_id=identity.netting_domain.exchange_instrument_id,
        )
        .on_conflict_do_nothing(
            index_elements=[
                strategy_universe_members.c.universe_version_id,
                strategy_universe_members.c.exchange_instrument_id,
            ]
        )
    )
    await connection.execute(
        pg_insert(strategy_universe_current)
        .values(
            event_spec_id=runtime.event_spec_id,
            universe_version_id=ticket.universe_version_id,
            semantic_digest=ticket.universe_semantic_digest,
            lifecycle_state="active",
            activation_generation=1,
            activated_at_ms=ticket.created_at_ms,
        )
        .on_conflict_do_update(
            index_elements=[strategy_universe_current.c.event_spec_id],
            set_={
                "universe_version_id": ticket.universe_version_id,
                "semantic_digest": ticket.universe_semantic_digest,
                "lifecycle_state": "active",
                "activated_at_ms": ticket.created_at_ms,
            },
        )
    )
