"""Console Runtime Signals ReadModel - 第二批只读 API"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from src.application.readmodels.console_models import ConsoleSignalItem, ConsoleSignalsResponse


def _to_iso_from_millis(timestamp_ms: Optional[int]) -> str:
    if not timestamp_ms:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")


class RuntimeSignalsReadModel:
    async def build(
        self,
        *,
        signal_repo: Optional[Any],
        symbol: Optional[str] = None,
        limit: int = 100,
    ) -> ConsoleSignalsResponse:
        """Build console-facing signals response.

        从 signal_repo 查询最近信号列表.
        """
        if signal_repo is None:
            return ConsoleSignalsResponse(signals=[])

        # 查询信号列表
        try:
            result = await signal_repo.get_signals(
                symbol=symbol,
                limit=limit,
            )
        except Exception:
            return ConsoleSignalsResponse(signals=[])

        # 真实 repo 返回 {"total": int, "data": list[dict]}
        if not isinstance(result, dict):
            return ConsoleSignalsResponse(signals=[])

        raw_signals = result.get("data", [])
        if not isinstance(raw_signals, list):
            return ConsoleSignalsResponse(signals=[])

        signals: list[ConsoleSignalItem] = []
        for raw in raw_signals:
            # raw 是 dict, 需要做字段映射
            signal_id = str(raw.get("id", "unknown"))
            symbol_val = str(raw.get("symbol", "unknown"))
            timeframe_val = str(raw.get("timeframe", "unknown"))
            direction_val = str(raw.get("direction", "LONG"))
            strategy_name = str(raw.get("strategy_name", "unknown"))
            score = float(raw.get("score", 0.0) or 0.0)
            created_at_ts = raw.get("created_at")
            status_val = raw.get("status")

            signals.append(
                ConsoleSignalItem(
                    signal_id=signal_id,
                    symbol=symbol_val,
                    timeframe=timeframe_val,
                    direction=direction_val if direction_val in {"LONG", "SHORT"} else "LONG",
                    strategy_name=strategy_name,
                    score=score,
                    created_at=_to_iso_from_millis(created_at_ts),
                    status=status_val,
                )
            )

        return ConsoleSignalsResponse(signals=signals)