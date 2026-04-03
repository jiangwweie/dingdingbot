"""
Config Repository - SQLite persistence for configuration management.
"""
import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

import aiosqlite

from src.infrastructure.logger import setup_logger

logger = setup_logger(__name__)


class ConfigRepository:
    """
    SQLite repository for persisting system configurations.

    Manages the following tables:
    - strategy_configs: Strategy configurations
    - risk_configs: Risk management configuration (singleton)
    - system_configs: System configuration (singleton)
    - symbol_configs: Symbol pool configuration
    - notification_configs: Notification channel configuration
    - config_snapshots: Configuration snapshots for version control
    - config_history: Configuration change history (auto-recorded via triggers)
    """

    def __init__(self, db_path: str = "data/config.db"):
        """
        Initialize ConfigRepository.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    async def initialize(self) -> None:
        """
        Initialize database connection and create tables.
        Also creates the data/ directory if it doesn't exist.
        """
        # Create data directory if not exists
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

        # Open database connection
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row

        # Enable foreign keys
        await self._db.execute("PRAGMA foreign_keys = ON")

        # Create all tables
        await self._create_strategy_configs_table()
        await self._create_risk_configs_table()
        await self._create_system_configs_table()
        await self._create_symbol_configs_table()
        await self._create_notification_configs_table()
        await self._create_config_snapshots_table()
        await self._create_config_history_table()

        # Create all triggers for auto-history and constraints
        await self._create_triggers()

        # Create all indexes
        await self._create_indexes()

        # Initialize default singleton records if not exist
        await self._initialize_default_configs()

        logger.info(f"配置数据库初始化完成：{self.db_path}")

    async def _create_strategy_configs_table(self) -> None:
        """Create strategy_configs table."""
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS strategy_configs (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT NOT NULL UNIQUE,
                description   TEXT,
                triggers      TEXT NOT NULL,
                filters       TEXT NOT NULL DEFAULT '[]',
                logic_tree    TEXT,
                apply_to      TEXT NOT NULL,
                is_active     INTEGER NOT NULL DEFAULT 0 CHECK (is_active IN (0, 1)),
                created_at    DATETIME NOT NULL DEFAULT (datetime('now')),
                updated_at    DATETIME NOT NULL DEFAULT (datetime('now'))
            )
        """)

    async def _create_risk_configs_table(self) -> None:
        """Create risk_configs table (singleton)."""
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS risk_configs (
                id                   INTEGER PRIMARY KEY,
                max_loss_percent     REAL NOT NULL DEFAULT 1.0 CHECK (max_loss_percent BETWEEN 0.1 AND 5.0),
                max_total_exposure   REAL NOT NULL DEFAULT 0.8 CHECK (max_total_exposure BETWEEN 0.5 AND 1.0),
                max_leverage         INTEGER NOT NULL DEFAULT 10 CHECK (max_leverage BETWEEN 1 AND 125),
                description          TEXT,
                updated_at           DATETIME NOT NULL DEFAULT (datetime('now'))
            )
        """)

    async def _create_system_configs_table(self) -> None:
        """Create system_configs table (singleton)."""
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS system_configs (
                id                   INTEGER PRIMARY KEY,
                history_bars         INTEGER NOT NULL DEFAULT 100 CHECK (history_bars BETWEEN 50 AND 1000),
                queue_batch_size     INTEGER NOT NULL DEFAULT 10 CHECK (queue_batch_size BETWEEN 1 AND 100),
                queue_flush_interval REAL NOT NULL DEFAULT 5.0 CHECK (queue_flush_interval BETWEEN 1.0 AND 60.0),
                description          TEXT,
                updated_at           DATETIME NOT NULL DEFAULT (datetime('now'))
            )
        """)

    async def _create_symbol_configs_table(self) -> None:
        """Create symbol_configs table."""
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS symbol_configs (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol        TEXT NOT NULL UNIQUE CHECK (symbol MATCH '^[A-Z]+/[A-Z]+(:[A-Z]+)?$'),
                is_core       INTEGER NOT NULL DEFAULT 1 CHECK (is_core IN (0, 1)),
                is_enabled    INTEGER NOT NULL DEFAULT 1 CHECK (is_enabled IN (0, 1)),
                updated_at    DATETIME NOT NULL DEFAULT (datetime('now'))
            )
        """)

    async def _create_notification_configs_table(self) -> None:
        """Create notification_configs table."""
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS notification_configs (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                channel       TEXT NOT NULL CHECK (channel IN ('feishu', 'wecom', 'telegram')),
                webhook_url   TEXT NOT NULL CHECK (webhook_url MATCH '^https?://.+'),
                is_enabled    INTEGER NOT NULL DEFAULT 1 CHECK (is_enabled IN (0, 1)),
                description   TEXT,
                updated_at    DATETIME NOT NULL DEFAULT (datetime('now'))
            )
        """)

    async def _create_config_snapshots_table(self) -> None:
        """Create config_snapshots table."""
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS config_snapshots (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                name            TEXT NOT NULL,
                description     TEXT,
                config_json     TEXT NOT NULL,
                is_auto         INTEGER DEFAULT 0 CHECK (is_auto IN (0, 1)),
                trigger_type    TEXT,
                created_at      DATETIME NOT NULL DEFAULT (datetime('now')),
                created_by      TEXT DEFAULT 'user'
            )
        """)

    async def _create_config_history_table(self) -> None:
        """Create config_history table."""
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS config_history (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                config_type     TEXT NOT NULL CHECK (config_type IN ('strategy', 'risk', 'system', 'symbol', 'notification')),
                config_id       INTEGER NOT NULL,
                action          TEXT NOT NULL CHECK (action IN ('create', 'update', 'delete')),
                old_value       TEXT,
                new_value       TEXT,
                created_at      DATETIME NOT NULL DEFAULT (datetime('now')),
                created_by      TEXT DEFAULT 'user'
            )
        """)

    async def _create_indexes(self) -> None:
        """Create all indexes for performance."""
        # Strategy configs indexes
        await self._db.execute("CREATE INDEX IF NOT EXISTS idx_strategy_active ON strategy_configs(is_active)")

        # Symbol configs index
        await self._db.execute("CREATE INDEX IF NOT EXISTS idx_symbol_enabled ON symbol_configs(is_enabled)")

        # Snapshot indexes
        await self._db.execute("CREATE INDEX IF NOT EXISTS idx_snapshot_name ON config_snapshots(name)")

        # History indexes
        await self._db.execute("CREATE INDEX IF NOT EXISTS idx_history_type ON config_history(config_type, config_id)")
        await self._db.execute("CREATE INDEX IF NOT EXISTS idx_history_time ON config_history(created_at)")

    async def _create_triggers(self) -> None:
        """Create all triggers for auto-history and constraints."""
        # Single active strategy constraint triggers
        await self._db.execute("""
            CREATE TRIGGER IF NOT EXISTS check_single_active_strategy_before_insert
            BEFORE INSERT ON strategy_configs
            WHEN NEW.is_active = 1 AND (SELECT COUNT(*) FROM strategy_configs WHERE is_active = 1) > 0
            BEGIN
                SELECT RAISE(ABORT, '同一时间只能有一个激活的策略');
            END
        """)

        await self._db.execute("""
            CREATE TRIGGER IF NOT EXISTS check_single_active_strategy_before_update
            BEFORE UPDATE ON strategy_configs
            WHEN NEW.is_active = 1 AND (SELECT COUNT(*) FROM strategy_configs WHERE is_active = 1 AND id != NEW.id) > 0
            BEGIN
                SELECT RAISE(ABORT, '同一时间只能有一个激活的策略');
            END
        """)

        # Risk configs singleton triggers
        await self._db.execute("""
            CREATE TRIGGER IF NOT EXISTS risk_configs_single_row_insert
            BEFORE INSERT ON risk_configs
            WHEN (SELECT COUNT(*) FROM risk_configs) >= 1
            BEGIN
                SELECT RAISE(ABORT, 'risk_configs 只能有一条记录');
            END
        """)

        await self._db.execute("""
            CREATE TRIGGER IF NOT EXISTS risk_configs_enforce_id_insert
            BEFORE INSERT ON risk_configs
            WHEN NEW.id != 1
            BEGIN
                SELECT RAISE(ABORT, 'risk_configs 的 id 必须为 1');
            END
        """)

        await self._db.execute("""
            CREATE TRIGGER IF NOT EXISTS risk_configs_enforce_id_update
            BEFORE UPDATE ON risk_configs
            WHEN NEW.id != 1
            BEGIN
                SELECT RAISE(ABORT, 'risk_configs 的 id 必须为 1');
            END
        """)

        # System configs singleton triggers
        await self._db.execute("""
            CREATE TRIGGER IF NOT EXISTS system_configs_single_row_insert
            BEFORE INSERT ON system_configs
            WHEN (SELECT COUNT(*) FROM system_configs) >= 1
            BEGIN
                SELECT RAISE(ABORT, 'system_configs 只能有一条记录');
            END
        """)

        await self._db.execute("""
            CREATE TRIGGER IF NOT EXISTS system_configs_enforce_id_insert
            BEFORE INSERT ON system_configs
            WHEN NEW.id != 1
            BEGIN
                SELECT RAISE(ABORT, 'system_configs 的 id 必须为 1');
            END
        """)

        await self._db.execute("""
            CREATE TRIGGER IF NOT EXISTS system_configs_enforce_id_update
            BEFORE UPDATE ON system_configs
            WHEN NEW.id != 1
            BEGIN
                SELECT RAISE(ABORT, 'system_configs 的 id 必须为 1');
            END
        """)

        # History triggers for strategy_configs
        await self._db.execute("""
            CREATE TRIGGER IF NOT EXISTS strategy_configs_audit_after_insert
            AFTER INSERT ON strategy_configs
            FOR EACH ROW
            BEGIN
                INSERT INTO config_history (config_type, config_id, action, old_value, new_value, created_at, created_by)
                VALUES (
                    'strategy', NEW.id, 'create', NULL,
                    json_object('name', NEW.name, 'triggers', NEW.triggers, 'filters', NEW.filters, 'apply_to', NEW.apply_to, 'is_active', NEW.is_active),
                    datetime('now'), 'system'
                );
            END
        """)

        await self._db.execute("""
            CREATE TRIGGER IF NOT EXISTS strategy_configs_audit_after_update
            AFTER UPDATE ON strategy_configs
            FOR EACH ROW
            BEGIN
                INSERT INTO config_history (config_type, config_id, action, old_value, new_value, created_at, created_by)
                VALUES (
                    'strategy', NEW.id, 'update',
                    json_object('name', OLD.name, 'triggers', OLD.triggers, 'filters', OLD.filters, 'apply_to', OLD.apply_to, 'is_active', OLD.is_active),
                    json_object('name', NEW.name, 'triggers', NEW.triggers, 'filters', NEW.filters, 'apply_to', NEW.apply_to, 'is_active', NEW.is_active),
                    datetime('now'), 'system'
                );
            END
        """)

        await self._db.execute("""
            CREATE TRIGGER IF NOT EXISTS strategy_configs_audit_after_delete
            AFTER DELETE ON strategy_configs
            FOR EACH ROW
            BEGIN
                INSERT INTO config_history (config_type, config_id, action, old_value, new_value, created_at, created_by)
                VALUES (
                    'strategy', OLD.id, 'delete',
                    json_object('name', OLD.name, 'triggers', OLD.triggers, 'filters', OLD.filters, 'apply_to', OLD.apply_to, 'is_active', OLD.is_active),
                    NULL, datetime('now'), 'system'
                );
            END
        """)

        # History triggers for risk_configs
        await self._db.execute("""
            CREATE TRIGGER IF NOT EXISTS risk_configs_audit_after_insert
            AFTER INSERT ON risk_configs
            FOR EACH ROW
            BEGIN
                INSERT INTO config_history (config_type, config_id, action, old_value, new_value, created_at, created_by)
                VALUES (
                    'risk', NEW.id, 'create', NULL,
                    json_object('max_loss_percent', NEW.max_loss_percent, 'max_total_exposure', NEW.max_total_exposure, 'max_leverage', NEW.max_leverage),
                    datetime('now'), 'system'
                );
            END
        """)

        await self._db.execute("""
            CREATE TRIGGER IF NOT EXISTS risk_configs_audit_after_update
            AFTER UPDATE ON risk_configs
            FOR EACH ROW
            BEGIN
                INSERT INTO config_history (config_type, config_id, action, old_value, new_value, created_at, created_by)
                VALUES (
                    'risk', NEW.id, 'update',
                    json_object('max_loss_percent', OLD.max_loss_percent, 'max_total_exposure', OLD.max_total_exposure, 'max_leverage', OLD.max_leverage),
                    json_object('max_loss_percent', NEW.max_loss_percent, 'max_total_exposure', NEW.max_total_exposure, 'max_leverage', NEW.max_leverage),
                    datetime('now'), 'system'
                );
            END
        """)

        await self._db.execute("""
            CREATE TRIGGER IF NOT EXISTS risk_configs_audit_after_delete
            AFTER DELETE ON risk_configs
            FOR EACH ROW
            BEGIN
                INSERT INTO config_history (config_type, config_id, action, old_value, new_value, created_at, created_by)
                VALUES (
                    'risk', OLD.id, 'delete',
                    json_object('max_loss_percent', OLD.max_loss_percent, 'max_total_exposure', OLD.max_total_exposure, 'max_leverage', OLD.max_leverage),
                    NULL, datetime('now'), 'system'
                );
            END
        """)

        # History triggers for system_configs
        await self._db.execute("""
            CREATE TRIGGER IF NOT EXISTS system_configs_audit_after_insert
            AFTER INSERT ON system_configs
            FOR EACH ROW
            BEGIN
                INSERT INTO config_history (config_type, config_id, action, old_value, new_value, created_at, created_by)
                VALUES (
                    'system', NEW.id, 'create', NULL,
                    json_object('history_bars', NEW.history_bars, 'queue_batch_size', NEW.queue_batch_size, 'queue_flush_interval', NEW.queue_flush_interval),
                    datetime('now'), 'system'
                );
            END
        """)

        await self._db.execute("""
            CREATE TRIGGER IF NOT EXISTS system_configs_audit_after_update
            AFTER UPDATE ON system_configs
            FOR EACH ROW
            BEGIN
                INSERT INTO config_history (config_type, config_id, action, old_value, new_value, created_at, created_by)
                VALUES (
                    'system', NEW.id, 'update',
                    json_object('history_bars', OLD.history_bars, 'queue_batch_size', OLD.queue_batch_size, 'queue_flush_interval', OLD.queue_flush_interval),
                    json_object('history_bars', NEW.history_bars, 'queue_batch_size', NEW.queue_batch_size, 'queue_flush_interval', NEW.queue_flush_interval),
                    datetime('now'), 'system'
                );
            END
        """)

    async def _initialize_default_configs(self) -> None:
        """Initialize default singleton records if they don't exist."""
        # Initialize risk_configs with default values
        await self._db.execute("""
            INSERT OR IGNORE INTO risk_configs (id, max_loss_percent, max_total_exposure, max_leverage)
            VALUES (1, 1.0, 0.8, 10)
        """)

        # Initialize system_configs with default values
        await self._db.execute("""
            INSERT OR IGNORE INTO system_configs (id, history_bars, queue_batch_size, queue_flush_interval)
            VALUES (1, 100, 10, 5.0)
        """)

        await self._db.commit()

    # ==================== Strategy Configs ====================

    async def list_strategies(self, include_inactive: bool = False) -> List[Dict[str, Any]]:
        """List all strategy configurations."""
        if include_inactive:
            query = "SELECT * FROM strategy_configs ORDER BY created_at DESC"
        else:
            query = "SELECT * FROM strategy_configs WHERE is_active = 1 ORDER BY created_at DESC"

        async with self._db.execute(query) as cursor:
            rows = await cursor.fetchall()
            strategies = []
            for row in rows:
                strategy = dict(row)
                strategy['triggers'] = json.loads(strategy['triggers'])
                strategy['filters'] = json.loads(strategy['filters'])
                strategy['apply_to'] = json.loads(strategy['apply_to'])
                if strategy.get('logic_tree'):
                    strategy['logic_tree'] = json.loads(strategy['logic_tree'])
                strategies.append(strategy)
            return strategies

    async def get_strategy(self, strategy_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific strategy by ID."""
        async with self._db.execute(
            "SELECT * FROM strategy_configs WHERE id = ?", (strategy_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                strategy = dict(row)
                strategy['triggers'] = json.loads(strategy['triggers'])
                strategy['filters'] = json.loads(strategy['filters'])
                strategy['apply_to'] = json.loads(strategy['apply_to'])
                if strategy.get('logic_tree'):
                    strategy['logic_tree'] = json.loads(strategy['logic_tree'])
                return strategy
            return None

    async def get_strategy_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a specific strategy by name."""
        async with self._db.execute(
            "SELECT * FROM strategy_configs WHERE name = ?", (name,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                strategy = dict(row)
                strategy['triggers'] = json.loads(strategy['triggers'])
                strategy['filters'] = json.loads(strategy['filters'])
                strategy['apply_to'] = json.loads(strategy['apply_to'])
                if strategy.get('logic_tree'):
                    strategy['logic_tree'] = json.loads(strategy['logic_tree'])
                return strategy
            return None

    async def get_active_strategy(self) -> Optional[Dict[str, Any]]:
        """Get the currently active strategy."""
        async with self._db.execute(
            "SELECT * FROM strategy_configs WHERE is_active = 1 LIMIT 1"
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                strategy = dict(row)
                strategy['triggers'] = json.loads(strategy['triggers'])
                strategy['filters'] = json.loads(strategy['filters'])
                strategy['apply_to'] = json.loads(strategy['apply_to'])
                if strategy.get('logic_tree'):
                    strategy['logic_tree'] = json.loads(strategy['logic_tree'])
                return strategy
            return None

    async def create_strategy(self, name: str, triggers: List[Dict], filters: List[Dict],
                              apply_to: List[str], description: str = None,
                              logic_tree: Dict = None) -> int:
        """Create a new strategy configuration."""
        now = datetime.now(timezone.utc).isoformat()

        cursor = await self._db.execute(
            """
            INSERT INTO strategy_configs (name, description, triggers, filters, logic_tree, apply_to, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (name, description, json.dumps(triggers), json.dumps(filters),
             json.dumps(logic_tree) if logic_tree else None, json.dumps(apply_to), now, now)
        )
        await self._db.commit()
        return cursor.lastrowid

    async def update_strategy(self, strategy_id: int, name: str = None, triggers: List[Dict] = None,
                              filters: List[Dict] = None, apply_to: List[str] = None,
                              description: str = None, logic_tree: Dict = None,
                              is_active: int = None) -> None:
        """Update an existing strategy configuration."""
        now = datetime.now(timezone.utc).isoformat()
        updates = []
        params = []

        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if triggers is not None:
            updates.append("triggers = ?")
            params.append(json.dumps(triggers))
        if filters is not None:
            updates.append("filters = ?")
            params.append(json.dumps(filters))
        if apply_to is not None:
            updates.append("apply_to = ?")
            params.append(json.dumps(apply_to))
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        if logic_tree is not None:
            updates.append("logic_tree = ?")
            params.append(json.dumps(logic_tree) if logic_tree else None)
        if is_active is not None:
            updates.append("is_active = ?")
            params.append(is_active)

        if updates:
            updates.append("updated_at = ?")
            params.append(now)
            params.append(strategy_id)

            query = f"UPDATE strategy_configs SET {', '.join(updates)} WHERE id = ?"
            await self._db.execute(query, params)
            await self._db.commit()

    async def delete_strategy(self, strategy_id: int) -> None:
        """Delete a strategy configuration."""
        await self._db.execute("DELETE FROM strategy_configs WHERE id = ?", (strategy_id,))
        await self._db.commit()

    async def activate_strategy(self, strategy_id: int) -> None:
        """Activate a strategy (automatically deactivates others due to trigger)."""
        await self.update_strategy(strategy_id, is_active=1)

    # ==================== Risk Configs ====================

    async def get_risk_config(self) -> Dict[str, Any]:
        """Get the risk configuration (singleton)."""
        async with self._db.execute(
            "SELECT * FROM risk_configs WHERE id = 1"
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def update_risk_config(self, max_loss_percent: float = None,
                                 max_total_exposure: float = None,
                                 max_leverage: int = None,
                                 description: str = None) -> None:
        """Update the risk configuration."""
        updates = []
        params = []

        if max_loss_percent is not None:
            updates.append("max_loss_percent = ?")
            params.append(max_loss_percent)
        if max_total_exposure is not None:
            updates.append("max_total_exposure = ?")
            params.append(max_total_exposure)
        if max_leverage is not None:
            updates.append("max_leverage = ?")
            params.append(max_leverage)
        if description is not None:
            updates.append("description = ?")
            params.append(description)

        if updates:
            updates.append("updated_at = datetime('now')")
            params.append(1)

            query = f"UPDATE risk_configs SET {', '.join(updates)} WHERE id = ?"
            await self._db.execute(query, params)
            await self._db.commit()

    # ==================== System Configs ====================

    async def get_system_config(self) -> Dict[str, Any]:
        """Get the system configuration (singleton)."""
        async with self._db.execute(
            "SELECT * FROM system_configs WHERE id = 1"
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def update_system_config(self, history_bars: int = None,
                                   queue_batch_size: int = None,
                                   queue_flush_interval: float = None,
                                   description: str = None) -> None:
        """Update the system configuration."""
        updates = []
        params = []

        if history_bars is not None:
            updates.append("history_bars = ?")
            params.append(history_bars)
        if queue_batch_size is not None:
            updates.append("queue_batch_size = ?")
            params.append(queue_batch_size)
        if queue_flush_interval is not None:
            updates.append("queue_flush_interval = ?")
            params.append(queue_flush_interval)
        if description is not None:
            updates.append("description = ?")
            params.append(description)

        if updates:
            updates.append("updated_at = datetime('now')")
            params.append(1)

            query = f"UPDATE system_configs SET {', '.join(updates)} WHERE id = ?"
            await self._db.execute(query, params)
            await self._db.commit()

    # ==================== Symbol Configs ====================

    async def list_symbols(self, enabled_only: bool = False) -> List[Dict[str, Any]]:
        """List all symbol configurations."""
        query = "SELECT * FROM symbol_configs ORDER BY symbol"
        if enabled_only:
            query = "SELECT * FROM symbol_configs WHERE is_enabled = 1 ORDER BY symbol"

        async with self._db.execute(query) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_symbol(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get a specific symbol configuration."""
        async with self._db.execute(
            "SELECT * FROM symbol_configs WHERE symbol = ?", (symbol,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_symbol_by_id(self, symbol_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific symbol configuration by ID."""
        async with self._db.execute(
            "SELECT * FROM symbol_configs WHERE id = ?", (symbol_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def add_symbol(self, symbol: str, is_core: int = 1, is_enabled: int = 1) -> int:
        """Add a new symbol configuration."""
        cursor = await self._db.execute(
            "INSERT INTO symbol_configs (symbol, is_core, is_enabled) VALUES (?, ?, ?)",
            (symbol, is_core, is_enabled)
        )
        await self._db.commit()
        return cursor.lastrowid

    async def update_symbol(self, symbol: str, is_core: int = None, is_enabled: int = None) -> None:
        """Update a symbol configuration."""
        updates = []
        params = []

        if is_core is not None:
            updates.append("is_core = ?")
            params.append(is_core)
        if is_enabled is not None:
            updates.append("is_enabled = ?")
            params.append(is_enabled)

        if updates:
            updates.append("updated_at = datetime('now')")
            params.append(symbol)

            query = f"UPDATE symbol_configs SET {', '.join(updates)} WHERE symbol = ?"
            await self._db.execute(query, params)
            await self._db.commit()

    async def remove_symbol(self, symbol: str) -> None:
        """Remove a symbol configuration."""
        # Check if it's a core symbol
        symbol_record = await self.get_symbol(symbol)
        if symbol_record and symbol_record.get('is_core'):
            raise ValueError("核心币种不可删除")

        await self._db.execute("DELETE FROM symbol_configs WHERE symbol = ?", (symbol,))
        await self._db.commit()

    async def remove_symbol_by_id(self, symbol_id: int) -> bool:
        """Remove a symbol configuration by ID.

        Returns:
            bool: True if deleted, False if not found

        Raises:
            ValueError: If attempting to delete a core symbol
        """
        # Check if it's a core symbol
        symbol_record = await self.get_symbol_by_id(symbol_id)
        if not symbol_record:
            return False
        if symbol_record.get('is_core'):
            raise ValueError("核心币种不可删除")

        cursor = await self._db.execute("DELETE FROM symbol_configs WHERE id = ?", (symbol_id,))
        await self._db.commit()
        return cursor.rowcount > 0

    async def get_enabled_symbols(self) -> List[str]:
        """Get list of enabled symbols."""
        async with self._db.execute(
            "SELECT symbol FROM symbol_configs WHERE is_enabled = 1 ORDER BY symbol"
        ) as cursor:
            rows = await cursor.fetchall()
            return [row['symbol'] for row in rows]

    async def get_all_symbols(self) -> List[Dict[str, Any]]:
        """Get all symbol configurations (for API v1)."""
        return await self.list_symbols(enabled_only=False)

    async def delete_symbol(self, symbol_id: int) -> bool:
        """Delete a symbol configuration by ID (for API v1).

        Returns:
            bool: True if deleted, False if not found

        Raises:
            ValueError: If attempting to delete a core symbol
        """
        return await self.remove_symbol_by_id(symbol_id)

    async def get_core_symbols(self) -> List[str]:
        """Get list of core symbols."""
        async with self._db.execute(
            "SELECT symbol FROM symbol_configs WHERE is_core = 1 ORDER BY symbol"
        ) as cursor:
            rows = await cursor.fetchall()
            return [row['symbol'] for row in rows]

    # ==================== Notification Configs ====================

    async def list_notifications(self, enabled_only: bool = False) -> List[Dict[str, Any]]:
        """List all notification configurations."""
        query = "SELECT * FROM notification_configs ORDER BY channel"
        if enabled_only:
            query = "SELECT * FROM notification_configs WHERE is_enabled = 1 ORDER BY channel"

        async with self._db.execute(query) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_notification(self, notification_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific notification configuration."""
        async with self._db.execute(
            "SELECT * FROM notification_configs WHERE id = ?", (notification_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def add_notification(self, channel: str, webhook_url: str,
                               is_enabled: int = 1, description: str = None) -> int:
        """Add a new notification configuration."""
        cursor = await self._db.execute(
            "INSERT INTO notification_configs (channel, webhook_url, is_enabled, description) VALUES (?, ?, ?, ?)",
            (channel, webhook_url, is_enabled, description)
        )
        await self._db.commit()
        return cursor.lastrowid

    async def update_notification(self, notification_id: int, channel: str = None,
                                  webhook_url: str = None, is_enabled: int = None,
                                  description: str = None) -> None:
        """Update a notification configuration."""
        updates = []
        params = []

        if channel is not None:
            updates.append("channel = ?")
            params.append(channel)
        if webhook_url is not None:
            updates.append("webhook_url = ?")
            params.append(webhook_url)
        if is_enabled is not None:
            updates.append("is_enabled = ?")
            params.append(is_enabled)
        if description is not None:
            updates.append("description = ?")
            params.append(description)

        if updates:
            updates.append("updated_at = datetime('now')")
            params.append(notification_id)

            query = f"UPDATE notification_configs SET {', '.join(updates)} WHERE id = ?"
            await self._db.execute(query, params)
            await self._db.commit()

    async def delete_notification(self, notification_id: int) -> None:
        """Delete a notification configuration."""
        await self._db.execute(
            "DELETE FROM notification_configs WHERE id = ?", (notification_id,)
        )
        await self._db.commit()

    async def get_enabled_notifications(self) -> List[Dict[str, Any]]:
        """Get list of enabled notification configurations."""
        return await self.list_notifications(enabled_only=True)

    async def get_all_notifications(self) -> List[Dict[str, Any]]:
        """Get all notification configurations (for API v1)."""
        return await self.list_notifications(enabled_only=False)

    async def get_notification_by_id(self, notification_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific notification configuration by ID (for API v1)."""
        return await self.get_notification(notification_id)

    # ==================== Config Snapshots ====================

    async def list_snapshots(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """List configuration snapshots."""
        async with self._db.execute(
            "SELECT * FROM config_snapshots ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset)
        ) as cursor:
            rows = await cursor.fetchall()
            snapshots = []
            for row in rows:
                snapshot = dict(row)
                snapshot['config_json'] = json.loads(snapshot['config_json'])
                snapshots.append(snapshot)
            return snapshots

    async def get_snapshot(self, snapshot_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific snapshot by ID."""
        async with self._db.execute(
            "SELECT * FROM config_snapshots WHERE id = ?", (snapshot_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                snapshot = dict(row)
                snapshot['config_json'] = json.loads(snapshot['config_json'])
                return snapshot
            return None

    async def create_snapshot(self, name: str, config_json: Dict,
                              description: str = None, created_by: str = 'user',
                              is_auto: bool = False, trigger_type: str = None) -> int:
        """Create a new configuration snapshot."""
        cursor = await self._db.execute(
            """
            INSERT INTO config_snapshots (name, description, config_json, is_auto, trigger_type, created_by)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (name, description, json.dumps(config_json), 1 if is_auto else 0, trigger_type, created_by)
        )
        await self._db.commit()
        return cursor.lastrowid

    async def delete_snapshot(self, snapshot_id: int) -> None:
        """Delete a configuration snapshot."""
        await self._db.execute(
            "DELETE FROM config_snapshots WHERE id = ?", (snapshot_id,)
        )
        await self._db.commit()

    async def get_snapshot_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a specific snapshot by name."""
        async with self._db.execute(
            "SELECT * FROM config_snapshots WHERE name = ? ORDER BY created_at DESC LIMIT 1",
            (name,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                snapshot = dict(row)
                snapshot['config_json'] = json.loads(snapshot['config_json'])
                return snapshot
            return None

    async def get_snapshot_count(self) -> int:
        """Get total number of snapshots."""
        async with self._db.execute(
            "SELECT COUNT(*) as count FROM config_snapshots"
        ) as cursor:
            row = await cursor.fetchone()
            return row['count'] if row else 0

    # ==================== Config History ====================

    async def get_history(self, config_type: str = None, config_id: int = None,
                          limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Get configuration change history."""
        query = "SELECT * FROM config_history WHERE 1=1"
        params = []

        if config_type:
            query += " AND config_type = ?"
            params.append(config_type)
        if config_id:
            query += " AND config_id = ?"
            params.append(config_id)

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        async with self._db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            history = []
            for row in rows:
                h = dict(row)
                if h.get('old_value'):
                    h['old_value'] = json.loads(h['old_value'])
                if h.get('new_value'):
                    h['new_value'] = json.loads(h['new_value'])
                history.append(h)
            return history

    async def get_history_by_id(self, history_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific history entry by ID."""
        async with self._db.execute(
            "SELECT * FROM config_history WHERE id = ?", (history_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                h = dict(row)
                if h.get('old_value'):
                    h['old_value'] = json.loads(h['old_value'])
                if h.get('new_value'):
                    h['new_value'] = json.loads(h['new_value'])
                return h
            return None

    async def get_history_count(self, config_type: str = None, config_id: int = None) -> int:
        """Get total count of configuration history."""
        query = "SELECT COUNT(*) as count FROM config_history WHERE 1=1"
        params = []

        if config_type:
            query += " AND config_type = ?"
            params.append(config_type)
        if config_id:
            query += " AND config_id = ?"
            params.append(config_id)

        async with self._db.execute(query, params) as cursor:
            row = await cursor.fetchone()
            return row['count'] if row else 0

    async def clear_old_history(self, keep_days: int = 30) -> None:
        """Clear configuration history older than specified days."""
        await self._db.execute(
            "DELETE FROM config_history WHERE created_at < datetime('now', ?)",
            (f'-{keep_days} days',)
        )
        await self._db.commit()

    # ==================== Bulk Operations ====================

    async def get_full_config(self) -> Dict[str, Any]:
        """Get complete configuration for export or UI display."""
        strategy = await self.get_active_strategy()
        risk = await self.get_risk_config()
        system = await self.get_system_config()
        symbols = await self.list_symbols()
        notifications = await self.list_notifications()

        return {
            "strategy": strategy,
            "risk": risk,
            "system": system,
            "symbols": symbols,
            "notifications": notifications,
        }

    async def create_full_snapshot(self, name: str, description: str = None,
                                   created_by: str = 'user',
                                   is_auto: bool = False,
                                   trigger_type: str = None) -> int:
        """Create a snapshot of the complete configuration."""
        config_json = await self.get_full_config()
        config_json['exported_at'] = datetime.now(timezone.utc).isoformat()
        config_json['version'] = '1.0'

        return await self.create_snapshot(
            name=name,
            description=description,
            config_json=config_json,
            created_by=created_by,
            is_auto=is_auto,
            trigger_type=trigger_type,
        )

    async def rollback_snapshot(self, snapshot_id: int) -> bool:
        """Rollback to a snapshot configuration.

        This method restores all configurations from a snapshot.
        Note: This is a complex operation that should be used with caution.

        Args:
            snapshot_id: ID of the snapshot to rollback to

        Returns:
            bool: True if rollback was successful

        Raises:
            ValueError: If snapshot not found
        """
        snapshot = await self.get_snapshot(snapshot_id)
        if not snapshot:
            raise ValueError(f"Snapshot {snapshot_id} not found")

        config = snapshot['config_json']

        # Rollback risk config
        if 'risk' in config:
            risk = config['risk']
            await self.update_risk_config(
                max_loss_percent=risk.get('max_loss_percent'),
                max_total_exposure=risk.get('max_total_exposure'),
                max_leverage=risk.get('max_leverage'),
            )

        # Rollback system config
        if 'system' in config:
            system = config['system']
            await self.update_system_config(
                history_bars=system.get('history_bars'),
                queue_batch_size=system.get('queue_batch_size'),
                queue_flush_interval=system.get('queue_flush_interval'),
            )

        # Rollback symbols (add missing, update existing)
        if 'symbols' in config:
            for symbol_data in config['symbols']:
                existing = await self.get_symbol(symbol_data['symbol'])
                if existing:
                    await self.update_symbol(
                        symbol=symbol_data['symbol'],
                        is_core=symbol_data.get('is_core'),
                        is_enabled=symbol_data.get('is_enabled'),
                    )
                else:
                    await self.add_symbol(
                        symbol=symbol_data['symbol'],
                        is_core=symbol_data.get('is_core', 1),
                        is_enabled=symbol_data.get('is_enabled', 1),
                    )

        # Rollback notifications (add missing, update existing)
        if 'notifications' in config:
            for notif_data in config['notifications']:
                existing = await self.get_notification(notif_data['id']) if 'id' in notif_data else None
                if existing:
                    await self.update_notification(
                        notification_id=notif_data['id'],
                        channel=notif_data.get('channel'),
                        webhook_url=notif_data.get('webhook_url'),
                        is_enabled=notif_data.get('is_enabled'),
                    )
                else:
                    await self.add_notification(
                        channel=notif_data.get('channel'),
                        webhook_url=notif_data.get('webhook_url'),
                        is_enabled=notif_data.get('is_enabled', 1),
                        description=notif_data.get('description'),
                    )

        return True

    async def close(self) -> None:
        """Close database connection."""
        if self._db:
            await self._db.close()
            logger.info("配置数据库连接已关闭")
