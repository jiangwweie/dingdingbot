"""Runtime ownership context for the embedded execution process.

This module is intentionally lightweight: it names the runtime-owned objects
without moving execution behavior into the API layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Optional


@dataclass
class RuntimeContext:
    """Process-local runtime container owned by the main execution process."""

    _LEGACY_ATTR_ALIASES: ClassVar[dict[str, str]] = {
        "_repository": "signal_repository",
        "_signal_repo": "signal_repository",
        "_account_getter": "get_account_snapshot",
    }

    owner: str = "main"
    shutdown_event: Optional[Any] = None
    config_manager: Optional[Any] = None
    runtime_config_provider: Optional[Any] = None
    exchange_gateway: Optional[Any] = None
    notification_service: Optional[Any] = None
    signal_repository: Optional[Any] = None
    config_entry_repo: Optional[Any] = None
    order_repo: Optional[Any] = None
    execution_intent_repo: Optional[Any] = None
    execution_recovery_repo: Optional[Any] = None
    position_repo: Optional[Any] = None
    reconciliation_read_model_repo: Optional[Any] = None
    signal_pipeline: Optional[Any] = None
    account_service: Optional[Any] = None
    order_lifecycle_service: Optional[Any] = None
    capital_protection: Optional[Any] = None
    execution_orchestrator: Optional[Any] = None
    runtime_config_snapshot: Optional[Any] = None
    global_kill_switch_service: Optional[Any] = None
    startup_trading_guard_service: Optional[Any] = None
    account_risk_service: Optional[Any] = None
    campaign_state_service: Optional[Any] = None
    trace_service: Optional[Any] = None
    protection_health_monitor: Optional[Any] = None
    external_close_monitor: Optional[Any] = None
    startup_reconciliation_summary: Optional[dict[str, Any]] = None
    signal_tracker: Optional[Any] = None
    snapshot_service: Optional[Any] = None
    audit_logger: Optional[Any] = None
    strategy_repo: Optional[Any] = None
    risk_repo: Optional[Any] = None
    system_repo: Optional[Any] = None
    symbol_repo: Optional[Any] = None
    notification_repo: Optional[Any] = None
    history_repo: Optional[Any] = None
    snapshot_repo: Optional[Any] = None
    order_watch_tasks: list[Any] = field(default_factory=list)
    periodic_reconciliation_task: Optional[Any] = None
    snapshot_update_task: Optional[Any] = None
    ws_task: Optional[Any] = None
    api_task: Optional[Any] = None
    api_server: Optional[Any] = None
    started: bool = False
    shutdown_source: Optional[str] = None

    def __getattr__(self, name: str) -> Any:
        """Support legacy API code that still reads underscore-prefixed names."""
        alias = self._LEGACY_ATTR_ALIASES.get(name)
        if alias is not None:
            return getattr(self, alias)
        if name.startswith("_"):
            public_name = name[1:]
            if public_name in self.__dataclass_fields__:
                return getattr(self, public_name)
        raise AttributeError(name)

    def get_account_snapshot(self) -> Any:
        if self.exchange_gateway is None:
            return None
        getter = getattr(self.exchange_gateway, "get_account_snapshot", None)
        if getter is None:
            return None
        return getter()

    def block_startup_guard_for_shutdown(self, source: str) -> None:
        if self.startup_trading_guard_service is None:
            return
        self.startup_trading_guard_service.block(
            updated_by="system",
            reason="RUNTIME_SHUTDOWN_RESET",
            source=source,
        )

    async def start(self) -> None:
        """Mark the container as the active owner for its runtime objects."""
        self.started = True
        self.shutdown_source = None

    async def shutdown(self, source: str = "runtime_context_shutdown") -> None:
        """Request runtime shutdown through the owned process-local handles."""
        self.shutdown_source = source
        self.block_startup_guard_for_shutdown(source)
        if self.shutdown_event is not None and hasattr(self.shutdown_event, "set"):
            self.shutdown_event.set()
        self.started = False
