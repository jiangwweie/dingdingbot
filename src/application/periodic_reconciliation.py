"""Periodic report-only reconciliation loop for Live-safe v1."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Optional, Sequence

from src.infrastructure.logger import logger
from src.infrastructure.repository_ports import (
    ReconciliationReadModelMismatch,
    ReconciliationReadModelReport,
    ReconciliationReadModelRepositoryPort,
)


RECONCILIATION_INTERVAL_SECONDS = 300
RECONCILIATION_STARTUP_DELAY_SECONDS = 30


async def run_periodic_reconciliation(
    reconciliation_service: Any,
    symbols: list[str],
    shutdown_event: asyncio.Event,
    *,
    read_model_repository: Optional[ReconciliationReadModelRepositoryPort] = None,
    protection_health_monitor: Optional[Any] = None,
    external_close_monitor: Optional[Any] = None,
    interval_seconds: float = RECONCILIATION_INTERVAL_SECONDS,
    startup_delay_seconds: float = RECONCILIATION_STARTUP_DELAY_SECONDS,
) -> None:
    """Run reconciliation read model checks until shutdown.

    The reconciliation service remains read-only. Monitors may consume the read
    model to block new entries, emit trace/alerts, or mark local projection as
    externally closed when the exchange is already flat. This loop still must
    not place, cancel, edit, or close exchange orders.
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
                await _save_reconciliation_result_best_effort(
                    read_model_repository,
                    result,
                )
                if external_close_monitor is not None:
                    await external_close_monitor.handle_read_model_result(
                        result,
                        source="periodic",
                    )
                if protection_health_monitor is not None:
                    await protection_health_monitor.handle_read_model_result(
                        result,
                        source="periodic",
                    )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(
                    "Periodic reconciliation read model failed: symbol=%s, error=%s",
                    symbol,
                    e,
                    exc_info=True,
                )
                await _save_fetch_failure_best_effort(
                    read_model_repository,
                    symbol,
                    e,
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

    severe_count = sum(
        1 for item in mismatches if getattr(item, "severity", None) in {"SEVERE", "CRITICAL"}
    )
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


async def _save_reconciliation_result_best_effort(
    repository: Optional[ReconciliationReadModelRepositoryPort],
    result: Any,
) -> None:
    """Persist a successful read model result without affecting runtime behavior."""
    if repository is None:
        return

    try:
        report, mismatches = _to_persistence_records(result)
        await repository.save_report(report, mismatches)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.error(
            "Periodic reconciliation read model persistence failed: symbol=%s, error=%s",
            getattr(result, "symbol", "unknown"),
            exc,
            exc_info=True,
        )


async def _save_fetch_failure_best_effort(
    repository: Optional[ReconciliationReadModelRepositoryPort],
    symbol: str,
    exc: Exception,
) -> None:
    """Persist a build_read_model failure as report-only observation."""
    if repository is None:
        return

    checked_at_ms = int(time.time() * 1000)
    report = ReconciliationReadModelReport(
        report_id=_build_report_id(checked_at_ms, symbol),
        symbol=symbol,
        checked_at_ms=checked_at_ms,
        is_consistent=False,
        total_count=0,
        severe_count=0,
        warning_count=0,
        is_fetch_failure=True,
        fetch_failure_reason=_summarize_exception(exc),
        created_at=checked_at_ms,
    )
    try:
        await repository.save_report(report, [])
    except asyncio.CancelledError:
        raise
    except Exception as persist_exc:
        logger.error(
            "Periodic reconciliation fetch failure persistence failed: symbol=%s, error=%s",
            symbol,
            persist_exc,
            exc_info=True,
        )


def _to_persistence_records(
    result: Any,
) -> tuple[ReconciliationReadModelReport, list[ReconciliationReadModelMismatch]]:
    mismatches = list(getattr(result, "mismatches", []) or [])
    symbol = getattr(result, "symbol", "unknown")
    checked_at_ms = int(getattr(result, "checked_at", None) or time.time() * 1000)
    created_at = int(time.time() * 1000)
    severe_count = sum(
        1 for item in mismatches if getattr(item, "severity", None) in {"SEVERE", "CRITICAL"}
    )
    warning_count = sum(1 for item in mismatches if getattr(item, "severity", None) == "WARNING")
    report_id = _build_report_id(checked_at_ms, symbol)
    report = ReconciliationReadModelReport(
        report_id=report_id,
        symbol=symbol,
        checked_at_ms=checked_at_ms,
        is_consistent=not mismatches,
        total_count=len(mismatches),
        severe_count=severe_count,
        warning_count=warning_count,
        is_fetch_failure=False,
        fetch_failure_reason=None,
        created_at=created_at,
    )
    persisted_mismatches = [
        ReconciliationReadModelMismatch(
            report_id=report_id,
            symbol=getattr(item, "symbol", symbol),
            mismatch_type=getattr(item, "mismatch_type", "unknown"),
            severity=getattr(item, "severity", "UNKNOWN"),
            reason=getattr(item, "reason", ""),
            local_ref=getattr(item, "local_ref", None),
            exchange_ref=getattr(item, "exchange_ref", None),
            metadata=getattr(item, "metadata", None) or None,
            created_at=created_at,
        )
        for item in mismatches
    ]
    return report, persisted_mismatches


def _build_report_id(checked_at_ms: int, symbol: str) -> str:
    return f"{checked_at_ms}:{symbol}"


def _summarize_exception(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"


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
