"""Console Runtime Events ReadModel - aggregate timeline from multiple sources."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from src.application.readmodels.console_models import ConsoleEventItem, ConsoleEventsResponse


def _to_iso(timestamp_val) -> str:
    """Convert millisecond timestamp or ISO string to ISO format string."""
    if not timestamp_val:
        return ""
    if isinstance(timestamp_val, str):
        return timestamp_val
    try:
        return datetime.fromtimestamp(timestamp_val / 1000, tz=timezone.utc).isoformat()
    except (OSError, ValueError):
        return str(timestamp_val)


def _millis_or_max(timestamp_val) -> float:
    """Convert a value to milliseconds for sorting. Returns 0 on failure."""
    if not timestamp_val:
        return 0
    if isinstance(timestamp_val, (int, float)):
        return float(timestamp_val)
    if isinstance(timestamp_val, str):
        try:
            dt = datetime.fromisoformat(timestamp_val)
            return dt.timestamp() * 1000
        except (ValueError, TypeError):
            return 0
    return 0


# Map audit event_type → (category, severity)
_AUDIT_EVENT_MAP: dict[str, tuple[str, str]] = {
    "ORDER_CREATED": ("EXECUTION", "INFO"),
    "ORDER_SUBMITTED": ("EXECUTION", "INFO"),
    "ORDER_CONFIRMED": ("EXECUTION", "INFO"),
    "ORDER_PARTIAL_FILLED": ("EXECUTION", "INFO"),
    "ORDER_FILLED": ("EXECUTION", "SUCCESS"),
    "ORDER_CANCELED": ("EXECUTION", "WARN"),
    "ORDER_REJECTED": ("EXECUTION", "ERROR"),
    "ORDER_EXPIRED": ("EXECUTION", "WARN"),
    "ORDER_UPDATED": ("EXECUTION", "INFO"),
}

# Map signal final_result / status → severity
_SIGNAL_RESULT_SEVERITY: dict[str, str] = {
    "SIGNAL_FIRED": "SUCCESS",
    "FIRED": "SUCCESS",
    "NO_PATTERN": "INFO",
    "FILTERED": "WARN",
}


class RuntimeEventsReadModel:
    async def build(
        self,
        *,
        signal_repo: Optional[Any] = None,
        audit_logger: Optional[Any] = None,
        execution_orchestrator: Optional[Any] = None,
        startup_reconciliation_summary: Optional[dict[str, Any]] = None,
        execution_recovery_repo: Optional[Any] = None,
        limit: int = 100,
    ) -> ConsoleEventsResponse:
        """Build console-facing events timeline.

        Aggregates from multiple sources in priority order:
        1. Signals (SIGNAL category)
        2. Order audit logs (EXECUTION category)
        3. Startup reconciliation (STARTUP/RECONCILIATION)
        4. Breaker state (BREAKER)
        5. Recovery tasks (RECOVERY)
        """
        events: list[ConsoleEventItem] = []

        # --- Source 1: Signals ---
        await self._collect_signal_events(signal_repo, events)

        # --- Source 2: Order audit logs ---
        await self._collect_audit_events(audit_logger, events)

        # --- Source 3: Startup reconciliation ---
        self._collect_startup_events(startup_reconciliation_summary, events)

        # --- Source 4: Breaker state ---
        self._collect_breaker_events(execution_orchestrator, events)

        # --- Source 5: Recovery tasks ---
        await self._collect_recovery_events(execution_recovery_repo, events)

        # Sort by timestamp descending (newest first), then apply limit
        events.sort(key=lambda e: _millis_or_max(e.timestamp), reverse=True)
        events = events[:limit]

        return ConsoleEventsResponse(events=events)

    async def _collect_signal_events(
        self,
        signal_repo: Optional[Any],
        events: list[ConsoleEventItem],
    ) -> None:
        if signal_repo is None:
            return
        try:
            result = await signal_repo.get_signals(limit=50)
        except Exception:
            return

        if not isinstance(result, dict):
            return
        raw_signals = result.get("data", [])
        if not isinstance(raw_signals, list):
            return

        for raw in raw_signals:
            signal_id = str(raw.get("id", "unknown"))
            symbol = str(raw.get("symbol", "unknown"))
            direction = str(raw.get("direction", ""))
            strategy_name = str(raw.get("strategy_name", ""))
            status = str(raw.get("status", ""))
            created_at = raw.get("created_at")

            # Build message
            parts = []
            if strategy_name:
                parts.append(strategy_name)
            if direction:
                parts.append(direction)
            if symbol:
                parts.append(symbol)
            msg_core = " ".join(parts) if parts else "Signal"

            if status and status not in ("PENDING", "ACTIVE", "FIRED"):
                message = f"Signal {status.lower()}: {msg_core}"
            else:
                message = f"Signal fired: {msg_core}"

            severity = _SIGNAL_RESULT_SEVERITY.get(status, "INFO")
            if status in ("WON",):
                severity = "SUCCESS"
            elif status in ("LOST", "SUPERSEDED"):
                severity = "WARN"

            events.append(ConsoleEventItem(
                id=f"sig_{signal_id}",
                timestamp=_to_iso(created_at),
                category="SIGNAL",
                severity=severity,
                message=message,
                related_entities=[signal_id],
            ))

    async def _collect_audit_events(
        self,
        audit_logger: Optional[Any],
        events: list[ConsoleEventItem],
    ) -> None:
        if audit_logger is None:
            return

        repo = getattr(audit_logger, "_repository", None)
        if repo is None:
            return

        try:
            from src.domain.models import OrderAuditLogQuery
            query = OrderAuditLogQuery(limit=50, offset=0)
            audit_logs = await repo.query(query)
        except Exception:
            return

        for log in audit_logs:
            log_id = str(getattr(log, "id", "unknown"))
            order_id = str(getattr(log, "order_id", ""))
            signal_id = getattr(log, "signal_id", None)
            event_type = str(getattr(log, "event_type", ""))
            new_status = str(getattr(log, "new_status", ""))
            created_at = getattr(log, "created_at", 0)

            category, severity = _AUDIT_EVENT_MAP.get(event_type, ("EXECUTION", "INFO"))

            # Build message
            if event_type == "ORDER_FILLED":
                message = f"Order filled: {order_id}"
            elif event_type == "ORDER_CREATED":
                message = f"Order created: {order_id}"
            elif event_type == "ORDER_CANCELED":
                message = f"Order canceled: {order_id}"
            elif event_type == "ORDER_REJECTED":
                message = f"Order rejected: {order_id}"
            elif event_type == "ORDER_SUBMITTED":
                message = f"Order submitted: {order_id}"
            else:
                message = f"Order {new_status or event_type.lower()}: {order_id}"

            related = [order_id]
            if signal_id:
                related.append(str(signal_id))

            events.append(ConsoleEventItem(
                id=f"audit_{log_id}",
                timestamp=_to_iso(created_at),
                category=category,
                severity=severity,
                message=message,
                related_entities=related,
            ))

    def _collect_startup_events(
        self,
        summary: Optional[dict[str, Any]],
        events: list[ConsoleEventItem],
    ) -> None:
        if summary is None:
            return

        total = summary.get("total_candidates", 0)
        failures = summary.get("failure_count", 0)
        duration = summary.get("duration_ms", 0)

        # Startup reconciliation event
        if failures > 0:
            severity = "WARN"
            message = f"Startup reconciliation: {failures} failure(s) out of {total} candidate(s) ({duration}ms)"
        else:
            severity = "SUCCESS"
            message = f"Startup reconciliation passed: {total} candidate(s) checked ({duration}ms)"

        events.append(ConsoleEventItem(
            id="startup_reconciliation",
            timestamp=datetime.now(timezone.utc).isoformat(),
            category="RECONCILIATION",
            severity=severity,
            message=message,
            related_entities=[],
        ))

        # PG recovery events
        pg_resolved = summary.get("pg_recovery_resolved_count", 0)
        pg_retrying = summary.get("pg_recovery_retrying_count", 0)
        pg_failed = summary.get("pg_recovery_failed_count", 0)

        if pg_resolved > 0:
            events.append(ConsoleEventItem(
                id="startup_pg_recovery_resolved",
                timestamp=datetime.now(timezone.utc).isoformat(),
                category="RECOVERY",
                severity="SUCCESS",
                message=f"Startup recovery: {pg_resolved} task(s) resolved",
                related_entities=[],
            ))

        if pg_retrying > 0:
            events.append(ConsoleEventItem(
                id="startup_pg_recovery_retrying",
                timestamp=datetime.now(timezone.utc).isoformat(),
                category="RECOVERY",
                severity="WARN",
                message=f"Startup recovery: {pg_retrying} task(s) retrying",
                related_entities=[],
            ))

        if pg_failed > 0:
            events.append(ConsoleEventItem(
                id="startup_pg_recovery_failed",
                timestamp=datetime.now(timezone.utc).isoformat(),
                category="RECOVERY",
                severity="ERROR",
                message=f"Startup recovery: {pg_failed} task(s) failed",
                related_entities=[],
            ))

    def _collect_breaker_events(
        self,
        orchestrator: Optional[Any],
        events: list[ConsoleEventItem],
    ) -> None:
        if orchestrator is None:
            return

        if not hasattr(orchestrator, "list_circuit_breaker_symbols"):
            return

        try:
            breaker_symbols = orchestrator.list_circuit_breaker_symbols()
        except Exception:
            return

        for symbol in breaker_symbols:
            events.append(ConsoleEventItem(
                id=f"breaker_{symbol}",
                timestamp=datetime.now(timezone.utc).isoformat(),
                category="BREAKER",
                severity="ERROR",
                message=f"Circuit breaker tripped: {symbol}",
                related_entities=[symbol],
            ))

    async def _collect_recovery_events(
        self,
        recovery_repo: Optional[Any],
        events: list[ConsoleEventItem],
    ) -> None:
        if recovery_repo is None:
            return

        try:
            if hasattr(recovery_repo, "list_blocking"):
                tasks = await recovery_repo.list_blocking()
            elif hasattr(recovery_repo, "list_active"):
                tasks = await recovery_repo.list_active()
            else:
                return
        except Exception:
            return

        if not isinstance(tasks, list):
            return

        for task in tasks:
            if not isinstance(task, dict):
                continue

            task_id = str(task.get("id", "unknown"))
            symbol = str(task.get("symbol", "unknown"))
            status = str(task.get("status", "pending"))
            error_message = task.get("error_message", "")
            updated_at = task.get("updated_at")

            if status == "failed":
                severity = "ERROR"
                message = f"Recovery failed: {symbol}" + (f" - {error_message}" if error_message else "")
            elif status == "retrying":
                severity = "WARN"
                message = f"Recovery retrying: {symbol}"
            else:
                severity = "WARN"
                message = f"Recovery pending: {symbol}"

            related = [task_id]
            intent_id = task.get("intent_id")
            if intent_id:
                related.append(str(intent_id))

            events.append(ConsoleEventItem(
                id=f"recovery_{task_id}",
                timestamp=_to_iso(updated_at) if updated_at else datetime.now(timezone.utc).isoformat(),
                category="RECOVERY",
                severity=severity,
                message=message,
                related_entities=related,
            ))