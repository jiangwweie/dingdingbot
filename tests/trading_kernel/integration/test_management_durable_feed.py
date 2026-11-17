import pytest

from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork


@pytest.mark.asyncio
async def test_raw_events_are_durable_before_watermark_and_epoch_gap_cannot_be_erased(
    head_template_engine,
):
    e = head_template_engine
    async with PostgresKernelUnitOfWork(e) as u:
        await u.management.start_feed(
            scope_key="binance-usdm:account",
            epoch_id="epoch1",
            worker_id="worker",
            runtime_commit="a" * 40,
            now_ms=1000,
        )
        assert not await u.management.feed_ready("binance-usdm:account", now_ms=1001)
        await u.management.persist_stream_batch(
            scope_key="binance-usdm:account",
            epoch_id="epoch1",
            events=[
                {
                    "sequence": 1,
                    "received_at_ms": 1100,
                    "payload": {
                        "e": "ORDER_TRADE_UPDATE",
                        "E": 1001,
                        "T": 1001,
                        "o": {
                            "s": "BNBUSDT",
                            "c": "brc-entry",
                            "S": "SELL",
                            "o": "MARKET",
                            "f": "GTC",
                            "q": "2",
                            "p": "0",
                            "sp": "0",
                            "x": "TRADE",
                            "X": "FILLED",
                            "i": 11,
                            "z": "2",
                            "ps": "SHORT",
                            "cp": False,
                            "R": False,
                            "wt": "CONTRACT_PRICE",
                            "pP": False,
                            "pm": "NONE",
                            "V": "EXPIRE_MAKER",
                            "gtd": 0,
                            "O": 1001,
                        },
                    },
                }
            ],
            connected_at_ms=1000,
            now_ms=1200,
        )
        assert await u.management.feed_ready("binance-usdm:account", now_ms=1201)
        rows = await u.management.stream_events("binance-usdm:account", 1000, 2000)
        assert len(rows) == 1 and rows[0]["receive_sequence"] == 1
    async with PostgresKernelUnitOfWork(e) as u:
        await u.management.start_feed(
            scope_key="binance-usdm:account",
            epoch_id="epoch2",
            worker_id="worker2",
            runtime_commit="a" * 40,
            now_ms=17000,
        )
        assert not await u.management.feed_ready("binance-usdm:account", now_ms=17001)
        await u.management.persist_stream_batch(
            scope_key="binance-usdm:account",
            epoch_id="epoch2",
            events=[],
            connected_at_ms=17000,
            now_ms=18000,
        )
        assert await u.management.feed_ready("binance-usdm:account", now_ms=18001)
        assert not await u.management.continuity_covers(
            "binance-usdm:account", 1000, 18000
        )
        assert await u.management.continuity_covers(
            "binance-usdm:account", 17000, 18000
        )


@pytest.mark.asyncio
async def test_duplicate_receive_identity_with_changed_payload_is_rejected(
    head_template_engine,
):
    e = head_template_engine
    event = {
        "sequence": 1,
        "received_at_ms": 1100,
        "payload": {"e": "bad-event", "E": 1001},
    }
    async with PostgresKernelUnitOfWork(e) as u:
        await u.management.start_feed(
            scope_key="s",
            epoch_id="e",
            worker_id="w",
            runtime_commit="a" * 40,
            now_ms=1000,
        )
        await u.management.persist_stream_batch(
            scope_key="s",
            epoch_id="e",
            events=[event],
            connected_at_ms=1000,
            now_ms=1200,
        )
    async with PostgresKernelUnitOfWork(e) as u:
        changed = {**event, "payload": {"e": "different-event", "E": 1001}}
        with pytest.raises(ValueError, match="collision"):
            await u.management.persist_stream_batch(
                scope_key="s",
                epoch_id="e",
                events=[changed],
                connected_at_ms=1000,
                now_ms=1300,
            )


@pytest.mark.asyncio
async def test_live_epoch_cannot_be_renewed_by_another_worker(head_template_engine):
    async with PostgresKernelUnitOfWork(head_template_engine) as u:
        await u.management.start_feed(
            scope_key="s",
            epoch_id="e",
            worker_id="one",
            runtime_commit="a" * 40,
            now_ms=1000,
        )
        with pytest.raises(ValueError, match="owner"):
            await u.management.persist_stream_batch(
                scope_key="s",
                epoch_id="e",
                events=[],
                connected_at_ms=1000,
                now_ms=1100,
                worker_id="two",
            )


@pytest.mark.asyncio
async def test_pending_receive_backlog_never_advertises_ready_and_lease_expires(
    head_template_engine,
):
    async with PostgresKernelUnitOfWork(head_template_engine) as u:
        await u.management.start_feed(
            scope_key="s",
            epoch_id="e",
            worker_id="w",
            runtime_commit="a" * 40,
            now_ms=1000,
        )
        await u.management.persist_stream_batch(
            scope_key="s",
            epoch_id="e",
            events=[],
            connected_at_ms=1000,
            now_ms=1100,
            backlog_pending=True,
        )
        assert not await u.management.feed_ready("s", now_ms=1101)
        await u.management.persist_stream_batch(
            scope_key="s", epoch_id="e", events=[], connected_at_ms=1000, now_ms=1200
        )
        assert await u.management.feed_ready("s", now_ms=1201, runtime_commit="a" * 40)
        assert not await u.management.feed_ready(
            "s", now_ms=1201, runtime_commit="b" * 40
        )
        assert not await u.management.feed_ready("s", now_ms=18000)


@pytest.mark.asyncio
async def test_durable_receiver_acknowledges_only_after_commit_and_identity_gate(
    head_template_engine,
):
    from src.trading_kernel.interfaces.management_feed_worker import (
        persist_management_feed_once,
    )
    from tests.trading_kernel.support.lifecycle import (
        reach_position_protected,
        registered_sor_long_ticket,
    )

    e = head_template_engine
    t = registered_sor_long_ticket()
    await reach_position_protected(e, t)

    class Source:
        def __init__(self):
            self.acknowledged = []

        def management_feed_batches(self):
            return [
                {
                    "venue_id": "binance-usdm",
                    "account_id": t.identity.netting_domain.account_id,
                    "epoch_id": "durable-e",
                    "connection_observed_at_ms":6000,
                    "events": [],
                    "connected_at_ms": 1000,
                    "gap_reason": None,
                    "backlog_pending": False,
                }
            ]

        def acknowledge_management_events(self, epoch, watermark):
            self.acknowledged.append((epoch, watermark))

    source = Source()
    result = await persist_management_feed_once(
        lambda: PostgresKernelUnitOfWork(e),
        source,
        worker_id="receiver",
        runtime_commit="wrong",
        now_ms=5000,
        clock_ms=lambda: 5000,
    )
    assert result.status == "runtime_fenced" and source.acknowledged == []
    result = await persist_management_feed_once(
        lambda: PostgresKernelUnitOfWork(e),
        source,
        worker_id="receiver",
        runtime_commit="kernel-test-head",
        now_ms=6000,
        clock_ms=lambda: 6000,
    )
    assert result.status == "management_feed_persisted" and source.acknowledged == [
        ("durable-e", 0)
    ]

    class FailingContext:
        async def __aenter__(self):
            self.u = PostgresKernelUnitOfWork(e)
            return await self.u.__aenter__()

        async def __aexit__(self, *args):
            await self.u.__aexit__(RuntimeError, RuntimeError("commit failed"), None)
            raise RuntimeError("commit failed")

    source.acknowledged.clear()
    # Runtime identity checking itself also uses a UoW; failing there is sufficient
    # to prove no input is acknowledged on a failed durable commit boundary.
    with pytest.raises(RuntimeError, match="commit failed"):
        await persist_management_feed_once(
            FailingContext,
            source,
            worker_id="receiver",
            runtime_commit="kernel-test-head",
            now_ms=7000,
            clock_ms=lambda: 7000,
        )
    assert source.acknowledged == []


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", [None, "future_receipt", "future_exchange"])
async def test_receive_after_tick_start_is_not_a_protocol_error(
    head_template_engine, fault
):
    import json
    from pathlib import Path

    from src.trading_kernel.interfaces.management_feed_worker import (
        management_scope,
        persist_management_feed_once,
    )
    from tests.trading_kernel.support.lifecycle import (
        reach_position_protected,
        registered_sor_long_ticket,
    )

    e = head_template_engine
    t = registered_sor_long_ticket()
    await reach_position_protected(e, t)
    raw = json.loads(
        (
            Path(__file__).parents[1]
            / "fixtures/manual_management_recovery/receive_clock_event.json"
        ).read_text()
    )

    processed_at_ms = raw["received_at_ms"] + 1
    if fault == "future_receipt":
        raw["received_at_ms"] = processed_at_ms + 1
    elif fault == "future_exchange":
        raw["payload"]["T"] = raw["received_at_ms"] + 1
        raw["payload"]["E"] = raw["received_at_ms"] + 1

    class Source:
        def __init__(self):
            self.acknowledged = []
            self.restarts = []

        async def restart_management_transport(self, epoch_id):
            assert self.acknowledged == [(epoch_id, 1)]
            self.restarts.append(epoch_id)

        def management_feed_batches(self):
            return [
                {
                    "venue_id": "binance-usdm",
                    "account_id": t.identity.netting_domain.account_id,
                    "epoch_id": "clock-race",
                    "connection_observed_at_ms":processed_at_ms,
                    "connected_at_ms": raw["tick_started_ms"] - 100,
                    "events": [
                        {
                            "sequence": 1,
                            "received_at_ms": raw["received_at_ms"],
                            "payload": raw["payload"],
                        }
                    ],
                    "gap_reason": None,
                    "backlog_pending": False,
                }
            ]

        def acknowledge_management_events(self, epoch, watermark):
            self.acknowledged.append((epoch, watermark))

    source = Source()
    result = await persist_management_feed_once(
        lambda: PostgresKernelUnitOfWork(e),
        source,
        worker_id="receiver",
        runtime_commit="kernel-test-head",
        now_ms=raw["tick_started_ms"],
        clock_ms=lambda: processed_at_ms,
    )
    async with PostgresKernelUnitOfWork(e) as u:
        row = await u.management.get_feed(
            management_scope("binance-usdm", t.identity.netting_domain.account_id)
        )
        if fault is None:
            assert row["connection_state"] == "ready" and row["health_reason"] is None
            assert row["persisted_watermark"] == row["applied_watermark"] == 1
        else:
            assert (
                row["connection_state"] == "gap"
                and row["health_reason"] == "management_stream_protocol_invalid"
            )
            assert row["persisted_watermark"] == 1 and row["applied_watermark"] == 0
    assert source.acknowledged == [("clock-race", 1)]
    assert source.restarts == ([] if fault is None else ["clock-race"])
    assert result.status == (
        "management_feed_persisted" if fault is None else "management_feed_recovering"
    )
    assert result.detail == (
        None if fault is None else "management_stream_protocol_invalid"
    )


@pytest.mark.asyncio
async def test_deterministic_apply_failure_is_durable_bounded_and_ordered(
    head_template_engine,
):
    import sqlalchemy as sa

    from src.trading_kernel.domain.reducer import InvalidLifecycleTransition
    from src.trading_kernel.infrastructure.pg_models import (
        failure_diagnostics,
        trade_aggregates,
    )
    from tests.trading_kernel.support.lifecycle import (
        reach_position_protected,
        registered_sor_long_ticket,
    )

    e = head_template_engine
    t = registered_sor_long_ticket()
    await reach_position_protected(e, t)
    d = t.identity.netting_domain
    scope = f"binance-usdm:{d.account_id}"
    raw = {
        "e": "ORDER_TRADE_UPDATE",
        "E": 5000,
        "T": 5000,
        "o": {
            "s": "BTCUSDT",
            "c": "external-test",
            "S": "SELL",
            "o": "LIMIT",
            "f": "GTC",
            "q": "0.001",
            "p": "65000",
            "sp": "0",
            "x": "CANCELED",
            "X": "CANCELED",
            "i": 123,
            "z": "0",
            "ps": "LONG",
            "cp": False,
            "R": False,
            "wt": "CONTRACT_PRICE",
            "pP": False,
            "pm": "NONE",
            "V": "NONE",
            "gtd": 0,
            "O": 5000,
        },
    }
    calls = []
    for now in [5100, 5200, 10100, 10200, 40100, 100000]:
        async with PostgresKernelUnitOfWork(e) as u:
            if now == 5100:
                await u.management.start_feed(
                    scope_key=scope,
                    epoch_id="failure-epoch",
                    worker_id="test",
                    runtime_commit="a" * 40,
                    now_ms=5000,
                )

            async def fail(ticket_id, evidence, *, attempt_at=now):
                calls.append(attempt_at)
                await u._connection.execute(
                    sa.update(trade_aggregates)
                    .where(trade_aggregates.c.ticket_id == ticket_id)
                    .values(protected_qty=0)
                )
                raise InvalidLifecycleTransition("test deterministic failure")

            await u.management.persist_stream_batch(
                scope_key=scope,
                epoch_id="failure-epoch",
                events=[{"sequence": 1, "received_at_ms": 5001, "payload": raw}],
                connected_at_ms=5000,
                now_ms=now,
                apply_observer=fail,
                account_id=d.account_id,
            )
            feed = await u.management.get_feed(scope)
            assert feed["persisted_watermark"] == 1 and feed["applied_watermark"] == 0
            assert not await u.management.feed_ready(scope, now_ms=now)
    assert calls == [5100, 10100, 40100]
    async with PostgresKernelUnitOfWork(e) as u:
        with pytest.raises(ValueError, match="unapplied"):
            await u.management.start_feed(
                scope_key=scope,
                epoch_id="new-epoch",
                worker_id="test",
                runtime_commit="b" * 40,
                now_ms=120000,
            )
    async with PostgresKernelUnitOfWork(e) as u:
        applied = []

        async def repaired(ticket_id, evidence):
            applied.append(evidence.evidence_id)
            return True

        await u.management.persist_stream_batch(
            scope_key=scope,
            epoch_id="failure-epoch",
            events=[],
            connected_at_ms=5000,
            now_ms=120000,
            apply_observer=repaired,
            account_id=d.account_id,
            application_runtime_commit="b" * 40,
        )
        feed = await u.management.get_feed(scope)
        assert feed["applied_watermark"] == 1 and len(applied) == 1

    async with e.connect() as c:
        rows = (
            (
                await c.execute(
                    sa.select(failure_diagnostics).where(
                        failure_diagnostics.c.stage == "management_stream_apply"
                    )
                )
            )
            .mappings()
            .all()
        )
        assert len(rows) == 4
        assert sum(x["reason_code"] == "resolved" for x in rows) == 1
        assert (
            await c.scalar(
                sa.select(trade_aggregates.c.protected_qty).where(
                    trade_aggregates.c.ticket_id == t.identity.ticket_id
                )
            )
            == t.quantity
        )


@pytest.mark.asyncio
async def test_flat_cancellations_apply_in_order_without_takeover_or_budget_release(
    head_template_engine,
):
    import sqlalchemy as sa

    from src.trading_kernel.application.observe_trade_management import (
        observe_trade_management,
    )
    from src.trading_kernel.infrastructure.pg_models import (
        budget_reservations,
        management_feed_current,
        trade_aggregates,
    )
    from tests.trading_kernel.support.lifecycle import (
        reach_position_protected,
        registered_sor_long_ticket,
    )

    e = head_template_engine
    t = registered_sor_long_ticket()
    await reach_position_protected(e, t)
    d = t.identity.netting_domain
    scope = f"binance-usdm:{d.account_id}"
    raw = {
        "e": "ORDER_TRADE_UPDATE",
        "E": 5000,
        "T": 5000,
        "o": {
            "s": "BTCUSDT",
            "c": "external-test",
            "S": "SELL",
            "o": "LIMIT",
            "f": "GTC",
            "q": "0.001",
            "p": "65000",
            "sp": "0",
            "x": "CANCELED",
            "X": "CANCELED",
            "i": 123,
            "z": "0",
            "ps": "LONG",
            "cp": False,
            "R": False,
            "wt": "CONTRACT_PRICE",
            "pP": False,
            "pm": "NONE",
            "V": "NONE",
            "gtd": 0,
            "O": 5000,
        },
    }
    async with PostgresKernelUnitOfWork(e) as u:
        await u._connection.execute(
            sa.update(trade_aggregates)
            .where(trade_aggregates.c.ticket_id == t.identity.ticket_id)
            .values(position_qty=0, status="reconciliation_pending")
        )
        await u.management.start_feed(
            scope_key=scope,
            epoch_id="flat-epoch",
            worker_id="test",
            runtime_commit="a" * 40,
            now_ms=5000,
        )
        # Synthetic earlier prefix, no historical production cursor is mutated.
        await u._connection.execute(
            sa.update(management_feed_current)
            .where(management_feed_current.c.scope_key == scope)
            .values(persisted_watermark=161, applied_watermark=161)
        )
        before = await u._connection.scalar(
            sa.select(sa.func.count())
            .select_from(budget_reservations)
            .where(budget_reservations.c.status == "active")
        )
        calls = []

        async def observer(ticket_id, evidence):
            await observe_trade_management(
                u, ticket_id=ticket_id, evidence=evidence, now_ms=5100
            )
            calls.append(evidence.terms.exchange_order_id)
            return True

        second = {**raw, "o": {**raw["o"], "i": 124, "c": "external-second"}}
        await u.management.persist_stream_batch(
            scope_key=scope,
            epoch_id="flat-epoch",
            events=[
                {"sequence": 162, "received_at_ms": 5001, "payload": raw},
                {"sequence": 163, "received_at_ms": 5002, "payload": second},
            ],
            connected_at_ms=5000,
            now_ms=5100,
            apply_observer=observer,
            account_id=d.account_id,
        )
        assert calls == ["123", "124"]
        feed = await u.management.get_feed(scope)
        assert feed["applied_watermark"] == 163 and feed["connection_state"] == "ready"
        a = await u.aggregates.get(t.identity.ticket_id)
        assert (
            a.management_mode.value == "AUTO"
            and a.status.value == "reconciliation_pending"
        )
        assert (
            await u._connection.scalar(
                sa.select(sa.func.count())
                .select_from(budget_reservations)
                .where(budget_reservations.c.status == "active")
            )
            == before
        )


@pytest.mark.asyncio
async def test_failed_apply_rolls_back_uow_notice_and_evidence_buffers(head_template_engine):
    import sqlalchemy as sa

    from src.trading_kernel.application.observe_trade_management import (
        observe_trade_management,
    )
    from src.trading_kernel.domain.reducer import InvalidLifecycleTransition
    from src.trading_kernel.infrastructure.pg_models import notice_outbox
    from tests.trading_kernel.support.lifecycle import (
        reach_position_protected,
        registered_sor_long_ticket,
    )
    from tests.trading_kernel.support.manual_management import app_evidence
    e=head_template_engine;t=registered_sor_long_ticket();await reach_position_protected(e,t)
    d=t.identity.netting_domain;scope=f'binance-usdm:{d.account_id}'
    raw={'e':'ORDER_TRADE_UPDATE','E':5000,'T':5000,'o':{'s':'BTCUSDT','c':'external-test','S':'SELL','o':'LIMIT','f':'GTC','q':'0.001','p':'65000','sp':'0','x':'NEW','X':'NEW','i':123,'z':'0','ps':'LONG','cp':False,'R':False,'wt':'CONTRACT_PRICE','pP':False,'pm':'NONE','V':'NONE','gtd':0,'O':5000}}
    async with PostgresKernelUnitOfWork(e) as u:
        await u.management.start_feed(scope_key=scope,epoch_id='buffer-epoch',worker_id='w',runtime_commit='a'*40,now_ms=5000)
        async def fail(ticket_id,item):
            await observe_trade_management(u,ticket_id=ticket_id,evidence=app_evidence(t),now_ms=5100)
            raise InvalidLifecycleTransition('failure after real management reduction')
        await u.management.persist_stream_batch(scope_key=scope,epoch_id='buffer-epoch',events=[{'sequence':1,'received_at_ms':5001,'payload':raw}],connected_at_ms=5000,now_ms=5100,apply_observer=fail,account_id=d.account_id)
        assert u._notice_changes=={}
        assert u.management.new_evidence=={}
        assert (await u.aggregates.get(t.identity.ticket_id)).management_mode.value=='AUTO'
    async with e.connect() as c:
        assert await c.scalar(sa.select(sa.func.count()).select_from(notice_outbox).where(notice_outbox.c.kind=='takeover'))==0


@pytest.mark.asyncio
async def test_deferred_observer_cannot_commit_partial_side_effects(head_template_engine):
    import sqlalchemy as sa

    from src.trading_kernel.infrastructure.pg_models import trade_aggregates
    from tests.trading_kernel.support.lifecycle import (
        reach_position_protected,
        registered_sor_long_ticket,
    )
    e=head_template_engine;t=registered_sor_long_ticket();await reach_position_protected(e,t)
    d=t.identity.netting_domain;scope=f'binance-usdm:{d.account_id}'
    raw={'e':'ORDER_TRADE_UPDATE','E':5000,'T':5000,'o':{'s':'BTCUSDT','c':'external-test','S':'SELL','o':'LIMIT','f':'GTC','q':'0.001','p':'65000','sp':'0','x':'NEW','X':'NEW','i':123,'z':'0','ps':'LONG','cp':False,'R':False,'wt':'CONTRACT_PRICE','pP':False,'pm':'NONE','V':'NONE','gtd':0,'O':5000}}
    async with PostgresKernelUnitOfWork(e) as u:
        await u.management.start_feed(scope_key=scope,epoch_id='deferred-epoch',worker_id='w',runtime_commit='a'*40,now_ms=5000)
        async def defer(ticket_id,item):
            await u._connection.execute(sa.update(trade_aggregates).where(trade_aggregates.c.ticket_id==ticket_id).values(protected_qty=0))
            return False
        await u.management.persist_stream_batch(scope_key=scope,epoch_id='deferred-epoch',events=[{'sequence':1,'received_at_ms':5001,'payload':raw}],connected_at_ms=5000,now_ms=5100,apply_observer=defer,account_id=d.account_id)
        assert (await u.aggregates.get(t.identity.ticket_id)).protected_qty==t.quantity
        assert (await u.management.get_feed(scope))['applied_watermark']==0


@pytest.mark.asyncio
async def test_reconnect_persists_new_epoch_while_old_application_blocked_and_survives_restart(head_template_engine):
    import sqlalchemy as sa

    from src.trading_kernel.infrastructure.pg_models import management_stream_events
    from src.trading_kernel.interfaces.management_feed_worker import (
        management_scope,
        persist_management_feed_once,
    )
    from tests.trading_kernel.support.lifecycle import (
        reach_position_protected,
        registered_sor_long_ticket,
    )
    e=head_template_engine;t=registered_sor_long_ticket();await reach_position_protected(e,t)
    # An unrecognized regular order intentionally defers attribution, preserving
    # a real unapplied head event while the new connection keeps receiving.
    raw={'e':'ORDER_TRADE_UPDATE','E':5000,'T':5000,'o':{'s':'BTCUSDT','c':'external','S':'SELL','o':'LIMIT','f':'GTC',
        'q':'0.001','p':'65000','sp':'0','x':'NEW','X':'NEW','i':9001,'z':'0','ps':'LONG','cp':False,'R':False,
        'wt':'CONTRACT_PRICE','pP':False,'pm':'NONE','V':'NONE','gtd':0,'O':5000}}
    scope=management_scope('binance-usdm',t.identity.netting_domain.account_id)
    async with PostgresKernelUnitOfWork(e) as u:
        await u.management.start_feed(scope_key=scope,epoch_id='old-blocked',worker_id='receiver',runtime_commit='kernel-test-head',now_ms=5000)
        await u.management.persist_stream_batch(scope_key=scope,epoch_id='old-blocked',events=[{'sequence':1,'received_at_ms':5001,'payload':raw}],connected_at_ms=5000,now_ms=5100,account_id=t.identity.netting_domain.account_id)
    class Source:
        def __init__(self,epoch='new-receiving'):
            self.epoch=epoch;self.acks=[]
        def management_feed_batches(self):
            return [{'venue_id':'binance-usdm','account_id':t.identity.netting_domain.account_id,'epoch_id':self.epoch,
                'events':[{'sequence':1,'received_at_ms':6001,'payload':{**raw,'E':6000,'T':6000,'o':{**raw['o'],'i':9002,'O':6000}}}],
                'connected_at_ms':6000,'connection_observed_at_ms':7000,'gap_reason':None,'backlog_pending':False}]
        def acknowledge_management_events(self,epoch,watermark):self.acks.append((epoch,watermark))
    source=Source()
    result=await persist_management_feed_once(lambda:PostgresKernelUnitOfWork(e),source,worker_id='receiver',runtime_commit='kernel-test-head',now_ms=7000,clock_ms=lambda:7000)
    assert result.status=='management_feed_recovering'
    assert source.acks==[('new-receiving',1)]
    async with PostgresKernelUnitOfWork(e) as u:
        feed=await u.management.get_feed(scope)
        assert feed['epoch_id']=='old-blocked' and feed['applied_watermark']==0
        count=await u._require_connection().scalar(sa.select(sa.func.count()).select_from(management_stream_events).where(management_stream_events.c.epoch_id=='new-receiving'))
        assert count==1
    # Drop receiver memory entirely. Pending epoch can still be found from PG.
    async with PostgresKernelUnitOfWork(e) as u:
        pending=await u.management.next_received_epoch(scope,exclude_epoch='old-blocked')
        assert pending['epoch_id']=='new-receiving' and pending['persisted_watermark']==1

    from src.trading_kernel.domain.events import ExternalFlatDetected
    from src.trading_kernel.domain.reducer import reduce_event
    async with PostgresKernelUnitOfWork(e) as u:
        a=await u.aggregates.get_for_update(t.identity.ticket_id)
        event=ExternalFlatDetected(event_id='flat-for-recovery',ticket_id=t.identity.ticket_id,
            sequence=a.last_event_sequence+1,occurred_at_ms=8000)
        await u.commit_reduction(event=event,reduction=reduce_event(a,event),expected_version=a.version)
    class RestartedSource:
        def management_feed_batches(self):
            return [{'venue_id':'binance-usdm','account_id':t.identity.netting_domain.account_id,'epoch_id':'after-process-restart',
                'events':[],'connected_at_ms':9000,'connection_observed_at_ms':9000,'gap_reason':None,'backlog_pending':False}]
        def acknowledge_management_events(self,*args):pass
    restarted=RestartedSource()
    for now in (9000,10000):
        await persist_management_feed_once(lambda:PostgresKernelUnitOfWork(e),restarted,worker_id='receiver',runtime_commit='kernel-test-head',now_ms=now,clock_ms=lambda now=now:now)
    async with PostgresKernelUnitOfWork(e) as u:
        feed=await u.management.get_feed(scope)
        assert feed['epoch_id']=='after-process-restart'
        assert await u.management.feed_ready(scope,now_ms=10000)
        for epoch in ('old-blocked','new-receiving'):
            receipt=await u.management.received_epoch(scope,epoch)
            assert receipt['completed_at_ms'] is not None
        assert await u._require_connection().scalar(sa.select(sa.func.count()).select_from(management_stream_events))==2


@pytest.mark.asyncio
async def test_new_epoch_cannot_overtake_unflushed_pages_of_closed_receiver(head_template_engine):
    from collections import deque
    from types import SimpleNamespace

    from src.trading_kernel.domain.events import ExternalFlatDetected
    from src.trading_kernel.domain.reducer import reduce_event
    from src.trading_kernel.infrastructure.venue_adapter import CcxtVenueAdapter
    from src.trading_kernel.interfaces.management_feed_worker import (
        management_scope,
        persist_management_feed_once,
    )
    from tests.trading_kernel.support.lifecycle import (
        reach_position_protected,
        registered_sor_long_ticket,
    )
    e=head_template_engine;t=registered_sor_long_ticket();await reach_position_protected(e,t)
    async with PostgresKernelUnitOfWork(e) as u:
        a=await u.aggregates.get_for_update(t.identity.ticket_id)
        ev=ExternalFlatDetected(event_id='flat',ticket_id=t.identity.ticket_id,sequence=a.last_event_sequence+1,occurred_at_ms=4000)
        await u.commit_reduction(event=ev,reduction=reduce_event(a,ev),expected_version=a.version)
    raw={'e':'ORDER_TRADE_UPDATE','E':5000,'T':5000,'o':{'s':'BTCUSDT','c':'external','S':'SELL','o':'LIMIT','f':'GTC','q':'0.001','p':'65000','sp':'0','x':'CANCELED','X':'CANCELED','i':9001,'z':'0','ps':'LONG','cp':False,'R':False,'wt':'CONTRACT_PRICE','pP':False,'pm':'NONE','V':'NONE','gtd':0,'O':5000}}
    exchange=SimpleNamespace(management_closed_batches=deque([{'epoch_id':'paged-old','events':deque({'sequence':i,'received_at_ms':5001,'payload':{**raw,'o':{**raw['o'],'i':9000+i}}} for i in range(1,131)), 'connected_at_ms':5000,'gap_reason':None}]),
        management_epoch_id='live-new',management_pending_events=deque([{'sequence':1,'received_at_ms':6001,'payload':{**raw,'o':{**raw['o'],'i':9999}}}]),
        _management_connected_ms=6000,management_receive_gap=None)
    receiver_clock=[7000]
    source=CcxtVenueAdapter(exchanges={('binance-usdm',t.identity.netting_domain.account_id):exchange},clock_ms=lambda:receiver_clock[0])
    scope=management_scope('binance-usdm',t.identity.netting_domain.account_id)
    await persist_management_feed_once(lambda:PostgresKernelUnitOfWork(e),source,worker_id='receiver',runtime_commit='kernel-test-head',now_ms=7000,clock_ms=lambda:7000)
    async with PostgresKernelUnitOfWork(e) as u:
        feed=await u.management.get_feed(scope)
        assert feed['epoch_id']=='paged-old' and feed['applied_watermark']==128
        assert not await u.management.feed_ready(scope,now_ms=7000)
        assert (await u.management.received_epoch(scope,'live-new'))['persisted_watermark']==1
    receiver_clock[0]=8000
    await persist_management_feed_once(lambda:PostgresKernelUnitOfWork(e),source,worker_id='receiver',runtime_commit='kernel-test-head',now_ms=8000,clock_ms=lambda:8000)
    async with PostgresKernelUnitOfWork(e) as u:
        assert (await u.management.get_feed(scope))['epoch_id']=='live-new'
        assert (await u.management.received_epoch(scope,'paged-old'))['completed_at_ms']==8000
        assert await u.management.feed_ready(scope,now_ms=8000)


@pytest.mark.asyncio
async def test_epoch_switch_checks_received_tail_not_only_old_applied_row(head_template_engine):
    async with PostgresKernelUnitOfWork(head_template_engine) as u:
        await u.management.start_feed(scope_key='scope',epoch_id='old',worker_id='receiver',runtime_commit='a'*40,now_ms=1000)
        await u.management.persist_received_batch(scope_key='scope',epoch_id='old',events=[{'sequence':1,'received_at_ms':1100,'payload':{'e':'unknown'}}],connected_at_ms=1000,now_ms=1200,worker_id='receiver')
        with pytest.raises(ValueError,match='unapplied'):
            await u.management.start_feed(scope_key='scope',epoch_id='new',worker_id='receiver',runtime_commit='a'*40,now_ms=1300)


@pytest.mark.asyncio
async def test_old_epoch_replay_never_fills_real_disconnect_interval(head_template_engine):
    from src.trading_kernel.interfaces.management_feed_worker import (
        management_scope,
        persist_management_feed_once,
    )
    from tests.trading_kernel.support.lifecycle import (
        reach_position_protected,
        registered_sor_long_ticket,
    )
    e=head_template_engine;t=registered_sor_long_ticket();await reach_position_protected(e,t)
    scope=management_scope('binance-usdm',t.identity.netting_domain.account_id)
    async with PostgresKernelUnitOfWork(e) as u:
        await u.management.start_feed(scope_key=scope,epoch_id='before-disconnect',worker_id='receiver',runtime_commit='kernel-test-head',now_ms=1000)
        await u.management.persist_stream_batch(scope_key=scope,epoch_id='before-disconnect',events=[],connected_at_ms=1000,now_ms=1100)
    class Source:
        def management_feed_batches(self):
            return [{'venue_id':'binance-usdm','account_id':t.identity.netting_domain.account_id,'epoch_id':'after-restart','events':[],
                'connected_at_ms':10000,'connection_observed_at_ms':10000,'gap_reason':None,'backlog_pending':False}]
        def acknowledge_management_events(self,*args):pass
    await persist_management_feed_once(lambda:PostgresKernelUnitOfWork(e),Source(),worker_id='receiver',runtime_commit='kernel-test-head',now_ms=10000,clock_ms=lambda:10000)
    async with PostgresKernelUnitOfWork(e) as u:
        assert not await u.management.continuity_covers(scope,2000,9000)
        assert await u.management.continuity_covers(scope,10000,10000)
        import sqlalchemy as sa

        from src.trading_kernel.infrastructure.pg_models import (
            management_coverage_events,
        )
        ended=(await u._require_connection().execute(sa.select(management_coverage_events.c.to_ms).where(management_coverage_events.c.epoch_id=='before-disconnect',management_coverage_events.c.kind=='epoch_closed'))).scalar_one()
        assert ended==1100
