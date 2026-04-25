"""Console Runtime Execution Intents ReadModel - 第二批只读 API"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from src.application.readmodels.console_models import ConsoleExecutionIntentItem, ConsoleExecutionIntentsResponse
from src.domain.execution_intent import ExecutionIntentStatus


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


class RuntimeExecutionIntentsReadModel:
    async def build(
        self,
        *,
        intent_repo: Optional[Any],
        status: Optional[str] = None,
        limit: int = 100,
    ) -> ConsoleExecutionIntentsResponse:
        """Build console-facing execution intents response.

        从 intent_repo 查询执行意图列表.
        """
        if intent_repo is None:
            return ConsoleExecutionIntentsResponse(intents=[])

        # 查询意图列表
        try:
            raw_intents: list[Any] = []
            if status:
                # 安全转换 status 字符串为 ExecutionIntentStatus 枚举
                try:
                    intent_status = ExecutionIntentStatus(status)
                except ValueError:
                    return ConsoleExecutionIntentsResponse(intents=[])
                raw_intents = await intent_repo.list(status=intent_status)
            else:
                raw_intents = await intent_repo.list_unfinished()
        except Exception:
            return ConsoleExecutionIntentsResponse(intents=[])

        # 在 readmodel 层做 limit 切片
        raw_intents = raw_intents[:limit]

        intents: list[ConsoleExecutionIntentItem] = []
        for intent in raw_intents:
            # intent 可能是 ORM 对象或领域模型
            intent_id = str(getattr(intent, "id", "unknown"))
            # 区分 ORM 对象和领域模型 (ExecutionIntent)
            signal_payload = {}
            if hasattr(intent, "signal"):
                # 领域模型
                signal_obj = getattr(intent, "signal")
                if hasattr(signal_obj, "model_dump"):
                    signal_payload = signal_obj.model_dump()
                symbol_val = getattr(signal_obj, "symbol", "unknown")
            else:
                # ORM 模型
                signal_payload = getattr(intent, "signal_payload", {}) or {}
                symbol_attr = getattr(intent, "symbol", None)
                symbol_val = str(symbol_attr) if symbol_attr and symbol_attr != "unknown" else str(signal_payload.get("symbol", "unknown"))
            
            status_val = str(getattr(intent, "status", "pending"))
            signal_id = getattr(intent, "signal_id", None)
            created_at_ts = getattr(intent, "created_at", None)
            updated_at_ts = getattr(intent, "updated_at", None)
            
            direction = signal_payload.get("direction", "LONG")
            quantity = signal_payload.get("suggested_position_size", Decimal("0"))

            # side 映射: direction -> side
            side = "BUY" if direction == "LONG" else "SELL"

            intents.append(
                ConsoleExecutionIntentItem(
                    intent_id=intent_id,
                    symbol=symbol_val,
                    side=side,
                    intent_type="ENTRY",  # 默认 ENTRY
                    status=status_val,
                    quantity=_to_float(quantity),
                    created_at=_to_iso_from_millis(created_at_ts),
                    updated_at=_to_iso_from_millis(updated_at_ts) if updated_at_ts else None,
                    related_signal_id=str(signal_id) if signal_id else None,
                )
            )

        return ConsoleExecutionIntentsResponse(intents=intents)