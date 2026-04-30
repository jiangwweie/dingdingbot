"""Periodic report-only reconciliation loop for Live-safe v1."""

from __future__ import annotations

import asyncio
from typing import Any, Sequence

from src.infrastructure.logger import logger


RECONCILIATION_INTERVAL_SECONDS = 300
RECONCILIATION_STARTUP_DELAY_SECONDS = 30


async def run_periodic_reconciliation(
    reconciliation_service: Any,
    symbols: list[str],
    shutdown_event: asyncio.Event,
    *,
    interval_seconds: float = RECONCILIATION_INTERVAL_SECONDS,
    startup_delay_seconds: float = RECONCILIATION_STARTUP_DELAY_SECONDS,
) -> None:
    """Run report-only reconciliation read model checks until shutdown.

    This loop intentionally only observes and logs. It must not block symbols,
    create recovery tasks, repair orders, or mutate runtime trading state.
    """
    runtime_symbols = _dedupe_symbols(symbols)
    if not runtime_symbols:
        logger.info("Periodic reconciliation skipped: no runtime symbols configured")
        return

    logger.info(
        "Periodic reconciliation loop starting: symbols=%s, startup_delay=%ss, interval=%ss",
        runtime_symbols,
        startup_delay_seconds,
        interval_seconds,
    )

    if startup_delay_seconds > 0:
        if await _wait_for_shutdown_or_timeout(shutdown_event, startup_delay_seconds):
            logger.info("Periodic reconciliation stopped before first run")
            return

    while not shutdown_event.is_set():
        for symbol in runtime_symbols:
            if shutdown_event.is_set():
                return
            try:
                result = await reconciliation_service.build_read_model(symbol)
                _log_reconciliation_result(result)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(
                    "Periodic reconciliation read model failed: symbol=%s, error=%s",
                    symbol,
                    e,
                    exc_info=True,
                )

        if await _wait_for_shutdown_or_timeout(shutdown_event, interval_seconds):
            return


def _log_reconciliation_result(result: Any) -> None:
    """Log a reconciliation read model result without persisting or acting."""
    mismatches = list(getattr(result, "mismatches", []) or [])
    symbol = getattr(result, "symbol", "unknown")
    checked_at = getattr(result, "checked_at", None)

    if not mismatches:
        logger.info(
            "Periodic reconciliation consistent: symbol=%s, checked_at=%s",
            symbol,
            checked_at,
        )
        return

    severe_count = sum(1 for item in mismatches if getattr(item, "severity", None) == "SEVERE")
    warning_count = sum(1 for item in mismatches if getattr(item, "severity", None) == "WARNING")
    logger.warning(
        "Periodic reconciliation mismatches: symbol=%s, checked_at=%s, total=%s, severe=%s, warning=%s",
        symbol,
        checked_at,
        len(mismatches),
        severe_count,
        warning_count,
    )

    for item in mismatches:
        logger.warning(
            "Periodic reconciliation mismatch detail: symbol=%s, severity=%s, type=%s, reason=%s",
            getattr(item, "symbol", symbol),
            getattr(item, "severity", "UNKNOWN"),
            getattr(item, "mismatch_type", "unknown"),
            getattr(item, "reason", ""),
        )


async def _wait_for_shutdown_or_timeout(
    shutdown_event: asyncio.Event,
    timeout_seconds: float,
) -> bool:
    """Return True if shutdown was requested before timeout elapsed."""
    if timeout_seconds <= 0:
        return shutdown_event.is_set()

    try:
        await asyncio.wait_for(shutdown_event.wait(), timeout=timeout_seconds)
        return True
    except TimeoutError:
        return False


def _dedupe_symbols(symbols: Sequence[str]) -> list[str]:
    """Preserve order while removing duplicate symbols."""
    return list(dict.fromkeys(symbols))
