#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
初始化配置数据库表结构脚本

用法:
    python scripts/init_config_db.py

功能:
    1. 创建所有配置表
    2. 创建所有索引
    3. 创建所有触发器（单例约束 + 历史记录）
    4. 插入默认配置数据
"""

import asyncio
import aiosqlite
import os
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# 数据库文件路径
DB_PATH = os.getenv("CONFIG_DB_PATH", "data/config.db")


async def create_tables(conn: aiosqlite.Connection) -> None:
    """创建所有表结构"""
    print("正在创建表结构...")

    # 1. 策略配置表
    await conn.execute("""
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
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_strategy_active ON strategy_configs(is_active)")

    # 2. 风控配置表（单例）
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS risk_configs (
            id                   INTEGER PRIMARY KEY,
            max_loss_percent     REAL NOT NULL DEFAULT 1.0 CHECK (max_loss_percent BETWEEN 0.001 AND 0.05),
            max_total_exposure   REAL NOT NULL DEFAULT 0.8 CHECK (max_total_exposure BETWEEN 0.5 AND 1.0),
            max_leverage         INTEGER NOT NULL DEFAULT 10 CHECK (max_leverage BETWEEN 1 AND 125),
            description          TEXT,
            updated_at           DATETIME NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # 3. 系统配置表（单例）
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS system_configs (
            id                   INTEGER PRIMARY KEY,
            history_bars         INTEGER NOT NULL DEFAULT 100 CHECK (history_bars BETWEEN 50 AND 1000),
            queue_batch_size     INTEGER NOT NULL DEFAULT 10 CHECK (queue_batch_size BETWEEN 1 AND 100),
            queue_flush_interval REAL NOT NULL DEFAULT 5.0 CHECK (queue_flush_interval BETWEEN 1.0 AND 60.0),
            description          TEXT,
            updated_at           DATETIME NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # 4. 币池配置表
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS symbol_configs (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol        TEXT NOT NULL UNIQUE,
            is_core       INTEGER NOT NULL DEFAULT 1 CHECK (is_core IN (0, 1)),
            is_enabled    INTEGER NOT NULL DEFAULT 1 CHECK (is_enabled IN (0, 1)),
            updated_at    DATETIME NOT NULL DEFAULT (datetime('now'))
        )
    """)
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_symbol_enabled ON symbol_configs(is_enabled)")

    # 5. 通知配置表
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS notification_configs (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            channel       TEXT NOT NULL CHECK (channel IN ('feishu', 'wecom', 'telegram')),
            webhook_url   TEXT NOT NULL,
            is_enabled    INTEGER NOT NULL DEFAULT 1 CHECK (is_enabled IN (0, 1)),
            description   TEXT,
            updated_at    DATETIME NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # 6. 配置历史表
    await conn.execute("""
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
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_history_type ON config_history(config_type, config_id)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_history_time ON config_history(created_at)")

    # 7. 配置快照表
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS config_snapshots (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT NOT NULL,
            description     TEXT,
            config_json     TEXT NOT NULL,
            created_at      DATETIME NOT NULL DEFAULT (datetime('now')),
            created_by      TEXT DEFAULT 'user'
        )
    """)
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshot_name ON config_snapshots(name)")

    # 8. 为配置快照表添加自动快照字段（如果不存在）
    try:
        await conn.execute("ALTER TABLE config_snapshots ADD COLUMN is_auto INTEGER DEFAULT 0 CHECK (is_auto IN (0, 1))")
    except aiosqlite.OperationalError:
        pass  # 列已存在

    try:
        await conn.execute("ALTER TABLE config_snapshots ADD COLUMN trigger_type TEXT")
    except aiosqlite.OperationalError:
        pass  # 列已存在

    print("  ✓ 表结构创建完成")


async def create_triggers(conn: aiosqlite.Connection) -> None:
    """创建所有触发器"""
    print("正在创建触发器...")

    # ========== 策略配置单例约束触发器 ==========
    await conn.execute("DROP TRIGGER IF EXISTS check_single_active_strategy_before_insert")
    await conn.execute("""
        CREATE TRIGGER check_single_active_strategy_before_insert
        BEFORE INSERT ON strategy_configs
        WHEN NEW.is_active = 1 AND (SELECT COUNT(*) FROM strategy_configs WHERE is_active = 1) > 0
        BEGIN
            SELECT RAISE(ABORT, '同一时间只能有一个激活的策略');
        END
    """)

    await conn.execute("DROP TRIGGER IF EXISTS check_single_active_strategy_before_update")
    await conn.execute("""
        CREATE TRIGGER check_single_active_strategy_before_update
        BEFORE UPDATE ON strategy_configs
        WHEN NEW.is_active = 1 AND (SELECT COUNT(*) FROM strategy_configs WHERE is_active = 1 AND id != NEW.id) > 0
        BEGIN
            SELECT RAISE(ABORT, '同一时间只能有一个激活的策略');
        END
    """)

    # ========== 风控配置单例约束触发器 ==========
    await conn.execute("DROP TRIGGER IF EXISTS risk_configs_single_row_insert")
    await conn.execute("""
        CREATE TRIGGER risk_configs_single_row_insert
        BEFORE INSERT ON risk_configs
        WHEN (SELECT COUNT(*) FROM risk_configs) >= 1
        BEGIN
            SELECT RAISE(ABORT, 'risk_configs 只能有一条记录');
        END
    """)

    await conn.execute("DROP TRIGGER IF EXISTS risk_configs_enforce_id_insert")
    await conn.execute("""
        CREATE TRIGGER risk_configs_enforce_id_insert
        BEFORE INSERT ON risk_configs
        WHEN NEW.id != 1
        BEGIN
            SELECT RAISE(ABORT, 'risk_configs 的 id 必须为 1');
        END
    """)

    await conn.execute("DROP TRIGGER IF EXISTS risk_configs_enforce_id_update")
    await conn.execute("""
        CREATE TRIGGER risk_configs_enforce_id_update
        BEFORE UPDATE ON risk_configs
        WHEN NEW.id != 1
        BEGIN
            SELECT RAISE(ABORT, 'risk_configs 的 id 必须为 1');
        END
    """)

    # ========== 系统配置单例约束触发器 ==========
    await conn.execute("DROP TRIGGER IF EXISTS system_configs_single_row_insert")
    await conn.execute("""
        CREATE TRIGGER system_configs_single_row_insert
        BEFORE INSERT ON system_configs
        WHEN (SELECT COUNT(*) FROM system_configs) >= 1
        BEGIN
            SELECT RAISE(ABORT, 'system_configs 只能有一条记录');
        END
    """)

    await conn.execute("DROP TRIGGER IF EXISTS system_configs_enforce_id_insert")
    await conn.execute("""
        CREATE TRIGGER system_configs_enforce_id_insert
        BEFORE INSERT ON system_configs
        WHEN NEW.id != 1
        BEGIN
            SELECT RAISE(ABORT, 'system_configs 的 id 必须为 1');
        END
    """)

    await conn.execute("DROP TRIGGER IF EXISTS system_configs_enforce_id_update")
    await conn.execute("""
        CREATE TRIGGER system_configs_enforce_id_update
        BEFORE UPDATE ON system_configs
        WHEN NEW.id != 1
        BEGIN
            SELECT RAISE(ABORT, 'system_configs 的 id 必须为 1');
        END
    """)

    # ========== 策略配置历史触发器 ==========
    await conn.execute("DROP TRIGGER IF EXISTS strategy_configs_audit_after_insert")
    await conn.execute("""
        CREATE TRIGGER strategy_configs_audit_after_insert
        AFTER INSERT ON strategy_configs
        FOR EACH ROW
        BEGIN
            INSERT INTO config_history (config_type, config_id, action, old_value, new_value, created_at, created_by)
            VALUES (
                'strategy',
                NEW.id,
                'create',
                NULL,
                json_object('name', NEW.name, 'triggers', NEW.triggers, 'filters', NEW.filters, 'apply_to', NEW.apply_to, 'is_active', NEW.is_active),
                datetime('now'),
                'system'
            );
        END
    """)

    await conn.execute("DROP TRIGGER IF EXISTS strategy_configs_audit_after_update")
    await conn.execute("""
        CREATE TRIGGER strategy_configs_audit_after_update
        AFTER UPDATE ON strategy_configs
        FOR EACH ROW
        BEGIN
            INSERT INTO config_history (config_type, config_id, action, old_value, new_value, created_at, created_by)
            VALUES (
                'strategy',
                NEW.id,
                'update',
                json_object('name', OLD.name, 'triggers', OLD.triggers, 'filters', OLD.filters, 'apply_to', OLD.apply_to, 'is_active', OLD.is_active),
                json_object('name', NEW.name, 'triggers', NEW.triggers, 'filters', NEW.filters, 'apply_to', NEW.apply_to, 'is_active', NEW.is_active),
                datetime('now'),
                'system'
            );
        END
    """)

    await conn.execute("DROP TRIGGER IF EXISTS strategy_configs_audit_after_delete")
    await conn.execute("""
        CREATE TRIGGER strategy_configs_audit_after_delete
        AFTER DELETE ON strategy_configs
        FOR EACH ROW
        BEGIN
            INSERT INTO config_history (config_type, config_id, action, old_value, new_value, created_at, created_by)
            VALUES (
                'strategy',
                OLD.id,
                'delete',
                json_object('name', OLD.name, 'triggers', OLD.triggers, 'filters', OLD.filters, 'apply_to', OLD.apply_to, 'is_active', OLD.is_active),
                NULL,
                datetime('now'),
                'system'
            );
        END
    """)

    # ========== 风控配置历史触发器 ==========
    await conn.execute("DROP TRIGGER IF EXISTS risk_configs_audit_after_insert")
    await conn.execute("""
        CREATE TRIGGER risk_configs_audit_after_insert
        AFTER INSERT ON risk_configs
        FOR EACH ROW
        BEGIN
            INSERT INTO config_history (config_type, config_id, action, old_value, new_value, created_at, created_by)
            VALUES (
                'risk',
                NEW.id,
                'create',
                NULL,
                json_object('max_loss_percent', NEW.max_loss_percent, 'max_total_exposure', NEW.max_total_exposure, 'max_leverage', NEW.max_leverage),
                datetime('now'),
                'system'
            );
        END
    """)

    await conn.execute("DROP TRIGGER IF EXISTS risk_configs_audit_after_update")
    await conn.execute("""
        CREATE TRIGGER risk_configs_audit_after_update
        AFTER UPDATE ON risk_configs
        FOR EACH ROW
        BEGIN
            INSERT INTO config_history (config_type, config_id, action, old_value, new_value, created_at, created_by)
            VALUES (
                'risk',
                NEW.id,
                'update',
                json_object('max_loss_percent', OLD.max_loss_percent, 'max_total_exposure', OLD.max_total_exposure, 'max_leverage', OLD.max_leverage),
                json_object('max_loss_percent', NEW.max_loss_percent, 'max_total_exposure', NEW.max_total_exposure, 'max_leverage', NEW.max_leverage),
                datetime('now'),
                'system'
            );
        END
    """)

    await conn.execute("DROP TRIGGER IF EXISTS risk_configs_audit_after_delete")
    await conn.execute("""
        CREATE TRIGGER risk_configs_audit_after_delete
        AFTER DELETE ON risk_configs
        FOR EACH ROW
        BEGIN
            INSERT INTO config_history (config_type, config_id, action, old_value, new_value, created_at, created_by)
            VALUES (
                'risk',
                OLD.id,
                'delete',
                json_object('max_loss_percent', OLD.max_loss_percent, 'max_total_exposure', OLD.max_total_exposure, 'max_leverage', OLD.max_leverage),
                NULL,
                datetime('now'),
                'system'
            );
        END
    """)

    # ========== 系统配置历史触发器 ==========
    await conn.execute("DROP TRIGGER IF EXISTS system_configs_audit_after_insert")
    await conn.execute("""
        CREATE TRIGGER system_configs_audit_after_insert
        AFTER INSERT ON system_configs
        FOR EACH ROW
        BEGIN
            INSERT INTO config_history (config_type, config_id, action, old_value, new_value, created_at, created_by)
            VALUES (
                'system',
                NEW.id,
                'create',
                NULL,
                json_object('history_bars', NEW.history_bars, 'queue_batch_size', NEW.queue_batch_size, 'queue_flush_interval', NEW.queue_flush_interval),
                datetime('now'),
                'system'
            );
        END
    """)

    await conn.execute("DROP TRIGGER IF EXISTS system_configs_audit_after_update")
    await conn.execute("""
        CREATE TRIGGER system_configs_audit_after_update
        AFTER UPDATE ON system_configs
        FOR EACH ROW
        BEGIN
            INSERT INTO config_history (config_type, config_id, action, old_value, new_value, created_at, created_by)
            VALUES (
                'system',
                NEW.id,
                'update',
                json_object('history_bars', OLD.history_bars, 'queue_batch_size', OLD.queue_batch_size, 'queue_flush_interval', OLD.queue_flush_interval),
                json_object('history_bars', NEW.history_bars, 'queue_batch_size', NEW.queue_batch_size, 'queue_flush_interval', NEW.queue_flush_interval),
                datetime('now'),
                'system'
            );
        END
    """)

    # ========== 币池配置历史触发器 ==========
    await conn.execute("DROP TRIGGER IF EXISTS symbol_configs_audit_after_insert")
    await conn.execute("""
        CREATE TRIGGER symbol_configs_audit_after_insert
        AFTER INSERT ON symbol_configs
        FOR EACH ROW
        BEGIN
            INSERT INTO config_history (config_type, config_id, action, old_value, new_value, created_at, created_by)
            VALUES (
                'symbol',
                NEW.id,
                'create',
                NULL,
                json_object('symbol', NEW.symbol, 'is_core', NEW.is_core, 'is_enabled', NEW.is_enabled),
                datetime('now'),
                'system'
            );
        END
    """)

    await conn.execute("DROP TRIGGER IF EXISTS symbol_configs_audit_after_update")
    await conn.execute("""
        CREATE TRIGGER symbol_configs_audit_after_update
        AFTER UPDATE ON symbol_configs
        FOR EACH ROW
        BEGIN
            INSERT INTO config_history (config_type, config_id, action, old_value, new_value, created_at, created_by)
            VALUES (
                'symbol',
                NEW.id,
                'update',
                json_object('symbol', OLD.symbol, 'is_core', OLD.is_core, 'is_enabled', OLD.is_enabled),
                json_object('symbol', NEW.symbol, 'is_core', NEW.is_core, 'is_enabled', NEW.is_enabled),
                datetime('now'),
                'system'
            );
        END
    """)

    await conn.execute("DROP TRIGGER IF EXISTS symbol_configs_audit_after_delete")
    await conn.execute("""
        CREATE TRIGGER symbol_configs_audit_after_delete
        AFTER DELETE ON symbol_configs
        FOR EACH ROW
        BEGIN
            INSERT INTO config_history (config_type, config_id, action, old_value, new_value, created_at, created_by)
            VALUES (
                'symbol',
                OLD.id,
                'delete',
                json_object('symbol', OLD.symbol, 'is_core', OLD.is_core, 'is_enabled', OLD.is_enabled),
                NULL,
                datetime('now'),
                'system'
            );
        END
    """)

    # ========== 通知配置历史触发器 ==========
    await conn.execute("DROP TRIGGER IF EXISTS notification_configs_audit_after_insert")
    await conn.execute("""
        CREATE TRIGGER notification_configs_audit_after_insert
        AFTER INSERT ON notification_configs
        FOR EACH ROW
        BEGIN
            INSERT INTO config_history (config_type, config_id, action, old_value, new_value, created_at, created_by)
            VALUES (
                'notification',
                NEW.id,
                'create',
                NULL,
                json_object('channel', NEW.channel, 'webhook_url', NEW.webhook_url, 'is_enabled', NEW.is_enabled, 'description', NEW.description),
                datetime('now'),
                'system'
            );
        END
    """)

    await conn.execute("DROP TRIGGER IF EXISTS notification_configs_audit_after_update")
    await conn.execute("""
        CREATE TRIGGER notification_configs_audit_after_update
        AFTER UPDATE ON notification_configs
        FOR EACH ROW
        BEGIN
            INSERT INTO config_history (config_type, config_id, action, old_value, new_value, created_at, created_by)
            VALUES (
                'notification',
                NEW.id,
                'update',
                json_object('channel', OLD.channel, 'webhook_url', OLD.webhook_url, 'is_enabled', OLD.is_enabled, 'description', OLD.description),
                json_object('channel', NEW.channel, 'webhook_url', NEW.webhook_url, 'is_enabled', NEW.is_enabled, 'description', NEW.description),
                datetime('now'),
                'system'
            );
        END
    """)

    await conn.execute("DROP TRIGGER IF EXISTS notification_configs_audit_after_delete")
    await conn.execute("""
        CREATE TRIGGER notification_configs_audit_after_delete
        AFTER DELETE ON notification_configs
        FOR EACH ROW
        BEGIN
            INSERT INTO config_history (config_type, config_id, action, old_value, new_value, created_at, created_by)
            VALUES (
                'notification',
                OLD.id,
                'delete',
                json_object('channel', OLD.channel, 'webhook_url', OLD.webhook_url, 'is_enabled', OLD.is_enabled, 'description', OLD.description),
                NULL,
                datetime('now'),
                'system'
            );
        END
    """)

    print("  ✓ 触发器创建完成")


async def insert_default_data(conn: aiosqlite.Connection) -> None:
    """插入默认配置数据"""
    print("正在插入默认配置数据...")

    # 1. 默认风控配置
    await conn.execute("""
        INSERT OR IGNORE INTO risk_configs (id, max_loss_percent, max_total_exposure, max_leverage)
        VALUES (1, 1.0, 0.8, 10)
    """)

    # 2. 默认系统配置
    await conn.execute("""
        INSERT OR IGNORE INTO system_configs (id, history_bars, queue_batch_size, queue_flush_interval)
        VALUES (1, 100, 10, 5.0)
    """)

    # 3. 默认核心币池配置
    core_symbols = [
        ("BTC/USDT:USDT", 1, 1),
        ("ETH/USDT:USDT", 1, 1),
        ("SOL/USDT:USDT", 1, 1),
        ("BNB/USDT:USDT", 1, 1),
    ]
    for symbol, is_core, is_enabled in core_symbols:
        await conn.execute("""
            INSERT OR IGNORE INTO symbol_configs (symbol, is_core, is_enabled)
            VALUES (?, ?, ?)
        """, (symbol, is_core, is_enabled))

    # 4. 默认策略配置（Pinbar + EMA 趋势过滤）
    default_strategy = """
        {
            "name": "Pinbar+EMA60",
            "description": "Pinbar 形态策略 + EMA60 趋势过滤",
            "triggers": [
                {
                    "type": "pinbar",
                    "enabled": true,
                    "params": {
                        "min_wick_ratio": 0.6,
                        "max_body_ratio": 0.3,
                        "body_position_tolerance": 0.1
                    }
                }
            ],
            "filters": [
                {
                    "type": "ema_trend",
                    "enabled": true,
                    "params": {
                        "period": 60
                    }
                },
                {
                    "type": "atr",
                    "enabled": true,
                    "params": {
                        "period": 14,
                        "min_atr_ratio": 0.3
                    }
                }
            ],
            "logic_tree": {
                "type": "AND",
                "children": [
                    {"type": "trigger", "id": "pinbar"},
                    {"type": "filter", "id": "ema_trend"},
                    {"type": "filter", "id": "atr"}
                ]
            },
            "apply_to": ["BTC/USDT:USDT:15m", "ETH/USDT:USDT:15m", "SOL/USDT:USDT:15m", "BNB/USDT:USDT:15m"],
            "is_active": 1
        }
    """

    await conn.execute("""
        INSERT OR IGNORE INTO strategy_configs (name, description, triggers, filters, logic_tree, apply_to, is_active)
        SELECT
            'Pinbar+EMA60',
            'Pinbar 形态策略 + EMA60 趋势过滤',
            '[{"type": "pinbar", "enabled": true, "params": {"min_wick_ratio": 0.6, "max_body_ratio": 0.3, "body_position_tolerance": 0.1}}]',
            '[{"type": "ema_trend", "enabled": true, "params": {"period": 60}}, {"type": "atr", "enabled": true, "params": {"period": 14, "min_atr_ratio": 0.3}}]',
            '{"type": "AND", "children": [{"type": "trigger", "id": "pinbar"}, {"type": "filter", "id": "ema_trend"}, {"type": "filter", "id": "atr"}]}',
            '["BTC/USDT:USDT:15m", "ETH/USDT:USDT:15m", "SOL/USDT:USDT:15m", "BNB/USDT:USDT:15m"]',
            1
        WHERE NOT EXISTS (SELECT 1 FROM strategy_configs WHERE name = 'Pinbar+EMA60')
    """)

    print("  ✓ 默认配置数据插入完成")


async def main() -> None:
    """主函数"""
    db_path = Path(DB_PATH)

    # 确保目录存在
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # 如果数据库已存在，先备份
    if db_path.exists():
        backup_path = db_path.with_suffix(".db.bak")
        print(f"发现现有数据库，正在备份到 {backup_path}...")
        import shutil
        shutil.copy2(db_path, backup_path)
        print(f"  ✓ 备份完成")

    print(f"正在初始化数据库：{db_path.absolute()}")
    print("=" * 60)

    async with aiosqlite.connect(db_path) as conn:
        # 启用外键约束
        await conn.execute("PRAGMA foreign_keys = ON")

        await create_tables(conn)
        await create_triggers(conn)
        await insert_default_data(conn)

        # 提交所有更改
        await conn.commit()

    print("=" * 60)
    print("数据库初始化完成！")
    print(f"数据库路径：{db_path.absolute()}")
    print("\n已创建的表:")
    print("  - strategy_configs      (策略配置表)")
    print("  - risk_configs          (风控配置表，单例)")
    print("  - system_configs        (系统配置表，单例)")
    print("  - symbol_configs        (币池配置表)")
    print("  - notification_configs  (通知配置表)")
    print("  - config_history        (配置历史表)")
    print("  - config_snapshots      (配置快照表)")
    print("\n已创建的触发器:")
    print("  - 单例约束触发器 (risk_configs, system_configs)")
    print("  - 激活策略唯一性触发器 (strategy_configs)")
    print("  - 历史记录触发器 (INSERT/UPDATE/DELETE)")


if __name__ == "__main__":
    asyncio.run(main())
