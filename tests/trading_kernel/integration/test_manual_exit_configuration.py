from decimal import Decimal as D

import pytest
import sqlalchemy as sa

from src.trading_kernel.application.exit_configuration import (
    ActivateExitConfigurationRequest,
    activate_exit_configuration,
    preview_exit_configuration,
)
from src.trading_kernel.application.exit_regime import check_exit_regime
from src.trading_kernel.application.owner_control import OwnerControlConflict
from src.trading_kernel.domain.exit_configuration import (
    EXIT_EVENTS,
    ExitConfigurationIntent,
)
from src.trading_kernel.domain.exit_regime import FOUR_HOURS_MS, BtcMa50Snapshot
from src.trading_kernel.domain.market import ClosedCandle
from src.trading_kernel.infrastructure.pg_models import (
    event_exit_profile_binding_current,
    exit_configurations,
    exit_policies,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from tests.trading_kernel.support.exit_configuration import intent


async def activate(engine, proposed):
    async with PostgresKernelUnitOfWork(engine) as uow:
        preview = await preview_exit_configuration(uow, intent=proposed, now_ms=2000)
    request = ActivateExitConfigurationRequest(
        expected_version=0,
        intent=proposed,
        preview_digest=preview.preview_digest,
        preview_valid_until_ms=preview.valid_until_ms,
        reason="Owner-approved configuration",
        idempotency_key="request-config-1",
        owner_identity="owner",
        now_ms=2100,
    )
    async with PostgresKernelUnitOfWork(engine) as uow:
        record = await activate_exit_configuration(
            uow, request=request, authentication_strength="totp_step_up"
        )
    return record, request


@pytest.mark.asyncio
async def test_atomic_six_profiles_three_gates_idempotency_and_no_resume(
    lifecycle_engine,
):
    proposed = await intent(lifecycle_engine)
    record, request = await activate(lifecycle_engine, proposed)
    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        assert (
            await uow.exit_profiles.get_current_configuration(
                venue_id="binance-usdm", account_id="manual-account"
            )
            == record
        )
        repeated = await activate_exit_configuration(
            uow, request=request, authentication_strength="totp_step_up"
        )
        assert repeated == record
        for event in EXIT_EVENTS:
            current = await uow.exit_profiles.get_current_binding(event)
            assert current.projection_version == 2
        reason, _ = await check_exit_regime(
            uow,
            venue_id="binance-usdm",
            account_id="manual-account",
            event_spec_id=EXIT_EVENTS[0],
            now_ms=2200,
        )
        assert reason == "ma50_unavailable"
        assert (
            await check_exit_regime(
                uow,
                venue_id="binance-usdm",
                account_id="manual-account",
                event_spec_id=EXIT_EVENTS[3],
                now_ms=2200,
            )
        )[0] is None
    async with lifecycle_engine.connect() as c:
        assert (
            await c.scalar(sa.select(sa.func.count()).select_from(exit_configurations))
            == 1
        )
        assert (
            await c.scalar(
                sa.select(sa.func.count())
                .select_from(exit_policies)
                .where(exit_policies.c.profile_schema_version == "exit_profile_v2")
            )
            == 6
        )


@pytest.mark.asyncio
async def test_sixth_binding_failure_rolls_back_entire_bundle(
    lifecycle_engine, monkeypatch
):
    from src.trading_kernel.infrastructure.pg_exit_profile_repository import (
        PostgresExitProfileAuthorityRepository,
    )

    proposed = await intent(lifecycle_engine)
    original = PostgresExitProfileAuthorityRepository.switch_current_binding
    calls = 0

    async def fail_sixth(self, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 6:
            raise RuntimeError("injected sixth binding failure")
        return await original(self, **kwargs)

    monkeypatch.setattr(
        PostgresExitProfileAuthorityRepository, "switch_current_binding", fail_sixth
    )
    with pytest.raises(RuntimeError, match="sixth"):
        await activate(lifecycle_engine, proposed)
    async with lifecycle_engine.connect() as c:
        assert (
            await c.scalar(sa.select(sa.func.count()).select_from(exit_configurations))
            == 0
        )
        assert (
            await c.scalar(
                sa.select(sa.func.count())
                .select_from(exit_policies)
                .where(exit_policies.c.profile_schema_version == "exit_profile_v2")
            )
            == 0
        )
        assert (
            not (
                await c.execute(
                    sa.select(
                        event_exit_profile_binding_current.c.projection_version
                    ).where(
                        event_exit_profile_binding_current.c.event_spec_id.in_(
                            EXIT_EVENTS
                        )
                    )
                )
            )
            .scalars()
            .all()
            .count(2)
        )


@pytest.mark.asyncio
async def test_preview_expires_and_cannot_activate_stale_bindings(lifecycle_engine):
    proposed = await intent(lifecycle_engine)
    await activate(lifecycle_engine, proposed)
    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        with pytest.raises(OwnerControlConflict):
            await preview_exit_configuration(uow, intent=proposed, now_ms=2200)


@pytest.mark.asyncio
async def test_ma50_new_boundary_invalidates_old_allowed_proof(lifecycle_engine):
    proposed = await intent(lifecycle_engine)
    await activate(lifecycle_engine, proposed)
    now = 51 * FOUR_HOURS_MS + 100
    rows = tuple(
        ClosedCandle(
            open_time_ms=(i + 1) * FOUR_HOURS_MS,
            close_time_ms=(i + 2) * FOUR_HOURS_MS,
            open=D(100 if i == 49 else 90),
            high=D(100 if i == 49 else 90),
            low=D(100 if i == 49 else 90),
            close=D(100 if i == 49 else 90),
            volume=D(1),
        )
        for i in range(50)
    )
    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        await uow.exit_profiles.save_ma50_snapshot(
            BtcMa50Snapshot.create(candles=rows, observed_at_ms=now)
        )
        assert (
            await check_exit_regime(
                uow,
                venue_id="binance-usdm",
                account_id="manual-account",
                event_spec_id=EXIT_EVENTS[0],
                now_ms=now,
            )
        )[0] is None
        assert (
            await check_exit_regime(
                uow,
                venue_id="binance-usdm",
                account_id="manual-account",
                event_spec_id=EXIT_EVENTS[0],
                now_ms=52 * FOUR_HOURS_MS,
            )
        )[0] == "ma50_stale"


@pytest.mark.asyncio
async def test_readonly_certification_accepts_only_audited_supported_owner_revisions(
    lifecycle_engine,
):
    from scripts.trading_kernel.certify_readonly import _exit_profile_authority_manifest
    from src.trading_kernel.infrastructure.pg_models import (
        event_exit_profile_binding_events,
        event_exit_profile_bindings,
        exit_configuration_current,
        owner_authorizations,
    )

    proposed = await intent(lifecycle_engine)
    await activate(lifecycle_engine, proposed)
    async with lifecycle_engine.connect() as c:
        profiles = (await c.execute(sa.select(exit_policies))).mappings().all()
        bindings = (
            (await c.execute(sa.select(event_exit_profile_bindings))).mappings().all()
        )
        events = (
            (await c.execute(sa.select(event_exit_profile_binding_events)))
            .mappings()
            .all()
        )
        configurations = (
            (await c.execute(sa.select(exit_configurations))).mappings().all()
        )
        current_config = (
            (await c.execute(sa.select(exit_configuration_current))).mappings().all()
        )
        auths = (await c.execute(sa.select(owner_authorizations))).mappings().all()
        rows = (
            (
                await c.execute(
                    sa.text("""SELECT cur.event_spec_id,cur.exit_binding_id,cur.binding_semantic_hash,cur.projection_version,
            b.event_spec_id AS binding_event_spec_id,b.exit_profile_id,b.exit_profile_semantic_hash,b.binding_semantic_hash AS fact_binding_hash,
            p.status AS profile_status,e.status AS event_status FROM brc_event_exit_profile_binding_current cur
            JOIN brc_event_exit_profile_bindings b USING(exit_binding_id) JOIN brc_exit_policies p ON p.exit_policy_id=b.exit_profile_id
            JOIN brc_event_specs e ON e.event_spec_id=cur.event_spec_id""")
                )
            )
            .mappings()
            .all()
        )

    def verify(profile_rows, authorization_rows=auths):
        return _exit_profile_authority_manifest(
            profile_rows=profile_rows,
            binding_rows=bindings,
            current_rows=rows,
            event_rows=events,
            configuration_rows=configurations,
            configuration_current_rows=current_config,
            authorization_rows=authorization_rows,
            account_id="manual-account",
        )

    assert verify(profiles)["status"] == "pass"
    assert verify(profiles, [])["status"] == "fail"
    alien = dict(profiles[-1])
    alien["exit_policy_id"] = "unapproved-profile"
    assert verify([*profiles, alien])["status"] == "fail"


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_fills", [False, True])
async def test_complete_entry_vwap_freezes_one_plan_after_stop_and_rejects_missing_proof(
    lifecycle_engine, missing_fills
):
    from src.trading_kernel.application.dispatch_exchange_command import (
        DispatchCommandRequest,
        dispatch_one_command,
    )
    from src.trading_kernel.application.issue_ticket import (
        IssueTicketStatus,
        issue_ticket,
    )
    from src.trading_kernel.application.reconcile_ticket import (
        PostFillStressReconcileRequest,
        ReconcileTicketRequest,
        reconcile_post_fill_stress,
        reconcile_ticket,
    )
    from src.trading_kernel.application.runtime_facts import InstrumentRulesFacts
    from src.trading_kernel.domain.aggregate import AggregateStatus
    from src.trading_kernel.domain.capacity import freeze_capacity_claim
    from src.trading_kernel.domain.commands import ExchangeCommandKind
    from src.trading_kernel.domain.exit_execution import (
        CompleteEntryFills,
        EntryFill,
        ExitOrderRules,
    )
    from src.trading_kernel.domain.position import PositionSnapshot
    from src.trading_kernel.infrastructure.pg_models import (
        post_fill_exit_plans,
        runtime_capabilities_current,
    )
    from src.trading_kernel.infrastructure.runtime_identity import (
        CURRENT_SCHEMA_REVISION,
    )
    from tests.trading_kernel.support.capacity_claims import make_issue_request
    from tests.trading_kernel.support.command_dispatch import (
        registered_sor_ticket,
        seed_policy,
    )
    from tests.trading_kernel.support.dispatch_venues import (
        KindAwareAcceptingVenue,
        PreflightFacts,
    )
    from tests.trading_kernel.support.runtime_scope import seed_ticket_runtime_scope

    base = registered_sor_ticket()
    proposed = await intent(lifecycle_engine,account_id=base.identity.netting_domain.account_id)
    await seed_policy(lifecycle_engine)
    await seed_ticket_runtime_scope(lifecycle_engine, base)
    proposed = proposed.model_copy(
        update={"account_id": base.identity.netting_domain.account_id}
    )
    _record, _ = await activate(lifecycle_engine, proposed)
    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        current = await uow.exit_profiles.get_current_binding(
            base.identity.runtime.event_spec_id
        )
        binding = await uow.exit_profiles.get_binding(current.exit_binding_id)
        _, proof = await check_exit_regime(
            uow,
            venue_id=base.identity.netting_domain.venue_id,
            account_id=base.identity.netting_domain.account_id,
            event_spec_id=base.identity.runtime.event_spec_id,
            now_ms=2200,
        )
    original = make_issue_request(ticket=base, now_ms=2200, claim_owner="issuer")
    payload = {
        name: getattr(original.capacity_claim, name)
        for name in type(original.capacity_claim).model_fields
        if name not in {"capacity_claim_id", "decision_digest"}
    }
    payload.update(
        exit_policy_id=binding.exit_profile_id,
        exit_policy_semantic_hash=binding.exit_profile_semantic_hash,
        exit_binding_id=binding.exit_binding_id,
        exit_binding_semantic_hash=binding.binding_semantic_hash,
        exit_binding_authority_version=current.projection_version,
        regime_admission=proof,
    )
    claim = freeze_capacity_claim(**payload)
    async with lifecycle_engine.begin() as c:
        await c.execute(
            sa.insert(runtime_capabilities_current).values(
                capability_key="exchange_commands",
                enabled=True,
                certified_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                certification={"product_id": "brc-app-manual-v1"},
                updated_at_ms=2000,
            )
        )
    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        result = await issue_ticket(
            uow, original.model_copy(update={"capacity_claim": claim})
        )
    assert result.status is IssueTicketStatus.ISSUED
    venue = KindAwareAcceptingVenue()

    async def dispatch(now):
        return await dispatch_one_command(
            lambda: PostgresKernelUnitOfWork(lifecycle_engine),
            venue,
            DispatchCommandRequest(
                worker_id="dispatcher",
                ticket_id=base.identity.ticket_id,
                now_ms=now,
                lease_until_ms=now + 5000,
                timeout_seconds=2,
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                admission_snapshot_validity_ms=1000,
            ),
            entry_facts_source=PreflightFacts(),
            clock_ms=lambda: now,
        )

    await dispatch(2300)
    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=base.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=base.identity.netting_domain,
                    quantity=base.quantity,
                    average_entry_price=base.entry_reference_price,
                    observed_at_ms=2400,
                ),
            ),
        )
    await dispatch(2500)
    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        refs = await uow.exchange_commands.list_order_references(
            base.identity.ticket_id
        )
        reference = next(r for r in refs if r.command_kind is ExchangeCommandKind.ENTRY)
        # Reuse the existing post-fill account authority builder, replacing only exact fills.
        from tests.trading_kernel.support.reducer_states import post_fill_stress_event

        aggregate = await uow.aggregates.get(base.identity.ticket_id)
        assert aggregate.status is AggregateStatus.POST_FILL_RISK_PENDING
        stress = post_fill_stress_event(aggregate)
        account_source = stress.evidence.request.account_snapshot
        account = type(account_source).create(
            **{
                name: getattr(account_source, name)
                for name in type(account_source).model_fields
                if name not in {"snapshot_digest", "observed_at_ms", "valid_until_ms"}
            },
            observed_at_ms=2600,
            valid_until_ms=3600,
        )
        rules = InstrumentRulesFacts(
            exchange_instrument_id=base.identity.netting_domain.exchange_instrument_id,
            quantity_step=D(".0001"),
            price_tick=D(".1"),
            min_quantity=D(".0001"),
            min_notional=D(5),
            exchange_max_leverage=10,
            maintenance_margin_brackets=stress.evidence.request.maintenance_margin_brackets,
            maintenance_margin_brackets_digest=stress.evidence.request.maintenance_margin_brackets_digest,
            notional_coefficient=D(1),
            notional_coefficient_certified=True,
            observed_at_ms=2600,
            valid_until_ms=3600,
            exit_order_rules=ExitOrderRules(
                quantity_step=D(".0001"),
                min_quantity=D(".0001"),
                max_quantity=D(100),
                price_tick=D(".1"),
                min_price=D(".1"),
                max_price=D(1000000),
                min_notional=D(5),
                runner_quantity_step=D(".0001"),
                runner_min_quantity=D(".0001"),
                runner_max_quantity=D(100),
                observed_at_ms=2600,
                valid_until_ms=3600,
            ),
        )
        await uow.signals.upsert_instrument_rules(
            venue_id=base.identity.netting_domain.venue_id,
            **{name: getattr(rules, name) for name in type(rules).model_fields},
        )
        request = PostFillStressReconcileRequest(
            ticket_id=base.identity.ticket_id,
            account_snapshot=account,
            instrument_rules=rules,
            assessed_at_ms=2600,
            entry_fills=None
            if missing_fills
            else CompleteEntryFills(
                command_id=reference.command_id,
                exchange_order_id=reference.submitted_exchange_order_id,
                fills=(
                    EntryFill(
                        trade_id="trade-1", quantity=base.quantity, price=D(60010)
                    ),
                ),
                observed_at_ms=2600,
            ),
        )
        await reconcile_post_fill_stress(uow, request)
    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        aggregate = await uow.aggregates.get(base.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(base.identity.ticket_id)
        if missing_fills:
            assert aggregate.status is AggregateStatus.CONTROLLED_FLATTEN_PENDING
            assert aggregate.post_fill_exit_plan is None
            assert not any(c.kind is ExchangeCommandKind.TAKE_PROFIT for c in commands)
        else:
            assert aggregate.post_fill_exit_plan.entry_price == D(60010)
            assert aggregate.post_fill_exit_plan.tp_price == D(61222)
            assert aggregate.ticket.entry_reference_price == D(60000)
            assert next(
                c for c in commands if c.kind is ExchangeCommandKind.TAKE_PROFIT
            ).payload.limit_price == D(61222)
            await reconcile_post_fill_stress(uow, request)
    async with lifecycle_engine.connect() as c:
        assert await c.scalar(
            sa.select(sa.func.count()).select_from(post_fill_exit_plans)
        ) == (0 if missing_fills else 1)


@pytest.mark.asyncio
async def test_initial_package_is_fixed_then_each_event_edits_independently(
    lifecycle_engine,
):
    from src.trading_kernel.application.owner_control import OwnerControlBlocked

    proposed = await intent(lifecycle_engine)
    changed = proposed.events[0].model_copy(update={"reward_multiple": D(2)})
    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        with pytest.raises(OwnerControlBlocked, match="approved_parameters"):
            await preview_exit_configuration(
                uow,
                intent=proposed.model_copy(
                    update={"events": (changed, *proposed.events[1:])}
                ),
                now_ms=2000,
            )
    record, _ = await activate(lifecycle_engine, proposed)
    next_parameters = []
    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        for item in record.intent.events:
            cur = await uow.exit_profiles.get_current_binding(item.event_spec_id)
            next_parameters.append(
                item.model_copy(
                    update={
                        "expected_binding_id": cur.exit_binding_id,
                        "expected_binding_revision": cur.projection_version,
                        "reward_multiple": D(2)
                        if item.event_spec_id == EXIT_EVENTS[0]
                        else item.reward_multiple,
                    }
                )
            )
        new_intent = ExitConfigurationIntent(
            account_id="manual-account",
            expected_revision=1,
            events=tuple(next_parameters),
        )
        preview = await preview_exit_configuration(uow, intent=new_intent, now_ms=3000)
        new = await activate_exit_configuration(
            uow,
            request=ActivateExitConfigurationRequest(
                expected_version=1,
                intent=new_intent,
                preview_digest=preview.preview_digest,
                preview_valid_until_ms=preview.valid_until_ms,
                reason="change CPM only",
                idempotency_key="request-config-2",
                owner_identity="owner",
                now_ms=3100,
            ),
            authentication_strength="totp_step_up",
        )
        assert new.revision == 2
        for item in new.profiles:
            old = next(
                p for p in record.profiles if p.event_spec_id == item.event_spec_id
            )
            assert item.profile.tp1.reward_multiple == (
                D(2)
                if item.event_spec_id == EXIT_EVENTS[0]
                else old.profile.tp1.reward_multiple
            )
            assert item.profile.runner == old.profile.runner


@pytest.mark.asyncio
async def test_closed_ma50_conflict_withdraws_bullish_permission(lifecycle_engine):
    from tests.trading_kernel.support.exit_configuration import refresh_bullish_ma50

    proposed = await intent(lifecycle_engine)
    await activate(lifecycle_engine, proposed)
    now = 51 * FOUR_HOURS_MS + 100
    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        await refresh_bullish_ma50(uow, now_ms=now)

    class CorrectedMarket:
        async def fetch_closed_candles(self, request):
            return tuple(
                ClosedCandle(
                    open_time_ms=(i + 1) * FOUR_HOURS_MS,
                    close_time_ms=(i + 2) * FOUR_HOURS_MS,
                    open=D(99),
                    high=D(99),
                    low=D(99),
                    close=D(99),
                    volume=D(1),
                )
                for i in range(50)
            )

    # A refresh of an already valid immutable window must explicitly reject changed contents.
    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        assert not await uow.exit_profiles.save_ma50_snapshot(
            BtcMa50Snapshot.create(
                candles=await CorrectedMarket().fetch_closed_candles(None),
                observed_at_ms=now + 1,
            )
        )
    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        assert await uow.exit_profiles.get_ma50_snapshot() is None
        reason, _ = await check_exit_regime(
            uow,
            venue_id="binance-usdm",
            account_id="manual-account",
            event_spec_id=EXIT_EVENTS[0],
            now_ms=now + 2,
        )
        assert reason == "ma50_unavailable"


@pytest.mark.asyncio
async def test_conflicted_ma50_cannot_restore_permission_with_same_original_window(
    lifecycle_engine,
):
    from tests.trading_kernel.support.exit_configuration import refresh_bullish_ma50

    proposed = await intent(lifecycle_engine)
    await activate(lifecycle_engine, proposed)
    now = 51 * FOUR_HOURS_MS + 100
    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        await refresh_bullish_ma50(uow, now_ms=now)
        original = await uow.exit_profiles.get_ma50_snapshot()
        conflict = original.model_copy(
            update={
                "window_digest": "sha256:" + "b" * 64,
                "latest_close": D(99),
                "observed_at_ms": now + 1,
            }
        )
        assert not await uow.exit_profiles.save_ma50_snapshot(conflict)
        assert not await uow.exit_profiles.save_ma50_snapshot(
            original.model_copy(update={"observed_at_ms": now + 2})
        )
        assert await uow.exit_profiles.get_ma50_snapshot() is None


@pytest.mark.asyncio
async def test_exit_configuration_refuses_other_account_even_with_valid_binding_ids(lifecycle_engine):
    from src.trading_kernel.application.owner_control import OwnerControlBlocked
    proposed=await intent(lifecycle_engine)
    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        with pytest.raises(OwnerControlBlocked,match='account_scope'):
            await preview_exit_configuration(uow,intent=proposed.model_copy(update={'account_id':'other-account'}),now_ms=2000)


@pytest.mark.asyncio
async def test_split_configuration_preserves_effective_sor_exit_terms_instead_of_seed_defaults(
    lifecycle_engine,
):
    from src.trading_kernel.application.owner_control import OwnerControlBlocked
    from src.trading_kernel.domain.exit_configuration import EventExitParameters
    from src.trading_kernel.domain.orb_session_selection import ORB_DIRECTIONAL_EVENTS
    from src.trading_kernel.domain.strategy_registry import (
        registered_strategy_contracts,
    )
    from src.trading_kernel.infrastructure.strategy_registry_seed import (
        seed_strategy_registry,
    )

    original_intent = await intent(lifecycle_engine)
    changed = original_intent.model_copy(update={
        "events": tuple(item.model_copy(update={"reward_multiple": D("1.7")})
                        if item.event_spec_id in EXIT_EVENTS[4:] else item
                        for item in original_intent.events)
    })
    await activate(lifecycle_engine, original_intent)
    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        revised_events = []
        for item in changed.events:
            current = await uow.exit_profiles.get_current_binding(item.event_spec_id)
            revised_events.append(item.model_copy(update={
                "expected_binding_id": current.exit_binding_id,
                "expected_binding_revision": current.projection_version,
            }))
        revised = changed.model_copy(update={"expected_revision": 1, "events": tuple(revised_events)})
        revised_preview = await preview_exit_configuration(uow, intent=revised, now_ms=2300)
        original = await activate_exit_configuration(
            uow, request=ActivateExitConfigurationRequest(
                expected_version=1, intent=revised, preview_digest=revised_preview.preview_digest,
                preview_valid_until_ms=revised_preview.valid_until_ms,
                reason="test effective exit configuration", idempotency_key="test-configuration-v2",
                owner_identity="owner", now_ms=2400,
            ), authentication_strength="totp_step_up",
        )
    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        await seed_strategy_registry(uow, seeded_at_ms=3000, contracts=tuple(
            c for c in registered_strategy_contracts(include_sor_split=True)
            if c.event_spec_id in ORB_DIRECTIONAL_EVENTS
        ))
        events = []
        for parameters in original.intent.events:
            event_id = parameters.event_spec_id
            if event_id in EXIT_EVENTS[4:]:
                event_id = ORB_DIRECTIONAL_EVENTS[EXIT_EVENTS[4:].index(event_id)]
            current = await uow.exit_profiles.get_current_binding(event_id)
            events.append(EventExitParameters.model_validate({
                **parameters.model_dump(),
                "event_spec_id": event_id,
                "expected_binding_id": current.exit_binding_id,
                "expected_binding_revision": current.projection_version,
                "ma50_enabled": event_id == ORB_DIRECTIONAL_EVENTS[0] or parameters.ma50_enabled,
            }))
        proposal = ExitConfigurationIntent(account_id="manual-account", expected_revision=original.revision, events=tuple(events))
        preview = await preview_exit_configuration(uow, intent=proposal, now_ms=4000)
        for lineage in preview.profiles:
            if lineage.event_spec_id not in ORB_DIRECTIONAL_EVENTS:
                continue
            source_id = EXIT_EVENTS[4:][ORB_DIRECTIONAL_EVENTS.index(lineage.event_spec_id)]
            source = next(p.profile for p in original.profiles if p.event_spec_id == source_id)
            assert lineage.source_profile_id == source.exit_profile_id
            assert lineage.source_profile_hash == source.semantic_hash()
            assert lineage.profile.model_dump(exclude={"exit_profile_id", "exit_profile_version"}) == source.model_dump(exclude={"exit_profile_id", "exit_profile_version"})
        changed_first = tuple(e.model_copy(update={"reward_multiple": D("1.8")})
                              if e.event_spec_id == ORB_DIRECTIONAL_EVENTS[0] else e for e in events)
        with pytest.raises(OwnerControlBlocked, match="split_exit_configuration_must_preserve"):
            await preview_exit_configuration(uow, intent=proposal.model_copy(update={"events": changed_first}), now_ms=4000)

        split = await activate_exit_configuration(
            uow, request=ActivateExitConfigurationRequest(
                expected_version=original.revision, intent=proposal, preview_digest=preview.preview_digest,
                preview_valid_until_ms=preview.valid_until_ms, reason="test split cutover",
                idempotency_key="test-split-configuration", owner_identity="owner", now_ms=4100,
            ), authentication_strength="totp_step_up",
        )
        assert split.revision == original.revision + 1
        assert await uow.exit_profiles.get_configuration(original.configuration_id) == original
        assert (await check_exit_regime(
            uow, venue_id="binance-usdm", account_id="manual-account",
            event_spec_id=ORB_DIRECTIONAL_EVENTS[0], now_ms=4200,
        ))[0] == "ma50_unavailable"
        assert (await check_exit_regime(
            uow, venue_id="binance-usdm", account_id="manual-account",
            event_spec_id=ORB_DIRECTIONAL_EVENTS[1], now_ms=4200,
        ))[0] is None

    from scripts.trading_kernel.certify_readonly import _exit_profile_authority_manifest
    from src.trading_kernel.infrastructure.pg_models import (
        event_exit_profile_binding_events,
        event_exit_profile_bindings,
        exit_configuration_current,
        owner_authorizations,
    )

    async with lifecycle_engine.connect() as connection:
        async def rows(table):
            return (await connection.execute(sa.select(table))).mappings().all()

        current_bindings = (await connection.execute(sa.text("""
            SELECT cur.event_spec_id,cur.exit_binding_id,cur.binding_semantic_hash,
                   cur.projection_version,b.event_spec_id AS binding_event_spec_id,
                   b.exit_profile_id,b.exit_profile_semantic_hash,b.binding_semantic_hash AS fact_binding_hash,
                   p.status AS profile_status,e.status AS event_status
            FROM brc_event_exit_profile_binding_current cur
            JOIN brc_event_exit_profile_bindings b USING(exit_binding_id)
            JOIN brc_exit_policies p ON p.exit_policy_id=b.exit_profile_id
            JOIN brc_event_specs e ON e.event_spec_id=cur.event_spec_id
        """))).mappings().all()
        result = _exit_profile_authority_manifest(
            profile_rows=await rows(exit_policies),
            binding_rows=await rows(event_exit_profile_bindings),
            current_rows=current_bindings,
            event_rows=await rows(event_exit_profile_binding_events),
            configuration_rows=(await connection.execute(
                sa.select(exit_configurations).order_by(exit_configurations.c.revision)
            )).mappings().all(),
            configuration_current_rows=await rows(exit_configuration_current),
            authorization_rows=await rows(owner_authorizations),
            account_id="manual-account",
        )
        assert result["status"] == "pass", result
