"""
ConfigRepository - Configuration Repository Layer

This module provides the repository layer for configuration management.

Responsibility:
- Database connection management
- SQL operation encapsulation
- Cache management (with TTL)
- File I/O operations

Architecture:
    ConfigService → ConfigRepository → ConfigParser
    
Usage:
    from src.application.config import ConfigRepository
    
    repo = ConfigRepository()
    await repo.initialize(db_path="data/v3_dev.db")
    risk_config = await repo.get_risk_config()
"""
import asyncio
import copy
import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import List, Dict, Any, Optional

import aiosqlite
import cachetools
import yaml

from src.domain.exceptions import FatalStartupError
from src.domain.models import (
    RiskConfig,
    StrategyDefinition,
    TriggerConfig,
    FilterConfig,
)
from src.infrastructure.logger import logger, mask_secret
from src.application.config.config_parser import ConfigParser
from src.application.config.models import (
    CoreConfig,
    UserConfig,
    ExchangeConfig,
    NotificationConfig,
    NotificationChannel,
    MtfMapping,
    EmaConfig,
    PinbarDefaults,
    WarmupConfig,
    SignalPipelineConfig,
    AtrConfig,
)


class ConfigRepository:
    """
    Configuration repository - responsible for data persistence.
    
    Responsibilities:
    - Database connection management
    - SQL operation encapsulation
    - Cache management (with TTL)
    - File I/O
    
    Architecture:
        ConfigService → ConfigRepository → ConfigParser
    """
    
    # ============================================================
    # Lifecycle Management
    # ============================================================
    
    def __init__(self):
        """Initialize ConfigRepository."""
        self._db_path: Optional[str] = None
        self._db: Optional[aiosqlite.Connection] = None
        self._lock: Optional[asyncio.Lock] = None
        self._init_lock: Optional[asyncio.Lock] = None
        self._init_event: Optional[asyncio.Event] = None
        self._initialized = False
        self._initializing = False
        
        # Configuration caches
        self._system_config_cache: Optional[Dict[str, Any]] = None
        self._risk_config_cache: Optional[RiskConfig] = None
        
        # TTL Cache for import/export preview (5 minutes expiry, max 100 entries)
        self._import_preview_cache: cachetools.TTLCache = cachetools.TTLCache(maxsize=100, ttl=300)
        
        # YAML parser
        self._parser = ConfigParser()
        
        # Config directory (for YAML backward compatibility)
        self._config_dir: Optional[Path] = None
    
    def _ensure_init_lock(self) -> asyncio.Lock:
        """Ensure init lock is created for current event loop."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.Lock()
        
        if self._init_lock is None:
            self._init_lock = asyncio.Lock()
        return self._init_lock
    
    def _ensure_init_event(self) -> asyncio.Event:
        """Ensure init event is created for current event loop."""
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
    
    async def initialize(self, db_path: Optional[str] = None, config_dir: Optional[str] = None) -> None:
        """
        Initialize database connection and create default configurations.
        
        This method is idempotent - calling it multiple times has no effect
        after first initialization.
        
        Args:
            db_path: Path to SQLite database file. Defaults to ./data/v3_dev.db
            config_dir: Directory containing YAML config files. Defaults to ./config
        """
        # Fast path - already initialized
        if self._initialized:
            return
        
        # Get lock and event for current event loop
        init_lock = self._ensure_init_lock()
        init_event = self._ensure_init_event()
        
        async with init_lock:
            # Double-check after acquiring lock
            if self._initialized:
                return
            
            # If already initializing, wait for completion
            if self._initializing:
                logger.debug("ConfigRepository: Waiting for concurrent initialization to complete")
                await init_event.wait()
                return
            
            # Mark as initializing
            self._initializing = True
            
            try:
                # Set paths
                if db_path:
                    self._db_path = db_path
                else:
                    self._db_path = os.environ.get(
                        "CONFIG_DB_PATH",
                        str(Path(__file__).parent.parent.parent / "data" / "v3_dev.db")
                    )
                
                if config_dir:
                    self._config_dir = Path(config_dir)
                else:
                    self._config_dir = Path(__file__).parent.parent.parent / 'config'
                
                # Create data directory if not exists
                db_dir = os.path.dirname(self._db_path)
                if db_dir and not os.path.exists(db_dir):
                    os.makedirs(db_dir, exist_ok=True)
                
                # Open database connection
                self._db = await aiosqlite.connect(self._db_path)
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
                
                # Validate configuration integrity and apply defaults if empty
                await self._validate_and_apply_default_configs()
                
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
        
        logger.info(f"ConfigRepository initialized from database: {self._db_path}")
    
    async def close(self) -> None:
        """Close database connection."""
        if self._db:
            await self._db.close()
            self._db = None
        self._initialized = False
        logger.info("ConfigRepository database connection closed")
    
    @property
    def is_initialized(self) -> bool:
        """Check if repository has been initialized."""
        return self._initialized
    
    def assert_initialized(self) -> None:
        """
        Assert that repository has been fully initialized.
        
        Raises:
            FatalStartupError: If repository is not initialized
        """
        if not self._initialized:
            if self._initializing:
                raise FatalStartupError(
                    "ConfigRepository 正在初始化中，请稍候",
                    "F-003",
                )
            else:
                raise FatalStartupError(
                    "ConfigRepository 未初始化 - 请确保先调用 initialize()",
                    "F-003",
                )
    
    # ============================================================
    # Database Schema Management
    # ============================================================
    
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
                    daily_max_trades INTEGER,
                    daily_max_loss DECIMAL(10,4),
                    max_position_hold_time INTEGER,
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
                    warmup_history_bars INTEGER DEFAULT 100,
                    atr_filter_enabled BOOLEAN DEFAULT TRUE,
                    atr_period INTEGER DEFAULT 14,
                    atr_min_ratio DECIMAL(5,2) DEFAULT 0.5,
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
        logger.debug("Database tables created/verified")
    
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
                logger.info("Default system config initialized")
        
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
                logger.info("Default risk config initialized")
        
        # Initialize core symbols
        core_symbols = [
            ("BTC/USDT:USDT", True, True),
            ("ETH/USDT:USDT", True, True),
            ("SOL/USDT:USDT", True, True),
            ("BNB/USDT:USDT", True, True),
        ]
        for symbol, is_core, is_active in core_symbols:
            await self._db.execute("""
                INSERT OR IGNORE INTO symbols (symbol, is_core, is_active)
                VALUES (?, ?, ?)
            """, (symbol, is_core, is_active))
        
        await self._db.commit()
        logger.debug("Default core symbols initialized")
    
    async def _validate_and_apply_default_configs(self) -> None:
        """Validate configuration integrity and apply defaults if empty."""
        is_empty = await self._is_empty_config()
        
        if is_empty:
            logger.warning("数据库配置为空或不完全，使用默认配置启动系统")
            await self._apply_hardcoded_defaults()
    
    async def _is_empty_config(self) -> bool:
        """Check if the database configuration is empty."""
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
        """Apply hard-coded default configurations to ensure system can start."""
        applied_defaults = []
        
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
                applied_defaults.append("风控配置：max_loss=1%, max_leverage=10x, max_exposure=80%")
        
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
                applied_defaults.append("通知渠道：飞书占位符 (需配置真实 webhook)")
        
        # Default system config
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
                applied_defaults.append("系统配置：core_symbols=BTC/ETH/SOL/BNB, ema_period=60")
        
        await self._db.commit()
        
        # Startup warning for hardcoded defaults
        if applied_defaults:
            logger.warning(
                "⚠️  [R4.2] 系统使用默认配置启动:\n"
                + "\n".join(f"  - {d}" for d in applied_defaults)
                + "\n建议尽快在配置管理页面修改为适合您交易风格的参数。"
            )
        else:
            logger.info("配置已加载，系统可以安全启动")
    
    # ============================================================
    # System Config Operations
    # ============================================================
    
    async def get_system_config(self) -> Dict[str, Any]:
        """Get system configuration."""
        self.assert_initialized()
        
        if self._system_config_cache is not None:
            return copy.deepcopy(self._system_config_cache)
        
        await self._load_system_config()
        return copy.deepcopy(self._system_config_cache)
    
    async def update_system_config(self, config: Dict[str, Any]) -> None:
        """Update system configuration."""
        self.assert_initialized()
        
        async with self._ensure_lock():
            now = datetime.now(timezone.utc).isoformat()
            
            await self._db.execute("""
                UPDATE system_configs
                SET core_symbols = ?, ema_period = ?, mtf_ema_period = ?,
                    mtf_mapping = ?, signal_cooldown_seconds = ?,
                    warmup_history_bars = ?, atr_filter_enabled = ?,
                    atr_period = ?, atr_min_ratio = ?, updated_at = ?
                WHERE id = 'global'
            """, (
                json.dumps(config.get("core_symbols", [])),
                config.get("ema_period", 60),
                config.get("mtf_ema_period", 60),
                json.dumps(config.get("mtf_mapping", {})),
                config.get("signal_cooldown_seconds", 14400),
                config.get("warmup_history_bars", 100),
                config.get("atr_filter_enabled", True),
                config.get("atr_period", 14),
                str(config.get("atr_min_ratio", "0.5")),
                now,
            ))
            
            await self._log_config_change(
                entity_type="system_config",
                entity_id="global",
                action="UPDATE",
                new_values=config,
                changed_by="system",
            )
            
            await self._db.commit()
            
            # Invalidate cache
            self._system_config_cache = config
    
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
                    "warmup_history_bars": row["warmup_history_bars"] if row["warmup_history_bars"] is not None else 100,
                    "atr_filter_enabled": bool(row["atr_filter_enabled"]) if row["atr_filter_enabled"] is not None else True,
                    "atr_period": row["atr_period"] if row["atr_period"] is not None else 14,
                    "atr_min_ratio": str(row["atr_min_ratio"]) if row["atr_min_ratio"] is not None else "0.5",
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
                }
        return self._system_config_cache
    
    # ============================================================
    # Risk Config Operations
    # ============================================================
    
    async def get_risk_config(self) -> RiskConfig:
        """Get risk configuration."""
        self.assert_initialized()
        
        if self._risk_config_cache is not None:
            return copy.deepcopy(self._risk_config_cache)
        
        await self._load_risk_config()
        return copy.deepcopy(self._risk_config_cache)
    
    async def update_risk_config(self, config: RiskConfig, changed_by: str = "user") -> None:
        """
        Update risk configuration.
        
        Args:
            config: New RiskConfig
            changed_by: User identifier for audit trail
        """
        self.assert_initialized()
        
        async with self._ensure_lock():
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
    
    # ============================================================
    # User Config Operations
    # ============================================================
    
    async def get_user_config_dict(self) -> Dict[str, Any]:
        """
        Get user configuration dictionary (with merged configs).
        
        Returns:
            Dictionary containing user configuration
        """
        self.assert_initialized()
        
        # Load from YAML for backward compatibility
        yaml_config = self._load_user_config_from_yaml()
        
        # Load system and risk configs
        await self._load_system_config()
        await self._load_risk_config()
        
        # Load strategies with degradation support
        strategies = await self._load_strategies_from_db()
        
        return {
            "exchange": yaml_config.exchange,
            "user_symbols": [],  # Will be loaded from symbols table
            "timeframes": yaml_config.timeframes,
            "active_strategies": strategies,
            "risk": self._risk_config_cache,
            "asset_polling": yaml_config.asset_polling,
            "notification": await self._build_notification_config(),
            "mtf_ema_period": self._system_config_cache.get("mtf_ema_period", 60),
            "mtf_mapping": self._system_config_cache.get("mtf_mapping", {}),
        }
    
    def _load_user_config_from_yaml(self) -> UserConfig:
        """Load user config from YAML file (fallback for backward compatibility)."""
        user_path = self._config_dir / 'user.yaml' if self._config_dir else None
        
        if not user_path or not user_path.exists():
            return self._create_default_user_config()
        
        try:
            with open(user_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            logger.error(f"user.yaml 解析失败，使用默认配置：{e}")
            return self._create_default_user_config()
        
        try:
            return UserConfig(**data)
        except ValidationError as e:
            logger.error(f"user.yaml 配置验证失败，使用默认配置：{e}")
            return self._create_default_user_config()
    
    def _create_default_user_config(self) -> UserConfig:
        """Create a default user configuration."""
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
    
    async def _build_notification_config(self) -> NotificationConfig:
        """Build notification config from database."""
        if self._db is None:
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
                return self._load_user_config_from_yaml().notification
            
            return NotificationConfig(channels=channels)
    
    # ============================================================
    # Strategy CRUD Operations
    # ============================================================
    
    async def get_all_strategies(self) -> List[StrategyDefinition]:
        """Get all active strategies."""
        self.assert_initialized()
        
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
        self.assert_initialized()
        
        from uuid import uuid4
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
        
        return strategy_id
    
    async def delete_strategy(self, strategy_id: str, changed_by: str = "user") -> bool:
        """
        Delete strategy by ID.
        
        Args:
            strategy_id: Strategy ID to delete
            changed_by: User identifier
        
        Returns:
            True if strategy was deleted, False if not found
        """
        self.assert_initialized()
        
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
                return True
            
            return False
    
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
    
    # ============================================================
    # Notification Config Operations
    # ============================================================
    
    async def get_notification_config(self) -> NotificationConfig:
        """Get notification configuration."""
        self.assert_initialized()
        return await self._build_notification_config()
    
    # ============================================================
    # Backtest Config Operations (KV Mode)
    # ============================================================
    
    async def get_backtest_configs(self, profile_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get backtest configuration (KV mode).
        
        Args:
            profile_name: Profile name. If None, uses 'default'
        
        Returns:
            Dictionary containing backtest configuration:
            - slippage_rate: Decimal (default 0.001)
            - fee_rate: Decimal (default 0.0004)
            - initial_balance: Decimal (default 10000)
            - tp_slippage_rate: Decimal (default 0.0005)
            - funding_rate_enabled: bool (default True)
            - funding_rate: Decimal (default 0.0001, per 8 hours)
        """
        self.assert_initialized()
        
        # Use 'default' if profile not specified
        if profile_name is None:
            profile_name = "default"
        
        # TODO: Use ConfigEntryRepository for KV storage
        # For now, return default values
        return {
            "slippage_rate": Decimal("0.001"),
            "fee_rate": Decimal("0.0004"),
            "initial_balance": Decimal("10000"),
            "tp_slippage_rate": Decimal("0.0005"),
            "funding_rate_enabled": True,
            "funding_rate": Decimal("0.0001"),
        }
    
    async def save_backtest_configs(
        self,
        configs: Dict[str, Any],
        profile_name: Optional[str] = None,
        changed_by: str = "user"
    ) -> int:
        """
        Save backtest configuration (KV mode).
        
        Args:
            configs: Backtest configuration dictionary
            profile_name: Profile name. If None, uses 'default'
            changed_by: User identifier
        
        Returns:
            Number of configuration items saved
        """
        self.assert_initialized()
        
        if profile_name is None:
            profile_name = "default"
        
        # TODO: Use ConfigEntryRepository for KV storage
        # For now, just log the operation
        await self._log_config_change(
            entity_type="backtest_config",
            entity_id=f"profile:{profile_name}",
            action="UPDATE",
            new_values={k: str(v) for k, v in configs.items()},
            changed_by=changed_by,
            change_summary=f"回测配置更新 - Profile:{profile_name}, 变更项:{len(configs)}",
        )
        
        return len(configs)
    
    # ============================================================
    # YAML Import/Export Operations
    # ============================================================
    
    async def import_from_yaml(self, yaml_path: str, changed_by: str = "system") -> Dict[str, Any]:
        """
        Import configuration from YAML file.
        
        Args:
            yaml_path: Path to YAML file
            changed_by: User identifier
        
        Returns:
            Imported configuration dictionary
        """
        self.assert_initialized()
        
        if not os.path.exists(yaml_path):
            raise FileNotFoundError(f"YAML file not found: {yaml_path}")
        
        with open(yaml_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        # TODO: Parse and import into database
        logger.info(f"Configuration imported from {yaml_path}")
        
        # Log the import operation to config history
        await self._log_config_change(
            entity_type="config_bundle",
            entity_id="import_export",
            action="IMPORT",
            old_values=None,
            new_values={"source_path": yaml_path, "data_keys": list(data.keys()) if data else []},
            changed_by=changed_by,
            change_summary=f"Configuration imported from {yaml_path}",
        )
        
        return data
    
    async def export_to_yaml(self, yaml_path: str, config: Optional[Dict[str, Any]] = None, changed_by: str = "system") -> None:
        """
        Export current configuration to YAML file.

        Args:
            yaml_path: Path to output YAML file
            config: Configuration to export. If None, exports current config
            changed_by: User identifier
        """
        self.assert_initialized()

        # Get current config if not provided
        if config is None:
            config = await self.get_user_config_dict()

        # Use ConfigParser to serialize - handles Decimal precision and Pydantic models
        yaml_str = self._parser.dump_to_yaml(config)

        # Write to file
        with open(yaml_path, 'w', encoding='utf-8') as f:
            f.write(yaml_str)

        logger.info(f"Configuration exported to {yaml_path}")

        # Log the export operation
        await self._log_config_change(
            entity_type="config_bundle",
            entity_id="import_export",
            action="EXPORT",
            old_values=None,
            new_values={"destination_path": yaml_path},
            changed_by=changed_by,
            change_summary=f"Configuration exported to {yaml_path}",
        )
    
    # ============================================================
    # Cache Management
    # ============================================================
    
    def _init_cache(self) -> None:
        """Initialize TTL cache (called during initialization)."""
        # TTL Cache for import/export preview (5 minutes expiry, max 100 entries)
        self._import_preview_cache = cachetools.TTLCache(maxsize=100, ttl=300)
        logger.debug("TTL cache initialized (maxsize=100, ttl=300s)")
    
    async def _invalidate_cache(self) -> None:
        """Invalidate all caches (called on config update)."""
        self._system_config_cache = None
        self._risk_config_cache = None
        logger.debug("Configuration cache invalidated")
    
    def get_import_preview_cache(self) -> cachetools.TTLCache:
        """Get import preview cache (for API layer)."""
        return self._import_preview_cache
    
    # ============================================================
    # Config History Logging
    # ============================================================
    
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
        """
        Log a configuration change to history table.
        
        Args:
            entity_type: Type of entity (e.g., 'risk_config', 'strategy')
            entity_id: ID of the entity
            action: Action performed (CREATE, UPDATE, DELETE)
            old_values: Previous values (for UPDATE)
            new_values: New values (for CREATE/UPDATE)
            changed_by: User identifier
            change_summary: Human-readable summary
        """
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
        logger.debug(f"Config change logged: {entity_type}:{entity_id} {action}")


# Import ValidationError for the module
from pydantic import ValidationError
