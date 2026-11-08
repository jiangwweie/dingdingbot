from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from src.trading_kernel.domain.management_observation import ManagementScan
from src.trading_kernel.domain.position import PositionSnapshot, VenueOrderSnapshot
from src.trading_kernel.domain.trade_management import (
    ManagementMode,
    OrderEvidence,
    OrderTerms,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.interfaces.management_observation_worker import (
    observe_management_once,
)
from tests.trading_kernel.support.lifecycle import (
    reach_position_protected,
    registered_sor_long_ticket,
)


@pytest.mark.asyncio
async def test_worker_reads_app_order_and_persists_takeover(head_template_engine):
    t = registered_sor_long_ticket()
    e = head_template_engine
    await reach_position_protected(e, t)
    d = t.identity.netting_domain
    terms = OrderTerms(
        venue_id=d.venue_id,
        account_id=d.account_id,
        exchange_instrument_id=d.exchange_instrument_id,
        position_side=d.position_side,
        order_namespace="regular",
        exchange_order_id="app-1",
        client_order_id="app",
        side="sell",
        order_type="LIMIT",
        quantity="0.001",
        price="65000",
        trigger_price=None,
        close_position=False,
        reduce_only=False,
        time_in_force="GTC",
        working_type="CONTRACT_PRICE",
        price_protect=False,
        activation_price=None,
        callback_rate=None,
        price_match="NONE",
        self_trade_prevention_mode="NONE",
        good_till_date_ms=0,
    )
    event = OrderEvidence(
        evidence_id="external-new",
        terms=terms,
        action="new",
        exchange_event_at_ms=5000,
        received_at_ms=5001,
        created_at_ms=5000,
        executed_quantity="0",
        coverage_complete=True,
        known_command_outcome_pending=False,
    )
    order = VenueOrderSnapshot(
        exchange_order_id="app-1",
        venue_client_order_id="app",
        position_side="long",
        reduce_only=False,
        order_namespace="regular",
        terms=terms,
    )
    source = AsyncMock()
    source.read_management_scan.return_value = ManagementScan(
        ticket_id=t.identity.ticket_id,
        snapshot=PositionSnapshot(
            netting_domain=d,
            quantity=t.quantity,
            average_entry_price=Decimal(60000),
            open_orders=(order,),
            observed_at_ms=6000,
        ),
        orders=(terms,),
        evidence=(event,),
        complete=True,
        covered_until_ms=6000,
    )
    assert (
        await observe_management_once(
            lambda: PostgresKernelUnitOfWork(e),
            source,
            ticket_id=t.identity.ticket_id,
            now_ms=6000,
        )
        == "MANUAL"
    )
    async with PostgresKernelUnitOfWork(e) as u:
        a = await u.aggregates.get(t.identity.ticket_id)
        assert a.management_mode is ManagementMode.MANUAL
        assert a.management_orders[0]["exchange_order_id"] == "app-1"
        assert (
            await u.management.account_blocker(d.venue_id, d.account_id, 6000)
            is not None
        )


@pytest.mark.asyncio
async def test_collection_failure_persists_gap_and_blocks_new_entry(
    head_template_engine,
):
    t = registered_sor_long_ticket()
    e = head_template_engine
    await reach_position_protected(e, t)
    source = AsyncMock()
    source.read_management_scan.side_effect = TimeoutError()
    assert (
        await observe_management_once(
            lambda: PostgresKernelUnitOfWork(e),
            source,
            ticket_id=t.identity.ticket_id,
            now_ms=6000,
        )
        == "management_facts_unavailable"
    )
    async with PostgresKernelUnitOfWork(e) as u:
        d = t.identity.netting_domain
        assert (
            await u.management.account_blocker(d.venue_id, d.account_id, 6000)
            == "manual_management_risk_unavailable"
        )


@pytest.mark.asyncio
async def test_collection_failure_freezes_automatic_actions(head_template_engine):
    t = registered_sor_long_ticket()
    e = head_template_engine
    await reach_position_protected(e, t)
    source = AsyncMock()
    source.read_management_scan.side_effect = TimeoutError()
    await observe_management_once(
        lambda: PostgresKernelUnitOfWork(e),
        source,
        ticket_id=t.identity.ticket_id,
        now_ms=6000,
    )
    async with PostgresKernelUnitOfWork(e) as u:
        assert (
            await u.aggregates.get(t.identity.ticket_id)
        ).management_mode is ManagementMode.REVIEW_REQUIRED


@pytest.mark.asyncio
async def test_empty_history_cannot_clear_observation_gap(head_template_engine):
    t = registered_sor_long_ticket()
    e = head_template_engine
    await reach_position_protected(e, t)
    source = AsyncMock()
    source.read_management_scan.side_effect = TimeoutError()
    await observe_management_once(
        lambda: PostgresKernelUnitOfWork(e),
        source,
        ticket_id=t.identity.ticket_id,
        now_ms=6000,
    )
    source.read_management_scan.side_effect = None
    source.read_management_scan.return_value = ManagementScan(
        ticket_id=t.identity.ticket_id,
        snapshot=PositionSnapshot(
            netting_domain=t.identity.netting_domain,
            quantity=t.quantity,
            average_entry_price=Decimal(60000),
            observed_at_ms=7000,
        ),
        orders=(),
        evidence=(),
        complete=True,
        covered_until_ms=7000,
    )
    result = await observe_management_once(
        lambda: PostgresKernelUnitOfWork(e),
        source,
        ticket_id=t.identity.ticket_id,
        now_ms=7000,
    )
    assert result == "REVIEW_REQUIRED"
    async with PostgresKernelUnitOfWork(e) as u:
        assert (
            await u.aggregates.get(t.identity.ticket_id)
        ).management_mode is ManagementMode.REVIEW_REQUIRED


@pytest.mark.asyncio
async def test_worker_system_tp_creation_does_not_take_over(head_template_engine):
 from src.trading_kernel.domain.trade_management import OrderAction
 e=head_template_engine;t=registered_sor_long_ticket();await reach_position_protected(e,t);d=t.identity.netting_domain
 async with PostgresKernelUnitOfWork(e) as u:
  rows=await u.management.command_rows(t.identity.ticket_id)
  row=next(r for r in rows if r['command_kind']=='take_profit')
  a=await u.aggregates.get(t.identity.ticket_id)
 now=max(6000,row['completed_at_ms'],row['created_at_ms'])
 payload=row['request_payload']
 terms=OrderTerms(venue_id=d.venue_id,account_id=d.account_id,exchange_instrument_id=d.exchange_instrument_id,position_side=d.position_side,order_namespace='regular',exchange_order_id=row['result_payload']['exchange_order_id'],client_order_id=row['venue_client_order_id'],side=payload['side'],order_type='LIMIT',quantity=payload['quantity'],price=payload['limit_price'],trigger_price=None,close_position=False,reduce_only=False,time_in_force=payload['time_in_force'],working_type='CONTRACT_PRICE',price_protect=False,activation_price=None,callback_rate=None,price_match='NONE',self_trade_prevention_mode='NONE',good_till_date_ms=0)
 event=OrderEvidence(evidence_id='system-tp-new',terms=terms,action=OrderAction.NEW,exchange_event_at_ms=row['created_at_ms'],received_at_ms=now,created_at_ms=row['created_at_ms'],executed_quantity='0',coverage_complete=True,known_command_outcome_pending=False)
 source=AsyncMock();source.read_management_scan.return_value=ManagementScan(ticket_id=t.identity.ticket_id,snapshot=PositionSnapshot(netting_domain=d,quantity=t.quantity,average_entry_price=Decimal(60000),observed_at_ms=now),orders=(),evidence=(event,),complete=True,covered_until_ms=now)
 assert await observe_management_once(lambda:PostgresKernelUnitOfWork(e),source,ticket_id=t.identity.ticket_id,now_ms=now)=='AUTO'
 async with PostgresKernelUnitOfWork(e) as u:assert (await u.aggregates.get(t.identity.ticket_id)).status==a.status


@pytest.mark.asyncio
async def test_manual_ownership_not_cleared_after_gap_recovery(head_template_engine):
 from src.trading_kernel.domain.events import ManualTakeoverConfirmed
 from src.trading_kernel.domain.reducer import reduce_event
 e=head_template_engine;t=registered_sor_long_ticket();await reach_position_protected(e,t)
 async with PostgresKernelUnitOfWork(e) as u:
  a=await u.aggregates.get(t.identity.ticket_id)
  ev=ManualTakeoverConfirmed(event_id='take',ticket_id=t.identity.ticket_id,sequence=a.last_event_sequence+1,occurred_at_ms=5000,evidence_id='app',reason='app')
  await u.commit_reduction(event=ev,reduction=reduce_event(a,ev),expected_version=a.version)
 source=AsyncMock();source.read_management_scan.side_effect=TimeoutError()
 await observe_management_once(lambda:PostgresKernelUnitOfWork(e),source,ticket_id=t.identity.ticket_id,now_ms=6000)
 source.read_management_scan.side_effect=None
 source.read_management_scan.return_value=ManagementScan(ticket_id=t.identity.ticket_id,snapshot=PositionSnapshot(netting_domain=t.identity.netting_domain,quantity=t.quantity,average_entry_price=Decimal(60000),observed_at_ms=7000),orders=(),evidence=(),complete=True,covered_until_ms=7000)
 assert await observe_management_once(lambda:PostgresKernelUnitOfWork(e),source,ticket_id=t.identity.ticket_id,now_ms=7000)=='MANUAL'


@pytest.mark.asyncio
async def test_wrong_batch_identity_freezes_automatic_management(head_template_engine):
    t = registered_sor_long_ticket()
    e = head_template_engine
    await reach_position_protected(e, t)
    source = AsyncMock()
    source.read_management_scan.return_value = ManagementScan(ticket_id='wrong-ticket',
        snapshot=PositionSnapshot(netting_domain=t.identity.netting_domain, quantity=t.quantity,
            average_entry_price=Decimal(60000), observed_at_ms=6000), orders=(), evidence=(),
        complete=True, covered_until_ms=6000)
    assert await observe_management_once(lambda: PostgresKernelUnitOfWork(e), source,
        ticket_id=t.identity.ticket_id, now_ms=6000) == 'management_facts_unavailable'
    async with PostgresKernelUnitOfWork(e) as u:
        assert (await u.aggregates.get(t.identity.ticket_id)).management_mode is ManagementMode.REVIEW_REQUIRED


@pytest.mark.asyncio
async def test_selected_auto_ticket_observed_before_legacy_position_reconciliation(head_template_engine):
    from src.trading_kernel.interfaces.reconciliation_worker import (
        ReconciliationWorkerRequest,
        _run_reconciliation_worker_once_core_impl,
    )
    t = registered_sor_long_ticket()
    e = head_template_engine
    await reach_position_protected(e, t)
    async with PostgresKernelUnitOfWork(e) as u:
        a = await u.aggregates.get(t.identity.ticket_id)
    source = AsyncMock()
    source.read_management_scan.side_effect = TimeoutError()
    source.read_position_snapshot.return_value = PositionSnapshot(
        netting_domain=t.identity.netting_domain, quantity=Decimal(0), average_entry_price=None, observed_at_ms=6000)
    await _run_reconciliation_worker_once_core_impl(lambda:PostgresKernelUnitOfWork(e), AsyncMock(), source,
        ReconciliationWorkerRequest(worker_id='selected-ticket', runtime_commit='kernel-test-head',
            schema_revision='0017_app_management_observation', now_ms=6000, timeout_seconds=1,
            unknown_visibility_grace_ms=30000, idle_poll_interval_ms=1000),
        unknown=None, aggregate=a)
    source.read_management_scan.assert_awaited_once()
    source.read_position_snapshot.assert_not_awaited()
    async with PostgresKernelUnitOfWork(e) as u:
        assert (await u.aggregates.get(t.identity.ticket_id)).management_mode is ManagementMode.REVIEW_REQUIRED


@pytest.mark.asyncio
async def test_full_exact_system_history_clears_recoverable_review(head_template_engine):
    e = head_template_engine
    t = registered_sor_long_ticket()
    await reach_position_protected(e, t)
    source = AsyncMock()
    source.read_management_scan.side_effect = TimeoutError()
    await observe_management_once(lambda:PostgresKernelUnitOfWork(e), source,
        ticket_id=t.identity.ticket_id, now_ms=6000)
    async with PostgresKernelUnitOfWork(e) as u:
        rows = await u.management.command_rows(t.identity.ticket_id)
    d = t.identity.netting_domain
    evidence = []
    for row in rows:
        p = row['request_payload']
        if row['command_kind'] == 'cancel_order':
            continue
        terms = OrderTerms(venue_id=d.venue_id, account_id=d.account_id,
            exchange_instrument_id=d.exchange_instrument_id, position_side=d.position_side,
            order_namespace='conditional' if p['order_type'] in ('stop_market', 'take_profit_market') else 'regular',
            exchange_order_id=row['result_payload']['exchange_order_id'], client_order_id=row['venue_client_order_id'],
            side=p['side'], order_type=p['order_type'].upper(), quantity=p['quantity'],
            price=p.get('limit_price'), trigger_price=p.get('stop_price'),
            close_position=False, reduce_only=False, time_in_force=p.get('time_in_force') or 'GTC',
            working_type='CONTRACT_PRICE', price_protect=False, activation_price=None, callback_rate=None,
            price_match='NONE', self_trade_prevention_mode='NONE', good_till_date_ms=0)
        evidence.append(OrderEvidence(evidence_id=row['command_id'], terms=terms, action='new',
            exchange_event_at_ms=row['created_at_ms'], received_at_ms=7000,
            created_at_ms=row['created_at_ms'], executed_quantity='0',
            coverage_complete=True, known_command_outcome_pending=False))
    source.read_management_scan.side_effect = None
    source.read_management_scan.return_value = ManagementScan(ticket_id=t.identity.ticket_id,
        snapshot=PositionSnapshot(netting_domain=d, quantity=t.quantity, average_entry_price=Decimal(60000),
            observed_at_ms=7000), orders=(), evidence=tuple(evidence), complete=True, covered_until_ms=7000)
    assert await observe_management_once(lambda:PostgresKernelUnitOfWork(e), source,
        ticket_id=t.identity.ticket_id, now_ms=7000) == 'AUTO'


@pytest.mark.asyncio
async def test_selected_auto_ticket_still_reconciles_after_complete_scan(head_template_engine):
    from src.trading_kernel.interfaces.reconciliation_worker import (
        ReconciliationWorkerRequest,
        _run_reconciliation_worker_once_core_impl,
    )
    t = registered_sor_long_ticket()
    e = head_template_engine
    await reach_position_protected(e, t)
    async with PostgresKernelUnitOfWork(e) as u:
        a = await u.aggregates.get(t.identity.ticket_id)
    source = AsyncMock()
    snap = PositionSnapshot(netting_domain=t.identity.netting_domain, quantity=t.quantity,
        average_entry_price=Decimal(60000), observed_at_ms=6000)
    source.read_management_scan.return_value = ManagementScan(ticket_id=t.identity.ticket_id,
        snapshot=snap, orders=(), evidence=(), complete=True, covered_until_ms=6000)
    source.read_position_snapshot.return_value = snap
    await _run_reconciliation_worker_once_core_impl(lambda:PostgresKernelUnitOfWork(e), AsyncMock(), source,
        ReconciliationWorkerRequest(worker_id='selected-ticket', runtime_commit='kernel-test-head',
            schema_revision='0017_app_management_observation', now_ms=6000, timeout_seconds=1,
            unknown_visibility_grace_ms=30000, idle_poll_interval_ms=1000), unknown=None, aggregate=a)
    source.read_management_scan.assert_awaited_once()
    source.read_position_snapshot.assert_awaited_once()
