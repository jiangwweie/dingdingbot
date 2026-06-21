"""Shared config globals for the current BRC FastAPI composition root."""
from typing import Optional, Any

# Config repositories for the current runtime composition root.
_strategy_repo: Optional[Any] = None  # StrategyConfigRepository instance
_risk_repo: Optional[Any] = None  # RiskConfigRepository instance
_system_repo: Optional[Any] = None  # SystemConfigRepository instance
_symbol_repo: Optional[Any] = None  # SymbolConfigRepository instance
_notification_repo: Optional[Any] = None  # NotificationConfigRepository instance
_history_repo: Optional[Any] = None  # ConfigHistoryRepository instance
_snapshot_repo: Optional[Any] = None  # ConfigSnapshotRepositoryExtended instance
_config_manager: Optional[Any] = None  # ConfigManager for hot-reload
_observer: Optional[Any] = None  # Observer for hot-reload notifications
