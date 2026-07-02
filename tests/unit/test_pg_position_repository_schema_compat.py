from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from src.domain.models import Direction, Position
from src.infrastructure.pg_models import PGPositionORM
from src.infrastructure.pg_position_repository import PgPositionRepository


def test_pg_position_select_uses_deployed_current_qty_schema():
    stmt = select(PGPositionORM).where(PGPositionORM.is_closed == 0)
    sql = str(stmt.compile(dialect=postgresql.dialect()))

    assert "positions.current_qty" in sql
    assert "positions.highest_price_since_entry" in sql
    assert "positions.created_at" in sql
    assert "positions.runtime_instance_id" in sql
    assert "positions.order_candidate_id" in sql
    assert "positions.quantity" not in sql
    assert "positions.position_payload" not in sql
    assert "positions.opened_at" not in sql


def test_pg_position_repository_maps_deployed_schema_to_domain_position():
    orm = PGPositionORM(
        id="pos-1",
        signal_id="sig-1",
        symbol="BNB/USDT:USDT",
        direction="LONG",
        entry_price="600",
        current_qty="0.01",
        highest_price_since_entry="610",
        realized_pnl="1.23",
        total_fees_paid="0.02",
        is_closed=0,
        created_at=1780550000,
        updated_at=1780550001,
    )

    position = PgPositionRepository._to_domain(orm)

    assert position.current_qty == Decimal("0.01")
    assert position.watermark_price == Decimal("610")
    assert position.realized_pnl == Decimal("1.23")
    assert position.total_fees_paid == Decimal("0.02")
    assert position.opened_at == 1780550000000
    assert position.is_closed is False
    assert position.runtime_instance_id is None
    assert position.order_candidate_id is None


def test_pg_position_repository_persists_domain_position_to_deployed_schema():
    position = Position(
        id="pos-1",
        signal_id="sig-1",
        symbol="BNB/USDT:USDT",
        direction=Direction.LONG,
        entry_price=Decimal("600"),
        current_qty=Decimal("0.01"),
        watermark_price=Decimal("610"),
        realized_pnl=Decimal("1.23"),
        total_fees_paid=Decimal("0.02"),
        opened_at=1780550000000,
        is_closed=True,
        runtime_instance_id="runtime-1",
        trial_binding_id="trial-1",
        strategy_family_id="family-1",
        strategy_family_version_id="version-1",
        signal_evaluation_id="signal-eval-1",
        order_candidate_id="candidate-1",
    )

    orm = PgPositionRepository._to_orm(position)

    assert orm.current_qty == "0.01"
    assert orm.highest_price_since_entry == "610"
    assert orm.realized_pnl == "1.23"
    assert orm.total_fees_paid == "0.02"
    assert orm.created_at == 1780550000
    assert orm.is_closed == 1
    assert orm.runtime_instance_id == "runtime-1"
    assert orm.trial_binding_id == "trial-1"
    assert orm.strategy_family_id == "family-1"
    assert orm.strategy_family_version_id == "version-1"
    assert orm.signal_evaluation_id == "signal-eval-1"
    assert orm.order_candidate_id == "candidate-1"
