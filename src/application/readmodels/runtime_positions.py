"""Console Runtime Positions ReadModel - 第二批只读 API"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from src.application.readmodels.console_models import ConsolePositionItem, ConsolePositionsResponse


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_iso_from_millis(timestamp_ms: Optional[int]) -> Optional[str]:
    if not timestamp_ms:
        return None
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")


class RuntimePositionsReadModel:
    async def build(
        self,
        *,
        account_snapshot: Optional[Any],
        position_repo: Optional[Any] = None,
    ) -> ConsolePositionsResponse:
        """Build console-facing positions response.

        优先使用 account_snapshot (实时账户数据),
        如果不可用则尝试从 position_repo 查询 (PG 历史数据).
        """
        positions: list[ConsolePositionItem] = []

        # 优先使用 account_snapshot (实时数据)
        if account_snapshot is not None:
            for pos in getattr(account_snapshot, "positions", []):
                symbol = getattr(pos, "symbol", "unknown")
                side = getattr(pos, "side", "long")
                direction = "SHORT" if str(side).lower() in {"short", "sell"} else "LONG"

                size = getattr(pos, "size", Decimal("0"))
                entry_price = getattr(pos, "entry_price", Decimal("0"))
                # PositionInfo 没有 current_price, 使用 entry_price 作为 fallback
                current_price = getattr(pos, "current_price", entry_price) or entry_price
                unrealized_pnl = getattr(pos, "unrealized_pnl", Decimal("0"))
                leverage = int(getattr(pos, "leverage", 1) or 1)

                # 计算 margin 和 exposure
                notional = abs(size * entry_price)
                margin = _to_float(notional / leverage) if leverage else 0.0
                exposure = _to_float(notional)

                positions.append(
                    ConsolePositionItem(
                        symbol=symbol,
                        direction=direction,
                        quantity=_to_float(size),
                        entry_price=_to_float(entry_price),
                        current_price=_to_float(current_price),
                        unrealized_pnl=_to_float(unrealized_pnl),
                        leverage=leverage,
                        margin=margin,
                        exposure=exposure,
                        updated_at=_to_iso_from_millis(getattr(pos, "timestamp", None)),
                    )
                )

        return ConsolePositionsResponse(positions=positions)
