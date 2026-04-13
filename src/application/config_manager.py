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
import copy
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

from src.domain.exceptions import FatalStartupError, DependencyNotReadyError
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
    from src.infrastructure.config_entry_repository import ConfigEntryRepository
    from src.infrastructure.config_profile_repository import ConfigProfileRepository


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


class AtrConfig(BaseModel):
    """ATR (Average True Range) filter configuration."""
    enabled: bool = Field(default=True, description="Enable ATR filter")
    period: int = Field(default=14, ge=1, description="ATR calculation period")
    min_ratio: Decimal = Field(default=Decimal('0.5'), ge=0, description="Minimum ATR ratio for signal validation")


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
    atr: AtrConfig = Field(default_factory=AtrConfig)


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
    enabled: bool = Field(default=True, description="Enable asset polling")
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

        # Repository references (for KV config operations)
        self._config_entry_repo: Optional["ConfigEntryRepository"] = None
        self._config_profile_repo: Optional["ConfigProfileRepository"] = None

        # R9.3: Initialization state and lock for race condition prevention
        self._initialized = False
        self._initializing = False
        self._init_lock: Optional[asyncio.Lock] = None
        self._init_event: Optional[asyncio.Event] = None

        # R3.2: Configuration version for hot-reload consistency
        self._config_version = 0
        self._config_lock: Optional[asyncio.Lock] = None

        # User config cache (populated after initialization for sync access)
        self._user_config_cache: Optional[UserConfig] = None

    def _ensure_init_lock(self) -> asyncio.Lock:
        """Ensure init lock is created for current event loop (R9.3)."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.Lock()

        if self._init_lock is None:
            self._init_lock = asyncio.Lock()
        return self._init_lock

    def _ensure_init_event(self) -> asyncio.Event:
        """Ensure init event is created for current event loop (R9.3)."""
        if self._init_event is None:
            self._init_event = asyncio.Event()
        return self._init_event

    def _ensure_lock(self) -> asyncio.Lock:
        """Ensure lock is created for current event loop."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.Lock()

        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def _ensure_config_lock(self) -> asyncio.Lock:
        """Ensure config lock is created for current event loop (R3.2)."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.Lock()

        if self._config_lock is None:
            self._config_lock = asyncio.Lock()
        return self._config_lock

    def get_config_version(self) -> int:
        """Get current configuration version number (R3.2)."""
        return self._config_version

    async def initialize_from_db(self) -> None:
        """
        Initialize database connection and create default configurations.

        This method is idempotent - calling it multiple times has no effect
        after first initialization.

        R9.3: Uses double-checked locking to prevent race conditions during
        concurrent initialization. Concurrent callers will wait for the first
        initialization to complete.
        """
        # Fast path - already initialized
        if self._initialized:
            return

        # R9.3: Get lock and event for current event loop
        init_lock = self._ensure_init_lock()
        init_event = self._ensure_init_event()

        async with init_lock:
            # Double-check after acquiring lock
            if self._initialized:
                return

            # If already initializing, wait for completion
            if self._initializing:
                logger.debug("ConfigManager: Waiting for concurrent initialization to complete")
                await init_event.wait()
                return

            # Mark as initializing
            self._initializing = True

            try:
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

                # R4.3: Validate configuration integrity and apply defaults if empty
                await self._validate_and_apply_default_configs()

                # Populate _user_config_cache for sync access
                user_config_dict = await self._build_user_config_dict()
                try:
                    self._user_config_cache = UserConfig(**user_config_dict)
                except ValidationError as e:
                    logger.warning(f"Failed to build user config cache: {e}, using default")
                    self._user_config_cache = self._create_default_user_config()

                # Mark as initialized
                self._initialized = True
                init_event.set()  # Notify waiting coroutines
            except Exception:
                # Reset state on failure
                self._initializing = False
                init_event.clear()
                raise
            finally:
                self._initializing = False

        logger.info(f"ConfigManager initialized from database: {self.db_path}")

    def assert_initialized(self) -> None:
        """
        R7.1: Assert that ConfigManager has been fully initialized.

        Other modules should call this method before accessing configuration
        to ensure ConfigManager is ready.

        Raises:
            DependencyNotReadyError: If ConfigManager is not initialized yet
        """
        if not self._initialized:
            if self._initializing:
                raise DependencyNotReadyError(
                    "ConfigManager 正在初始化中，请稍候",
                    "F-003",
                )
            else:
                raise DependencyNotReadyError(
                    "ConfigManager 未初始化 - 请确保在 main.py 中先调用 config_manager.initialize_from_db()",
                    "F-003",
                )

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

                CREATE TABLE IF NOT EXISTS exchange_configs (
                    id TEXT PRIMARY KEY DEFAULT 'primary',
                    exchange_name TEXT NOT NULL DEFAULT 'binance',
                    api_key TEXT NOT NULL,
                    api_secret TEXT NOT NULL,
                    testnet BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    version INTEGER DEFAULT 1
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

        # Handle ALTER TABLE for system_configs new columns (SQLite silent on duplicate column)
        try:
            await self._db.execute("ALTER TABLE system_configs ADD COLUMN timeframes TEXT NOT NULL DEFAULT '[\"15m\",\"1h\"]'")
        except Exception:
            pass
        try:
            await self._db.execute("ALTER TABLE system_configs ADD COLUMN asset_polling_enabled BOOLEAN DEFAULT TRUE")
        except Exception:
            pass
        try:
            await self._db.execute("ALTER TABLE system_configs ADD COLUMN asset_polling_interval INTEGER DEFAULT 60")
        except Exception:
            pass

        await self._db.commit()

    async def _initialize_default_configs(self) -> None:
        """Initialize default configurations if not exists.

        Note: This method creates minimal core configs (system, risk, symbols).
        R4.3: Notification channels are created by _validate_and_apply_default_configs()
        to ensure warning logs are generated when starting with empty database.
        """
        # Initialize system config (with extended fields)
        async with self._db.execute(
            "SELECT id FROM system_configs WHERE id = 'global'"
        ) as cursor:
            if not await cursor.fetchone():
                await self._db.execute("""
                    INSERT INTO system_configs
                    (id, core_symbols, ema_period, mtf_ema_period, mtf_mapping, signal_cooldown_seconds,
                     timeframes, asset_polling_enabled, asset_polling_interval)
                    VALUES ('global', ?, 60, 60, ?, 14400, ?, TRUE, 60)
                """, (
                    json.dumps(["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT"]),
                    json.dumps({"15m": "1h", "1h": "4h", "4h": "1d", "1d": "1w"}),
                    json.dumps(["15m", "1h"]),
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

        # R4.3: Removed notification channel initialization from here
        # It is now handled by _validate_and_apply_default_configs() to generate warning logs

        # Initialize exchange config
        async with self._db.execute(
            "SELECT id FROM exchange_configs WHERE id = 'primary'"
        ) as cursor:
            if not await cursor.fetchone():
                await self._db.execute("""
                    INSERT INTO exchange_configs
                    (id, exchange_name, api_key, api_secret, testnet)
                    VALUES ('primary', 'binance', '', '', TRUE)
                """)

        await self._db.commit()

    async def _validate_and_apply_default_configs(self) -> None:
        """
        R4.3: Validate configuration integrity and apply defaults if empty.

        This method ensures that the system can start even with an empty database
        by applying hard-coded default configurations.
        """
        # Check if database is effectively empty (no user-configured data)
        is_empty = await self._is_empty_config()

        if is_empty:
            logger.warning("数据库配置为空或不完全，使用默认配置启动系统")
            await self._apply_hardcoded_defaults()

    async def _is_empty_config(self) -> bool:
        """
        Check if the database configuration is empty.

        Task A-5: Also checks exchange_configs table.

        Returns:
            True if critical configurations are missing
        """
        # Check for exchange config
        try:
            async with self._db.execute(
                "SELECT COUNT(*) as cnt FROM exchange_configs WHERE id = 'primary'"
            ) as cursor:
                row = await cursor.fetchone()
                if row and row["cnt"] == 0:
                    return True
        except Exception:
            return True  # Table doesn't exist yet

        # Check for notification channels
        async with self._db.execute(
            "SELECT COUNT(*) as cnt FROM notifications WHERE is_active = TRUE"
        ) as cursor:
            row = await cursor.fetchone()
            if row and row["cnt"] == 0:
                return True

        # Check for risk config
        async with self._db.execute(
            "SELECT COUNT(*) as cnt FROM risk_configs WHERE id = 'global'"
        ) as cursor:
            row = await cursor.fetchone()
            if row and row["cnt"] == 0:
                return True

        # Check for system config
        async with self._db.execute(
            "SELECT COUNT(*) as cnt FROM system_configs WHERE id = 'global'"
        ) as cursor:
            row = await cursor.fetchone()
            if row and row["cnt"] == 0:
                return True

        return False

    async def _apply_hardcoded_defaults(self) -> None:
        """
        R4.2/R4.3: Apply hard-coded default configurations to ensure system can start.

        Task A-5: Also initializes exchange config defaults.

        This method inserts minimal required configurations for system startup.
        NOTE: These are hardcoded defaults. User should modify via Config UI.
        """
        # R4.2: Track which defaults were applied for startup warning
        applied_defaults = []

        # Default exchange config (Task A-5)
        try:
            async with self._db.execute(
                "SELECT id FROM exchange_configs WHERE id = 'primary'"
            ) as cursor:
                if not await cursor.fetchone():
                    await self._db.execute("""
                        INSERT INTO exchange_configs
                        (id, exchange_name, api_key, api_secret, testnet)
                        VALUES ('primary', 'binance', '', '', TRUE)
                    """)
                    applied_defaults.append("交易所配置：binance (测试网, 需配置 API Key)")
        except Exception:
            pass  # Table may not exist yet

        # Default risk config
        async with self._db.execute(
            "SELECT id FROM risk_configs WHERE id = 'global'"
        ) as cursor:
            if not await cursor.fetchone():
                await self._db.execute("""
                    INSERT INTO risk_configs
                    (id, max_loss_percent, max_leverage, max_total_exposure, cooldown_minutes)
                    VALUES ('global', 0.01, 10, 0.8, 240)
                """)
                applied_defaults.append("风控配置: max_loss=1%, max_leverage=10x, max_exposure=80%")

        # Default notification channel
        async with self._db.execute(
            "SELECT id FROM notifications LIMIT 1"
        ) as cursor:
            if not await cursor.fetchone():
                await self._db.execute("""
                    INSERT INTO notifications
                    (id, channel_type, webhook_url, is_active, notify_on_signal, notify_on_order, notify_on_error)
                    VALUES ('default', 'feishu', 'https://placeholder.feishu.cn/webhook', TRUE, TRUE, TRUE, TRUE)
                """)
                applied_defaults.append("通知渠道: 飞书占位符 (需配置真实 webhook)")

        # Default system config
        async with self._db.execute(
            "SELECT id FROM system_configs WHERE id = 'global'"
        ) as cursor:
            if not await cursor.fetchone():
                await self._db.execute("""
                    INSERT INTO system_configs
                    (id, core_symbols, ema_period, mtf_ema_period, mtf_mapping, signal_cooldown_seconds,
                     timeframes, asset_polling_enabled, asset_polling_interval)
                    VALUES ('global', ?, 60, 60, ?, 14400, ?, TRUE, 60)
                """, (
                    json.dumps(["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT"]),
                    json.dumps({"15m": "1h", "1h": "4h", "4h": "1d", "1d": "1w"}),
                    json.dumps(["15m", "1h"]),
                ))
                applied_defaults.append("系统配置: core_symbols=BTC/ETH/SOL/BNB, ema_period=60")

        await self._db.commit()

        # R4.2: Startup warning for hardcoded defaults
        if applied_defaults:
            logger.warning(
                "⚠️  [R4.2] 系统使用默认配置启动:\n"
                + "\n".join(f"  - {d}" for d in applied_defaults)
                + "\n建议尽快在配置管理页面修改为适合您交易风格的参数。"
            )
        else:
            logger.info("配置已加载，系统可以安全启动")

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
                    # Extended fields (optional, with defaults from table schema)
                    "warmup_history_bars": row["warmup_history_bars"] if row["warmup_history_bars"] is not None else 100,
                    "atr_filter_enabled": bool(row["atr_filter_enabled"]) if row["atr_filter_enabled"] is not None else True,
                    "atr_period": row["atr_period"] if row["atr_period"] is not None else 14,
                    "atr_min_ratio": str(row["atr_min_ratio"]) if row["atr_min_ratio"] is not None else "0.5",
                    # Extended fields for timeframes and asset polling
                    "timeframes": json.loads(row["timeframes"]) if row["timeframes"] is not None else ["15m", "1h"],
                    "asset_polling_enabled": bool(row["asset_polling_enabled"]) if row["asset_polling_enabled"] is not None else True,
                    "asset_polling_interval": row["asset_polling_interval"] if row["asset_polling_interval"] is not None else 60,
                }
            else:
                self._system_config_cache = {
                    "core_symbols": ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT"],
                    "ema_period": 60,
                    "mtf_ema_period": 60,
                    "mtf_mapping": {"15m": "1h", "1h": "4h", "4h": "1d", "1d": "1w"},
                    "signal_cooldown_seconds": 14400,
                    "warmup_history_bars": 100,
                    "atr_filter_enabled": True,
                    "atr_period": 14,
                    "atr_min_ratio": "0.5",
                    "timeframes": ["15m", "1h"],
                    "asset_polling_enabled": True,
                    "asset_polling_interval": 60,
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
                    daily_max_trades=row["daily_max_trades"] if row["daily_max_trades"] is not None else None,
                    daily_max_loss=Decimal(str(row["daily_max_loss"])) if row["daily_max_loss"] is not None else None,
                    max_position_hold_time=row["max_position_hold_time"] if row["max_position_hold_time"] is not None else None,
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
            # DB not ready - use hardcoded defaults
            return self._build_default_core_config()

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
            warmup=WarmupConfig(history_bars=self._system_config_cache.get("warmup_history_bars", 100)),
            signal_pipeline=SignalPipelineConfig(
                cooldown_seconds=self._system_config_cache["signal_cooldown_seconds"]
            ),
            atr=AtrConfig(
                enabled=self._system_config_cache.get("atr_filter_enabled", True),
                period=self._system_config_cache.get("atr_period", 14),
                min_ratio=Decimal(str(self._system_config_cache.get("atr_min_ratio", "0.5"))) if self._system_config_cache.get("atr_min_ratio") is not None else Decimal("0.5"),
            ),
        )

    async def get_core_config_async(self) -> CoreConfig:
        """Get core configuration from database asynchronously."""
        if self._db is None:
            # Not initialized - use hardcoded defaults
            return self._build_default_core_config()

        await self._load_system_config()
        return self.get_core_config()

    async def get_system_config(self) -> Dict[str, Any]:
        """Get system config from cache as a plain dict."""
        await self._load_system_config()
        return dict(self._system_config_cache)

    async def merge_strategy_monitoring_config(
        self,
        strategy_timeframes: List[str],
        strategy_symbols: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        将策略的监控配置合并到系统级 system_configs 中。

        - timeframes: 取并集（sorted set）
        - core_symbols: 取并集（sorted set）

        如果未发生变化，不执行 DB 写入。

        Returns:
            {
                "changed": bool,
                "timeframes": List[str],
                "symbols": List[str],
            }
        """
        await self._load_system_config()
        current_timeframes = self._system_config_cache.get("timeframes", ["15m", "1h"])
        current_symbols = self._system_config_cache.get("core_symbols", [])

        # 合并（取并集，排序去重）
        merged_timeframes = sorted(set(current_timeframes) | set(strategy_timeframes))
        merged_symbols = (
            sorted(set(current_symbols) | set(strategy_symbols))
            if strategy_symbols
            else current_symbols
        )

        # 检查是否需要更新
        changed = (merged_timeframes != current_timeframes) or (
            merged_symbols != current_symbols
        )

        if changed and self._db is not None:
            await self._db.execute(
                "UPDATE system_configs SET timeframes = ?, core_symbols = ? WHERE id = 'global'",
                (json.dumps(merged_timeframes), json.dumps(merged_symbols)),
            )
            await self._db.commit()

            # 更新缓存
            self._system_config_cache["timeframes"] = merged_timeframes
            self._system_config_cache["core_symbols"] = merged_symbols

        return {
            "changed": changed,
            "timeframes": merged_timeframes,
            "symbols": merged_symbols,
        }

    async def get_risk_config(self) -> RiskConfig:
        """Get risk config from cache."""
        await self._load_risk_config()
        return self._risk_config_cache

    def _build_default_core_config(self) -> CoreConfig:
        """Build default core configuration (hardcoded defaults).

        Used when DB is not yet initialized or unavailable.
        No YAML file fallback — DB or defaults only.
        """
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
            atr=AtrConfig(enabled=True, period=14, min_ratio=Decimal("0.5")),
        )

    async def get_user_config(self) -> UserConfig:
        """
        Get user configuration from database.

        Returns:
            UserConfig 配置副本（深拷贝），防止外部修改影响内部状态

        R9.3: If initialization is in progress, wait for it to complete (up to 30s timeout).
        """
        # R9.3: Wait for initialization if in progress
        if not self._initialized and self._init_event is not None:
            try:
                logger.debug("ConfigManager: Waiting for initialization to complete")
                await asyncio.wait_for(self._init_event.wait(), timeout=30.0)
            except asyncio.TimeoutError:
                raise RuntimeError("ConfigManager 初始化超时 (30 秒)")

        if self._db is None:
            # Not initialized - fallback to defaults
            config = self._create_default_user_config()
        else:
            # Build UserConfig from database with degradation support
            user_config_dict = await self._build_user_config_dict()

            try:
                config = UserConfig(**user_config_dict)
            except ValidationError as e:
                logger.error(f"UserConfig 验证失败，使用默认配置：{e}")
                config = self._create_default_user_config()  # 兜底

        # R3.1 fix: 返回配置副本，防止外部修改影响内部状态
        return copy.deepcopy(config)

    def get_user_config_sync(self) -> UserConfig:
        """
        Get user configuration synchronously (from memory cache).

        R3.1: Returns a deep copy to prevent external modification.
        Task A-3: Now returns from _user_config_cache (populated during initialization)
        instead of reading from YAML.

        Returns:
            UserConfig 配置副本（深拷贝），防止外部修改影响内部状态
        """
        if self._user_config_cache is not None:
            return copy.deepcopy(self._user_config_cache)

        # Not yet initialized - create default
        logger.warning("get_user_config_sync called before initialization, returning default")
        return self._create_default_user_config()

    @property
    def is_initialized(self) -> bool:
        """
        Check if ConfigManager has been initialized.
        
        R9.3: Useful for testing and health checks.
        
        Returns:
            True if initialization is complete
        """
        return self._initialized

    async def _build_user_config_dict(self) -> Dict[str, Any]:
        """Build user config dictionary from database (pure DB, no YAML)."""
        # Load from DB
        exchange_config = await self._get_exchange_config_db()
        timeframes = self._system_config_cache.get("timeframes", ["15m", "1h"])
        polling_enabled = self._system_config_cache.get("asset_polling_enabled", True)
        polling_interval = self._system_config_cache.get("asset_polling_interval", 60)

        # Override with database configs
        await self._load_system_config()
        await self._load_risk_config()

        # Load strategies with degradation support
        strategies = await self._load_strategies_from_db()

        return {
            "exchange": exchange_config,
            "user_symbols": [],  # Will be loaded from symbols table
            "timeframes": timeframes,
            "active_strategies": strategies,
            "risk": self._risk_config_cache,
            "asset_polling": AssetPollingConfig(
                enabled=polling_enabled,
                interval_seconds=polling_interval,
            ),
            "notification": await self._build_notification_config(),
            "mtf_ema_period": self._system_config_cache.get("mtf_ema_period", 60),
            "mtf_mapping": self._system_config_cache.get("mtf_mapping", {}),
        }

    async def _get_exchange_config_db(self) -> ExchangeConfig:
        """从 DB 获取交易所配置。"""
        async with self._db.execute(
            "SELECT * FROM exchange_configs WHERE id = 'primary'"
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return ExchangeConfig(
                    name=row["exchange_name"],
                    api_key=row["api_key"],
                    api_secret=row["api_secret"],
                    testnet=bool(row["testnet"]),
                )
        return ExchangeConfig(name="binance", api_key="", api_secret="", testnet=True)

    async def _load_strategies_from_db(self) -> List[StrategyDefinition]:
        """Load strategies from database with degradation support."""
        if self._db is None:
            return []

        async with self._db.execute(
            "SELECT * FROM strategies WHERE is_active = TRUE"
        ) as cursor:
            rows = await cursor.fetchall()
            strategies = []
            for row in rows:
                try:
                    # Handle corrupted JSON data
                    trigger_data = json.loads(row["trigger_config"]) if row["trigger_config"] else {}
                    filter_data = json.loads(row["filter_configs"]) if row["filter_configs"] else []

                    # Validate required fields
                    if not isinstance(trigger_data, dict):
                        logger.warning(f"策略 {row['id']} trigger_config 格式错误，跳过")
                        continue

                    trigger = TriggerConfig(
                        type=trigger_data.get("type", "pinbar"),
                        enabled=trigger_data.get("enabled", True),
                        params=trigger_data.get("params", {}),
                    )

                    # Handle corrupted filter data
                    filters = []
                    if isinstance(filter_data, list):
                        for f in filter_data:
                            if isinstance(f, dict):
                                filters.append(FilterConfig(
                                    type=f.get("type", "ema"),
                                    enabled=f.get("enabled", True),
                                    params=f.get("params", {}),
                                ))

                    strategies.append(StrategyDefinition(
                        id=row["id"],
                        name=row["name"],
                        trigger=trigger,
                        filters=filters,
                        filter_logic=row["filter_logic"] or "AND",
                    ))
                except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
                    logger.warning(f"策略 {row['id']} 数据损坏，跳过：{e}")
                    continue
                except Exception as e:
                    logger.error(f"策略 {row['id']} 解析失败：{e}")
                    continue

            return strategies

    async def _build_notification_config(self) -> NotificationConfig:
        """Build notification config from database (DB only, no YAML fallback)."""
        if self._db is None:
            return NotificationConfig(channels=[NotificationChannel(
                type="feishu",
                webhook_url="https://placeholder",
            )])

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
                return NotificationConfig(channels=[NotificationChannel(
                    type="feishu",
                    webhook_url="https://placeholder",
                )])

            return NotificationConfig(channels=channels)

    def _create_default_user_config(self) -> UserConfig:
        """
        Create a default user configuration.

        This is used as a fallback when database or YAML config is corrupted.
        """
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

    # ============================================================
    # Exchange / Timeframes / Asset Polling Updates (Task A-3)
    # ============================================================

    async def update_exchange_config(self, config: ExchangeConfig) -> None:
        """Update exchange configuration and trigger hot reload."""
        if self._db is None:
            raise FatalStartupError("Database not initialized", "F-003")

        async with self._ensure_lock():
            now = datetime.now(timezone.utc).isoformat()

            async with self._db.execute(
                "SELECT id FROM exchange_configs WHERE id = 'primary'"
            ) as cursor:
                exists = await cursor.fetchone()

            if exists:
                await self._db.execute("""
                    UPDATE exchange_configs
                    SET exchange_name = ?, api_key = ?, api_secret = ?,
                        testnet = ?, updated_at = ?, version = version + 1
                    WHERE id = 'primary'
                """, (config.name, config.api_key, config.api_secret, config.testnet, now))
            else:
                await self._db.execute("""
                    INSERT INTO exchange_configs
                    (id, exchange_name, api_key, api_secret, testnet)
                    VALUES ('primary', ?, ?, ?, ?)
                """, (config.name, config.api_key, config.api_secret, config.testnet))

            await self._log_config_change(
                entity_type="exchange_config",
                entity_id="primary",
                action="UPDATE",
                new_values={
                    "exchange_name": config.name,
                    "api_key": mask_secret(config.api_key),
                    "testnet": config.testnet,
                },
                changed_by="api",
            )

            await self._db.commit()

            # Refresh user config cache
            try:
                user_config_dict = await self._build_user_config_dict()
                self._user_config_cache = UserConfig(**user_config_dict)
            except ValidationError as e:
                logger.warning(f"Failed to rebuild user config cache: {e}")

            logger.info(f"Exchange config updated: {config.name} (testnet={config.testnet})")
            await self._notify_observers()

    async def update_timeframes(self, timeframes: List[str]) -> None:
        """Update timeframes and trigger hot reload."""
        if self._db is None:
            raise FatalStartupError("Database not initialized", "F-003")

        async with self._ensure_lock():
            now = datetime.now(timezone.utc).isoformat()

            await self._db.execute("""
                UPDATE system_configs
                SET timeframes = ?, updated_at = ?
                WHERE id = 'global'
            """, (json.dumps(timeframes), now))

            await self._log_config_change(
                entity_type="system_config",
                entity_id="global",
                action="UPDATE",
                new_values={"timeframes": timeframes},
                changed_by="api",
            )

            await self._db.commit()

            # Refresh caches
            await self._load_system_config()
            try:
                user_config_dict = await self._build_user_config_dict()
                self._user_config_cache = UserConfig(**user_config_dict)
            except ValidationError as e:
                logger.warning(f"Failed to rebuild user config cache: {e}")

            logger.info(f"Timeframes updated: {timeframes}")
            await self._notify_observers()

    async def update_asset_polling_config(self, config: AssetPollingConfig) -> None:
        """Update asset polling configuration and trigger hot reload."""
        if self._db is None:
            raise FatalStartupError("Database not initialized", "F-003")

        async with self._ensure_lock():
            now = datetime.now(timezone.utc).isoformat()

            await self._db.execute("""
                UPDATE system_configs
                SET asset_polling_enabled = ?, asset_polling_interval = ?, updated_at = ?
                WHERE id = 'global'
            """, (config.enabled, config.interval_seconds, now))

            await self._log_config_change(
                entity_type="system_config",
                entity_id="global",
                action="UPDATE",
                new_values={
                    "asset_polling_enabled": config.enabled,
                    "asset_polling_interval": config.interval_seconds,
                },
                changed_by="api",
            )

            await self._db.commit()

            # Refresh caches
            await self._load_system_config()
            try:
                user_config_dict = await self._build_user_config_dict()
                self._user_config_cache = UserConfig(**user_config_dict)
            except ValidationError as e:
                logger.warning(f"Failed to rebuild user config cache: {e}")

            logger.info(f"Asset polling config updated: enabled={config.enabled}, interval={config.interval_seconds}s")
            await self._notify_observers()

    async def close(self) -> None:
        """Close database connection."""
        if self._db:
            await self._db.close()
            self._db = None

    async def get_exchange_config(self) -> ExchangeConfig:
        """Get exchange config from DB."""
        if self._db is None:
            return ExchangeConfig(name="binance", api_key="", api_secret="", testnet=True)

        async with self._db.execute(
            "SELECT * FROM exchange_configs WHERE id = 'primary'"
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return ExchangeConfig(
                    name=row["exchange_name"],
                    api_key=row["api_key"],
                    api_secret=row["api_secret"],
                    testnet=bool(row["testnet"]),
                )
        return ExchangeConfig(name="binance", api_key="", api_secret="", testnet=True)

    async def get_timeframes(self) -> List[str]:
        """Get timeframes from DB."""
        await self._load_system_config()
        return self._system_config_cache.get("timeframes", ["15m", "1h"])

    async def get_asset_polling_config(self) -> AssetPollingConfig:
        """Get asset polling config from DB."""
        await self._load_system_config()
        enabled = self._system_config_cache.get("asset_polling_enabled", True)
        interval = self._system_config_cache.get("asset_polling_interval", 60)
        return AssetPollingConfig(enabled=enabled, interval_seconds=interval)

    # ============================================================
    # Cache Refresh (for Profile Switch)
    # ============================================================

    async def reload_all_configs_from_db(self) -> None:
        """
        Reload all configurations from database and refresh caches.

        用于 Profile 切换后刷新内存缓存，确保读取到新 Profile 的配置。

        Task A-3: Also refreshes _user_config_cache.

        注意：此方法会刷新所有缓存并通知观察者。
        """
        if self._db is None:
            logger.warning("ConfigManager: Database not initialized, skipping reload")
            return

        async with self._ensure_lock():
            # 重新加载系统配置
            await self._load_system_config()

            # 重新加载风控配置
            await self._load_risk_config()

            # Task A-3: Refresh user config cache
            try:
                user_config_dict = await self._build_user_config_dict()
                self._user_config_cache = UserConfig(**user_config_dict)
            except ValidationError as e:
                logger.warning(f"Failed to rebuild user config cache: {e}")

            logger.info("ConfigManager: All configs reloaded from database")

            # 通知观察者（触发 SignalPipeline 等组件更新）
            await self._notify_observers()

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

            # Update database with all fields including extended ones
            now = datetime.now(timezone.utc).isoformat()
            await self._db.execute("""
                UPDATE risk_configs
                SET max_loss_percent = ?, max_leverage = ?,
                    max_total_exposure = ?,
                    daily_max_trades = ?,
                    daily_max_loss = ?,
                    max_position_hold_time = ?,
                    updated_at = ?
                WHERE id = 'global'
            """, (
                str(config.max_loss_percent),
                config.max_leverage,
                str(config.max_total_exposure),
                config.daily_max_trades,
                str(config.daily_max_loss) if config.daily_max_loss is not None else None,
                config.max_position_hold_time,
                now,
            ))

            # Log history
            await self._log_config_change(
                entity_type="risk_config",
                entity_id="global",
                action="UPDATE",
                new_values={
                    "max_loss_percent": str(config.max_loss_percent),
                    "max_leverage": config.max_leverage,
                    "max_total_exposure": str(config.max_total_exposure),
                    "daily_max_trades": config.daily_max_trades,
                    "daily_max_loss": str(config.daily_max_loss) if config.daily_max_loss is not None else None,
                    "max_position_hold_time": config.max_position_hold_time,
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
        """
        Notify all observers of config changes (R3.2).

        Increments configuration version number before notifying observers
        to ensure observers can detect stale configurations.
        """
        if not self._observers:
            return

        # R3.2: Increment version number atomically under lock
        async with self._ensure_config_lock():
            self._config_version += 1
            logger.debug(f"Configuration version updated to {self._config_version}")

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

    def set_config_entry_repository(self, repo: "ConfigEntryRepository") -> None:
        """Inject ConfigEntryRepository for KV config operations."""
        self._config_entry_repo = repo
        logger.info("ConfigEntryRepository injected for KV config operations")

    def set_config_profile_repository(self, repo: "ConfigProfileRepository") -> None:
        """Inject ConfigProfileRepository for profile management."""
        self._config_profile_repo = repo
        logger.info("ConfigProfileRepository injected for profile management")

    # ============================================================
    # Backtest Configuration KV Methods (T2 Task)
    # ============================================================

    async def get_backtest_configs(self, profile_name: Optional[str] = None) -> Dict[str, Any]:
        """
        获取回测配置（KV 模式）。

        Args:
            profile_name: Profile 名称，如果未指定则获取当前激活的 Profile

        Returns:
            回测配置字典，包含以下键：
            - slippage_rate: Decimal (默认 0.001)
            - fee_rate: Decimal (默认 0.0004)
            - initial_balance: Decimal (默认 10000)
            - tp_slippage_rate: Decimal (默认 0.0005)
            - funding_rate_enabled: bool (默认 True)
            - funding_rate: Decimal (默认 0.0001, 每 8 小时)

        Raises:
            RuntimeError: 如果 ConfigEntryRepository 未注入
        """
        if self._config_entry_repo is None:
            raise RuntimeError("ConfigEntryRepository 未注入，请先调用 set_config_entry_repository()")

        # 如果未指定 Profile，获取当前激活的 Profile
        if profile_name is None:
            profile_name = await self._get_current_profile_name()

        # 使用 ConfigEntryRepository 读取配置
        configs = await self._config_entry_repo.get_backtest_configs(profile_name=profile_name)
        return configs

    async def save_backtest_configs(
        self,
        configs: Dict[str, Any],
        profile_name: Optional[str] = None,
        changed_by: str = "user"
    ) -> int:
        """
        保存回测配置（KV 模式）。

        Args:
            configs: 回测配置字典，支持的键：
                    - slippage_rate (Decimal)
                    - fee_rate (Decimal)
                    - initial_balance (Decimal)
                    - tp_slippage_rate (Decimal)
                    - funding_rate_enabled (bool)
                    - funding_rate (Decimal)
            profile_name: Profile 名称，如果未指定则使用当前激活的 Profile
            changed_by: 变更操作人标识

        Returns:
            保存的配置项数量

        Raises:
            RuntimeError: 如果 ConfigEntryRepository 未注入

        Side Effects:
            - 创建自动快照（如果 snapshot_service 可用）
            - 记录配置变更历史
        """
        if self._config_entry_repo is None:
            raise RuntimeError("ConfigEntryRepository 未注入，请先调用 set_config_entry_repository()")

        # 如果未指定 Profile，获取当前激活的 Profile
        if profile_name is None:
            profile_name = await self._get_current_profile_name()

        # 创建自动快照（在配置变更前）
        if self._snapshot_service:
            try:
                user_config = await self.get_user_config()
                await self._snapshot_service.create_auto_snapshot(
                    config=user_config,
                    description=f"回测配置变更 - {changed_by}"
                )
            except Exception as e:
                logger.warning(f"回测配置自动快照创建失败：{e}")

        # 查询旧配置（用于记录变更历史）
        old_configs = await self.get_backtest_configs(profile_name=profile_name)

        # 使用 ConfigEntryRepository 保存配置
        saved_count = await self._config_entry_repo.save_backtest_configs(
            configs=configs,
            profile_name=profile_name,
            version="v1.0.0"
        )

        # 记录配置变更历史（包含旧值和新值）
        await self._log_config_change(
            entity_type="backtest_config",
            entity_id=f"profile:{profile_name}",
            action="UPDATE",
            old_values={k: str(v) for k, v in old_configs.items()} if old_configs else None,
            new_values={k: str(v) for k, v in configs.items()},
            changed_by=changed_by,
            change_summary=f"回测配置更新 - Profile:{profile_name}, 变更项:{len(configs)}",
        )

        return saved_count

    async def _get_current_profile_name(self) -> str:
        """
        获取当前激活的 Profile 名称。

        Returns:
            Profile 名称，默认为 'default'
        """
        if self._config_profile_repo is not None:
            try:
                active_profile = await self._config_profile_repo.get_active_profile()
                if active_profile:
                    return active_profile.name
            except Exception as e:
                logger.warning(f"获取激活 Profile 失败，使用默认值：{e}")

        # 默认返回 'default'
        return "default"

    # ============================================================
    # YAML Backward Compatibility
    # ============================================================

    async def import_from_yaml(self, yaml_path: str, changed_by: str = "system") -> None:
        """
        Import configuration from YAML file into DB.

        Task A-3: Now actually parses YAML and writes to DB tables.
        """
        if not os.path.exists(yaml_path):
            raise FileNotFoundError(f"YAML file not found: {yaml_path}")

        with open(yaml_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        if not data:
            logger.warning(f"YAML file {yaml_path} is empty, skipping import")
            return

        if self._db is None:
            raise FatalStartupError("Database not initialized", "F-003")

        imported = []

        # Import exchange config
        if 'exchange' in data:
            exchange = data['exchange']
            await self._db.execute("""
                INSERT OR REPLACE INTO exchange_configs
                (id, exchange_name, api_key, api_secret, testnet)
                VALUES ('primary', ?, ?, ?, ?)
            """, (
                exchange.get('name', 'binance'),
                exchange.get('api_key', ''),
                exchange.get('api_secret', ''),
                exchange.get('testnet', True),
            ))
            imported.append("exchange")

        # Import timeframes
        if 'timeframes' in data:
            await self._db.execute("""
                UPDATE system_configs
                SET timeframes = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = 'global'
            """, (json.dumps(data['timeframes']),))
            imported.append("timeframes")

        # Import asset polling
        if 'asset_polling' in data:
            polling = data['asset_polling']
            if isinstance(polling, dict):
                await self._db.execute("""
                    UPDATE system_configs
                    SET asset_polling_enabled = ?, asset_polling_interval = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = 'global'
                """, (
                    polling.get('enabled', True),
                    polling.get('interval_seconds', 60),
                ))
                imported.append("asset_polling")

        # Import risk config (direct DB)
        if 'risk' in data:
            risk = data['risk']
            await self._db.execute("""
                UPDATE risk_configs
                SET max_loss_percent = ?, max_leverage = ?, max_total_exposure = ?,
                    cooldown_minutes = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = 'global'
            """, (
                risk.get('max_loss_percent', 0.01),
                risk.get('max_leverage', 10),
                risk.get('max_total_exposure', 0.8),
                risk.get('cooldown_minutes', 240),
            ))
            imported.append("risk")

        # Import system config (direct DB)
        if 'system' in data:
            system = data['system']
            await self._db.execute("""
                UPDATE system_configs
                SET core_symbols = ?, ema_period = ?, mtf_ema_period = ?,
                    mtf_mapping = ?, signal_cooldown_seconds = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = 'global'
            """, (
                json.dumps(system.get('core_symbols', [])),
                system.get('ema_period', 60),
                system.get('mtf_ema_period', 60),
                json.dumps(system.get('mtf_mapping', {})),
                system.get('signal_cooldown_seconds', 14400),
            ))
            imported.append("system")

        await self._db.commit()

        # Refresh caches
        await self._load_system_config()
        await self._load_risk_config()
        try:
            user_config_dict = await self._build_user_config_dict()
            self._user_config_cache = UserConfig(**user_config_dict)
        except ValidationError as e:
            logger.warning(f"Failed to rebuild user config cache after import: {e}")

        logger.info(f"Configuration imported from {yaml_path}: {', '.join(imported)}")

        # Log the import operation to config history
        await self._log_config_change(
            entity_type="config_bundle",
            entity_id="import_export",
            action="IMPORT",
            old_values=None,
            new_values={"source_path": yaml_path, "imported_sections": imported},
            changed_by=changed_by,
            change_summary=f"Configuration imported from {yaml_path}: {', '.join(imported)}",
        )

    async def export_to_yaml(self, yaml_path: str, changed_by: str = "system") -> None:
        """
        Export current DB configuration to YAML file.

        Task A-3: Now reads all config from DB tables.
        """
        if self._db is None:
            raise FatalStartupError("Database not initialized", "F-003")

        export_data = {
            "version": "1.0",
            "exported_at": datetime.now(timezone.utc).isoformat(),
        }

        # Export exchange config
        try:
            exchange = await self.get_exchange_config()
            export_data["exchange"] = {
                "name": exchange.name,
                "api_key": exchange.api_key,
                "api_secret": exchange.api_secret,
                "testnet": exchange.testnet,
            }
        except Exception as e:
            logger.warning(f"Failed to export exchange config: {e}")

        # Export timeframes
        try:
            export_data["timeframes"] = await self.get_timeframes()
        except Exception as e:
            logger.warning(f"Failed to export timeframes: {e}")

        # Export asset polling
        try:
            polling = await self.get_asset_polling_config()
            export_data["asset_polling"] = {
                "enabled": polling.enabled,
                "interval_seconds": polling.interval_seconds,
            }
        except Exception as e:
            logger.warning(f"Failed to export asset polling config: {e}")

        # Export risk config (direct DB read)
        try:
            await self._load_risk_config()
            risk = self._risk_config_cache
            export_data["risk"] = {
                "max_loss_percent": str(risk.max_loss_percent),
                "max_leverage": risk.max_leverage,
                "max_total_exposure": str(risk.max_total_exposure),
                "cooldown_minutes": 240,
            }
        except Exception as e:
            logger.warning(f"Failed to export risk config: {e}")

        # Export system config
        try:
            system_data = await self.get_system_config()
            export_data["system"] = system_data
        except Exception as e:
            logger.warning(f"Failed to export system config: {e}")

        # Export strategies
        try:
            strategies = await self._load_strategies_from_db()
            export_data["strategies"] = [
                {
                    "id": s.id,
                    "name": s.name,
                    "trigger": {"type": s.trigger.type, "params": s.trigger.params} if s.trigger else {},
                    "filters": [{"type": f.type, "params": f.params} for f in s.filters],
                    "filter_logic": s.filter_logic,
                }
                for s in strategies
            ]
        except Exception as e:
            logger.warning(f"Failed to export strategies: {e}")

        # Export symbols
        try:
            async with self._db.execute("SELECT * FROM symbols") as cursor:
                rows = await cursor.fetchall()
                export_data["symbols"] = [
                    {"symbol": r["symbol"], "is_active": bool(r["is_active"]), "is_core": bool(r["is_core"])}
                    for r in rows
                ]
        except Exception as e:
            logger.warning(f"Failed to export symbols: {e}")

        # Convert Decimals to strings for YAML serialization
        def convert_decimals(obj):
            if isinstance(obj, Decimal):
                return str(obj)
            elif isinstance(obj, dict):
                return {k: convert_decimals(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_decimals(item) for item in obj]
            return obj

        export_data = convert_decimals(export_data)

        # Write YAML file
        yaml_content = yaml.safe_dump(
            export_data,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )

        with open(yaml_path, 'w', encoding='utf-8') as f:
            f.write(yaml_content)

        logger.info(f"Configuration exported to {yaml_path}")

        # Log the export operation to config history
        await self._log_config_change(
            entity_type="config_bundle",
            entity_id="import_export",
            action="EXPORT",
            old_values=None,
            new_values={"target_path": yaml_path},
            changed_by=changed_by,
            change_summary=f"Configuration exported to {yaml_path}",
        )


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
