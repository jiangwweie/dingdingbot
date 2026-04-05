"""
Configuration Manager - Database-driven configuration management.

This module provides database-driven configuration management with:
- SQLite persistence for all configurations
- Hot-reload support via observer pattern
- Automatic snapshot creation on config changes
- Backward compatibility with YAML files

Architecture:
- ConfigManager: Main configuration manager (replaces YAML-based version)
- Uses repositories from src.infrastructure.config_repositories
- Integrates with ConfigSnapshotService for version control
"""
import asyncio
import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable, Awaitable, Set
from uuid import uuid4

import aiosqlite
import yaml
from pydantic import BaseModel, ValidationError

from src.domain.exceptions import FatalStartupError
from src.domain.models import (
    RiskConfig,
    StrategyDefinition,
    TriggerConfig,
    FilterConfig,
)
from src.infrastructure.logger import logger, register_secret, mask_secret
from src.infrastructure.repositories import (
    SystemConfigRepository,
    RiskConfigRepository,
    StrategyConfigRepository as StrategyRepository,
    SymbolConfigRepository as SymbolRepository,
    NotificationConfigRepository as NotificationRepository,
    ConfigHistoryRepository,
)
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.application.config_snapshot_service import ConfigSnapshotService


# ============================================================
# Pydantic Config Models (same as original for compatibility)
# ============================================================

from pydantic import Field, field_validator


class PinbarDefaults(BaseModel):
    min_wick_ratio: Decimal = Field(..., description="Minimum wick ratio")
    max_body_ratio: Decimal = Field(..., description="Maximum body ratio")
    body_position_tolerance: Decimal = Field(..., description="Body position tolerance")

    @field_validator('min_wick_ratio', 'max_body_ratio', 'body_position_tolerance')
    @classmethod
    def validate_decimal_range(cls, v):
        if v < 0 or v > 1:
            raise ValueError("Value must be between 0 and 1")
        return v


class EmaConfig(BaseModel):
    period: int = Field(..., ge=1, description="EMA period")


class MtfMapping(BaseModel):
    model_config = {'extra': 'allow'}


class WarmupConfig(BaseModel):
    history_bars: int = Field(..., ge=10, description="Number of historical bars to fetch")


class SignalQueueConfig(BaseModel):
    """Queue configuration for async I/O."""
    batch_size: int = Field(default=10, ge=1, description="批量落盘大小")
    flush_interval: float = Field(default=5.0, ge=0.1, description="最大等待时间 (秒)")
    max_queue_size: int = Field(default=1000, ge=100, description="队列最大容量")


class SignalPipelineConfig(BaseModel):
    cooldown_seconds: int = Field(default=14400, ge=60, description="Signal deduplication cooldown in seconds")
    queue: SignalQueueConfig = Field(default_factory=SignalQueueConfig)


class CoreConfig(BaseModel):
    """Core system configuration (read-only)"""
    core_symbols: List[str] = Field(..., min_length=1, description="Core trading symbols")
    pinbar_defaults: PinbarDefaults
    ema: EmaConfig
    mtf_mapping: MtfMapping

    # S3-1: Add MTF EMA period config
    mtf_ema_period: int = Field(
        default=60,
        description="Default EMA period for MTF trend calculation",
        ge=5,
        le=200
    )

    warmup: WarmupConfig
    signal_pipeline: SignalPipelineConfig = Field(default_factory=SignalPipelineConfig)


class ExchangeConfig(BaseModel):
    name: str = Field(..., description="Exchange name (ccxt id)")
    api_key: str = Field(..., description="API Key (read-only permission required)")
    api_secret: str = Field(..., description="API Secret")
    testnet: bool = Field(default=False, description="Use testnet")


class StrategyConfig(BaseModel):
    """
    Legacy strategy config (for backward compatibility).
    New systems should use active_strategies instead.
    """
    trend_filter_enabled: bool = Field(default=True, description="Enable EMA60 trend filter")
    mtf_validation_enabled: bool = Field(default=True, description="Enable MTF validation")


class AssetPollingConfig(BaseModel):
    interval_seconds: int = Field(default=60, ge=10, description="Asset polling interval")


class NotificationChannel(BaseModel):
    type: str = Field(..., description="Channel type: feishu or wecom")
    webhook_url: str = Field(..., description="Webhook URL")

    @field_validator('type')
    @classmethod
    def validate_channel_type(cls, v):
        if v not in ('feishu', 'wecom'):
            raise ValueError("Channel type must be 'feishu' or 'wecom'")
        return v


class NotificationConfig(BaseModel):
    channels: List[NotificationChannel] = Field(..., min_length=1, description="Notification channels")


class UserConfig(BaseModel):
    """User configuration (modifiable)"""
    exchange: ExchangeConfig
    user_symbols: List[str] = Field(default_factory=list, description="User-defined symbols")
    timeframes: List[str] = Field(..., min_length=1, description="Timeframes to monitor")
    # New dynamic rule engine config (Phase K)
    active_strategies: List[StrategyDefinition] = Field(
        default_factory=list,
        description="Active strategy definitions with attached filters"
    )
    # Legacy support - if active_strategies is empty, migrate from old strategy config
    strategy: Optional[StrategyConfig] = Field(default=None, description="Legacy strategy config (deprecated)")
    risk: RiskConfig
    asset_polling: AssetPollingConfig = Field(default_factory=AssetPollingConfig)
    notification: NotificationConfig

    # MTF Configuration (S3-1)
    mtf_ema_period: int = Field(
        default=60,
        description="EMA period for MTF trend calculation",
        ge=5,
        le=200
    )
    mtf_mapping: Dict[str, str] = Field(
        default_factory=lambda: {
            "15m": "1h",
            "1h": "4h",
            "4h": "1d",
            "1d": "1w",
        },
        description="MTF timeframe mapping: lower -> higher"
    )

    model_config = {'protected_namespaces': ()}

    @field_validator('mtf_ema_period')
    @classmethod
    def validate_mtf_ema_period(cls, v):
        if v < 5 or v > 200:
            raise ValueError("mtf_ema_period must be between 5 and 200")
        return v


# ============================================================
# Config Manager - Database-driven version
# ============================================================

class ConfigManager:
    """
    Database-driven configuration manager.

    Features:
    - SQLite persistence for all configurations
    - Hot-reload support via observer pattern
    - Automatic snapshot creation on config changes
    - Backward compatibility with YAML files

    Usage:
        config_manager = ConfigManager()
        await config_manager.initialize_from_db()

        # Load configurations
        core_config = config_manager.get_core_config()
        user_config = await config_manager.get_user_config()

        # Update configuration
        await config_manager.update_risk_config(new_risk_config)
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        config_dir: Optional[str] = None,
    ):
        """
        Initialize ConfigManager.

        Args:
            db_path: Path to SQLite database file. Defaults to ./data/v3_dev.db
            config_dir: Directory containing YAML config files (for backward compatibility)
        """
        # Database path
        if db_path:
            self.db_path = db_path
        else:
            self.db_path = os.environ.get(
                "CONFIG_DB_PATH",
                str(Path(__file__).parent.parent.parent / "data" / "v3_dev.db")
            )

        # Config directory (for YAML backward compatibility)
        if config_dir:
            self.config_dir = Path(config_dir)
        else:
            self.config_dir = Path(__file__).parent.parent.parent / 'config'

        # Database connection (initialized later)
        self._db: Optional[aiosqlite.Connection] = None
        self._lock: Optional[asyncio.Lock] = None

        # Configuration caches
        self._system_config_cache: Optional[Dict[str, Any]] = None
        self._risk_config_cache: Optional[RiskConfig] = None

        # Hot-reload state
        self._observers: Set[Callable[[], Awaitable[None]]] = set()

        # Snapshot service (for auto-snapshot hook)
        self._snapshot_service: Optional["ConfigSnapshotService"] = None

        # YAML fallback flag
        self._use_yaml_fallback = True

    def _ensure_lock(self) -> asyncio.Lock:
        """Ensure lock is created for current event loop."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.Lock()

        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def initialize_from_db(self) -> None:
        """
        Initialize database connection and create default configurations.

        This method is idempotent - calling it multiple times has no effect
        after first initialization.
        """
        if self._db is not None:
            # Already initialized
            return

        async with self._ensure_lock():
            # Create data directory if not exists
            db_dir = os.path.dirname(self.db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)

            # Open database connection
            self._db = await aiosqlite.connect(self.db_path)
            self._db.row_factory = aiosqlite.Row

            # Enable WAL mode for high concurrency
            await self._db.execute("PRAGMA journal_mode=WAL")
            await self._db.execute("PRAGMA synchronous=NORMAL")
            await self._db.execute("PRAGMA wal_autocheckpoint=1000")

            # Create tables if not exists
            await self._create_tables()

            # Initialize default configurations
            await self._initialize_default_configs()

            # Load configurations into cache
            await self._load_system_config()
            await self._load_risk_config()

        logger.info(f"ConfigManager initialized from database: {self.db_path}")

    async def _create_tables(self) -> None:
        """Create configuration tables if not exists."""
        # Read schema from SQL file
        sql_path = Path(__file__).parent.parent / "infrastructure" / "db" / "config_tables.sql"

        if sql_path.exists():
            with open(sql_path, "r", encoding="utf-8") as f:
                schema_sql = f.read()
            await self._db.executescript(schema_sql)
        else:
            # Inline schema (fallback)
            await self._db.executescript("""
                CREATE TABLE IF NOT EXISTS strategies (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    trigger_config TEXT NOT NULL,
                    filter_configs TEXT NOT NULL,
                    filter_logic TEXT DEFAULT 'AND',
                    symbols TEXT NOT NULL,
                    timeframes TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    version INTEGER DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS risk_configs (
                    id TEXT PRIMARY KEY DEFAULT 'global',
                    max_loss_percent DECIMAL(5,4) NOT NULL,
                    max_leverage INTEGER NOT NULL,
                    max_total_exposure DECIMAL(5,4),
                    cooldown_minutes INTEGER DEFAULT 240,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS system_configs (
                    id TEXT PRIMARY KEY DEFAULT 'global',
                    core_symbols TEXT NOT NULL,
                    ema_period INTEGER DEFAULT 60,
                    mtf_ema_period INTEGER DEFAULT 60,
                    mtf_mapping TEXT NOT NULL,
                    signal_cooldown_seconds INTEGER DEFAULT 14400,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS symbols (
                    symbol TEXT PRIMARY KEY,
                    is_active BOOLEAN DEFAULT TRUE,
                    is_core BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS notifications (
                    id TEXT PRIMARY KEY,
                    channel_type TEXT NOT NULL,
                    webhook_url TEXT NOT NULL,
                    is_active BOOLEAN DEFAULT TRUE,
                    notify_on_signal BOOLEAN DEFAULT TRUE,
                    notify_on_order BOOLEAN DEFAULT TRUE,
                    notify_on_error BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS config_snapshots (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    snapshot_data TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_by TEXT,
                    is_auto BOOLEAN DEFAULT FALSE
                );

                CREATE TABLE IF NOT EXISTS config_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    old_values TEXT,
                    new_values TEXT,
                    changed_by TEXT,
                    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    change_summary TEXT
                );
            """)

        await self._db.commit()

    async def _initialize_default_configs(self) -> None:
        """Initialize default configurations if not exists."""
        # Initialize system config
        async with self._db.execute(
            "SELECT id FROM system_configs WHERE id = 'global'"
        ) as cursor:
            if not await cursor.fetchone():
                await self._db.execute("""
                    INSERT INTO system_configs
                    (id, core_symbols, ema_period, mtf_ema_period, mtf_mapping, signal_cooldown_seconds)
                    VALUES ('global', ?, 60, 60, ?, 14400)
                """, (
                    json.dumps(["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT"]),
                    json.dumps({"15m": "1h", "1h": "4h", "4h": "1d", "1d": "1w"}),
                ))

        # Initialize risk config
        async with self._db.execute(
            "SELECT id FROM risk_configs WHERE id = 'global'"
        ) as cursor:
            if not await cursor.fetchone():
                await self._db.execute("""
                    INSERT INTO risk_configs
                    (id, max_loss_percent, max_leverage, max_total_exposure, cooldown_minutes)
                    VALUES ('global', 0.01, 10, 0.8, 240)
                """)

        # Initialize core symbols
        core_symbols = [
            ("BTC/USDT:USDT", True),
            ("ETH/USDT:USDT", True),
            ("SOL/USDT:USDT", True),
            ("BNB/USDT:USDT", True),
        ]
        for symbol, is_core in core_symbols:
            await self._db.execute("""
                INSERT OR IGNORE INTO symbols (symbol, is_core, is_active)
                VALUES (?, ?, ?)
            """, (symbol, is_core, True))

        await self._db.commit()

    async def _load_system_config(self) -> Dict[str, Any]:
        """Load system configuration from database."""
        async with self._db.execute(
            "SELECT * FROM system_configs WHERE id = 'global'"
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                self._system_config_cache = {
                    "core_symbols": json.loads(row["core_symbols"]),
                    "ema_period": row["ema_period"],
                    "mtf_ema_period": row["mtf_ema_period"],
                    "mtf_mapping": json.loads(row["mtf_mapping"]),
                    "signal_cooldown_seconds": row["signal_cooldown_seconds"],
                }
            else:
                self._system_config_cache = {
                    "core_symbols": ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT"],
                    "ema_period": 60,
                    "mtf_ema_period": 60,
                    "mtf_mapping": {"15m": "1h", "1h": "4h", "4h": "1d", "1d": "1w"},
                    "signal_cooldown_seconds": 14400,
                }
        return self._system_config_cache

    async def _load_risk_config(self) -> RiskConfig:
        """Load risk configuration from database."""
        async with self._db.execute(
            "SELECT * FROM risk_configs WHERE id = 'global'"
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                self._risk_config_cache = RiskConfig(
                    max_loss_percent=Decimal(str(row["max_loss_percent"])),
                    max_leverage=row["max_leverage"],
                    max_total_exposure=Decimal(str(row["max_total_exposure"] or "0.8")),
                )
            else:
                self._risk_config_cache = RiskConfig(
                    max_loss_percent=Decimal("0.01"),
                    max_leverage=10,
                    max_total_exposure=Decimal("0.8"),
                )
        return self._risk_config_cache

    def get_core_config(self) -> CoreConfig:
        """
        Get core configuration.

        Note: This is a synchronous method that returns cached config.
        For database-driven config, use get_core_config_async().
        """
        if self._system_config_cache is None:
            # Synchronous fallback - load from YAML
            return self._load_core_config_from_yaml()

        return CoreConfig(
            core_symbols=self._system_config_cache["core_symbols"],
            pinbar_defaults=PinbarDefaults(
                min_wick_ratio=Decimal("0.6"),
                max_body_ratio=Decimal("0.3"),
                body_position_tolerance=Decimal("0.1"),
            ),
            ema=EmaConfig(period=self._system_config_cache["ema_period"]),
            mtf_mapping=MtfMapping(**self._system_config_cache["mtf_mapping"]),
            mtf_ema_period=self._system_config_cache["mtf_ema_period"],
            warmup=WarmupConfig(history_bars=100),
            signal_pipeline=SignalPipelineConfig(
                cooldown_seconds=self._system_config_cache["signal_cooldown_seconds"]
            ),
        )

    async def get_core_config_async(self) -> CoreConfig:
        """Get core configuration from database asynchronously."""
        if self._db is None:
            # Not initialized - fallback to YAML
            return self._load_core_config_from_yaml()

        await self._load_system_config()
        return self.get_core_config()

    def _load_core_config_from_yaml(self) -> CoreConfig:
        """Load core config from YAML file (fallback for backward compatibility)."""
        core_path = self.config_dir / 'core.yaml'

        if not core_path.exists():
            # Return default config
            return CoreConfig(
                core_symbols=["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT"],
                pinbar_defaults=PinbarDefaults(
                    min_wick_ratio=Decimal("0.6"),
                    max_body_ratio=Decimal("0.3"),
                    body_position_tolerance=Decimal("0.1"),
                ),
                ema=EmaConfig(period=60),
                mtf_mapping=MtfMapping(**{"15m": "1h", "1h": "4h", "4h": "1d", "1d": "1w"}),
                mtf_ema_period=60,
                warmup=WarmupConfig(history_bars=100),
                signal_pipeline=SignalPipelineConfig(cooldown_seconds=14400),
            )

        with open(core_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        return CoreConfig(**data)

    async def get_user_config(self) -> UserConfig:
        """
        Get user configuration from database.

        Returns:
            UserConfig with all settings from database
        """
        if self._db is None:
            # Not initialized - fallback to YAML
            return self._load_user_config_from_yaml()

        # Build UserConfig from database
        # For now, load exchange and notification from YAML (backward compatibility)
        # In production, these would be stored in database
        user_config_dict = await self._build_user_config_dict()

        return UserConfig(**user_config_dict)

    async def _build_user_config_dict(self) -> Dict[str, Any]:
        """Build user config dictionary from database."""
        # Load from YAML for backward compatibility
        # TODO: Migrate to full database storage
        yaml_config = self._load_user_config_from_yaml()

        # Override with database configs
        await self._load_system_config()
        await self._load_risk_config()

        return {
            "exchange": yaml_config.exchange,
            "user_symbols": [],  # Will be loaded from symbols table
            "timeframes": yaml_config.timeframes,
            "active_strategies": await self._load_strategies_from_db(),
            "risk": self._risk_config_cache,
            "asset_polling": yaml_config.asset_polling,
            "notification": await self._build_notification_config(),
            "mtf_ema_period": self._system_config_cache.get("mtf_ema_period", 60),
            "mtf_mapping": self._system_config_cache.get("mtf_mapping", {}),
        }

    async def _load_strategies_from_db(self) -> List[StrategyDefinition]:
        """Load strategies from database."""
        if self._db is None:
            return []

        async with self._db.execute(
            "SELECT * FROM strategies WHERE is_active = TRUE"
        ) as cursor:
            rows = await cursor.fetchall()
            strategies = []
            for row in rows:
                try:
                    trigger_data = json.loads(row["trigger_config"])
                    filter_data = json.loads(row["filter_configs"])

                    trigger = TriggerConfig(
                        type=trigger_data.get("type", "pinbar"),
                        enabled=trigger_data.get("enabled", True),
                        params=trigger_data.get("params", {}),
                    )

                    filters = [
                        FilterConfig(
                            type=f.get("type", "ema"),
                            enabled=f.get("enabled", True),
                            params=f.get("params", {}),
                        )
                        for f in filter_data
                    ]

                    strategies.append(StrategyDefinition(
                        id=row["id"],
                        name=row["name"],
                        trigger=trigger,
                        filters=filters,
                        filter_logic=row["filter_logic"] or "AND",
                    ))
                except Exception as e:
                    logger.error(f"Failed to parse strategy: {e}")

            return strategies

    async def _build_notification_config(self) -> NotificationConfig:
        """Build notification config from database."""
        if self._db is None:
            # Fallback to YAML
            return self._load_user_config_from_yaml().notification

        async with self._db.execute(
            "SELECT * FROM notifications WHERE is_active = TRUE"
        ) as cursor:
            rows = await cursor.fetchall()
            channels = []
            for row in rows:
                channels.append(NotificationChannel(
                    type=row["channel_type"],
                    webhook_url=row["webhook_url"],
                ))

            if not channels:
                # Fallback to YAML
                return self._load_user_config_from_yaml().notification

            return NotificationConfig(channels=channels)

    def _load_user_config_from_yaml(self) -> UserConfig:
        """Load user config from YAML file (fallback for backward compatibility)."""
        user_path = self.config_dir / 'user.yaml'

        if not user_path.exists():
            # Return minimal default config
            return UserConfig(
                exchange=ExchangeConfig(
                    name="binance",
                    api_key="placeholder",
                    api_secret="placeholder",
                    testnet=True,
                ),
                timeframes=["15m", "1h"],
                risk=RiskConfig(
                    max_loss_percent=Decimal("0.01"),
                    max_leverage=10,
                    max_total_exposure=Decimal("0.8"),
                ),
                notification=NotificationConfig(
                    channels=[NotificationChannel(
                        type="feishu",
                        webhook_url="https://placeholder",
                    )]
                ),
            )

        with open(user_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        return UserConfig(**data)

    async def close(self) -> None:
        """Close database connection."""
        if self._db:
            await self._db.close()
            self._db = None

    # ============================================================
    # Configuration Update Methods
    # ============================================================

    async def update_risk_config(self, config: RiskConfig, changed_by: str = "user") -> None:
        """
        Update risk configuration with auto-snapshot.

        Args:
            config: New RiskConfig
            changed_by: User identifier for audit trail
        """
        if self._db is None:
            raise FatalStartupError("Database not initialized", "F-003")

        async with self._ensure_lock():
            # Create auto-snapshot before update
            if self._snapshot_service:
                try:
                    user_config = await self.get_user_config()
                    await self._snapshot_service.create_auto_snapshot(
                        config=user_config,
                        description=f"风控配置变更 - {changed_by}"
                    )
                except Exception as e:
                    logger.warning(f"Auto-snapshot failed: {e}")

            # Update database
            now = datetime.now(timezone.utc).isoformat()
            await self._db.execute("""
                UPDATE risk_configs
                SET max_loss_percent = ?, max_leverage = ?,
                    max_total_exposure = ?, updated_at = ?
                WHERE id = 'global'
            """, (
                float(config.max_loss_percent),
                config.max_leverage,
                float(config.max_total_exposure),
                now,
            ))

            # Log history
            await self._log_config_change(
                entity_type="risk_config",
                entity_id="global",
                action="UPDATE",
                new_values={
                    "max_loss_percent": float(config.max_loss_percent),
                    "max_leverage": config.max_leverage,
                    "max_total_exposure": float(config.max_total_exposure),
                },
                changed_by=changed_by,
            )

            await self._db.commit()

            # Invalidate cache
            self._risk_config_cache = config

            # Notify observers
            await self._notify_observers()

    async def save_strategy(
        self,
        strategy: StrategyDefinition,
        changed_by: str = "user",
    ) -> str:
        """
        Save strategy (create or update).

        Args:
            strategy: StrategyDefinition to save
            changed_by: User identifier

        Returns:
            Strategy ID
        """
        if self._db is None:
            raise FatalStartupError("Database not initialized", "F-003")

        strategy_id = strategy.id or str(uuid4())

        async with self._ensure_lock():
            # Serialize trigger and filters
            trigger_config = json.dumps({
                "type": strategy.trigger.type if strategy.trigger else "pinbar",
                "enabled": strategy.trigger.enabled if strategy.trigger else True,
                "params": strategy.trigger.params if strategy.trigger else {},
            })

            filter_configs = json.dumps([
                {"type": f.type, "enabled": getattr(f, "enabled", True), "params": f.params or {}}
                for f in strategy.filters
            ])

            now = datetime.now(timezone.utc).isoformat()

            # Check if strategy exists
            async with self._db.execute(
                "SELECT id, version FROM strategies WHERE id = ?", (strategy_id,)
            ) as cursor:
                existing = await cursor.fetchone()

            if existing:
                # Update existing strategy
                await self._db.execute("""
                    UPDATE strategies
                    SET name = ?, description = ?, is_active = ?,
                        trigger_config = ?, filter_configs = ?,
                        filter_logic = ?, symbols = ?, timeframes = ?,
                        updated_at = ?, version = version + 1
                    WHERE id = ?
                """, (
                    strategy.name,
                    getattr(strategy, 'description', None),
                    getattr(strategy, 'enabled', True),
                    trigger_config,
                    filter_configs,
                    strategy.filter_logic,
                    json.dumps(strategy.apply_to if strategy.apply_to else []),
                    json.dumps([]),
                    now,
                    strategy_id,
                ))
            else:
                # Insert new strategy
                await self._db.execute("""
                    INSERT INTO strategies
                    (id, name, description, is_active, trigger_config, filter_configs,
                     filter_logic, symbols, timeframes, updated_at, version)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """, (
                    strategy_id,
                    strategy.name,
                    getattr(strategy, 'description', None),
                    getattr(strategy, 'enabled', True),
                    trigger_config,
                    filter_configs,
                    strategy.filter_logic,
                    json.dumps(strategy.apply_to if strategy.apply_to else []),
                    json.dumps([]),
                    now,
                ))

            # Log history
            await self._log_config_change(
                entity_type="strategy",
                entity_id=strategy_id,
                action="CREATE" if not existing else "UPDATE",
                new_values={"name": strategy.name},
                changed_by=changed_by,
            )

            await self._db.commit()

            # Notify observers
            await self._notify_observers()

        return strategy_id

    async def delete_strategy(self, strategy_id: str, changed_by: str = "user") -> bool:
        """Delete strategy by ID."""
        if self._db is None:
            raise FatalStartupError("Database not initialized", "F-003")

        async with self._ensure_lock():
            cursor = await self._db.execute(
                "DELETE FROM strategies WHERE id = ?", (strategy_id,)
            )

            if cursor.rowcount > 0:
                # Log history
                await self._log_config_change(
                    entity_type="strategy",
                    entity_id=strategy_id,
                    action="DELETE",
                    changed_by=changed_by,
                )

                await self._db.commit()

                # Notify observers
                await self._notify_observers()

                return True

            return False

    async def _log_config_change(
        self,
        entity_type: str,
        entity_id: str,
        action: str,
        old_values: Optional[Dict[str, Any]] = None,
        new_values: Optional[Dict[str, Any]] = None,
        changed_by: str = "system",
        change_summary: Optional[str] = None,
    ) -> None:
        """Log a configuration change to history table."""
        await self._db.execute("""
            INSERT INTO config_history
            (entity_type, entity_id, action, old_values, new_values, changed_by, change_summary)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            entity_type,
            entity_id,
            action,
            json.dumps(old_values) if old_values else None,
            json.dumps(new_values) if new_values else None,
            changed_by,
            change_summary,
        ))

    # ============================================================
    # Observer Pattern (Hot-reload)
    # ============================================================

    def add_observer(self, callback: Callable[[], Awaitable[None]]) -> None:
        """Add an observer callback for config changes."""
        self._observers.add(callback)

    def remove_observer(self, callback: Callable[[], Awaitable[None]]) -> None:
        """Remove an observer callback."""
        self._observers.discard(callback)

    async def _notify_observers(self) -> None:
        """Notify all observers of config changes."""
        if not self._observers:
            return

        results = await asyncio.gather(
            *[self._safe_observer_call(cb) for cb in self._observers],
            return_exceptions=True
        )

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Observer {i} failed: {result}")

    async def _safe_observer_call(self, callback: Callable[[], Awaitable[None]]) -> Any:
        """Safely call an observer, catching any exceptions."""
        try:
            return await callback()
        except Exception as e:
            logger.error(f"Observer callback raised: {e}")
            raise

    def set_snapshot_service(self, snapshot_service: "ConfigSnapshotService") -> None:
        """Inject snapshot service for auto-snapshot hooks."""
        self._snapshot_service = snapshot_service
        logger.info("Snapshot service injected for auto-snapshot hooks")

    # ============================================================
    # YAML Backward Compatibility
    # ============================================================

    async def import_from_yaml(self, yaml_path: str) -> None:
        """Import configuration from YAML file."""
        if not os.path.exists(yaml_path):
            raise FileNotFoundError(f"YAML file not found: {yaml_path}")

        with open(yaml_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        # TODO: Parse and import into database
        logger.info(f"Configuration imported from {yaml_path}")

    async def export_to_yaml(self, yaml_path: str) -> None:
        """Export current configuration to YAML file."""
        # TODO: Export database config to YAML
        logger.info(f"Configuration exported to {yaml_path}")


# ============================================================
# Convenience function
# ============================================================

async def load_all_configs_async(
    db_path: Optional[str] = None,
    config_dir: Optional[str] = None,
) -> ConfigManager:
    """
    Load all configurations from database and return ConfigManager instance.

    Args:
        db_path: Path to SQLite database
        config_dir: Path to YAML config directory (for backward compatibility)

    Returns:
        ConfigManager with all configs loaded
    """
    manager = ConfigManager(db_path=db_path, config_dir=config_dir)
    await manager.initialize_from_db()
    return manager


def load_all_configs(config_dir: Optional[str] = None) -> ConfigManager:
    """
    Load all configurations (YAML version for backward compatibility).

    This is the legacy synchronous version that loads from YAML files.
    For database-driven config, use load_all_configs_async().

    Args:
        config_dir: Optional config directory path

    Returns:
        ConfigManager with all configs loaded
    """
    manager = ConfigManager(config_dir=config_dir)
    # Don't initialize from DB - use YAML fallback
    return manager
