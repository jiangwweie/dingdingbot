from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from src.trading_kernel.domain.orb_session_selection import OrbSessionSelectionSpec
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    RuntimeAuthoritySeedRequest,
    seed_runtime_authority,
)
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION

D = 1_800_000_000_000 // 86_400_000 * 86_400_000


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault",
    ["none", "pause_during_audit", "pause_resume_during_audit", "identity_during_audit", "source_failure", "crossed_close"],
)
async def test_global_pause_resume_of_completed_hourly_pair_requires_fresh_audit(
    head_template_engine,
    fault,
):
    from decimal import Decimal

    from src.trading_kernel.application.coordinate_selection_materialization import (
        CoordinateSelectionMaterializationRequest,
        complete_pending_authority_gap_audit,
        coordinate_selection_materialization_once,
    )
    from src.trading_kernel.application.ingest_signal import (
        resolve_selection_entry_authority,
    )
    from src.trading_kernel.application.owner_control import (
        ControlMutationRequest,
        set_global_entry_state,
        set_strategy_entry_state,
        stage_orb_dynamic_selection_mode,
    )
    from src.trading_kernel.domain.instrument_selection import (
        SelectionKline,
        SelectionSourceWindow,
    )
    from src.trading_kernel.domain.market import ClosedCandle
    from src.trading_kernel.domain.orb_session_selection import (
        ORB_EVENT_SPEC_IDS,
        ORB_STATIC_MEMBERS,
        build_orb_session_period,
        compute_orb_selection,
    )
    from src.trading_kernel.domain.owner_control import StrategyEntryState
    from src.trading_kernel.infrastructure.pg_models import runtime_capabilities_current
    from src.trading_kernel.interfaces.authority_gap_audit_source import (
        PublicMarketAuthorityGapAuditSource,
    )
    from tests.trading_kernel.integration.universe_activation_support import (
        make_warming_ready,
    )

    engine = head_template_engine
    hour = 3_600_000
    session = D + 86_400_000
    spec = OrbSessionSelectionSpec()
    async with PostgresKernelUnitOfWork(engine) as uow:
        await seed_runtime_authority(
            uow,
            RuntimeAuthoritySeedRequest(
                account_id="orb-test",
                runtime_commit="orb-local-test",
                schema_revision=CURRENT_SCHEMA_REVISION,
                seeded_at_ms=D,
            ),
        )
        await uow.instrument_selection.install_orb_spec(spec, installed_at_ms=D + 1)
        await uow._connection.execute(
            sa.update(runtime_capabilities_current)
            .where(runtime_capabilities_current.c.capability_key == "exchange_commands")
            .values(enabled=True)
        )
    pair = await install_static_pair(engine)
    for uid in pair:
        await make_warming_ready(
            engine,
            universe_version_id=uid,
            warm_closed_bar_time_ms=session + hour,
            valid_until_ms=session + 24 * hour,
        )
    async with PostgresKernelUnitOfWork(engine) as uow:
        control = await stage_orb_dynamic_selection_mode(
            uow,
            effective_session_start_ms=session,
            request=ControlMutationRequest(
                expected_version=1,
                reason="dynamic",
                idempotency_key="orb:global:first:dynamic",
                owner_identity="owner",
                now_ms=D + hour + 100,
            ),
            authentication_strength="totp_step_up",
        )
        await set_strategy_entry_state(
            uow,
            strategy_group_id=spec.strategy_group_id,
            target_state=StrategyEntryState.ENABLED,
            request=ControlMutationRequest(
                expected_version=1,
                reason="enable",
                idempotency_key="orb:global:first:enable",
                owner_identity="owner",
                now_ms=D + hour + 101,
            ),
            authentication_strength="totp_step_up",
        )
        policy = await uow.entry_admission.get_owner_policy("policy-main")
        await set_global_entry_state(
            uow,
            owner_policy_id="policy-main",
            enabled=True,
            request=ControlMutationRequest(
                expected_version=policy.policy_version,
                reason="initial resume",
                idempotency_key="orb:global:first:resume",
                owner_identity="owner",
                now_ms=D + hour + 102,
            ),
            authentication_strength="totp_step_up",
        )
    windows = tuple(
        SelectionSourceWindow(
            exchange_instrument_id=member,
            input_window_start_ms=session - 23 * hour,
            feature_cutoff_at_ms=session + hour,
            klines=tuple(
                SelectionKline(
                    open_time_ms=session - 23 * hour + i * 900_000,
                    close_time_ms=session - 23 * hour + (i + 1) * 900_000,
                    open=Decimal(100),
                    close=Decimal(100),
                    high=Decimal(101 if i < 92 or member in ORB_STATIC_MEMBERS else 103),
                    low=Decimal(99),
                    quote_volume=Decimal(1_000_000),
                )
                for i in range(96)
            ),
        )
        for member in spec.candidate_ids
    )
    computation = compute_orb_selection(
        spec=spec,
        period=build_orb_session_period(session),
        selection_epoch_id=control.selection_epoch_id,
        source_windows=windows,
        decision_at_ms=session + hour,
        source_observed_at_ms=session + hour + 1,
        created_at_ms=session + hour + 2,
    )
    async with PostgresKernelUnitOfWork(engine) as uow:
        claim = await uow.instrument_selection.claim_orb_selection_job(
            selection_spec_id=spec.selection_spec_id,
            selection_epoch_id=control.selection_epoch_id,
            session_start_ms=session,
            worker_id="orb:global:selector",
            now_ms=session + hour,
            lease_duration_ms=120_000,
        )
        await uow.instrument_selection.complete_orb_selection_snapshot(
            claim=claim, computation=computation, completed_at_ms=session + hour + 2
        )
    request = CoordinateSelectionMaterializationRequest(
        selection_spec_id=spec.selection_spec_id,
        strategy_group_id=spec.strategy_group_id,
        session_start_ms=session,
        worker_id="orb:global:materializer",
    )
    initial = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(engine),
        request=request,
        clock_ms=lambda: session + hour + 3,
    )
    assert initial.disposition == "NO_CHANGE"

    async def change_global(enabled, at_ms, key):
        async with PostgresKernelUnitOfWork(engine) as uow:
            policy = await uow.entry_admission.get_owner_policy("policy-main")
            return await set_global_entry_state(
                uow,
                owner_policy_id="policy-main",
                enabled=enabled,
                request=ControlMutationRequest(
                    expected_version=policy.policy_version,
                    reason="maintenance",
                    idempotency_key=key,
                    owner_identity="owner",
                    now_ms=at_ms,
                ),
                authentication_strength="totp_step_up" if enabled else "session",
            )

    class Market:
        async def fetch_closed_candles(self, request):
            return tuple(
                ClosedCandle(
                    open_time_ms=session + i * hour,
                    close_time_ms=session + (i + 1) * hour,
                    open=Decimal(100),
                    close=Decimal(100),
                    high=Decimal(101),
                    low=Decimal(99),
                    volume=Decimal(100),
                )
                for i in range(request.limit)
            )

    previous_audit = None
    previous_authority = initial.selection_authority_id
    for turn in range(2):
        base = session + (2 + turn) * hour
        await change_global(False, base + 100, f"orb:global:pause:{turn}")
        paused = await coordinate_selection_materialization_once(
            uow_factory=lambda: PostgresKernelUnitOfWork(engine),
            request=request,
            clock_ms=lambda base=base: base + 101,
        )
        assert paused.selection_authority_id is None
        await change_global(True, base + 200, f"orb:global:resume:{turn}")
        recovery = await coordinate_selection_materialization_once(
            uow_factory=lambda: PostgresKernelUnitOfWork(engine),
            request=request,
            clock_ms=lambda base=base: base + 201,
        )
        assert recovery.disposition == "GAP_AUDIT_PENDING"
        assert recovery.authority_gap_audit_id != previous_audit
        repeated = await coordinate_selection_materialization_once(
            uow_factory=lambda: PostgresKernelUnitOfWork(engine),
            request=request,
            clock_ms=lambda base=base: base + 202,
        )
        assert repeated.authority_gap_audit_id == recovery.authority_gap_audit_id
        if turn == 0 and fault != "none":
            clock = [base + 203]

            class ChangingAudit:
                async def evaluate_authority_gap(self, audit_request, base=base, clock=clock):
                    if fault == "source_failure":
                        raise TimeoutError("market unavailable")
                    if fault in {"pause_during_audit", "pause_resume_during_audit"}:
                        await change_global(False, base + 203, "orb:global:audit:pause")
                    if fault == "pause_resume_during_audit":
                        await change_global(True, base + 204, "orb:global:audit:resume")
                    if fault == "identity_during_audit":
                        async with engine.begin() as connection:
                            await connection.execute(
                                sa.update(runtime_capabilities_current)
                                .where(runtime_capabilities_current.c.capability_key == "exchange_commands")
                                .values(certified_commit="different-runtime")
                            )
                    if fault == "crossed_close":
                        clock[0] = base + hour + 1
                    return await PublicMarketAuthorityGapAuditSource(Market()).evaluate_authority_gap(audit_request)

            rejected = await complete_pending_authority_gap_audit(
                uow_factory=lambda: PostgresKernelUnitOfWork(engine),
                authority_gap_audit_id=recovery.authority_gap_audit_id,
                audit_source=ChangingAudit(),
                clock_ms=lambda clock=clock: clock[0],
            )
            assert rejected.disposition in {"BLOCKED", "GAP_AUDIT_WINDOW_EXPIRED"}
            async with PostgresKernelUnitOfWork(engine) as uow:
                current = await uow.instrument_selection.get_current_authority_projection(spec.selection_spec_id)
                assert current.authority.selection_authority_id == previous_authority
                audit = await uow.instrument_selection.get_authority_gap_audit(recovery.authority_gap_audit_id)
                assert audit.state == ("FAILED" if fault == "source_failure" else "PENDING")
                assert await uow._connection.scalar(sa.text("SELECT count(*) FROM brc_exchange_commands")) == 0
            if fault == "pause_resume_during_audit":
                newer = await coordinate_selection_materialization_once(
                    uow_factory=lambda: PostgresKernelUnitOfWork(engine),
                    request=request,
                    clock_ms=lambda base=base: base + 205,
                )
                assert newer.disposition == "GAP_AUDIT_PENDING"
                assert newer.authority_gap_audit_id != recovery.authority_gap_audit_id
                stale = await complete_pending_authority_gap_audit(
                    uow_factory=lambda: PostgresKernelUnitOfWork(engine),
                    authority_gap_audit_id=recovery.authority_gap_audit_id,
                    audit_source=PublicMarketAuthorityGapAuditSource(Market()),
                    clock_ms=lambda base=base: base + 206,
                )
                assert stale.reason_code == "ORB_RECOVERY_BASIS_CHANGED"
            return
        recovered = await complete_pending_authority_gap_audit(
            uow_factory=lambda: PostgresKernelUnitOfWork(engine),
            authority_gap_audit_id=recovery.authority_gap_audit_id,
            audit_source=PublicMarketAuthorityGapAuditSource(Market()),
            clock_ms=lambda base=base: base + 203,
        )
        assert recovered.disposition == "PRE_FENCE_CONTINUITY"
        assert recovered.selection_authority_id != previous_authority
        duplicate = await complete_pending_authority_gap_audit(
            uow_factory=lambda: PostgresKernelUnitOfWork(engine),
            authority_gap_audit_id=recovery.authority_gap_audit_id,
            audit_source=PublicMarketAuthorityGapAuditSource(Market()),
            clock_ms=lambda base=base: base + 204,
        )
        assert duplicate.selection_authority_id == recovered.selection_authority_id
        assert duplicate.reason_code == "AUTHORITY_GAP_AUDIT_ALREADY_COMMITTED"
        async with PostgresKernelUnitOfWork(engine) as uow:
            current = await uow.instrument_selection.get_current_authority_projection(
                spec.selection_spec_id
            )
            first = current.authority.first_eligible_close_time_ms
            assert first == base + hour
            for event in ORB_EVENT_SPEC_IDS:
                scope_id = await uow._connection.scalar(
                    sa.text(
                        "SELECT runtime_scope_id FROM brc_runtime_scopes_current "
                        "WHERE event_spec_id=:event AND lifecycle_state='active' LIMIT 1"
                    ),
                    {"event": event},
                )
                scope = await uow.signals.get_runtime_scope(scope_id)
                early = await resolve_selection_entry_authority(
                    uow,
                    runtime_scope=scope,
                    birth_selection_authority_id=current.authority.selection_authority_id,
                    observed_close_time_ms=first - hour,
                    now_ms=first - 1,
                    allow_current_as_birth=False,
                )
                assert not early.allowed
                fresh = await resolve_selection_entry_authority(
                    uow,
                    runtime_scope=scope,
                    birth_selection_authority_id=current.authority.selection_authority_id,
                    observed_close_time_ms=first,
                    now_ms=first + 1,
                    allow_current_as_birth=False,
                )
                assert fresh.allowed
                old = await resolve_selection_entry_authority(
                    uow,
                    runtime_scope=scope,
                    birth_selection_authority_id=previous_authority,
                    observed_close_time_ms=first,
                    now_ms=first + 1,
                    allow_current_as_birth=False,
                )
                assert not old.allowed
            assert await uow._connection.scalar(
                sa.text("SELECT count(*) FROM brc_exchange_commands")
            ) == 0
        previous_audit = recovery.authority_gap_audit_id
        previous_authority = recovered.selection_authority_id

    await change_global(False, session + 5 * hour, "orb:global:last:pause")
    stale_completed = await complete_pending_authority_gap_audit(
        uow_factory=lambda: PostgresKernelUnitOfWork(engine),
        authority_gap_audit_id=previous_audit,
        audit_source=PublicMarketAuthorityGapAuditSource(Market()),
        clock_ms=lambda: session + 5 * hour + 1,
    )
    assert stale_completed.reason_code == "ORB_RECOVERY_BASIS_CHANGED"


@pytest.mark.asyncio
async def test_hourly_spec_installs_as_independent_paused_pair_with_frozen_candidate_panel(
    head_template_engine: AsyncEngine,
) -> None:
    async with head_template_engine.connect() as c:
        assert (
            await c.scalar(
                sa.text(
                    "SELECT to_regclass('public.brc_orb_session_selection_specs_v1')"
                )
            )
            is not None
        )
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        await seed_runtime_authority(
            uow,
            RuntimeAuthoritySeedRequest(
                account_id="orb-test",
                runtime_commit="orb-local-test",
                schema_revision=CURRENT_SCHEMA_REVISION,
                seeded_at_ms=D,
            ),
        )
        await uow.instrument_selection.install_orb_spec(
            OrbSessionSelectionSpec(), installed_at_ms=D + 1
        )
    async with head_template_engine.connect() as c:
        assert (
            await c.scalar(
                sa.text(
                    "SELECT entry_state FROM brc_strategy_entry_controls_current WHERE strategy_group_id='SOR-1H-001'"
                )
            )
            == "paused"
        )
        assert (
            await c.scalar(
                sa.text(
                    "SELECT count(*) FROM brc_instrument_selection_spec_members WHERE selection_spec_id='SOR_1H_OR_ATR_DYNAMIC_V1'"
                )
            )
            == 24
        )
        assert (
            await c.scalar(
                sa.text(
                    "SELECT count(*) FROM brc_instrument_selection_spec_events WHERE selection_spec_id='SOR_1H_OR_ATR_DYNAMIC_V1'"
                )
            )
            == 2
        )
        assert (
            await c.scalar(
                sa.text(
                    "SELECT selection_kind FROM brc_instrument_selection_specs WHERE selection_spec_id='SOR_1H_OR_ATR_DYNAMIC_V1'"
                )
            )
            == "orb_session_dynamic_v1"
        )
        assert (
            await c.scalar(sa.text("SELECT count(*) FROM brc_exchange_commands")) == 0
        )
        assert (
            await c.scalar(
                sa.text(
                    "SELECT count(*) FROM brc_selection_session_authorities WHERE selection_spec_id='SOR_1H_OR_ATR_DYNAMIC_V1'"
                )
            )
            == 0
        )
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        assert (
            await uow.instrument_selection.get_orb_spec("SOR_1H_OR_ATR_DYNAMIC_V1")
            == OrbSessionSelectionSpec()
        )


@pytest.mark.asyncio
async def test_hourly_snapshot_member_results_are_immutable_independent_and_epoch_bound(
    head_template_engine: AsyncEngine,
) -> None:
    from decimal import Decimal

    from src.trading_kernel.domain.instrument_selection import (
        SelectionKline,
        SelectionSourceWindow,
    )
    from src.trading_kernel.domain.orb_session_selection import (
        build_orb_session_period,
        compute_orb_selection,
    )

    spec = OrbSessionSelectionSpec()
    h = 3_600_000
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        await seed_runtime_authority(
            uow,
            RuntimeAuthoritySeedRequest(
                account_id="orb-test",
                runtime_commit="orb-local-test",
                schema_revision=CURRENT_SCHEMA_REVISION,
                seeded_at_ms=D,
            ),
        )
        await uow.instrument_selection.install_orb_spec(spec, installed_at_ms=D + 1)
    windows = tuple(
        SelectionSourceWindow(
            exchange_instrument_id=m,
            input_window_start_ms=D - 23 * h,
            feature_cutoff_at_ms=D + h,
            klines=tuple(
                SelectionKline(
                    open_time_ms=D - 23 * h + i * 900000,
                    close_time_ms=D - 23 * h + (i + 1) * 900000,
                    open=Decimal(100),
                    close=Decimal(100),
                    high=Decimal(101),
                    low=Decimal(99),
                    quote_volume=Decimal(1000000),
                )
                for i in range(96)
            ),
        )
        for m in spec.candidate_ids
    )
    result = compute_orb_selection(
        spec=spec,
        period=build_orb_session_period(D),
        selection_epoch_id="epoch:orb:pg",
        source_windows=windows,
        decision_at_ms=D + h,
        source_observed_at_ms=D + h + 1,
        created_at_ms=D + h + 2,
    )
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        await uow.instrument_selection.save_orb_snapshot(result)
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        assert (
            await uow.instrument_selection.get_orb_snapshot(
                result.snapshot.selection_snapshot_id
            )
            == result
        )
    async with head_template_engine.connect() as c:
        assert (
            await c.scalar(
                sa.text(
                    "SELECT count(*) FROM brc_instrument_selection_member_decisions WHERE selection_family='orb_session_dynamic_v1'"
                )
            )
            == 24
        )
    with pytest.raises(Exception, match="immutable"):
        async with head_template_engine.begin() as c:
            await c.execute(
                sa.text(
                    "UPDATE brc_instrument_selection_snapshots SET selected_count=6 WHERE selection_snapshot_id=:sid"
                ),
                {"sid": result.snapshot.selection_snapshot_id},
            )


async def install_static_pair(engine: AsyncEngine):
    from src.trading_kernel.application.advance_strategy_universe import (
        UniverseActivationRequest,
        UniverseActivationStatus,
        advance_strategy_universe,
    )
    from src.trading_kernel.application.install_strategy_universe import (
        UniverseInstallRequest,
        install_strategy_universe,
    )
    from src.trading_kernel.domain.orb_session_selection import (
        ORB_EVENT_SPEC_IDS,
        ORB_STATIC_MEMBERS,
    )
    from tests.trading_kernel.integration.universe_activation_support import (
        make_warming_ready,
    )

    result = []
    for event in ORB_EVENT_SPEC_IDS:
        async with PostgresKernelUnitOfWork(engine) as uow:
            r = await install_strategy_universe(
                uow,
                UniverseInstallRequest(
                    event_spec_id=event,
                    runtime_profile_id="tiny-live-v1",
                    owner_policy_id="policy-main",
                    exchange_instrument_ids=ORB_STATIC_MEMBERS,
                    installed_at_ms=D + 10,
                ),
            )
        assert r.universe is not None
        await make_warming_ready(
            engine,
            universe_version_id=r.universe.universe_version_id,
            warm_closed_bar_time_ms=D + 3600000,
            valid_until_ms=D + 7200000,
        )
        async with PostgresKernelUnitOfWork(engine) as uow:
            a = await advance_strategy_universe(
                uow,
                UniverseActivationRequest(
                    universe_version_id=r.universe.universe_version_id,
                    attempted_at_ms=D + 3600001,
                ),
            )
        assert a.status in {
            UniverseActivationStatus.ACTIVATED,
            UniverseActivationStatus.ALREADY_ACTIVE,
        }
        result.append(r.universe.universe_version_id)
    return tuple(result)


@pytest.mark.asyncio
async def test_static_pair_and_owner_intent_drive_daily_job_on_later_session(
    head_template_engine: AsyncEngine,
):
    from src.trading_kernel.application.owner_control import (
        ControlMutationRequest,
        stage_orb_dynamic_selection_mode,
    )
    from src.trading_kernel.domain.generic_selection_jobs import (
        GenericSelectionJobClaim,
    )

    spec = OrbSessionSelectionSpec()
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        await seed_runtime_authority(
            uow,
            RuntimeAuthoritySeedRequest(
                account_id="orb-test",
                runtime_commit="orb-local-test",
                schema_revision=CURRENT_SCHEMA_REVISION,
                seeded_at_ms=D,
            ),
        )
        await uow.instrument_selection.install_orb_spec(spec, installed_at_ms=D + 1)
    await install_static_pair(head_template_engine)
    from tests.trading_kernel.support.owner_roles import (
        apply_owner_control_grants as _apply_owner_control_grants,
    )
    await _apply_owner_control_grants(head_template_engine)
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        await uow._connection.execute(sa.text('SET LOCAL ROLE brc_owner_control'))
        c = await stage_orb_dynamic_selection_mode(
            uow,
            effective_session_start_ms=D + 86400000,
            request=ControlMutationRequest(
                expected_version=1,
                reason="hourly dynamic",
                idempotency_key="orb:first:dynamic",
                owner_identity="owner",
                now_ms=D + 3600100,
            ),
            authentication_strength="totp_step_up",
        )
    with pytest.raises(Exception,match='permission denied'):
        async with head_template_engine.begin() as connection:
            await connection.execute(sa.text('SET LOCAL ROLE brc_owner_control'))
            await connection.execute(sa.text("UPDATE brc_strategy_universe_current SET lifecycle_state='retired' WHERE event_spec_id='event_spec:SOR-1H-001:SOR-1H-LONG:v1'"))
    assert (
        c.pending_authorization_id and c.selection_epoch_id and c.rollback_baseline_id
    )
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        claim = await uow.instrument_selection.claim_orb_selection_job(
            selection_spec_id=spec.selection_spec_id,
            selection_epoch_id=c.selection_epoch_id,
            session_start_ms=D + 2 * 86400000,
            worker_id="orb:test",
            now_ms=D + 2 * 86400000 + 3600000,
            lease_duration_ms=120000,
        )
    assert isinstance(claim, GenericSelectionJobClaim)
    assert (
        claim.selection_epoch_id == c.selection_epoch_id
        and claim.period_anchor_ms == D + 2 * 86400000
    )
    from src.trading_kernel.domain.instrument_selection import SelectionAttemptOutcome

    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        await uow.instrument_selection.complete_selection_failure(
            claim=claim,
            outcome=SelectionAttemptOutcome.SOURCE_FAILED,
            reason_code="SOURCE_TIMEOUT",
            source_member_count=0,
            source_digest=None,
            completed_at_ms=D + 2 * 86400000 + 3600001,
        )
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        preserved = await uow.instrument_selection.get_selection_control(
            spec.strategy_group_id
        )
        assert preserved == c
        next_claim = await uow.instrument_selection.claim_orb_selection_job(
            selection_spec_id=spec.selection_spec_id,
            selection_epoch_id=c.selection_epoch_id,
            session_start_ms=D + 3 * 86400000,
            worker_id="orb:test",
            now_ms=D + 3 * 86400000 + 3600000,
            lease_duration_ms=120000,
        )
        assert isinstance(next_claim, GenericSelectionJobClaim)
        assert next_claim.selection_epoch_id == c.selection_epoch_id
        replacement=await uow.instrument_selection.claim_orb_selection_job(selection_spec_id=spec.selection_spec_id,
            selection_epoch_id=c.selection_epoch_id,session_start_ms=D+4*86400000,worker_id='orb:next',now_ms=D+4*86400000+3600000,lease_duration_ms=120000)
        assert isinstance(replacement,GenericSelectionJobClaim)
        old=await uow.instrument_selection.get_selection_job(selection_spec_id=spec.selection_spec_id,
            selection_epoch_id=c.selection_epoch_id,period_anchor_ms=next_claim.period_anchor_ms)
        assert old.state=='SUPERSEDED'

    async with head_template_engine.connect() as connection:
        assert (
            await connection.scalar(
                sa.text("SELECT count(*) FROM brc_exchange_commands")
            )
            == 0
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("changed,failed,late", [(False,False,False),(True,False,False),(True,True,False),(None,False,False),(False,False,True),(True,False,"static_failure"),(True,False,"static_audit_failure"),(None,False,"static_after_empty_failure"),(True,False,"static_last_hour"),(True,False,"static_unfenced_dynamic")])
async def test_hourly_first_no_change_commits_exact_pair_epoch_and_owner_proof(head_template_engine, changed, failed, late, monkeypatch):
    from decimal import Decimal

    from src.trading_kernel.application.coordinate_selection_materialization import (
        CoordinateSelectionMaterializationRequest,
        coordinate_selection_materialization_once,
    )
    from src.trading_kernel.application.owner_control import (
        ControlMutationRequest,
        set_strategy_entry_state,
        stage_orb_dynamic_selection_mode,
    )
    from src.trading_kernel.domain.instrument_selection import (
        SelectionKline,
        SelectionSourceWindow,
    )
    from src.trading_kernel.domain.orb_session_selection import (
        ORB_STATIC_MEMBERS,
        build_orb_session_period,
        compute_orb_selection,
    )
    from src.trading_kernel.domain.owner_control import StrategyEntryState
    h=3600000;day=86400000;session=D+day;spec=OrbSessionSelectionSpec()
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        await seed_runtime_authority(uow,RuntimeAuthoritySeedRequest(account_id='orb-test',runtime_commit='orb-local-test',schema_revision=CURRENT_SCHEMA_REVISION,seeded_at_ms=D))
        await uow.instrument_selection.install_orb_spec(spec,installed_at_ms=D+1)
    await install_static_pair(head_template_engine)
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        control=await stage_orb_dynamic_selection_mode(uow,effective_session_start_ms=session,
            request=ControlMutationRequest(expected_version=1,reason='dynamic',idempotency_key='orb:first:dynamic',owner_identity='owner',now_ms=D+h+100),authentication_strength='totp_step_up')
        await set_strategy_entry_state(uow,strategy_group_id=spec.strategy_group_id,target_state=StrategyEntryState.ENABLED,
            request=ControlMutationRequest(expected_version=1,reason='test resume',idempotency_key='orb:first:resume',owner_identity='owner',now_ms=D+h+101),authentication_strength='totp_step_up')
    windows=tuple(SelectionSourceWindow(exchange_instrument_id=m,input_window_start_ms=session-23*h,feature_cutoff_at_ms=session+h,
        klines=tuple(SelectionKline(open_time_ms=session-23*h+i*900000,close_time_ms=session-23*h+(i+1)*900000,
            open=Decimal(100),close=Decimal(100),high=Decimal(101 if i<92 or m in (spec.candidate_ids[:7] if changed else ORB_STATIC_MEMBERS) else 103),
            low=Decimal(99),quote_volume=Decimal(1 if changed is None else 1000000)) for i in range(96))) for m in spec.candidate_ids)
    computation=compute_orb_selection(spec=spec,period=build_orb_session_period(session),selection_epoch_id=control.selection_epoch_id,
        source_windows=windows,decision_at_ms=session+h,source_observed_at_ms=session+h+1,created_at_ms=session+h+2)
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        claim=await uow.instrument_selection.claim_orb_selection_job(selection_spec_id=spec.selection_spec_id,
            selection_epoch_id=control.selection_epoch_id,session_start_ms=session,worker_id='orb:selector',now_ms=session+h,lease_duration_ms=120000)
        await uow.instrument_selection.complete_orb_selection_snapshot(claim=claim,computation=computation,completed_at_ms=session+h+2)
    if changed is False:
        stale=await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(head_template_engine),
            request=CoordinateSelectionMaterializationRequest(selection_spec_id=spec.selection_spec_id,strategy_group_id=spec.strategy_group_id,session_start_ms=session,worker_id='orb:stale'),clock_ms=lambda:session+h+3)
        assert stale.disposition=='BLOCKED' and stale.reason_code.startswith('ORB_CURRENT_PAIR_')
        from tests.trading_kernel.integration.universe_activation_support import (
            make_warming_ready,
        )
        async with head_template_engine.connect() as connection:
            current_ids=tuple((await connection.execute(sa.text("SELECT p.universe_version_id FROM brc_strategy_universe_current p JOIN brc_strategy_universe_versions u USING(universe_version_id) WHERE u.strategy_group_id='SOR-1H-001'"))).scalars())
        for uid in current_ids:
            await make_warming_ready(head_template_engine,universe_version_id=uid,warm_closed_bar_time_ms=session+(2*h if late is True else h),valid_until_ms=session+(3*h if late is True else 2*h))
    result=await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(head_template_engine),
        request=CoordinateSelectionMaterializationRequest(selection_spec_id=spec.selection_spec_id,strategy_group_id=spec.strategy_group_id,
            session_start_ms=session,worker_id='orb:materializer'),clock_ms=lambda:session+(2*h+1 if late is True else h+3))
    if changed is None:
        assert result.disposition=='VALID_EMPTY_INTENT'
        from src.trading_kernel.application.drain_strategy_entry_vacuum import (
            DrainStrategyEntryVacuumRequest,
            drain_strategy_entry_vacuum_once,
        )
        for tick in range(4,7):
            async with PostgresKernelUnitOfWork(head_template_engine) as uow:
                empty=await drain_strategy_entry_vacuum_once(uow,DrainStrategyEntryVacuumRequest(strategy_group_id=spec.strategy_group_id,selection_spec_id=spec.selection_spec_id,now_ms=session+h+tick))
            if empty.status=='VALID_EMPTY_COMMITTED':break
        assert empty.status=='VALID_EMPTY_COMMITTED'
        async with PostgresKernelUnitOfWork(head_template_engine) as uow:
            final=await uow.instrument_selection.get_current_authority_projection(spec.selection_spec_id)
            assert final.authority.authority_outcome=='VALID_EMPTY' and final.authority.authorized_pair is None
            assert final.authority.activation_authorization_id==control.pending_authorization_id
        await assert_empty_waits_for_nonempty_snapshot(head_template_engine,spec,session,static_retry=late=="static_after_empty_failure")
        return
    if changed:
        assert result.disposition=='GENERATION_PENDING'
        async with PostgresKernelUnitOfWork(head_template_engine) as uow:
            generation=await uow.instrument_selection.get_materialization_generation(result.materialization_generation_id)
            assert generation.selection_epoch_id==control.selection_epoch_id
            assert generation.selection_control_version==control.control_version
            assert generation.strategy_group_id==spec.strategy_group_id
        with pytest.raises(Exception,match='Generation source identity is immutable'):
            async with head_template_engine.begin() as connection:
                await connection.execute(sa.text('UPDATE brc_strategy_universe_materialization_generations SET selection_control_version=999 WHERE materialization_generation_id=:gid'),{'gid':generation.materialization_generation_id})
        request=CoordinateSelectionMaterializationRequest(selection_spec_id=spec.selection_spec_id,strategy_group_id=spec.strategy_group_id,session_start_ms=session,worker_id='orb:materializer')
        outcomes=[]
        for tick in range(4,9):
            progress=await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(head_template_engine),request=request,clock_ms=lambda tick=tick:session+h+tick)
            outcomes.append(progress.disposition.value)
            if progress.disposition=='WAITING_VACUUM':
                from src.trading_kernel.application.drain_strategy_entry_vacuum import (
                    DrainStrategyEntryVacuumRequest,
                    drain_strategy_entry_vacuum_once,
                )
                async with PostgresKernelUnitOfWork(head_template_engine) as uow:
                    await drain_strategy_entry_vacuum_once(uow,DrainStrategyEntryVacuumRequest(strategy_group_id=spec.strategy_group_id,selection_spec_id=spec.selection_spec_id,now_ms=session+h+tick))
        assert outcomes[:2]==['GENERATION_DESIRED','WAITING_VACUUM']
        assert outcomes[-1]=='LONG_WARMING'
        from tests.trading_kernel.integration.universe_activation_support import (
            make_warming_ready,
        )
        for tick in range(9,15):
            if failed:
                tick=1800100
            async with head_template_engine.connect() as connection:
                warming=tuple((await connection.execute(sa.text("SELECT universe_version_id FROM brc_strategy_universe_versions WHERE materialization_generation_id=:gid AND lifecycle_state='warming'"),{'gid':generation.materialization_generation_id})).scalars())
            for uid in warming:
                await make_warming_ready(head_template_engine,universe_version_id=uid,warm_closed_bar_time_ms=session+h,valid_until_ms=session+2*h)
            progress=await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(head_template_engine),request=request,clock_ms=lambda tick=tick:session+h+tick)
            if progress.disposition=='GAP_AUDIT_PENDING':break
        assert progress.disposition=='GAP_AUDIT_PENDING'
        if not failed:
            await assert_staged_facts_refresh(head_template_engine,spec,session,monkeypatch)
        from src.trading_kernel.application.coordinate_selection_materialization import (
            complete_pending_authority_gap_audit,
        )
        from src.trading_kernel.domain.market import ClosedCandle
        from src.trading_kernel.interfaces.authority_gap_audit_source import (
            PublicMarketAuthorityGapAuditSource,
        )
        class Market:
            async def fetch_closed_candles(self, request):
                assert request.timeframe=='1h' and request.limit==1
                return (ClosedCandle(open_time_ms=session,close_time_ms=session+h,open=Decimal(100),high=Decimal(101),low=Decimal(99),close=Decimal(100),volume=Decimal(1000)),)
        active=await complete_pending_authority_gap_audit(uow_factory=lambda:PostgresKernelUnitOfWork(head_template_engine),authority_gap_audit_id=progress.authority_gap_audit_id,
            audit_source=PublicMarketAuthorityGapAuditSource(Market()),clock_ms=lambda:session+h+(1800101 if failed else 15))
        assert active.disposition==('FALLBACK_PREVIOUS' if failed else 'ACTIVE_NEW')
        if failed:
            async with PostgresKernelUnitOfWork(head_template_engine) as uow:
                kept=await uow.instrument_selection.get_selection_control(spec.strategy_group_id)
                assert kept==control
                baseline=await uow.instrument_selection.get_orb_static_baseline(control.rollback_baseline_id)
                assert baseline.rollback_baseline_id==control.rollback_baseline_id
                restored=await uow.instrument_selection.get_current_authority_projection(spec.selection_spec_id)
                assert restored.authority.selection_mode=='static_baseline'
                assert restored.authority.activation_authorization_id is None
            return
        await assert_pair_entry_authority(head_template_engine,spec,session,active.selection_authority_id)
        await assert_explicit_static_intent(head_template_engine,spec,session,fail=late in {"static_failure", "static_audit_failure"}, audit_failure=late=="static_audit_failure", last_hour_wait=late=="static_last_hour",unfenced_dynamic=late=="static_unfenced_dynamic")
        return
    if late is True:
        assert result.disposition=='GAP_AUDIT_PENDING'
        from src.trading_kernel.application.coordinate_selection_materialization import (
            complete_pending_authority_gap_audit,
        )
        from src.trading_kernel.domain.market import ClosedCandle
        from src.trading_kernel.interfaces.authority_gap_audit_source import (
            PublicMarketAuthorityGapAuditSource,
        )
        class LateMarket:
            async def fetch_closed_candles(self,request):
                assert request.timeframe=='1h' and request.limit==2
                return tuple(ClosedCandle(open_time_ms=session+i*h,close_time_ms=session+(i+1)*h,
                    open=Decimal(100),high=Decimal(103 if i else 101),low=Decimal(99),close=Decimal(102 if i else 100),volume=Decimal(100)) for i in range(2))
        result=await complete_pending_authority_gap_audit(uow_factory=lambda:PostgresKernelUnitOfWork(head_template_engine),authority_gap_audit_id=result.authority_gap_audit_id,
            audit_source=PublicMarketAuthorityGapAuditSource(LateMarket()),clock_ms=lambda:session+2*h+2)
    assert result.disposition=='NO_CHANGE'
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        authority=await uow.instrument_selection.get_current_authority_projection(spec.selection_spec_id)
        current_control=await uow.instrument_selection.get_selection_control(spec.strategy_group_id)
        assert authority.authority.selection_epoch_id==control.selection_epoch_id
        assert authority.authority.activation_authorization_id==control.pending_authorization_id
        assert authority.authority.selection_control_version==current_control.control_version==3
        assert authority.authority.first_eligible_close_time_ms==session+(3*h if late else 2*h)
        assert current_control.pending_authorization_id is None

    await assert_pair_entry_authority(head_template_engine,spec,session,result.selection_authority_id)
    await assert_next_day_continuity(head_template_engine,spec,session)


async def assert_pair_entry_authority(engine,spec,session,authority_id):
    from src.trading_kernel.application.ingest_signal import (
        resolve_selection_entry_authority,
    )
    async with engine.connect() as connection:
        scopes=tuple((await connection.execute(sa.text("SELECT runtime_scope_id FROM brc_runtime_scopes_current WHERE strategy_group_id='SOR-1H-001' AND lifecycle_state='active' ORDER BY event_spec_id LIMIT 14"))).scalars())
    assert len(scopes)==14
    async with PostgresKernelUnitOfWork(engine) as uow:
        current=await uow.instrument_selection.get_current_authority_projection(spec.selection_spec_id)
        close=current.authority.first_eligible_close_time_ms
        sides=set()
        for scope_id in scopes:
            scope=await uow.signals.get_runtime_scope(scope_id)
            sides.add(scope.position_side)
            decision=await resolve_selection_entry_authority(uow,runtime_scope=scope,birth_selection_authority_id=authority_id,
                observed_close_time_ms=close,now_ms=close+1,allow_current_as_birth=False)
            assert decision.reason_code=="selection_owner_or_policy_blocked"
            assert decision.current_selection_authority_id==authority_id
        assert sides=={'long','short'}


async def assert_next_day_continuity(engine,spec,session):
    from decimal import Decimal

    from src.trading_kernel.application.coordinate_selection_materialization import (
        CoordinateSelectionMaterializationRequest,
        complete_pending_authority_gap_audit,
        coordinate_selection_materialization_once,
    )
    from src.trading_kernel.domain.market import ClosedCandle
    from src.trading_kernel.interfaces.authority_gap_audit_source import (
        PublicMarketAuthorityGapAuditSource,
    )
    day=session+86400000;h=3600000
    planned=await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(engine),
        request=CoordinateSelectionMaterializationRequest(selection_spec_id=spec.selection_spec_id,strategy_group_id=spec.strategy_group_id,session_start_ms=day,worker_id='orb:continuity'),clock_ms=lambda:day+h+1)
    assert planned.disposition=='GAP_AUDIT_PENDING'
    class Market:
        async def fetch_closed_candles(self,request):
            assert request.limit==1 and request.timeframe=='1h'
            return (ClosedCandle(open_time_ms=day,close_time_ms=day+h,open=Decimal(100),high=Decimal(101),low=Decimal(99),close=Decimal(100),volume=Decimal(100)),)
    continued=await complete_pending_authority_gap_audit(uow_factory=lambda:PostgresKernelUnitOfWork(engine),authority_gap_audit_id=planned.authority_gap_audit_id,audit_source=PublicMarketAuthorityGapAuditSource(Market()),clock_ms=lambda:day+h+2)
    assert continued.disposition=='PRE_FENCE_CONTINUITY'
    await assert_owner_pause(engine,spec,day)


async def assert_owner_pause(engine,spec,session):
    from src.trading_kernel.application.coordinate_selection_materialization import (
        CoordinateSelectionMaterializationRequest,
        coordinate_selection_materialization_once,
    )
    from src.trading_kernel.application.owner_control import (
        ControlMutationRequest,
        set_strategy_entry_state,
    )
    from src.trading_kernel.domain.owner_control import StrategyEntryState
    async with PostgresKernelUnitOfWork(engine) as uow:
        await set_strategy_entry_state(uow,strategy_group_id=spec.strategy_group_id,target_state=StrategyEntryState.PAUSED,
            request=ControlMutationRequest(expected_version=2,reason='test pause',idempotency_key='orb:pause',owner_identity='owner',now_ms=session+3600100),authentication_strength='session')
    paused=await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(engine),request=CoordinateSelectionMaterializationRequest(selection_spec_id=spec.selection_spec_id,strategy_group_id=spec.strategy_group_id,session_start_ms=session,worker_id='orb:pause'),clock_ms=lambda:session+3600101)
    assert paused.disposition=='OWNER_PAUSED'
    async with PostgresKernelUnitOfWork(engine) as uow:
        current=await uow.instrument_selection.get_current_authority_projection(spec.selection_spec_id)
        assert current.authority.blocks_new_entry
        vacuum=await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=spec.strategy_group_id,selection_spec_id=spec.selection_spec_id)
        assert vacuum.blocks_new_entry
    from src.trading_kernel.application.drain_strategy_entry_vacuum import (
        DrainStrategyEntryVacuumRequest,
        drain_strategy_entry_vacuum_once,
    )
    for tick in (102,103):
        async with PostgresKernelUnitOfWork(engine) as uow:
            await drain_strategy_entry_vacuum_once(uow,DrainStrategyEntryVacuumRequest(strategy_group_id=spec.strategy_group_id,selection_spec_id=spec.selection_spec_id,now_ms=session+3600000+tick))
    async with PostgresKernelUnitOfWork(engine) as uow:
        await set_strategy_entry_state(uow,strategy_group_id=spec.strategy_group_id,target_state=StrategyEntryState.ENABLED,
            request=ControlMutationRequest(expected_version=3,reason='test resume',idempotency_key='orb:resumed',owner_identity='owner',now_ms=session+3600200),authentication_strength='totp_step_up')
    resumed=await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(engine),request=CoordinateSelectionMaterializationRequest(selection_spec_id=spec.selection_spec_id,strategy_group_id=spec.strategy_group_id,session_start_ms=session,worker_id='orb:resume'),clock_ms=lambda:session+3600201)
    assert resumed.disposition=='GAP_AUDIT_PENDING'
    with pytest.raises(Exception,match='ORB.*audit'):
        async with engine.begin() as connection:
            await connection.execute(sa.text("UPDATE brc_selection_authority_gap_audits_current SET state='COMPLETE',audited_through_close_time_ms=:through,first_eligible_close_time_ms=:first,audit_scope_digest=:digest,audit_result_digest=:digest,projection_version=projection_version+1 WHERE authority_gap_audit_id=:aid"),{'through':session+3600000,'first':session+7200000,'digest':'sha256:'+'a'*64,'aid':resumed.authority_gap_audit_id})
    from decimal import Decimal

    from src.trading_kernel.application.coordinate_selection_materialization import (
        complete_pending_authority_gap_audit,
    )
    from src.trading_kernel.domain.market import ClosedCandle
    from src.trading_kernel.interfaces.authority_gap_audit_source import (
        PublicMarketAuthorityGapAuditSource,
    )
    with pytest.raises(Exception,match='ORB.*audit'):
        async with engine.begin() as connection:
            await connection.execute(sa.text("UPDATE brc_strategy_entry_vacuums_current SET state='RESOLVED_CONTINUITY',resolved_at_ms=:at,projection_version=projection_version+1 WHERE strategy_group_id='SOR-1H-001' AND state='OWNER_PAUSED'"),{'at':session+3600202})
    class Market:
        async def fetch_closed_candles(self,request):
            return (ClosedCandle(open_time_ms=session,close_time_ms=session+3600000,open=Decimal(100),high=Decimal(101),low=Decimal(99),close=Decimal(100),volume=Decimal(100)),)
    recovered=await complete_pending_authority_gap_audit(uow_factory=lambda:PostgresKernelUnitOfWork(engine),authority_gap_audit_id=resumed.authority_gap_audit_id,audit_source=PublicMarketAuthorityGapAuditSource(Market()),clock_ms=lambda:session+3600202)
    assert recovered.disposition=='PRE_FENCE_CONTINUITY'
    async with PostgresKernelUnitOfWork(engine) as uow:
        vacuum=await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=spec.strategy_group_id,selection_spec_id=spec.selection_spec_id)
        assert vacuum is None or not vacuum.blocks_new_entry


async def assert_empty_waits_for_nonempty_snapshot(engine,spec,session,static_retry=False):
    from src.trading_kernel.application.coordinate_selection_materialization import (
        CoordinateSelectionMaterializationRequest,
        coordinate_selection_materialization_once,
    )
    result=await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(engine),
        request=CoordinateSelectionMaterializationRequest(selection_spec_id=spec.selection_spec_id,strategy_group_id=spec.strategy_group_id,session_start_ms=session+86400000,worker_id='orb:empty'),clock_ms=lambda:session+90000001)
    assert result.disposition=='WAITING_SELECTION'
    from decimal import Decimal

    from src.trading_kernel.domain.instrument_selection import (
        SelectionKline,
        SelectionSourceWindow,
    )
    from src.trading_kernel.domain.orb_session_selection import (
        ORB_STATIC_MEMBERS,
        build_orb_session_period,
        compute_orb_selection,
    )
    day=session+86400000;h=3600000
    async with PostgresKernelUnitOfWork(engine) as uow:
        control=await uow.instrument_selection.get_selection_control(spec.strategy_group_id)
        claim=await uow.instrument_selection.claim_orb_selection_job(selection_spec_id=spec.selection_spec_id,selection_epoch_id=control.selection_epoch_id,session_start_ms=day,worker_id='orb:nonempty',now_ms=day+h,lease_duration_ms=120000)
        windows=tuple(SelectionSourceWindow(exchange_instrument_id=m,input_window_start_ms=day-23*h,feature_cutoff_at_ms=day+h,
            klines=tuple(SelectionKline(open_time_ms=day-23*h+i*900000,close_time_ms=day-23*h+(i+1)*900000,open=Decimal(100),close=Decimal(100),
                high=Decimal(101 if i<92 or m in ORB_STATIC_MEMBERS else 103),low=Decimal(99),quote_volume=Decimal(1000000)) for i in range(96))) for m in spec.candidate_ids)
        computation=compute_orb_selection(spec=spec,period=build_orb_session_period(day),selection_epoch_id=control.selection_epoch_id,source_windows=windows,decision_at_ms=day+h,source_observed_at_ms=day+h+1,created_at_ms=day+h+2)
        await uow.instrument_selection.complete_orb_selection_snapshot(claim=claim,computation=computation,completed_at_ms=day+h+2)
    request=CoordinateSelectionMaterializationRequest(selection_spec_id=spec.selection_spec_id,strategy_group_id=spec.strategy_group_id,session_start_ms=day,worker_id='orb:nonempty')
    created=await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(engine),request=request,clock_ms=lambda:day+h+3)
    assert created.disposition=='GENERATION_PENDING'
    from src.trading_kernel.application.drain_strategy_entry_vacuum import (
        DrainStrategyEntryVacuumRequest,
        drain_strategy_entry_vacuum_once,
    )
    for tick in range(4,8):
        progress=await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(engine),request=request,clock_ms=lambda tick=tick:day+h+tick)
        if progress.disposition=='WAITING_VACUUM':
            async with PostgresKernelUnitOfWork(engine) as uow:
                await drain_strategy_entry_vacuum_once(uow,DrainStrategyEntryVacuumRequest(strategy_group_id=spec.strategy_group_id,selection_spec_id=spec.selection_spec_id,now_ms=day+h+tick))
    assert progress.disposition=='LONG_WARMING'

    failed=await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(engine),request=request,clock_ms=lambda:day+h+1800100)
    assert failed.disposition=='WAITING_SELECTION' and failed.reason_code=='NO_PREVIOUS_ENTRY_AUTHORITY_AFTER_EMPTY'
    async with PostgresKernelUnitOfWork(engine) as uow:
        current=await uow.instrument_selection.get_current_authority_projection(spec.selection_spec_id)
        assert current.authority.authority_outcome=='VALID_EMPTY'
        vacuum=await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=spec.strategy_group_id,selection_spec_id=spec.selection_spec_id)
        assert vacuum.blocks_new_entry
    if static_retry:
        await assert_explicit_static_intent(engine,spec,day,existing_failed_vacuum=True)
        return
    later=day+86400000
    async with PostgresKernelUnitOfWork(engine) as uow:
        claim=await uow.instrument_selection.claim_orb_selection_job(selection_spec_id=spec.selection_spec_id,selection_epoch_id=control.selection_epoch_id,session_start_ms=later,worker_id='orb:retry:nonempty',now_ms=later+h,lease_duration_ms=120000)
        shifted=tuple(SelectionSourceWindow(exchange_instrument_id=w.exchange_instrument_id,input_window_start_ms=later-23*h,feature_cutoff_at_ms=later+h,
            klines=tuple(SelectionKline.model_validate({**b.model_dump(),'open_time_ms':b.open_time_ms+86400000,'close_time_ms':b.close_time_ms+86400000}) for b in w.klines)) for w in windows)
        retry=compute_orb_selection(spec=spec,period=build_orb_session_period(later),selection_epoch_id=control.selection_epoch_id,source_windows=shifted,decision_at_ms=later+h,source_observed_at_ms=later+h+1,created_at_ms=later+h+2)
        await uow.instrument_selection.complete_orb_selection_snapshot(claim=claim,computation=retry,completed_at_ms=later+h+2)
    resumed=await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(engine),request=CoordinateSelectionMaterializationRequest(selection_spec_id=spec.selection_spec_id,strategy_group_id=spec.strategy_group_id,session_start_ms=later,worker_id='orb:retry:nonempty'),clock_ms=lambda:later+h+3)
    assert resumed.disposition=='GENERATION_DESIRED'

@pytest.mark.asyncio
async def test_orb_readonly_view_loads_current_epoch_job(head_template_engine):
    from src.trading_kernel.application.owner_control import (
        ControlMutationRequest,
        stage_orb_dynamic_selection_mode,
    )
    from src.trading_kernel.interfaces.readonly_api import (
        SelectionRuntimeReadonlyRequest,
        get_selection_runtime_view,
    )
    spec=OrbSessionSelectionSpec();day=D+86400000
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        await seed_runtime_authority(uow,RuntimeAuthoritySeedRequest(account_id='orb-test',runtime_commit='orb-local-test',schema_revision=CURRENT_SCHEMA_REVISION,seeded_at_ms=D))
        await uow.instrument_selection.install_orb_spec(spec,installed_at_ms=D+1)
    await install_static_pair(head_template_engine)
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        control=await stage_orb_dynamic_selection_mode(uow,effective_session_start_ms=day,request=ControlMutationRequest(expected_version=1,reason='test',idempotency_key='orb:read',owner_identity='owner',now_ms=D+3600100),authentication_strength='totp_step_up')
        claim=await uow.instrument_selection.claim_orb_selection_job(selection_spec_id=spec.selection_spec_id,selection_epoch_id=control.selection_epoch_id,session_start_ms=day,worker_id='orb:read',now_ms=day+3600000,lease_duration_ms=30000)
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        view=await get_selection_runtime_view(uow,SelectionRuntimeReadonlyRequest(strategy_group_id=spec.strategy_group_id,selection_spec_id=spec.selection_spec_id,session_start_ms=day))
        assert view.selection_job.selection_job_id==claim.selection_job_id


async def assert_staged_facts_refresh(engine,spec,session,monkeypatch):
    from decimal import Decimal

    from src.trading_kernel.application.observe_strategy_scope import (
        ObservationRequest,
        observe_strategy_scope,
    )
    from src.trading_kernel.domain.market import ClosedCandle
    from src.trading_kernel.infrastructure.pg_instrument_selection_repository import (
        PostgresInstrumentSelectionRepository,
    )
    async with engine.connect() as connection:
        ids=tuple((await connection.execute(sa.text("SELECT runtime_scope_id FROM brc_runtime_scopes_current WHERE strategy_group_id='SOR-1H-001' AND lifecycle_state='staged' ORDER BY runtime_scope_id"))).scalars())
    assert len(ids)==14
    async def clock(self):return session+3600014
    monkeypatch.setattr(PostgresInstrumentSelectionRepository,'read_authority_clock_ms',clock)
    class Market:
        async def fetch_closed_candles(self,request):
            assert request.timeframe=='1h'
            return (ClosedCandle(open_time_ms=session,close_time_ms=session+3600000,open=Decimal(100),high=Decimal(101),low=Decimal(99),close=Decimal(100),volume=Decimal(100)),)
    for sid in ids:
        refreshed=await observe_strategy_scope(lambda:PostgresKernelUnitOfWork(engine),Market(),ObservationRequest(runtime_scope_id=sid,
            runtime_commit='orb-local-test',schema_revision=CURRENT_SCHEMA_REVISION,trigger_candle_close_time_ms=session+3600000,attempted_at_ms=session+3600014,
            operation='refresh_staged_facts'))
        assert refreshed.status=='facts_refreshed' and refreshed.signal_event_id is None
    async with engine.connect() as connection:
        assert await connection.scalar(sa.text("SELECT count(*) FROM brc_signal_events"))==0


async def assert_explicit_static_intent(engine,spec,session,fail=False, audit_failure=False, existing_failed_vacuum=False,last_hour_wait=False,unfenced_dynamic=False):
    from src.trading_kernel.application.owner_control import (
        ControlMutationRequest,
        stage_orb_static_selection_mode,
    )
    if unfenced_dynamic:
        from decimal import Decimal

        from src.trading_kernel.application.coordinate_selection_materialization import (
            _build_pending_generation,
        )
        from src.trading_kernel.domain.instrument_selection import (
            SelectionKline,
            SelectionSourceWindow,
        )
        from src.trading_kernel.domain.orb_session_selection import (
            build_orb_session_period,
            compute_orb_selection,
        )
        from src.trading_kernel.domain.selection_authority import UniverseAuthorityPair
        old_day=session+86400000;h=3600000
        async with PostgresKernelUnitOfWork(engine) as uow:
            current=await uow.instrument_selection.get_selection_control(spec.strategy_group_id)
            claim=await uow.instrument_selection.claim_orb_selection_job(selection_spec_id=spec.selection_spec_id,selection_epoch_id=current.selection_epoch_id,
                session_start_ms=old_day,worker_id='orb:unfenced',now_ms=old_day+h,lease_duration_ms=120000)
            windows=tuple(SelectionSourceWindow(exchange_instrument_id=m,input_window_start_ms=old_day-23*h,feature_cutoff_at_ms=old_day+h,
                klines=tuple(SelectionKline(open_time_ms=old_day-23*h+i*900000,close_time_ms=old_day-23*h+(i+1)*900000,
                    open=Decimal(100),close=Decimal(100),high=Decimal(101 if i<92 or m in spec.candidate_ids[-7:] else 103),low=Decimal(99),quote_volume=Decimal(1000000)) for i in range(96))) for m in spec.candidate_ids)
            value=compute_orb_selection(spec=spec,period=build_orb_session_period(old_day),selection_epoch_id=current.selection_epoch_id,
                source_windows=windows,decision_at_ms=old_day+h,source_observed_at_ms=old_day+h+1,created_at_ms=old_day+h+2)
            await uow.instrument_selection.complete_orb_selection_snapshot(claim=claim,computation=value,completed_at_ms=old_day+h+2)
            long=await uow.strategy_universes.get_current(spec.event_spec_ids[0]);short=await uow.strategy_universes.get_current(spec.event_spec_ids[1])
            prior=await uow.instrument_selection.get_current_authority_projection(spec.selection_spec_id)
            predecessor,targets=_build_pending_generation(snapshot=value.snapshot,selected_members=tuple(m.exchange_instrument_id for m in value.member_decisions if m.selected),
                previous_pair=UniverseAuthorityPair(long_universe_version_id=long.universe_version_id,short_universe_version_id=short.universe_version_id),
                created_at_ms=old_day+h+3,selection_control=current,previous_authority=prior.authority)
            await uow.instrument_selection.add_pending_materialization_generation(predecessor,targets=targets)
            await uow.instrument_selection.mark_materialization_generation_desired(predecessor.materialization_generation_id,expected_projection_version=1,desired_at_ms=old_day+h+4)
        session=old_day
    async with PostgresKernelUnitOfWork(engine) as uow:
        current=await uow.instrument_selection.get_selection_control(spec.strategy_group_id)
        pending=await stage_orb_static_selection_mode(uow,rollback_baseline_id=current.rollback_baseline_id,
            selection_epoch_id=current.selection_epoch_id,effective_session_start_ms=session+86400000,
            request=ControlMutationRequest(expected_version=current.control_version,reason='test Static rollback',idempotency_key='orb:static',owner_identity='owner',now_ms=session+7200100),authentication_strength='totp_step_up')
        assert pending.pending_selection_mode=='static_baseline' and pending.selection_mode=='dynamic_selection'
        assert pending.pending_authorization_id

    from src.trading_kernel.application.coordinate_selection_materialization import (
        CoordinateSelectionMaterializationRequest,
        coordinate_selection_materialization_once,
    )
    day=session+86400000
    if last_hour_wait:
        request=CoordinateSelectionMaterializationRequest(selection_spec_id=spec.selection_spec_id,strategy_group_id=spec.strategy_group_id,session_start_ms=day,worker_id='orb:static:late')
        before=await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(engine),request=request,clock_ms=lambda:day+22*3600000+1)
        assert before.disposition=='GENERATION_PENDING'
        desired=await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(engine),request=request,clock_ms=lambda:day+22*3600000+2)
        assert desired.disposition=='GENERATION_DESIRED'
        after=await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(engine),request=request,clock_ms=lambda:day+23*3600000)
        assert after.disposition=='WAITING_SELECTION'
        async with PostgresKernelUnitOfWork(engine) as uow:
            assert await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=spec.strategy_group_id,selection_spec_id=spec.selection_spec_id) is None
            assert await uow.instrument_selection.get_selection_control(spec.strategy_group_id)==pending
        day+=86400000
    created=await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(engine),request=CoordinateSelectionMaterializationRequest(selection_spec_id=spec.selection_spec_id,strategy_group_id=spec.strategy_group_id,session_start_ms=day,worker_id='orb:static'),clock_ms=lambda:day+3600001)
    assert created.disposition==('GENERATION_DESIRED' if existing_failed_vacuum else 'GENERATION_PENDING')
    async with PostgresKernelUnitOfWork(engine) as uow:
        generation=await uow.instrument_selection.get_materialization_generation(created.materialization_generation_id)
        assert generation.selection_mode=='static_baseline' and generation.rollback_baseline_id==pending.rollback_baseline_id
        assert generation.activation_authorization_id==pending.pending_authorization_id
    from src.trading_kernel.application.drain_strategy_entry_vacuum import (
        DrainStrategyEntryVacuumRequest,
        drain_strategy_entry_vacuum_once,
    )
    from tests.trading_kernel.integration.universe_activation_support import (
        make_warming_ready,
    )
    request=CoordinateSelectionMaterializationRequest(selection_spec_id=spec.selection_spec_id,strategy_group_id=spec.strategy_group_id,session_start_ms=day,worker_id='orb:static')
    for tick in range(2,12):
        if fail and tick>=5:tick=1800100
        async with engine.connect() as connection:
            warming=tuple((await connection.execute(sa.text("SELECT universe_version_id FROM brc_strategy_universe_versions WHERE materialization_generation_id=:gid AND lifecycle_state='warming'"),{'gid':generation.materialization_generation_id})).scalars())
        for uid in warming:
            await make_warming_ready(engine,universe_version_id=uid,warm_closed_bar_time_ms=day+3600000,valid_until_ms=day+7200000)
        progress=await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(engine),request=request,clock_ms=lambda tick=tick:day+3600000+tick)
        if progress.disposition=='WAITING_VACUUM':
            async with PostgresKernelUnitOfWork(engine) as uow:
                await drain_strategy_entry_vacuum_once(uow,DrainStrategyEntryVacuumRequest(strategy_group_id=spec.strategy_group_id,selection_spec_id=spec.selection_spec_id,now_ms=day+3600000+tick))
        if progress.disposition=='GAP_AUDIT_PENDING':break
    assert progress.disposition=='GAP_AUDIT_PENDING'
    async with PostgresKernelUnitOfWork(engine) as uow:
        audit=await uow.instrument_selection.get_authority_gap_audit(progress.authority_gap_audit_id)
        assert audit.proposed_authority_outcome==('FALLBACK_PREVIOUS' if fail else 'ACTIVE_NEW')
    from decimal import Decimal

    from src.trading_kernel.application.coordinate_selection_materialization import (
        complete_pending_authority_gap_audit,
    )
    from src.trading_kernel.domain.market import ClosedCandle
    from src.trading_kernel.interfaces.authority_gap_audit_source import (
        PublicMarketAuthorityGapAuditSource,
    )
    class Market:
        async def fetch_closed_candles(self,request):
            assert request.timeframe=='1h' and request.limit==1
            return (ClosedCandle(open_time_ms=day,close_time_ms=day+3600000,open=Decimal(100),high=Decimal(101),low=Decimal(99),close=Decimal(100),volume=Decimal(100)),)
    if audit_failure:
        class OfflineMarket:
            async def fetch_closed_candles(self, request):
                raise TimeoutError("local audit source unavailable")
        failed_audit=await complete_pending_authority_gap_audit(uow_factory=lambda:PostgresKernelUnitOfWork(engine),authority_gap_audit_id=progress.authority_gap_audit_id,
            audit_source=PublicMarketAuthorityGapAuditSource(OfflineMarket()),clock_ms=lambda:day+3600000+1800101)
        assert failed_audit.reason_code == "AUTHORITY_GAP_SOURCE_UNAVAILABLE"
        async with PostgresKernelUnitOfWork(engine) as uow:
            original=await uow.instrument_selection.get_authority_gap_audit(progress.authority_gap_audit_id)
            old_vacuum=await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=spec.strategy_group_id,selection_spec_id=spec.selection_spec_id)
        later=day+86400000
        request=CoordinateSelectionMaterializationRequest(selection_spec_id=spec.selection_spec_id,strategy_group_id=spec.strategy_group_id,session_start_ms=later,worker_id='orb:static:retry')
        for tick in range(1,15):
            async with engine.connect() as connection:
                warming=tuple((await connection.execute(sa.text("SELECT universe_version_id FROM brc_strategy_universe_versions WHERE strategy_group_id='SOR-1H-001' AND lifecycle_state='warming'"))).scalars())
            for uid in warming:
                await make_warming_ready(engine,universe_version_id=uid,warm_closed_bar_time_ms=later+3600000,valid_until_ms=later+7200000)
            retried=await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(engine),request=request,clock_ms=lambda tick=tick:later+3600000+tick)
            if retried.disposition=='GAP_AUDIT_PENDING':
                break
        assert retried.disposition=='GAP_AUDIT_PENDING',retried
        class LaterMarket:
            async def fetch_closed_candles(self,request):
                return (ClosedCandle(open_time_ms=later,close_time_ms=later+3600000,open=Decimal(100),high=Decimal(101),low=Decimal(99),close=Decimal(100),volume=Decimal(100)),)
        recovered=await complete_pending_authority_gap_audit(uow_factory=lambda:PostgresKernelUnitOfWork(engine),authority_gap_audit_id=retried.authority_gap_audit_id,
            audit_source=PublicMarketAuthorityGapAuditSource(LaterMarket()),clock_ms=lambda:later+3600000+16)
        assert recovered.disposition=='ACTIVE_NEW'
        async with PostgresKernelUnitOfWork(engine) as uow:
            final=await uow.instrument_selection.get_selection_control(spec.strategy_group_id)
            authority=await uow.instrument_selection.get_current_authority_projection(spec.selection_spec_id)
            failed_still=await uow.instrument_selection.get_authority_gap_audit(original.authority_gap_audit_id)
            assert failed_still==original
            assert final.selection_mode=='static_baseline' and final.pending_authorization_id is None and final.selection_epoch_id is None
            assert authority.authority.activation_authorization_id==pending.pending_authorization_id
            assert authority.authority.first_eligible_close_time_ms==later+7200000
            assert await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=spec.strategy_group_id,selection_spec_id=spec.selection_spec_id) is None
        async with engine.connect() as connection:
            assert await connection.scalar(sa.text("SELECT count(*) FROM brc_strategy_universe_current p JOIN brc_strategy_universe_versions u USING(universe_version_id) WHERE u.strategy_group_id='SOR-1H-001' AND u.source_kind='static_baseline' AND p.lifecycle_state='active'"))==2
            final_vacuum=(await connection.execute(sa.text("SELECT * FROM brc_strategy_entry_vacuums_current WHERE entry_vacuum_id=:vid"),{'vid':old_vacuum.entry_vacuum_id})).mappings().one()
            assert final_vacuum['fenced_at_ms']==old_vacuum.fenced_at_ms
            assert final_vacuum['drained_at_ms']==old_vacuum.drained_at_ms
            assert await connection.scalar(sa.text('SELECT count(*) FROM brc_exchange_commands'))==0
        return
    activated=await complete_pending_authority_gap_audit(uow_factory=lambda:PostgresKernelUnitOfWork(engine),authority_gap_audit_id=progress.authority_gap_audit_id,
        audit_source=PublicMarketAuthorityGapAuditSource(Market()),clock_ms=lambda:day+3600000+(1800101 if fail else 13))
    assert activated.disposition==('FALLBACK_PREVIOUS' if fail else 'ACTIVE_NEW')
    if fail:
        async with PostgresKernelUnitOfWork(engine) as uow:
            kept=await uow.instrument_selection.get_selection_control(spec.strategy_group_id)
            assert kept==pending
        retried=await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(engine),request=CoordinateSelectionMaterializationRequest(selection_spec_id=spec.selection_spec_id,strategy_group_id=spec.strategy_group_id,session_start_ms=day+86400000,worker_id='orb:static:retry'),clock_ms=lambda:day+90000001)
        assert retried.disposition=='GENERATION_PENDING'
        return
    async with PostgresKernelUnitOfWork(engine) as uow:
        control=await uow.instrument_selection.get_selection_control(spec.strategy_group_id)
        assert control.selection_mode=='static_baseline' and control.selection_epoch_id is None
        baseline=await uow.instrument_selection.get_orb_static_baseline(control.rollback_baseline_id)
        current=await uow.instrument_selection.get_current_authority_projection(spec.selection_spec_id)
        assert current.authority.selection_mode=='static_baseline'
        assert current.authority.activation_authorization_id==pending.pending_authorization_id
        assert current.authority.authorized_pair.long_universe_version_id != baseline.source_events[0].universe_version_id
        assert current.authority.authorized_pair.short_universe_version_id != baseline.source_events[1].universe_version_id
        from src.trading_kernel.application.ingest_signal import (
            SelectionEntryAuthorityFacts,
            evaluate_selection_entry_authority,
        )
        authority=current.authority
        decision=evaluate_selection_entry_authority(SelectionEntryAuthorityFacts(selection_control=control,current_authority=authority,authority_chain=(authority,),
            current_pair=authority.authorized_pair,active_generation_pair=authority.authorized_pair,scoped_vacuum_open=False,authority_interrupted=False,
            owner_entry_enabled=True,owner_control_version=authority.owner_control_version,global_policy_enabled=True,trigger_suppressed=False),
            birth_selection_authority_id=authority.selection_authority_id,observed_close_time_ms=day+7200000,now_ms=day+7200001,allow_current_as_birth=False)
        assert decision.allowed,decision.reason_code
        from src.trading_kernel.application.owner_control import (
            stage_orb_dynamic_selection_mode,
        )
        restarted=await stage_orb_dynamic_selection_mode(uow,effective_session_start_ms=day+86400000,
            request=ControlMutationRequest(expected_version=control.control_version,reason='restart Dynamic',idempotency_key='orb:restart',owner_identity='owner',now_ms=day+7200100),authentication_strength='totp_step_up')
        assert restarted.selection_epoch_id!=pending.selection_epoch_id
        assert restarted.rollback_baseline_id==control.rollback_baseline_id
        pending_static=evaluate_selection_entry_authority(SelectionEntryAuthorityFacts(selection_control=restarted,current_authority=authority,authority_chain=(authority,),
            current_pair=authority.authorized_pair,active_generation_pair=authority.authorized_pair,scoped_vacuum_open=False,authority_interrupted=False,
            owner_entry_enabled=True,owner_control_version=authority.owner_control_version,global_policy_enabled=True,trigger_suppressed=False),
            birth_selection_authority_id=authority.selection_authority_id,observed_close_time_ms=day+7200000,now_ms=day+7200101,allow_current_as_birth=False)
        assert pending_static.allowed,pending_static.reason_code



@pytest.mark.asyncio
async def test_bootstrap_only_hourly_static_pair_uses_formal_workers_and_does_not_touch_other_groups(head_template_engine):
    from decimal import Decimal

    from scripts.trading_kernel.bootstrap_strategy_universes import (
        bootstrap_strategy_universes,
    )
    from src.trading_kernel.domain.market import ClosedCandle
    from src.trading_kernel.interfaces.observation_worker import (
        ObservationWorkerRequest,
        run_observation_worker_once,
    )
    from src.trading_kernel.interfaces.reconciliation_worker import (
        ReconciliationWorkerRequest,
        ReconciliationWorkerStatus,
        run_reconciliation_worker_once,
    )
    from tests.trading_kernel.integration.universe_certification_support import (
        RecordingReadonlyCertificationSource,
    )
    from tests.trading_kernel.support.dispatch_venues import AcceptingVenue
    engine=head_template_engine
    async with PostgresKernelUnitOfWork(engine) as uow:
        await seed_runtime_authority(uow,RuntimeAuthoritySeedRequest(account_id='orb-bootstrap',runtime_commit='orb-local-test',schema_revision=CURRENT_SCHEMA_REVISION,seeded_at_ms=D))
        await uow.instrument_selection.install_orb_spec(OrbSessionSelectionSpec(),installed_at_ms=D+1)
    class Market:
        async def fetch_closed_candles(self,request):
            assert request.timeframe=='1h'
            return (ClosedCandle(open_time_ms=D,close_time_ms=D+3600000,open=Decimal(100),high=Decimal(101),low=Decimal(99),close=Decimal(100),volume=Decimal(1000000)),)
    class Positions:
        async def fetch_position(self,request):raise AssertionError('bootstrap must not load Ticket positions')
    factory=lambda:PostgresKernelUnitOfWork(engine)
    now=D+3600000+100
    async def workers(delay):
        nonlocal now
        for _ in range(7):
            certified=await run_reconciliation_worker_once(factory,AcceptingVenue(engine),Positions(),ReconciliationWorkerRequest(worker_id='orb:bootstrap:cert',runtime_commit='orb-local-test',schema_revision=CURRENT_SCHEMA_REVISION,
                now_ms=now,timeout_seconds=1,unknown_visibility_grace_ms=30000,idle_poll_interval_ms=1000,certification_lease_ms=60000,certification_valid_for_ms=600000,
                certification_eligible_check_interval_ms=300000,certification_owner_action_check_interval_ms=300000,certification_transient_retry_interval_ms=30000),instrument_certification_source=RecordingReadonlyCertificationSource(engine))
            if certified.status is not ReconciliationWorkerStatus.INSTRUMENT_CERTIFIED:break
        for _ in range(7):
            await run_observation_worker_once(factory,Market(),ObservationWorkerRequest(worker_id='orb:bootstrap:observe',runtime_commit='orb-local-test',schema_revision=CURRENT_SCHEMA_REVISION,
                now_ms=now,lease_until_ms=now+30000,timeout_seconds=1,retry_interval_ms=1000))
        now+=10
    results=await bootstrap_strategy_universes(engine.url.render_as_string(hide_password=False),runtime_profile_id='tiny-live-v1',strategy_group_id='SOR-1H-001',
        now_ms=lambda:now,wait_timeout_ms=30000,poll_interval_ms=1,sleep=workers)
    assert tuple(r.event_id for r in results)==('SOR-1H-LONG','SOR-1H-SHORT')
    async with engine.connect() as connection:
        assert await connection.scalar(sa.text('SELECT count(*) FROM brc_strategy_universe_current'))==2
        assert await connection.scalar(sa.text('SELECT count(*) FROM brc_exchange_commands'))==0
        assert await connection.scalar(sa.text("SELECT entry_state FROM brc_strategy_entry_controls_current WHERE strategy_group_id='SOR-1H-001'"))=='paused'
