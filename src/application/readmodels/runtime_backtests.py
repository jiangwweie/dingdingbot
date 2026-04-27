"""Console Research Backtests ReadModel - list backtest reports from repository."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from src.application.readmodels.console_models import (
    ConsoleBacktestItem,
    ConsoleBacktestMetrics,
    ConsoleBacktestsResponse,
)


def _ms_to_iso(ms: Optional[int]) -> str:
    if not ms:
        return ""
    try:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    except (OSError, ValueError):
        return ""


def _to_optional_float(val: Any) -> Optional[float]:
    """Convert value to float, preserving None for missing data."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, Decimal):
        try:
            return float(val)
        except (InvalidOperation, OverflowError):
            return None
    if isinstance(val, str):
        try:
            return float(val)
        except (ValueError, InvalidOperation):
            return None
    return None


def _to_optional_int(val: Any) -> Optional[int]:
    """Convert value to int, preserving None for missing data."""
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


class RuntimeBacktestsReadModel:
    async def build(
        self,
        *,
        backtest_repo: Optional[Any] = None,
        limit: int = 100,
    ) -> ConsoleBacktestsResponse:
        if backtest_repo is None:
            return ConsoleBacktestsResponse()

        # Let repo exceptions propagate — the route handler decides how to respond
        result = await backtest_repo.list_reports(page_size=limit)

        if not isinstance(result, dict):
            return ConsoleBacktestsResponse()

        raw_reports = result.get("reports", [])
        if not isinstance(raw_reports, list):
            return ConsoleBacktestsResponse()

        # Truncate to limit (repo may return more via pagination edge cases)
        raw_reports = raw_reports[:limit]

        items: list[ConsoleBacktestItem] = []
        for raw in raw_reports:
            report_id = str(raw.get("id", "unknown"))
            strategy_id = str(raw.get("strategy_id", ""))
            strategy_name = str(raw.get("strategy_name", ""))
            symbol = str(raw.get("symbol", ""))
            timeframe = str(raw.get("timeframe", ""))
            backtest_start = raw.get("backtest_start")
            backtest_end = raw.get("backtest_end")

            # Preserve None for missing metrics — don't fabricate zeros
            total_return = _to_optional_float(raw.get("total_return"))
            win_rate = _to_optional_float(raw.get("win_rate"))
            max_drawdown = _to_optional_float(raw.get("max_drawdown"))
            sharpe = _to_optional_float(raw.get("sharpe_ratio"))
            trades = _to_optional_int(raw.get("total_trades"))

            # Derive status: if report exists in DB it's completed
            status = "COMPLETED"

            # candidate_ref: use strategy_id as the reference
            candidate_ref = strategy_id if strategy_id else strategy_name

            items.append(ConsoleBacktestItem(
                id=report_id,
                candidate_ref=candidate_ref,
                symbol=symbol,
                timeframe=timeframe,
                start_date=_ms_to_iso(backtest_start),
                end_date=_ms_to_iso(backtest_end),
                status=status,
                metrics=ConsoleBacktestMetrics(
                    total_return=total_return,
                    sharpe=sharpe,
                    max_drawdown=max_drawdown,
                    win_rate=win_rate,
                    trades=trades,
                ),
            ))

        return ConsoleBacktestsResponse(backtests=items)