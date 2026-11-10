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
    )
    assert result.status == "runtime_fenced" and source.acknowledged == []
    result = await persist_management_feed_once(
        lambda: PostgresKernelUnitOfWork(e),
        source,
        worker_id="receiver",
        runtime_commit="kernel-test-head",
        now_ms=6000,
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
        )
    assert source.acknowledged == []
