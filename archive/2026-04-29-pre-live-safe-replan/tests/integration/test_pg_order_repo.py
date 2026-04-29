"""Integration tests for PgOrderRepository against real PostgreSQL."""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from src.domain.models import Order, OrderStatus, OrderType, OrderRole, Direction


def make_order(**overrides) -> Order:
    now = int(datetime.now(timezone.utc).timestamp() * 1000)
    defaults = dict(
        id=str(uuid4()),
        signal_id=str(uuid4()),
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal("0.001"),
        filled_qty=Decimal("0"),
        status=OrderStatus.OPEN,
        created_at=now,
        updated_at=now,
    )
    defaults.update(overrides)
    return Order(**defaults)


# ------------------------------------------------------------------
# 1. save / get_order round trip
# ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_save_get_order_round_trip(order_repo):
    order = make_order(
        exchange_order_id="ex-123",
        price=Decimal("65000.50"),
        trigger_price=Decimal("64000.00"),
        average_exec_price=Decimal("65001.00"),
        filled_qty=Decimal("0.001"),
        reduce_only=False,
        parent_order_id=None,
        oco_group_id=None,
        exit_reason=None,
        filled_at=None,
    )
    await order_repo.save(order)

    fetched = await order_repo.get_order(order.id)
    assert fetched is not None
    assert fetched.id == order.id
    assert fetched.signal_id == order.signal_id
    assert fetched.exchange_order_id == "ex-123"
    assert fetched.symbol == "BTC/USDT:USDT"
    assert fetched.direction == Direction.LONG
    assert fetched.order_type == OrderType.MARKET
    assert fetched.order_role == OrderRole.ENTRY
    assert fetched.price == Decimal("65000.50")
    assert fetched.trigger_price == Decimal("64000.00")
    assert fetched.requested_qty == Decimal("0.001")
    assert fetched.filled_qty == Decimal("0.001")
    assert fetched.average_exec_price == Decimal("65001.00")
    assert fetched.status == OrderStatus.OPEN
    assert fetched.created_at == order.created_at
    assert fetched.updated_at == order.updated_at


# ------------------------------------------------------------------
# 2. save_batch round trip
# ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_save_batch_round_trip(order_repo):
    orders = [make_order(symbol="BTC/USDT:USDT") for _ in range(3)]
    await order_repo.save_batch(orders)

    for o in orders:
        fetched = await order_repo.get_order(o.id)
        assert fetched is not None
        assert fetched.id == o.id


# ------------------------------------------------------------------
# 3. get_orders with symbol / status / order_role / limit / offset
# ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_orders_filtering_and_pagination(order_repo):
    sig = str(uuid4())
    now = int(datetime.now(timezone.utc).timestamp() * 1000)

    orders = [
        make_order(signal_id=sig, symbol="BTC/USDT:USDT", status=OrderStatus.OPEN, order_role=OrderRole.ENTRY, created_at=now + i)
        for i in range(4)
    ] + [
        make_order(signal_id=sig, symbol="ETH/USDT:USDT", status=OrderStatus.FILLED, order_role=OrderRole.SL, created_at=now + 10 + i)
        for i in range(3)
    ]
    await order_repo.save_batch(orders)

    # Filter by symbol
    result = await order_repo.get_orders(symbol="BTC/USDT:USDT")
    assert result["total"] == 4
    assert all(o.symbol == "BTC/USDT:USDT" for o in result["items"])

    # Filter by status
    result = await order_repo.get_orders(status=OrderStatus.FILLED)
    assert result["total"] == 3
    assert all(o.status == OrderStatus.FILLED for o in result["items"])

    # Filter by order_role
    result = await order_repo.get_orders(order_role=OrderRole.ENTRY)
    assert result["total"] == 4
    assert all(o.order_role == OrderRole.ENTRY for o in result["items"])

    # Combined filter
    result = await order_repo.get_orders(symbol="ETH/USDT:USDT", status=OrderStatus.FILLED)
    assert result["total"] == 3

    # Pagination
    result = await order_repo.get_orders(symbol="BTC/USDT:USDT", limit=2, offset=0)
    assert len(result["items"]) == 2
    assert result["total"] == 4
    result2 = await order_repo.get_orders(symbol="BTC/USDT:USDT", limit=2, offset=2)
    assert len(result2["items"]) == 2


# ------------------------------------------------------------------
# 4. get_orders_by_signal_ids
# ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_orders_by_signal_ids(order_repo):
    sig_a = str(uuid4())
    sig_b = str(uuid4())
    now = int(datetime.now(timezone.utc).timestamp() * 1000)

    orders = [
        make_order(signal_id=sig_a, order_role=OrderRole.ENTRY, created_at=now),
        make_order(signal_id=sig_a, order_role=OrderRole.TP1, created_at=now + 1),
        make_order(signal_id=sig_a, order_role=OrderRole.SL, created_at=now + 2),
        make_order(signal_id=sig_b, order_role=OrderRole.ENTRY, created_at=now + 10),
        make_order(signal_id=sig_b, order_role=OrderRole.TP1, created_at=now + 11),
    ]
    await order_repo.save_batch(orders)

    # Both signals
    result = await order_repo.get_orders_by_signal_ids([sig_a, sig_b])
    assert result["total"] == 5
    assert len(result["orders"]) == 5

    # Single signal
    result = await order_repo.get_orders_by_signal_ids([sig_a])
    assert result["total"] == 3

    # With order_role filter
    result = await order_repo.get_orders_by_signal_ids([sig_a, sig_b], order_role="ENTRY")
    assert result["total"] == 2
    assert all(o.order_role == OrderRole.ENTRY for o in result["orders"])

    # Pagination
    result = await order_repo.get_orders_by_signal_ids([sig_a, sig_b], page=1, page_size=2)
    assert len(result["orders"]) == 2
    assert result["total"] == 5
    result2 = await order_repo.get_orders_by_signal_ids([sig_a, sig_b], page=2, page_size=2)
    assert len(result2["orders"]) == 2

    # Empty signal_ids
    result = await order_repo.get_orders_by_signal_ids([])
    assert result["total"] == 0
    assert result["orders"] == []


# ------------------------------------------------------------------
# 5. get_orders_by_role with optional signal_id and symbol
# ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_orders_by_role(order_repo):
    sig = str(uuid4())
    now = int(datetime.now(timezone.utc).timestamp() * 1000)

    orders = [
        make_order(signal_id=sig, symbol="BTC/USDT:USDT", order_role=OrderRole.ENTRY, created_at=now),
        make_order(signal_id=sig, symbol="BTC/USDT:USDT", order_role=OrderRole.TP1, created_at=now + 1),
        make_order(signal_id=sig, symbol="BTC/USDT:USDT", order_role=OrderRole.SL, created_at=now + 2),
        make_order(signal_id=str(uuid4()), symbol="ETH/USDT:USDT", order_role=OrderRole.ENTRY, created_at=now + 10),
    ]
    await order_repo.save_batch(orders)

    # By role only
    result = await order_repo.get_orders_by_role(OrderRole.ENTRY)
    assert len(result) == 2
    assert all(o.order_role == OrderRole.ENTRY for o in result)

    # With signal_id
    result = await order_repo.get_orders_by_role(OrderRole.ENTRY, signal_id=sig)
    assert len(result) == 1
    assert result[0].signal_id == sig

    # With symbol
    result = await order_repo.get_orders_by_role(OrderRole.ENTRY, symbol="ETH/USDT:USDT")
    assert len(result) == 1
    assert result[0].symbol == "ETH/USDT:USDT"

    # With signal_id + symbol
    result = await order_repo.get_orders_by_role(OrderRole.TP1, signal_id=sig, symbol="BTC/USDT:USDT")
    assert len(result) == 1


# ------------------------------------------------------------------
# 6. get_order_chain
# ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_order_chain(order_repo):
    sig = str(uuid4())
    entry_id = str(uuid4())
    now = int(datetime.now(timezone.utc).timestamp() * 1000)

    entry = make_order(id=entry_id, signal_id=sig, order_role=OrderRole.ENTRY, created_at=now)
    tp1 = make_order(signal_id=sig, order_role=OrderRole.TP1, parent_order_id=entry_id, created_at=now + 1)
    tp2 = make_order(signal_id=sig, order_role=OrderRole.TP2, parent_order_id=entry_id, created_at=now + 2)
    sl = make_order(signal_id=sig, order_role=OrderRole.SL, parent_order_id=entry_id, created_at=now + 3)
    await order_repo.save_batch([entry, tp1, tp2, sl])

    chain = await order_repo.get_order_chain(sig)
    assert len(chain["entry"]) == 1
    assert chain["entry"][0].id == entry_id
    assert len(chain["tps"]) == 2
    assert {o.order_role for o in chain["tps"]} == {OrderRole.TP1, OrderRole.TP2}
    assert len(chain["sl"]) == 1
    assert chain["sl"][0].order_role == OrderRole.SL


# ------------------------------------------------------------------
# 7. get_order_chain_by_order_id
# ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_order_chain_by_order_id(order_repo):
    entry_id = str(uuid4())
    sig = str(uuid4())
    now = int(datetime.now(timezone.utc).timestamp() * 1000)

    entry = make_order(id=entry_id, signal_id=sig, order_role=OrderRole.ENTRY, created_at=now)
    tp1 = make_order(signal_id=sig, order_role=OrderRole.TP1, parent_order_id=entry_id, created_at=now + 1)
    sl = make_order(signal_id=sig, order_role=OrderRole.SL, parent_order_id=entry_id, created_at=now + 2)
    await order_repo.save_batch([entry, tp1, sl])

    # From entry order
    chain = await order_repo.get_order_chain_by_order_id(entry_id)
    assert len(chain) == 3
    assert chain[0].id == entry_id
    child_roles = {o.order_role for o in chain[1:]}
    assert child_roles == {OrderRole.TP1, OrderRole.SL}

    # From child order
    chain = await order_repo.get_order_chain_by_order_id(tp1.id)
    assert len(chain) == 3
    assert chain[0].id == entry_id

    # Non-existent order
    chain = await order_repo.get_order_chain_by_order_id(str(uuid4()))
    assert chain == []


# ------------------------------------------------------------------
# 8. get_oco_group
# ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_oco_group(order_repo):
    oco_id = str(uuid4())
    now = int(datetime.now(timezone.utc).timestamp() * 1000)

    orders = [
        make_order(oco_group_id=oco_id, order_role=OrderRole.TP1, created_at=now),
        make_order(oco_group_id=oco_id, order_role=OrderRole.SL, created_at=now + 1),
    ]
    await order_repo.save_batch(orders)

    group = await order_repo.get_oco_group(oco_id)
    assert len(group) == 2
    assert {o.order_role for o in group} == {OrderRole.TP1, OrderRole.SL}

    # Non-existent group
    group = await order_repo.get_oco_group(str(uuid4()))
    assert group == []


# ------------------------------------------------------------------
# 9. get_order_tree
# ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_order_tree(order_repo):
    entry_id = str(uuid4())
    sig = str(uuid4())
    now = int(datetime.now(timezone.utc).timestamp() * 1000)

    entry = make_order(id=entry_id, signal_id=sig, order_role=OrderRole.ENTRY, created_at=now)
    tp1 = make_order(signal_id=sig, order_role=OrderRole.TP1, parent_order_id=entry_id, created_at=now + 1)
    sl = make_order(signal_id=sig, order_role=OrderRole.SL, parent_order_id=entry_id, created_at=now + 2)
    await order_repo.save_batch([entry, tp1, sl])

    tree = await order_repo.get_order_tree(symbol="BTC/USDT:USDT", days=1)
    assert tree["total_count"] >= 1
    assert len(tree["items"]) >= 1

    root_item = tree["items"][0]
    assert root_item["level"] == 0
    assert root_item["has_children"] is True
    assert root_item["order"]["order_id"] == entry_id
    assert len(root_item["children"]) == 2

    child_roles = {c["order"]["order_role"] for c in root_item["children"]}
    assert child_roles == {"TP1", "SL"}

    # With symbol filter returning empty
    tree = await order_repo.get_order_tree(symbol="DOGE/USDT:USDT", days=1)
    assert tree["total_count"] == 0
    assert tree["items"] == []


# ------------------------------------------------------------------
# 10. delete_orders_batch
# ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_delete_orders_batch(order_repo):
    entry_id = str(uuid4())
    sig = str(uuid4())
    now = int(datetime.now(timezone.utc).timestamp() * 1000)

    standalone = make_order(status=OrderStatus.CANCELED, created_at=now)
    entry = make_order(id=entry_id, signal_id=sig, order_role=OrderRole.ENTRY, status=OrderStatus.OPEN, created_at=now)
    tp1 = make_order(signal_id=sig, order_role=OrderRole.TP1, parent_order_id=entry_id, status=OrderStatus.OPEN, created_at=now + 1)
    sl = make_order(signal_id=sig, order_role=OrderRole.SL, parent_order_id=entry_id, status=OrderStatus.OPEN, created_at=now + 2)
    await order_repo.save_batch([standalone, entry, tp1, sl])

    # Delete standalone (no exchange cancel needed)
    result = await order_repo.delete_orders_batch([standalone.id], cancel_on_exchange=False)
    assert result["deleted_count"] == 1
    assert standalone.id in result["deleted_from_db"]
    assert await order_repo.get_order(standalone.id) is None

    # Delete entry cascades to children
    result = await order_repo.delete_orders_batch([entry_id], cancel_on_exchange=False)
    assert result["deleted_count"] == 3
    assert set(result["deleted_from_db"]) == {entry_id, tp1.id, sl.id}
    assert await order_repo.get_order(entry_id) is None
    assert await order_repo.get_order(tp1.id) is None
    assert await order_repo.get_order(sl.id) is None

    # Empty list raises ValueError
    with pytest.raises(ValueError):
        await order_repo.delete_orders_batch([], cancel_on_exchange=False)


# ------------------------------------------------------------------
# 11. Unique exchange_order_id constraint
# ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_unique_exchange_order_id_constraint(pg_session_maker):
    now = int(datetime.now(timezone.utc).timestamp() * 1000)
    from src.infrastructure.pg_models import PGOrderORM

    orm1 = PGOrderORM(
        id=str(uuid4()),
        signal_id=str(uuid4()),
        symbol="BTC/USDT:USDT",
        direction="LONG",
        order_type="MARKET",
        order_role="ENTRY",
        requested_qty=Decimal("0.001"),
        filled_qty=Decimal("0"),
        status="OPEN",
        exchange_order_id="dup-exchange-id",
        created_at=now,
        updated_at=now,
    )
    async with pg_session_maker() as session:
        session.add(orm1)
        await session.commit()

    orm2 = PGOrderORM(
        id=str(uuid4()),
        signal_id=str(uuid4()),
        symbol="ETH/USDT:USDT",
        direction="SHORT",
        order_type="LIMIT",
        order_role="SL",
        requested_qty=Decimal("0.01"),
        filled_qty=Decimal("0"),
        status="OPEN",
        exchange_order_id="dup-exchange-id",
        created_at=now + 1,
        updated_at=now + 1,
    )
    with pytest.raises(IntegrityError):
        async with pg_session_maker() as session:
            session.add(orm2)
            await session.commit()


# ------------------------------------------------------------------
# 12. CheckConstraint violations
# ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_check_constraint_invalid_direction(pg_session_maker):
    from src.infrastructure.pg_models import PGOrderORM

    now = int(datetime.now(timezone.utc).timestamp() * 1000)
    orm = PGOrderORM(
        id=str(uuid4()),
        signal_id=str(uuid4()),
        symbol="BTC/USDT:USDT",
        direction="INVALID",
        order_type="MARKET",
        order_role="ENTRY",
        requested_qty=Decimal("0.001"),
        filled_qty=Decimal("0"),
        status="OPEN",
        created_at=now,
        updated_at=now,
    )
    with pytest.raises(IntegrityError):
        async with pg_session_maker() as session:
            session.add(orm)
            await session.commit()


@pytest.mark.asyncio
async def test_check_constraint_invalid_order_role(pg_session_maker):
    from src.infrastructure.pg_models import PGOrderORM

    now = int(datetime.now(timezone.utc).timestamp() * 1000)
    orm = PGOrderORM(
        id=str(uuid4()),
        signal_id=str(uuid4()),
        symbol="BTC/USDT:USDT",
        direction="LONG",
        order_type="MARKET",
        order_role="TP6",
        requested_qty=Decimal("0.001"),
        filled_qty=Decimal("0"),
        status="OPEN",
        created_at=now,
        updated_at=now,
    )
    with pytest.raises(IntegrityError):
        async with pg_session_maker() as session:
            session.add(orm)
            await session.commit()


@pytest.mark.asyncio
async def test_check_constraint_invalid_status(pg_session_maker):
    from src.infrastructure.pg_models import PGOrderORM

    now = int(datetime.now(timezone.utc).timestamp() * 1000)
    orm = PGOrderORM(
        id=str(uuid4()),
        signal_id=str(uuid4()),
        symbol="BTC/USDT:USDT",
        direction="LONG",
        order_type="MARKET",
        order_role="ENTRY",
        requested_qty=Decimal("0.001"),
        filled_qty=Decimal("0"),
        status="UNKNOWN",
        created_at=now,
        updated_at=now,
    )
    with pytest.raises(IntegrityError):
        async with pg_session_maker() as session:
            session.add(orm)
            await session.commit()


# ------------------------------------------------------------------
# 13. update_status round trip
# ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_update_status(order_repo):
    order = make_order(status=OrderStatus.OPEN, filled_qty=Decimal("0"))
    await order_repo.save(order)

    now = int(datetime.now(timezone.utc).timestamp() * 1000)
    await order_repo.update_status(
        order_id=order.id,
        status=OrderStatus.FILLED,
        filled_qty=Decimal("0.001"),
        average_exec_price=Decimal("65000"),
        filled_at=now,
    )

    fetched = await order_repo.get_order(order.id)
    assert fetched is not None
    assert fetched.status == OrderStatus.FILLED
    assert fetched.filled_qty == Decimal("0.001")
    assert fetched.average_exec_price == Decimal("65000")
    assert fetched.filled_at == now


# ------------------------------------------------------------------
# 14. get_order_by_exchange_id
# ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_order_by_exchange_id(order_repo):
    order = make_order(exchange_order_id="ex-lookup-001")
    await order_repo.save(order)

    fetched = await order_repo.get_order_by_exchange_id("ex-lookup-001")
    assert fetched is not None
    assert fetched.id == order.id

    assert await order_repo.get_order_by_exchange_id("nonexistent") is None


# ------------------------------------------------------------------
# 15. get_open_orders
# ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_open_orders(order_repo):
    now = int(datetime.now(timezone.utc).timestamp() * 1000)
    open_order = make_order(status=OrderStatus.OPEN, created_at=now)
    partial_order = make_order(status=OrderStatus.PARTIALLY_FILLED, created_at=now + 1)
    filled_order = make_order(status=OrderStatus.FILLED, created_at=now + 2)
    canceled_order = make_order(status=OrderStatus.CANCELED, created_at=now + 3)
    await order_repo.save_batch([open_order, partial_order, filled_order, canceled_order])

    open_orders = await order_repo.get_open_orders()
    open_ids = {o.id for o in open_orders}
    assert open_order.id in open_ids
    assert partial_order.id in open_ids
    assert filled_order.id not in open_ids
    assert canceled_order.id not in open_ids


# ------------------------------------------------------------------
# 16. save overwrite (upsert) semantics
# ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_save_overwrite(order_repo):
    order = make_order(status=OrderStatus.OPEN, filled_qty=Decimal("0"))
    await order_repo.save(order)

    updated = make_order(
        id=order.id,
        signal_id=order.signal_id,
        status=OrderStatus.FILLED,
        filled_qty=Decimal("0.001"),
        created_at=order.created_at,
        updated_at=order.updated_at,
    )
    await order_repo.save(updated)

    fetched = await order_repo.get_order(order.id)
    assert fetched is not None
    assert fetched.status == OrderStatus.FILLED
    assert fetched.filled_qty == Decimal("0.001")


# ------------------------------------------------------------------
# 17. CheckConstraint: requested_qty must be > 0
# ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_check_constraint_requested_qty_zero(pg_session_maker):
    from src.infrastructure.pg_models import PGOrderORM

    now = int(datetime.now(timezone.utc).timestamp() * 1000)
    orm = PGOrderORM(
        id=str(uuid4()),
        signal_id=str(uuid4()),
        symbol="BTC/USDT:USDT",
        direction="LONG",
        order_type="MARKET",
        order_role="ENTRY",
        requested_qty=Decimal("0"),
        filled_qty=Decimal("0"),
        status="OPEN",
        created_at=now,
        updated_at=now,
    )
    with pytest.raises(IntegrityError):
        async with pg_session_maker() as session:
            session.add(orm)
            await session.commit()


# ------------------------------------------------------------------
# 18. CheckConstraint: filled_qty exceeds requested_qty
# ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_check_constraint_filled_qty_exceeds_requested(pg_session_maker):
    from src.infrastructure.pg_models import PGOrderORM

    now = int(datetime.now(timezone.utc).timestamp() * 1000)
    orm = PGOrderORM(
        id=str(uuid4()),
        signal_id=str(uuid4()),
        symbol="BTC/USDT:USDT",
        direction="LONG",
        order_type="MARKET",
        order_role="ENTRY",
        requested_qty=Decimal("0.001"),
        filled_qty=Decimal("0.002"),
        status="OPEN",
        created_at=now,
        updated_at=now,
    )
    with pytest.raises(IntegrityError):
        async with pg_session_maker() as session:
            session.add(orm)
            await session.commit()


# ------------------------------------------------------------------
# 19. CheckConstraint: invalid order_type
# ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_check_constraint_invalid_order_type(pg_session_maker):
    from src.infrastructure.pg_models import PGOrderORM

    now = int(datetime.now(timezone.utc).timestamp() * 1000)
    orm = PGOrderORM(
        id=str(uuid4()),
        signal_id=str(uuid4()),
        symbol="BTC/USDT:USDT",
        direction="LONG",
        order_type="INVALID_TYPE",
        order_role="ENTRY",
        requested_qty=Decimal("0.001"),
        filled_qty=Decimal("0"),
        status="OPEN",
        created_at=now,
        updated_at=now,
    )
    with pytest.raises(IntegrityError):
        async with pg_session_maker() as session:
            session.add(orm)
            await session.commit()


# ------------------------------------------------------------------
# 20. Null exchange_order_id allowed (partial unique index)
# ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_null_exchange_order_id_allowed(order_repo):
    a = make_order(exchange_order_id=None)
    b = make_order(exchange_order_id=None)
    await order_repo.save(a)
    await order_repo.save(b)

    fetched_a = await order_repo.get_order(a.id)
    fetched_b = await order_repo.get_order(b.id)
    assert fetched_a is not None
    assert fetched_b is not None
    assert fetched_a.exchange_order_id is None
    assert fetched_b.exchange_order_id is None
