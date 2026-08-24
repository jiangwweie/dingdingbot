"""Signal-ingest inputs and current runtime authority fixtures."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import JsonValue
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine

from src.trading_kernel.domain.cross_margin_stress import (
    AccountRiskSnapshot,
    MaintenanceMarginBracket,
)
from src.trading_kernel.domain.entry_admission_snapshot import EntryAdmissionSnapshot
from src.trading_kernel.domain.product import InstrumentProductProfile
from src.trading_kernel.domain.signal import (
    SignalFactSnapshot,
    StrategySignal,
    build_signal_fact_digest,
)
from src.trading_kernel.infrastructure.pg_models import (
    facts_current,
    instrument_certification_current,
    instrument_product_profiles,
    instrument_rules_current,
    instruments,
    owner_authorizations,
    owner_policy_current,
    runtime_capabilities_current,
    runtime_profiles,
    runtime_scopes_current,
    strategy_entry_control_events,
    strategy_entry_controls_current,
    strategy_universe_current,
    strategy_universe_members,
    strategy_universe_versions,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION
from src.trading_kernel.infrastructure.strategy_registry_seed import (
    seed_strategy_registry,
)


def signal(
    *,
    signal_event_id: str = "signal-live-1",
    runtime_scope_id: str = "scope-sor-btc-long",
    position_side: Literal["long", "short"] = "long",
    exchange_instrument_id: str = "binance-usdm:BTCUSDT:perpetual",
    occurred_at_ms: int = 1_000,
    selection_authority_id: str | None = None,
) -> StrategySignal:
    event_spec_id = (
        "event_spec:SOR-001:SOR-LONG:v4"
        if position_side == "long"
        else "event_spec:SOR-001:SOR-SHORT:v4"
    )
    facts = signal_facts(position_side=position_side)
    return StrategySignal(
        signal_event_id=signal_event_id,
        exposure_episode_id=f"episode:{signal_event_id}",
        runtime_scope_id=runtime_scope_id,
        runtime_scope_version=4,
        strategy_group_id="SOR-001",
        strategy_version_id="sgv:SOR-001:v4",
        event_spec_id=event_spec_id,
        universe_version_id="universe:sor-long:4",
        universe_semantic_digest="sha256:" + "a" * 64,
        exchange_instrument_id=exchange_instrument_id,
        position_side=position_side,
        fact_digest=build_signal_fact_digest(facts),
        occurred_at_ms=occurred_at_ms,
        observed_at_ms=occurred_at_ms + 1,
        expires_at_ms=10_000,
        facts=facts,
        selection_authority_id=selection_authority_id,
    )


def signal_facts(
    *, position_side: Literal["long", "short"]
) -> tuple[SignalFactSnapshot, ...]:
    values: tuple[tuple[str, str, JsonValue, bool], ...]
    if position_side == "long":
        values = (
            ("fact:opening_range_defined_v3:v3", "condition", True, True),
            ("fact:breakout_edge_crossed_v3:v3", "condition", True, True),
            (
                "fact:opening_range_high_reference_v3:v3",
                "lifecycle_reference",
                "10050.0",
                True,
            ),
            (
                "fact:opening_range_low_reference_v3:v3",
                "protection_reference",
                "9900.0",
                True,
            ),
            ("fact:session_start_ms_v3:v3", "identity_reference", "1000", True),
            ("fact:session_end_ms_v3:v3", "lifecycle_reference", "86401000", True),
        )
    else:
        values = (
            ("fact:opening_range_defined_v3:v3", "condition", True, True),
            ("fact:breakdown_edge_crossed_v3:v3", "condition", True, True),
            (
                "fact:opening_range_low_reference_v3:v3",
                "lifecycle_reference",
                "9950.0",
                True,
            ),
            (
                "fact:opening_range_high_reference_v3:v3",
                "protection_reference",
                "10100.0",
                True,
            ),
            ("fact:session_start_ms_v3:v3", "identity_reference", "1000", True),
            ("fact:session_end_ms_v3:v3", "lifecycle_reference", "86401000", True),
        )
    return tuple(
        SignalFactSnapshot(
            fact_definition_id=fact_definition_id,
            role=role,  # type: ignore[arg-type]
            value=value,
            satisfied=satisfied,
            observed_at_ms=1_000,
            valid_until_ms=10_000,
            projection_version=1,
        )
        for fact_definition_id, role, value, satisfied in values
    )


def admission_snapshot() -> EntryAdmissionSnapshot:
    return EntryAdmissionSnapshot(
        account_risk_snapshot=AccountRiskSnapshot.create(
            venue_id="binance-usdm",
            account_id="subaccount-main",
            account_risk_mode="standard_usdm_single_asset",
            settlement_asset="USDT",
            position_mode="independent_sides",
            margin_mode="cross",
            exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
            mark_price=Decimal(10000),
            configured_leverage=1,
            total_wallet_balance=Decimal(1000),
            total_margin_balance=Decimal(1000),
            total_initial_margin=Decimal(0),
            total_maintenance_margin=Decimal(0),
            available_margin=Decimal(1000),
            account_positions=(),
            observed_at_ms=1_001,
            valid_until_ms=10_000,
        ),
        best_bid_price=Decimal("9999.9"),
        best_ask_price=Decimal(10000),
        open_orders=(),
        observed_at_ms=1_001,
        valid_until_ms=10_000,
    )


async def seed_runtime_authority(engine: AsyncEngine) -> None:
    async with PostgresKernelUnitOfWork(engine) as uow:
        await seed_strategy_registry(uow, seeded_at_ms=1_000)
    brackets = (
        MaintenanceMarginBracket(
            bracket_id="test:1",
            notional_floor=Decimal(0),
            notional_cap=Decimal(20_000),
            maintenance_margin_rate=Decimal("0.005"),
            maintenance_amount=Decimal(0),
        ),
    )
    profile = InstrumentProductProfile(
        exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
        product_family="crypto_perpetual",
        asset_class="crypto",
        contract_type="PERPETUAL",
        underlying_type="CRYPTO",
        margin_asset="USDT",
        entry_session_policy="continuous",
        status="candidate",
    )
    async with engine.begin() as connection:
        for table, values, keys in (
            (
                owner_authorizations,
                {
                    "authorization_id": "owner-authorization:seed:SOR-001",
                    "purpose": "strategy_resume",
                    "owner_identity": "system-seed",
                    "authentication_strength": "session",
                    "request_digest": "sha256:" + "0" * 64,
                    "target_scope": {"seed": True},
                    "idempotency_key": "owner-request:seed:SOR-001",
                    "authorized_at_ms": 1_000,
                },
                [owner_authorizations.c.authorization_id],
            ),
            (
                strategy_entry_control_events,
                {
                    "strategy_entry_control_event_id": "strategy-control-event:seed:SOR-001",
                    "strategy_group_id": "SOR-001",
                    "control_version": 1,
                    "operation": "resume",
                    "target_state": "enabled",
                    "authorization_id": "owner-authorization:seed:SOR-001",
                    "reason": "seed_enabled",
                    "payload": {},
                    "created_at_ms": 1_000,
                },
                [strategy_entry_control_events.c.strategy_entry_control_event_id],
            ),
            (
                strategy_entry_controls_current,
                {
                    "strategy_group_id": "SOR-001",
                    "entry_state": "enabled",
                    "control_version": 1,
                    "last_event_id": "strategy-control-event:seed:SOR-001",
                    "reason": "seed_enabled",
                    "updated_at_ms": 1_000,
                },
                [strategy_entry_controls_current.c.strategy_group_id],
            ),
            (
                instruments,
                {
                    "exchange_instrument_id": "binance-usdm:BTCUSDT:perpetual",
                    "venue_id": "binance-usdm",
                    "asset_class": "crypto",
                    "venue_symbol": "BTCUSDT",
                    "contract_kind": "perpetual",
                    "status": "active",
                },
                [instruments.c.exchange_instrument_id],
            ),
        ):
            await connection.execute(
                pg_insert(table)
                .values(**values)
                .on_conflict_do_nothing(index_elements=keys)
            )
        await connection.execute(
            pg_insert(instrument_product_profiles).values(
                **profile.model_dump(mode="python"),
                semantic_digest=profile.semantic_digest,
                updated_at_ms=1_000,
            )
        )
        await connection.execute(
            pg_insert(strategy_universe_versions).values(
                universe_version_id="universe:sor-long:4",
                strategy_group_id="SOR-001",
                event_spec_id="event_spec:SOR-001:SOR-LONG:v4",
                universe_version=4,
                semantic_digest="sha256:" + "a" * 64,
                lifecycle_state="active",
                installed_at_ms=900,
                activated_at_ms=950,
            )
        )
        await connection.execute(
            pg_insert(strategy_universe_members).values(
                universe_version_id="universe:sor-long:4",
                exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
            )
        )
        await connection.execute(
            pg_insert(strategy_universe_current).values(
                event_spec_id="event_spec:SOR-001:SOR-LONG:v4",
                universe_version_id="universe:sor-long:4",
                semantic_digest="sha256:" + "a" * 64,
                lifecycle_state="active",
                activation_generation=1,
                activated_at_ms=950,
            )
        )
        await connection.execute(
            pg_insert(instrument_rules_current).values(
                venue_id="binance-usdm",
                exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
                quantity_step=Decimal("0.001"),
                price_tick=Decimal("0.1"),
                min_quantity=Decimal("0.001"),
                min_notional=Decimal(5),
                exchange_max_leverage=10,
                maintenance_margin_brackets=[
                    item.model_dump(mode="json") for item in brackets
                ],
                maintenance_margin_brackets_digest="sha256:" + "5" * 64,
                notional_coefficient=Decimal(1),
                notional_coefficient_certified=True,
                session_and_settlement={},
                observed_at_ms=1_000,
                valid_until_ms=10_000,
                projection_version=1,
            )
        )
        await connection.execute(
            pg_insert(owner_policy_current).values(
                owner_policy_id="policy-main",
                policy_version=7,
                enabled=True,
                new_entry_submit_enabled=True,
                priority_rank=1,
                max_concurrent_tickets=8,
                max_strategy_group_concurrent_tickets=2,
                family_ticket_limits={
                    "long_continuation": 1,
                    "opening_range": 2,
                    "rally_failure_short": 1,
                },
                max_ticket_stop_risk_fraction=Decimal("0.02"),
                max_gross_stop_risk_fraction=Decimal("0.06"),
                max_ticket_initial_margin_fraction=Decimal("0.30"),
                max_gross_initial_margin_utilization=Decimal("0.90"),
                directional_stop_risk_limit_fraction=Decimal("0.04"),
                min_materialization_ratio=Decimal("0.50"),
                max_leverage=10,
                supported_margin_mode="cross",
                post_stop_stress_multiple=Decimal("2.0"),
                max_post_fill_stop_risk_overrun_fraction=Decimal("0.10"),
                scope={
                    "event_runtime_profiles": [
                        {
                            "event_spec_id": "event_spec:SOR-001:SOR-LONG:v4",
                            "runtime_profile_id": "tiny-live-v1",
                        },
                        {
                            "event_spec_id": "event_spec:SOR-001:SOR-SHORT:v4",
                            "runtime_profile_id": "tiny-live-v1",
                        },
                    ]
                },
                updated_at_ms=1_000,
            )
        )
        await connection.execute(
            pg_insert(runtime_profiles).values(
                runtime_profile_id="tiny-live-v1",
                venue_id="binance-usdm",
                account_id="subaccount-main",
                environment="live",
                position_mode="independent_sides",
                status="active",
                updated_at_ms=1_000,
            )
        )
        await connection.execute(
            pg_insert(instrument_certification_current).values(
                runtime_profile_id="tiny-live-v1",
                exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
                status="eligible",
                blocker_code=None,
                facts_digest="sha256:" + "c" * 64,
                product_rules_digest="sha256:" + "d" * 64,
                configured_leverage=5,
                margin_mode="cross",
                position_mode="independent_sides",
                observed_at_ms=1_000,
                valid_until_ms=10_000,
                next_check_at_ms=5_000,
                lease_owner=None,
                lease_expires_at_ms=None,
                lease_universe_version_id=None,
                projection_version=1,
            )
        )
        await connection.execute(
            pg_insert(runtime_scopes_current).values(
                runtime_scope_id="scope-sor-btc-long",
                strategy_group_id="SOR-001",
                strategy_version_id="sgv:SOR-001:v4",
                event_spec_id="event_spec:SOR-001:SOR-LONG:v4",
                runtime_profile_id="tiny-live-v1",
                owner_policy_id="policy-main",
                exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
                position_side="long",
                universe_version_id="universe:sor-long:4",
                universe_semantic_digest="sha256:" + "a" * 64,
                lifecycle_state="active",
                observation_enabled=True,
                entry_enabled=True,
                scope_version=4,
                warm_closed_bar_time_ms=900,
                warm_completed_at_ms=900,
                warm_readiness_digest="sha256:" + "a" * 64,
                warm_valid_until_ms=10_000,
                updated_at_ms=1_000,
            )
        )
        for fact in signal_facts(position_side="long"):
            await connection.execute(
                pg_insert(facts_current).values(
                    fact_current_id=f"fact-current:scope-sor-btc-long:{fact.fact_definition_id}",
                    runtime_scope_id="scope-sor-btc-long",
                    fact_definition_id=fact.fact_definition_id,
                    value=fact.value,
                    satisfied=fact.satisfied,
                    observed_at_ms=fact.observed_at_ms,
                    valid_until_ms=fact.valid_until_ms,
                    projection_version=fact.projection_version,
                )
            )
        await connection.execute(
            pg_insert(runtime_capabilities_current).values(
                capability_key="strategy_signal_ingest",
                enabled=True,
                certified_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                certification={},
                updated_at_ms=1_000,
            )
        )
