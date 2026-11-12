"""Explicit local Owner configuration and bullish public BTC fixture; never production."""

from decimal import Decimal

from src.trading_kernel.application.exit_configuration import (
    ActivateExitConfigurationRequest,
    activate_exit_configuration,
    preview_exit_configuration,
)
from src.trading_kernel.domain.exit_configuration import (
    EXIT_EVENTS,
    MA50_EVENTS,
    EventExitParameters,
    ExitConfigurationIntent,
)
from src.trading_kernel.domain.exit_execution import ExitOrderRules
from src.trading_kernel.domain.exit_regime import FOUR_HOURS_MS, BtcMa50Snapshot
from src.trading_kernel.domain.market import ClosedCandle
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork


def executable_fixture_rules(
    *,
    now_ms: int,
    valid_until_ms: int,
    step: Decimal = Decimal(".001"),
    minimum: Decimal = Decimal(".001"),
    notional: Decimal = Decimal(5),
    tick: Decimal = Decimal(".1"),
) -> ExitOrderRules:
    return ExitOrderRules(
        quantity_step=step,
        min_quantity=minimum,
        max_quantity=Decimal(1000000000),
        min_notional=notional,
        price_tick=tick,
        min_price=Decimal(".00000001"),
        max_price=Decimal(1000000000),
        runner_quantity_step=step,
        runner_min_quantity=minimum,
        runner_max_quantity=Decimal(1000000000),
        observed_at_ms=now_ms,
        valid_until_ms=valid_until_ms,
    )


async def refresh_bullish_ma50(uow, *, now_ms: int) -> None:
    latest = now_ms // FOUR_HOURS_MS * FOUR_HOURS_MS
    if latest <= 50 * FOUR_HOURS_MS:
        return
    current = await uow.exit_profiles.get_ma50_snapshot()
    if (
        current is not None
        and current.observed_at_ms <= now_ms < current.valid_until_ms
    ):
        return
    rows = tuple(
        ClosedCandle(
            open_time_ms=latest - (50 - i) * FOUR_HOURS_MS,
            close_time_ms=latest - (49 - i) * FOUR_HOURS_MS,
            open=Decimal(101 if i == 49 else 100),
            high=Decimal(101 if i == 49 else 100),
            low=Decimal(101 if i == 49 else 100),
            close=Decimal(101 if i == 49 else 100),
            volume=Decimal(1),
        )
        for i in range(50)
    )
    await uow.exit_profiles.save_ma50_snapshot(
        BtcMa50Snapshot.create(candles=rows, observed_at_ms=now_ms)
    )


async def install_approved_exit_configuration(
    engine, *, account_id: str, now_ms: int
) -> None:
    async with PostgresKernelUnitOfWork(engine) as uow:
        await install_approved_exit_configuration_in_uow(
            uow, account_id=account_id, now_ms=now_ms
        )


async def install_approved_exit_configuration_in_uow(
    uow, *, account_id: str, now_ms: int
) -> None:
    current = await uow.exit_profiles.get_current_configuration(
        venue_id="binance-usdm", account_id=account_id
    )
    if current is None:
        parameters = []
        for event in EXIT_EVENTS:
            binding_current = await uow.exit_profiles.get_current_binding(event)
            binding = await uow.exit_profiles.get_binding(
                binding_current.exit_binding_id
            )
            profile = await uow.exit_profiles.get_profile(
                exit_profile_id=binding.exit_profile_id,
                semantic_hash=binding.exit_profile_semantic_hash,
            )
            sor = event in EXIT_EVENTS[4:]
            parameters.append(
                EventExitParameters(
                    event_spec_id=event,
                    expected_binding_id=binding_current.exit_binding_id,
                    expected_binding_revision=binding_current.projection_version,
                    reward_multiple=Decimal("1.2") if sor else Decimal(1),
                    target_fraction=profile.profile.tp1.quantity_fraction
                    if sor
                    else Decimal(".05"),
                    minimum_lift=not sor,
                    max_actual_fraction=Decimal(1) if sor else Decimal(".5"),
                    ma50_enabled=event in MA50_EVENTS,
                )
            )
        intent = ExitConfigurationIntent(
            account_id=account_id, expected_revision=0, events=tuple(parameters)
        )
        preview = await preview_exit_configuration(uow, intent=intent, now_ms=now_ms)
        await activate_exit_configuration(
            uow,
            request=ActivateExitConfigurationRequest(
                expected_version=0,
                intent=intent,
                preview_digest=preview.preview_digest,
                preview_valid_until_ms=preview.valid_until_ms,
                reason="explicit fixture Owner activation",
                idempotency_key="fixture-exit-config",
                owner_identity="fixture-owner",
                now_ms=now_ms,
            ),
            authentication_strength="totp_step_up",
        )
    await refresh_bullish_ma50(uow, now_ms=now_ms)


async def issue_ready_signal_with_exit_fixture(uow, request):
    """Selection tests explicitly supply the independent v2 Owner/venue prerequisites."""
    from src.trading_kernel.application.issue_ready_signal import issue_ready_signal

    account = request.admission_snapshot.account_risk_snapshot
    await install_approved_exit_configuration_in_uow(
        uow, account_id=account.account_id, now_ms=request.now_ms
    )
    if request.now_ms <= 50 * FOUR_HOURS_MS:
        # The Selection suite uses synthetic early-1970 clocks. BTC observation
        # is an independent declared boundary here; raw 50-bar behavior is tested
        # by test_btc_ma50_regime and the full-chain market consumer separately.
        from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest

        latest = request.now_ms // FOUR_HOURS_MS * FOUR_HOURS_MS
        await uow.exit_profiles.save_ma50_snapshot(
            BtcMa50Snapshot(
                latest_close_time_ms=latest,
                latest_close=Decimal(101),
                sma50=Decimal(100),
                window_digest=canonical_digest(
                    {"fixture": "independent_bullish_boundary", "closed_at_ms": latest}
                ),
                observed_at_ms=request.now_ms,
                valid_until_ms=latest + FOUR_HOURS_MS,
            )
        )
    rules = await uow.signals.get_instrument_rules(
        account.venue_id, account.exchange_instrument_id
    )
    if rules is not None and rules.exit_order_rules is None:
        payload = {
            name: getattr(rules, name)
            for name in type(rules).model_fields
            if name != "projection_version"
        }
        payload["exit_order_rules"] = executable_fixture_rules(
            now_ms=rules.observed_at_ms,
            valid_until_ms=rules.valid_until_ms,
            step=rules.quantity_step,
            minimum=rules.min_quantity,
            notional=rules.min_notional,
            tick=rules.price_tick,
        )
        await uow.signals.upsert_instrument_rules(**payload)
    return await issue_ready_signal(uow, request)


async def declared_postfill_exit_event(uow, aggregate, event):
    """Freeze exact recording-exchange facts for Selection-only lifecycle fixtures."""
    from src.trading_kernel.domain.commands import ExchangeCommandKind
    from src.trading_kernel.domain.events import PostFillStressAssessed
    from src.trading_kernel.domain.exit_execution import (
        CompleteEntryFills,
        EntryFill,
        build_post_fill_exit_plan,
    )

    if not isinstance(event, PostFillStressAssessed) or event.status != "passed":
        return event
    profile = await uow.exit_profiles.get_profile(
        exit_profile_id=aggregate.ticket.exit_policy_id,
        semantic_hash=aggregate.ticket.exit_policy_semantic_hash,
    )
    if profile is None or profile.profile.execution is None:
        return event
    refs = await uow.exchange_commands.list_order_references(
        aggregate.identity.ticket_id
    )
    entry = next(r for r in refs if r.command_kind is ExchangeCommandKind.ENTRY)
    rules = await uow.signals.get_instrument_rules(
        aggregate.identity.netting_domain.venue_id,
        aggregate.identity.netting_domain.exchange_instrument_id,
    )
    explicit = executable_fixture_rules(
        now_ms=event.occurred_at_ms,
        valid_until_ms=event.occurred_at_ms + 60_000,
        step=rules.quantity_step if rules else Decimal(".001"),
        minimum=rules.min_quantity if rules else Decimal(".001"),
        notional=rules.min_notional if rules else Decimal(5),
        tick=rules.price_tick if rules else Decimal(".01"),
    )
    plan = build_post_fill_exit_plan(
        ticket_id=aggregate.identity.ticket_id,
        entry_fills=CompleteEntryFills(
            command_id=entry.command_id,
            exchange_order_id=entry.submitted_exchange_order_id,
            fills=(
                EntryFill(
                    trade_id="selection-recorded-entry",
                    quantity=aggregate.position_qty,
                    price=aggregate.average_fill_price,
                ),
            ),
            observed_at_ms=event.occurred_at_ms,
        ),
        quantity=aggregate.position_qty,
        initial_stop=aggregate.ticket.initial_stop_price,
        profile=profile.profile,
        binding_id=aggregate.ticket.exit_binding_id,
        binding_revision=aggregate.ticket.exit_binding_authority_version,
        management_revision=aggregate.management_revision,
        rules=explicit,
        now_ms=event.occurred_at_ms,
    )
    return event.model_copy(update={"exit_plan": plan})


async def maintain_ticket_lifecycle_with_exact_tp_fixture(uow, request):
    from src.trading_kernel.application.maintain_ticket_lifecycle import (
        maintain_ticket_lifecycle,
    )
    from src.trading_kernel.domain.commands import ExchangeCommandKind
    from src.trading_kernel.domain.exit_execution import EntryFill, TpFillEvidence

    aggregate = await uow.aggregates.get(request.ticket_id)
    if (
        aggregate is not None
        and aggregate.post_fill_exit_plan is not None
        and request.facts.tp1_filled_quantity > 0
    ):
        reference = next(
            r
            for r in await uow.exchange_commands.list_order_references(
                request.ticket_id
            )
            if r.command_kind is ExchangeCommandKind.TAKE_PROFIT
        )
        proof = TpFillEvidence(
            command_id=reference.command_id,
            exchange_order_id=reference.submitted_exchange_order_id,
            fills=(
                EntryFill(
                    trade_id="selection-recorded-tp",
                    quantity=request.facts.tp1_filled_quantity,
                    price=request.facts.tp1_average_fill_price,
                ),
            ),
            observed_at_ms=request.facts.observed_at_ms,
        )
        request = request.model_copy(
            update={
                "facts": request.facts.model_copy(update={"tp_fill_evidence": proof})
            }
        )
    return await maintain_ticket_lifecycle(uow, request)

from src.trading_kernel.infrastructure.strategy_registry_seed import (
    seed_strategy_registry,
)


async def intent(engine,account_id="manual-account"):
    async with PostgresKernelUnitOfWork(engine) as uow:
        await seed_strategy_registry(uow, seeded_at_ms=1000)
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from src.trading_kernel.infrastructure.pg_models import runtime_profiles
    async with engine.begin() as c:
        await c.execute(pg_insert(runtime_profiles).values(runtime_profile_id="tiny-live-v1",venue_id="binance-usdm",account_id=account_id,
            environment="live",position_mode="independent_sides",status="active",updated_at_ms=1000).on_conflict_do_nothing())
    parameters = []
    async with PostgresKernelUnitOfWork(engine) as uow:
        for event in EXIT_EVENTS:
            current = await uow.exit_profiles.get_current_binding(event)
            binding = await uow.exit_profiles.get_binding(current.exit_binding_id)
            profile = await uow.exit_profiles.get_profile(
                exit_profile_id=binding.exit_profile_id,
                semantic_hash=binding.exit_profile_semantic_hash,
            )
            sor = event in EXIT_EVENTS[4:]
            parameters.append(
                EventExitParameters(
                    event_spec_id=event,
                    expected_binding_id=current.exit_binding_id,
                    expected_binding_revision=current.projection_version,
                    reward_multiple=Decimal("1.2") if sor else Decimal(1),
                    target_fraction=profile.profile.tp1.quantity_fraction
                    if sor
                    else Decimal(".05"),
                    minimum_lift=not sor,
                    max_actual_fraction=Decimal(1) if sor else Decimal(".5"),
                    ma50_enabled=event in MA50_EVENTS,
                )
            )
    return ExitConfigurationIntent(
        account_id=account_id, expected_revision=0, events=tuple(parameters)
    )
