from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from src.application.readmodels.console_models import (
    BreakerSummaryResponse,
    RecoverySummaryResponse,
    RuntimeHealthResponse,
)


def _iso_from_millis(timestamp_ms: Optional[int]) -> Optional[str]:
    if not timestamp_ms:
        return None
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")


class RuntimeHealthReadModel:
    async def build(
        self,
        *,
        runtime_config_provider: Optional[Any],
        exchange_gateway: Optional[Any],
        execution_orchestrator: Optional[Any],
        execution_recovery_repo: Optional[Any],
        startup_reconciliation_summary: Optional[dict[str, Any]],
        account_snapshot: Optional[Any],
    ) -> RuntimeHealthResponse:
        permission_summary = (
            exchange_gateway.get_permission_check_summary()
            if exchange_gateway is not None and hasattr(exchange_gateway, "get_permission_check_summary")
            else None
        )

        # Exchange status: distinguish startup warmup from real staleness
        if account_snapshot is None:
            # Startup warmup: no snapshot yet, use permission check as proxy
            if exchange_gateway is None:
                exchange_status = "DOWN"
            elif permission_summary is not None and permission_summary.get("status") in {
                "failed",
                "error",
            }:
                exchange_status = "DOWN"
            elif permission_summary is not None and permission_summary.get("status") in {
                "not_checked",
                "skipped_testnet",
            }:
                exchange_status = "DEGRADED"
            else:
                # Gateway exists, permission check passed or pending
                exchange_status = "DEGRADED"  # Conservative: warmup, not yet verified
        else:
            # Snapshot exists: use freshness + permission check
            exchange_status = "OK"
            age_seconds = max(
                0.0,
                datetime.now(timezone.utc).timestamp() - (getattr(account_snapshot, "timestamp", 0) / 1000),
            )
            if age_seconds > 300:
                exchange_status = "DOWN"
            elif age_seconds > 90:
                exchange_status = "DEGRADED"

        if exchange_status == "OK" and permission_summary is not None and permission_summary.get("status") in {
            "failed",
            "error",
            "not_checked",
        }:
            exchange_status = "DEGRADED"

        # PG status: conservative assessment (config exists != healthy)
        # Only mark as OK when we have verified connectivity
        if runtime_config_provider is None:
            pg_status = "DOWN"
        else:
            # Config exists but no real connectivity probe available
            # Use startup_reconciliation as weak signal of PG health
            if startup_reconciliation_summary is not None:
                # Reconciliation ran, suggesting PG was reachable at startup
                pg_status = "DEGRADED"  # Conservative: was reachable, not sure now
            else:
                pg_status = "DEGRADED"  # Config exists, no connectivity signal

        # Notification status: conservative assessment (webhook URL exists != healthy)
        if runtime_config_provider is None:
            notification_status = "DOWN"
        else:
            # Config exists but no delivery success signal available
            notification_status = "DEGRADED"  # Conservative: not verified

        breaker_symbols: list[str] = []
        if execution_orchestrator is not None and hasattr(execution_orchestrator, "list_circuit_breaker_symbols"):
            breaker_symbols = execution_orchestrator.list_circuit_breaker_symbols()

        active_recovery_tasks = []
        if execution_recovery_repo is not None and hasattr(execution_recovery_repo, "list_active"):
            active_recovery_tasks = await execution_recovery_repo.list_active()

        startup_markers = {
            "runtime_config": "PASSED" if runtime_config_provider is not None else "FAILED",
            "exchange_gateway": "PASSED" if exchange_gateway is not None else "FAILED",
            "permission_check": "PASSED"
            if permission_summary and permission_summary.get("verified")
            else "FAILED"
            if permission_summary and permission_summary.get("status") == "failed"
            else "PENDING",
            "startup_reconciliation": "PASSED"
            if startup_reconciliation_summary is not None
            else "PENDING",
            "breaker_rebuild": "PASSED" if execution_orchestrator is not None else "PENDING",
            "signal_pipeline": "PASSED",  # Placeholder, always OK for now
        }

        recent_warnings: list[str] = []
        if permission_summary and permission_summary.get("status") == "skipped_testnet":
            recent_warnings.append("withdraw permission check skipped on testnet")
        if exchange_status == "DEGRADED":
            recent_warnings.append("exchange health degraded")
        if pg_status == "DOWN":
            recent_warnings.append("pg config unavailable")
        elif pg_status == "DEGRADED":
            recent_warnings.append("pg connectivity not verified")
        if notification_status == "DOWN":
            recent_warnings.append("notification config unavailable")
        elif notification_status == "DEGRADED":
            recent_warnings.append("notification delivery not verified")

        recent_errors: list[str] = []
        if exchange_status == "DOWN":
            recent_errors.append("exchange heartbeat stale")
        if permission_summary and permission_summary.get("status") == "failed":
            recent_errors.append("exchange permission check failed")

        completed_tasks = 0
        last_recovery_time = None
        if startup_reconciliation_summary:
            completed_tasks = int(startup_reconciliation_summary.get("pg_recovery_resolved_count", 0))

        if active_recovery_tasks:
            latest_retry = max(
                (
                    task.get("updated_at")
                    or task.get("next_retry_at")
                    or task.get("created_at")
                    for task in active_recovery_tasks
                ),
                default=None,
            )
            if latest_retry:
                if isinstance(latest_retry, datetime):
                    last_recovery_time = latest_retry.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
                else:
                    last_recovery_time = str(latest_retry)

        return RuntimeHealthResponse(
            pg_status=pg_status,
            exchange_status=exchange_status,
            notification_status=notification_status,
            recent_warnings=recent_warnings,
            recent_errors=recent_errors,
            startup_markers=startup_markers,
            breaker_summary=BreakerSummaryResponse(
                total_tripped=len(breaker_symbols),
                active_breakers=breaker_symbols,
                last_trip_time=None,
            ),
            recovery_summary=RecoverySummaryResponse(
                pending_tasks=len(active_recovery_tasks),
                completed_tasks=completed_tasks,
                last_recovery_time=last_recovery_time,
            ),
        )

