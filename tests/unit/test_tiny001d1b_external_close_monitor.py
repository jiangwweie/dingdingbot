from __future__ import annotations

from decimal import Decimal

import pytest

from src.application.external_close_monitor import (
    POSITION_CLOSED_ON_EXCHANGE_NOT_PROJECTED,
    ExternalCloseMonitor,
)
from src.application.position_projection_service import PositionProjectionService
from src.application.reconciliation import ReconciliationMismatch, ReconciliationReadModelResult
from src.domain.models import Direction, Position


SYMBOL = "ETH/USDT:USDT"


class _PositionRepo:
    def __init__(self, positions: list[Position]) -> None:
        self.positions = {position.id: position for position in positions}

    async def save(self, position: Position) -> None:
        self.positions[position.id] = position

    async def get(self, position_id: str):
        return self.positions.get(position_id)

    async def list_active(self, *, symbol: str | None = None, limit: int = 100):
        return [
            position
            for position in self.positions.values()
            if not position.is_closed and (symbol is None or position.symbol == symbol)
        ][:limit]


class _Orchestrator:
    def __init__(self) -> None:
        self.blocks: list[tuple[str, str, dict]] = []

    def block_symbol_for_protection_health(self, symbol: str, reason_code: str, metadata: dict):
        self.blocks.append((symbol, reason_code, metadata))


class _Trace:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit_risk_decision(self, **kwargs):
        self.events.append(kwargs)


def _active_position() -> Position:
    return Position(
        id="pos-sig-1",
        signal_id="sig-1",
        symbol=SYMBOL,
        direction=Direction.LONG,
        entry_price=Decimal("2133"),
        current_qty=Decimal("0.01"),
        watermark_price=Decimal("2133"),
        realized_pnl=Decimal("0"),
        opened_at=1,
        is_closed=False,
    )


def _external_close_result() -> ReconciliationReadModelResult:
    return ReconciliationReadModelResult(
        symbol=SYMBOL,
        checked_at=1,
        mismatches=[
            ReconciliationMismatch(
                symbol=SYMBOL,
                mismatch_type="local_position_missing_on_exchange",
                severity="SEVERE",
                local_ref=SYMBOL,
                exchange_ref=None,
                reason="Local active position exists but exchange has no active position.",
                metadata={
                    "local_position_id": "pos-sig-1",
                    "local_qty": "0.01",
                    "exchange_qty": "0",
                },
            )
        ],
    )


@pytest.mark.asyncio
async def test_external_close_marks_local_position_unresolved_closed_and_blocks_entries():
    repo = _PositionRepo([_active_position()])
    projection = PositionProjectionService(repo)
    orchestrator = _Orchestrator()
    trace = _Trace()
    monitor = ExternalCloseMonitor(
        execution_orchestrator=orchestrator,
        position_projection_service=projection,
        trace_service=trace,
    )

    await monitor.handle_read_model_result(_external_close_result(), source="periodic")

    position = await repo.get("pos-sig-1")
    assert position.is_closed is True
    assert position.current_qty == Decimal("0")
    assert position.realized_pnl == Decimal("0")
    assert any(key.startswith("external_close:periodic:") for key in position.projected_exit_fills)
    assert orchestrator.blocks == [
        (
            SYMBOL,
            POSITION_CLOSED_ON_EXCHANGE_NOT_PROJECTED,
            orchestrator.blocks[0][2],
        )
    ]
    assert orchestrator.blocks[0][2]["pnl_status"] == "unresolved_no_reliable_fill"
    assert trace.events[0]["event_type"] == "control.external_close_detected"
    assert trace.events[0]["decision"] == "deny_new_entries"


@pytest.mark.asyncio
async def test_external_close_monitor_ignores_non_external_close_mismatches():
    repo = _PositionRepo([_active_position()])
    projection = PositionProjectionService(repo)
    orchestrator = _Orchestrator()
    monitor = ExternalCloseMonitor(
        execution_orchestrator=orchestrator,
        position_projection_service=projection,
    )
    result = ReconciliationReadModelResult(
        symbol=SYMBOL,
        checked_at=1,
        mismatches=[
            ReconciliationMismatch(
                symbol=SYMBOL,
                mismatch_type="protection_local_sl_missing_on_exchange",
                severity="CRITICAL",
                reason="PROTECTION_LOCAL_SL_MISSING_ON_EXCHANGE",
            )
        ],
    )

    await monitor.handle_read_model_result(result, source="periodic")

    position = await repo.get("pos-sig-1")
    assert position.is_closed is False
    assert orchestrator.blocks == []
