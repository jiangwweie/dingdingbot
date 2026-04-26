"""Console Runtime Orders ReadModel - 第二批只读 API"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from src.application.readmodels.console_models import ConsoleOrderItem, ConsoleOrdersResponse
from src.domain.models import OrderStatus


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_iso_from_millis(timestamp_ms: Optional[int]) -> str:
    if not timestamp_ms:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")


class RuntimeOrdersReadModel:
    async def build(
        self,
        *,
        order_repo: Optional[Any],
        symbol: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> ConsoleOrdersResponse:
        """Build console-facing orders response.

        从 order_repo 查询订单列表.
        """
        if order_repo is None:
            return ConsoleOrdersResponse(orders=[])

        # 查询订单列表
        try:
            raw_orders: list[Any] = []
            if status:
                # 安全转换 status 字符串为 OrderStatus 枚举
                try:
                    order_status = OrderStatus(status)
                except ValueError:
                    return ConsoleOrdersResponse(orders=[])
                raw_orders = await order_repo.get_orders_by_status(order_status, symbol=symbol)
            elif symbol:
                raw_orders = await order_repo.get_orders_by_symbol(symbol)
            else:
                # 无 symbol/status 时，尝试 get_open_orders (如果 repo 有)
                if hasattr(order_repo, "get_open_orders"):
                    raw_orders = await order_repo.get_open_orders()
                else:
                    # 没有 recent orders 能力，返回空列表
                    return ConsoleOrdersResponse(orders=[])
        except Exception:
            return ConsoleOrdersResponse(orders=[])

        # 在 readmodel 层做 limit 切片
        raw_orders = raw_orders[:limit]

        orders: list[ConsoleOrderItem] = []
        for order in raw_orders:
            # order 可能是 ORM 对象或领域模型
            order_id = str(getattr(order, "id", "unknown"))
            symbol_val = str(getattr(order, "symbol", "unknown"))
            direction = str(getattr(order, "direction", "LONG"))
            order_type = str(getattr(order, "order_type", "MARKET"))
            status_val = str(getattr(order, "status", "PENDING"))
            requested_qty = getattr(order, "requested_qty", Decimal("0"))
            price = getattr(order, "price", None)
            reduce_only = bool(getattr(order, "reduce_only", False))
            created_at_ts = getattr(order, "created_at", None)
            updated_at_ts = getattr(order, "updated_at", None)

            # side 映射: direction -> side
            side = "BUY" if direction == "LONG" else "SELL"

            orders.append(
                ConsoleOrderItem(
                    order_id=order_id,
                    symbol=symbol_val,
                    order_role=str(getattr(getattr(order, "order_role", None), "value", getattr(order, "order_role", None)) or "ENTRY"),
                    side=side,
                    type=order_type,
                    status=status_val,
                    qty=_to_float(requested_qty),
                    price=_to_float(price) if price else None,
                    reduce_only=reduce_only,
                    created_at=_to_iso_from_millis(created_at_ts),
                    updated_at=_to_iso_from_millis(updated_at_ts) if updated_at_ts else None,
                )
            )

        return ConsoleOrdersResponse(orders=orders)
