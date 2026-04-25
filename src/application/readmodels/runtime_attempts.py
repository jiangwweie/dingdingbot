"""Console Runtime Attempts ReadModel - 第二批只读 API"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from src.application.readmodels.console_models import ConsoleAttemptItem, ConsoleAttemptsResponse


def _to_iso_from_millis(timestamp_ms: Optional[int]) -> str:
    if not timestamp_ms:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")


class RuntimeAttemptsReadModel:
    async def build(
        self,
        *,
        signal_repo: Optional[Any],
        symbol: Optional[str] = None,
        timeframe: Optional[str] = None,
        limit: int = 100,
    ) -> ConsoleAttemptsResponse:
        """Build console-facing attempts response.

        从 signal_repo 查询最近尝试列表.
        """
        if signal_repo is None:
            return ConsoleAttemptsResponse(attempts=[])

        # 查询尝试列表
        try:
            result = await signal_repo.get_attempts(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
            )
        except Exception:
            return ConsoleAttemptsResponse(attempts=[])

        # 真实 repo 返回 {"total": int, "data": list[dict]}
        if not isinstance(result, dict):
            return ConsoleAttemptsResponse(attempts=[])

        raw_attempts = result.get("data", [])
        if not isinstance(raw_attempts, list):
            return ConsoleAttemptsResponse(attempts=[])

        attempts: list[ConsoleAttemptItem] = []
        for raw in raw_attempts:
            # raw 是 dict, 需要做字段映射
            attempt_id = str(raw.get("id", "unknown"))
            signal_id = raw.get("signal_id")
            symbol_val = str(raw.get("symbol", "unknown"))
            timeframe_val = str(raw.get("timeframe", "unknown"))
            final_result = str(raw.get("final_result", "UNKNOWN"))
            created_at_ts = raw.get("kline_timestamp") or raw.get("created_at")

            # 推导 reject_reason / filter_reason
            reject_reason = None
            filter_reason = None
            if final_result == "FILTERED":
                filter_reason = raw.get("filter_reason") or "filter_rejected"
            elif final_result == "NO_PATTERN":
                reject_reason = "no_pattern_detected"

            attempts.append(
                ConsoleAttemptItem(
                    attempt_id=attempt_id,
                    signal_id=str(signal_id) if signal_id else None,
                    symbol=symbol_val,
                    timeframe=timeframe_val,
                    final_result=final_result,
                    reject_reason=reject_reason,
                    filter_reason=filter_reason,
                    created_at=_to_iso_from_millis(created_at_ts),
                )
            )

        return ConsoleAttemptsResponse(attempts=attempts)