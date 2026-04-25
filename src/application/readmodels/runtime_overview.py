from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from src.application.readmodels.console_models import RuntimeOverviewResponse


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _to_iso_from_millis(timestamp_ms: Optional[int]) -> str:
    if not timestamp_ms:
        return _iso_now()
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _freshness_from_age(age_seconds: float) -> str:
    if age_seconds <= 90:
        return "Fresh"
    if age_seconds <= 300:
        return "Stale"
    return "Possibly Dead"


class RuntimeOverviewReadModel:
    async def build(
        self,
        *,
        runtime_config_provider: Optional[Any],
        account_snapshot: Optional[Any],
        exchange_gateway: Optional[Any],
        execution_orchestrator: Optional[Any],
        startup_reconciliation_summary: Optional[dict[str, Any]],
    ) -> RuntimeOverviewResponse:
        now = datetime.now(timezone.utc)
        server_time = now.isoformat().replace("+00:00", "Z")

        runtime_update_at = _to_iso_from_millis(getattr(account_snapshot, "timestamp", None))
        heartbeat_at = runtime_update_at

        snapshot_ts = getattr(account_snapshot, "timestamp", None)
        if snapshot_ts:
            age_seconds = max(0.0, now.timestamp() - (snapshot_ts / 1000))
        else:
            age_seconds = 999999.0

        freshness_status = _freshness_from_age(age_seconds)

        if runtime_config_provider is not None:
            resolved = runtime_config_provider.resolved_config
            environment = resolved.environment
            market = resolved.market
            profile = resolved.profile_name
            version = str(resolved.version)
            config_hash = resolved.config_hash
            frozen = True
            symbol = market.primary_symbol
            timeframe = market.primary_timeframe
            backend_summary = (
                f"intent={environment.core_execution_intent_backend}, "
                f"order={environment.core_order_backend}, "
                f"position={environment.core_position_backend}"
            )
            pg_health = "OK" if environment.pg_database_url.get_secret_value() else "DOWN"
            webhook_health = "OK" if environment.feishu_webhook_url.get_secret_value() else "DOWN"
        else:
            profile = "unavailable"
            version = "unavailable"
            config_hash = "unavailable"
            frozen = False
            symbol = "unavailable"
            timeframe = "unavailable"
            backend_summary = "unavailable"
            pg_health = "DOWN"
            webhook_health = "DOWN"

        permission_summary = (
            exchange_gateway.get_permission_check_summary()
            if exchange_gateway is not None and hasattr(exchange_gateway, "get_permission_check_summary")
            else None
        )

        # Exchange health: prioritize freshness, then permission check
        exchange_health = "OK"
        if freshness_status == "Possibly Dead":
            exchange_health = "DOWN"
        elif freshness_status == "Stale":
            exchange_health = "DEGRADED"
        elif permission_summary is not None and permission_summary.get("status") in {
            "failed",
            "error",
            "not_checked",
        }:
            exchange_health = "DEGRADED"

        breaker_symbols = []
        if execution_orchestrator is not None and hasattr(execution_orchestrator, "list_circuit_breaker_symbols"):
            breaker_symbols = execution_orchestrator.list_circuit_breaker_symbols()

        if startup_reconciliation_summary:
            reconciliation_summary = (
                f"candidates={startup_reconciliation_summary.get('candidate_orders_count', 0)}, "
                f"failed={startup_reconciliation_summary.get('failed_reconciliations_count', 0)}"
            )
        else:
            reconciliation_summary = "not_run"

        return RuntimeOverviewResponse(
            profile=profile,
            version=version,
            hash=config_hash,
            frozen=frozen,
            symbol=symbol,
            timeframe=timeframe,
            mode="SIM-1",
            backend_summary=backend_summary,
            exchange_health=exchange_health,
            pg_health=pg_health,
            webhook_health=webhook_health,
            breaker_count=len(breaker_symbols),
            reconciliation_summary=reconciliation_summary,
            server_time=server_time,
            last_runtime_update_at=runtime_update_at,
            last_heartbeat_at=heartbeat_at,
            freshness_status=freshness_status,
        )

