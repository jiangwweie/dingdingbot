#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 YAML 配置文件迁移配置到 SQLite 数据库脚本

用法:
    python scripts/migrate_config_to_db.py

功能:
    1. 从 config/core.yaml 和 config/user.yaml 读取配置
    2. 将配置数据迁移到 SQLite 数据库
    3. 创建迁移前快照（可选）
    4. 验证迁移结果
"""

import asyncio
import aiosqlite
import os
import sys
import json
from pathlib import Path
from datetime import datetime
from decimal import Decimal

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# 数据库文件路径
DB_PATH = os.getenv("CONFIG_DB_PATH", "data/config.db")

# YAML 配置文件路径
CORE_YAML_PATH = Path(__file__).parent.parent / "config" / "core.yaml"
USER_YAML_PATH = Path(__file__).parent.parent / "config" / "user.yaml"


def load_yaml_file(path: Path) -> dict:
    """加载 YAML 文件"""
    import yaml
    if not path.exists():
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def decimal_to_float(obj):
    """递归将 Decimal 转换为 float（用于 JSON 序列化）"""
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: decimal_to_float(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [decimal_to_float(item) for item in obj]
    return obj


async def create_migration_snapshot(conn: aiosqlite.Connection, description: str) -> int:
    """在迁移前创建当前配置的快照"""
    snapshot_name = f"pre-migration-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    # 导出当前配置
    config_export = {
        "exported_at": datetime.now().isoformat(),
        "version": "1.0",
        "description": description,
        "strategy": None,
        "risk": None,
        "system": None,
        "symbols": [],
        "notifications": []
    }

    # 获取当前策略配置
    async with conn.execute("SELECT * FROM strategy_configs LIMIT 1") as cursor:
        row = await cursor.fetchone()
        if row:
            config_export["strategy"] = {
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "triggers": json.loads(row[3]) if row[3] else [],
                "filters": json.loads(row[4]) if row[4] else [],
                "apply_to": json.loads(row[6]) if row[6] else [],
                "is_active": bool(row[7])
            }

    # 获取当前风控配置
    async with conn.execute("SELECT * FROM risk_configs WHERE id = 1") as cursor:
        row = await cursor.fetchone()
        if row:
            config_export["risk"] = {
                "max_loss_percent": row[1],
                "max_total_exposure": row[2],
                "max_leverage": row[3]
            }

    # 获取当前系统配置
    async with conn.execute("SELECT * FROM system_configs WHERE id = 1") as cursor:
        row = await cursor.fetchone()
        if row:
            config_export["system"] = {
                "history_bars": row[1],
                "queue_batch_size": row[2],
                "queue_flush_interval": row[3]
            }

    # 获取当前币池配置
    async with conn.execute("SELECT * FROM symbol_configs") as cursor:
        rows = await cursor.fetchall()
        config_export["symbols"] = [
            {"symbol": row[1], "is_core": bool(row[2]), "is_enabled": bool(row[3])}
            for row in rows
        ]

    # 获取当前通知配置
    async with conn.execute("SELECT * FROM notification_configs") as cursor:
        rows = await cursor.fetchall()
        config_export["notifications"] = [
            {"channel": row[1], "webhook_url": row[2], "is_enabled": bool(row[3]), "description": row[4]}
            for row in rows
        ]

    # 插入快照记录
    await conn.execute("""
        INSERT INTO config_snapshots (name, description, config_json, created_at, created_by, is_auto, trigger_type)
        VALUES (?, ?, ?, datetime('now'), 'migration_script', 1, 'migration')
    """, (snapshot_name, description, json.dumps(config_export, indent=2)))

    snapshot_id = conn.total_changes
    print(f"  ✓ 已创建迁移前快照：{snapshot_name} (ID: {snapshot_id})")
    return snapshot_id


async def migrate_system_config(conn: aiosqlite.Connection, core_config: dict) -> None:
    """迁移系统配置"""
    print("正在迁移系统配置...")

    history_bars = core_config.get("warmup", {}).get("history_bars", 100)
    pipeline_config = core_config.get("signal_pipeline", {})
    queue_config = pipeline_config.get("queue", {})

    # 检查是否已存在系统配置
    async with conn.execute("SELECT COUNT(*) FROM system_configs WHERE id = 1") as cursor:
        count = await cursor.fetchone()
        if count[0] > 0:
            # 已存在，执行更新
            await conn.execute("""
                UPDATE system_configs
                SET history_bars = ?,
                    queue_batch_size = ?,
                    queue_flush_interval = ?,
                    description = '从 YAML 迁移的系统配置',
                    updated_at = datetime('now')
                WHERE id = 1
            """, (
                history_bars,
                queue_config.get("batch_size", 10),
                queue_config.get("flush_interval", 5.0)
            ))
        else:
            # 不存在，执行插入
            await conn.execute("""
                INSERT INTO system_configs (id, history_bars, queue_batch_size, queue_flush_interval, description, updated_at)
                VALUES (1, ?, ?, ?, ?, datetime('now'))
            """, (
                history_bars,
                queue_config.get("batch_size", 10),
                queue_config.get("flush_interval", 5.0),
                "从 YAML 迁移的系统配置"
            ))

    print(f"  ✓ 系统配置迁移完成：history_bars={history_bars}")


async def migrate_risk_config(conn: aiosqlite.Connection, user_config: dict) -> None:
    """迁移风控配置"""
    print("正在迁移风控配置...")

    risk_config = user_config.get("risk", {})

    # 处理 Decimal 字符串
    max_loss = risk_config.get("max_loss_percent", "0.01")
    max_exposure = risk_config.get("max_total_exposure", "0.8")

    if isinstance(max_loss, str):
        max_loss = float(Decimal(max_loss))
    if isinstance(max_exposure, str):
        max_exposure = float(Decimal(max_exposure))

    # 检查是否已存在风控配置
    async with conn.execute("SELECT COUNT(*) FROM risk_configs WHERE id = 1") as cursor:
        count = await cursor.fetchone()
        if count[0] > 0:
            # 已存在，执行更新
            await conn.execute("""
                UPDATE risk_configs
                SET max_loss_percent = ?,
                    max_total_exposure = ?,
                    max_leverage = ?,
                    description = '从 YAML 迁移的风控配置',
                    updated_at = datetime('now')
                WHERE id = 1
            """, (
                max_loss,
                max_exposure,
                risk_config.get("max_leverage", 10)
            ))
        else:
            # 不存在，执行插入
            await conn.execute("""
                INSERT INTO risk_configs (id, max_loss_percent, max_total_exposure, max_leverage, description, updated_at)
                VALUES (1, ?, ?, ?, ?, datetime('now'))
            """, (
                max_loss,
                max_exposure,
                risk_config.get("max_leverage", 10),
                "从 YAML 迁移的风控配置"
            ))

    print(f"  ✓ 风控配置迁移完成：max_loss={max_loss}, max_exposure={max_exposure}")


async def migrate_symbol_config(conn: aiosqlite.Connection, core_config: dict) -> None:
    """迁移币池配置"""
    print("正在迁移币池配置...")

    core_symbols = core_config.get("core_symbols", [
        "BTC/USDT:USDT",
        "ETH/USDT:USDT",
        "SOL/USDT:USDT",
        "BNB/USDT:USDT"
    ])

    # 插入核心币
    for symbol in core_symbols:
        await conn.execute("""
            INSERT OR IGNORE INTO symbol_configs (symbol, is_core, is_enabled, updated_at)
            VALUES (?, 1, 1, datetime('now'))
        """, (symbol,))

    # 迁移用户配置中的币池
    user_symbols = core_config.get("user_symbols", [])
    for symbol in user_symbols:
        if symbol not in core_symbols:
            await conn.execute("""
                INSERT OR IGNORE INTO symbol_configs (symbol, is_core, is_enabled, updated_at)
                VALUES (?, 0, 1, datetime('now'))
            """, (symbol,))

    print(f"  ✓ 币池配置迁移完成：共 {len(core_symbols)} 个核心币")


async def migrate_notification_config(conn: aiosqlite.Connection, user_config: dict) -> None:
    """迁移通知配置"""
    print("正在迁移通知配置...")

    notification_config = user_config.get("notification", {})
    channels = notification_config.get("channels", [])

    migrated_count = 0
    for channel in channels:
        channel_type = channel.get("type", "feishu")
        webhook_url = channel.get("webhook_url", "")
        is_enabled = channel.get("enabled", True)
        description = channel.get("description", f"从 YAML 迁移的{channel_type}通知")

        # 映射通道类型
        channel_map = {
            "feishu": "feishu",
            "wecom": "wecom",
            "telegram": "telegram",
            "dingtalk": "feishu"  # 钉钉映射到飞书
        }
        mapped_channel = channel_map.get(channel_type, "feishu")

        await conn.execute("""
            INSERT INTO notification_configs (channel, webhook_url, is_enabled, description, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'))
        """, (mapped_channel, webhook_url, 1 if is_enabled else 0, description))
        migrated_count += 1

    if migrated_count == 0:
        print("  - 无通知配置需要迁移")
    else:
        print(f"  ✓ 通知配置迁移完成：共 {migrated_count} 个通道")


async def migrate_strategy_config(conn: aiosqlite.Connection, core_config: dict, user_config: dict) -> None:
    """迁移策略配置"""
    print("正在迁移策略配置...")

    # 检查是否已存在策略配置
    async with conn.execute("SELECT COUNT(*) FROM strategy_configs") as cursor:
        count = await cursor.fetchone()
        if count[0] > 0:
            print("  - 已存在策略配置，跳过迁移")
            return

    # 从 user.yaml 读取策略配置
    active_strategies = user_config.get("active_strategies", [])

    if not active_strategies:
        # 使用默认配置
        print("  - 无活跃策略配置，使用默认配置")
        await conn.execute("""
            INSERT INTO strategy_configs (name, description, triggers, filters, logic_tree, apply_to, is_active)
            VALUES (
                'Pinbar+EMA60',
                '从 YAML 迁移的默认策略',
                '[{"type": "pinbar", "enabled": true, "params": {"min_wick_ratio": 0.6, "max_body_ratio": 0.3, "body_position_tolerance": 0.1}}]',
                '[]',
                '{"type": "AND", "children": [{"type": "trigger", "id": "pinbar"}]}',
                '["BTC/USDT:USDT:15m", "ETH/USDT:USDT:15m", "SOL/USDT:USDT:15m", "BNB/USDT:USDT:15m"]',
                1
            )
        """)
        return

    # 迁移第一个活跃策略
    strategy = active_strategies[0]

    # 转换触发器格式
    triggers = []
    for trigger in strategy.get("triggers", []):
        triggers.append({
            "type": trigger.get("type", "pinbar"),
            "enabled": trigger.get("enabled", True),
            "params": trigger.get("params", {})
        })

    # 转换过滤器格式
    filters = []
    for filter_config in strategy.get("filters", []):
        filters.append({
            "type": filter_config.get("type", "ema_trend"),
            "enabled": filter_config.get("enabled", True),
            "params": filter_config.get("params", {})
        })

    # 构建 apply_to 列表
    apply_to = strategy.get("apply_to", [])
    if not apply_to:
        # 如果没有指定，使用核心币池 + 默认周期
        core_symbols = core_config.get("core_symbols", ["BTC/USDT:USDT", "ETH/USDT:USDT"])
        default_timeframe = "15m"
        apply_to = [f"{sym}:{default_timeframe}" for sym in core_symbols]

    await conn.execute("""
        INSERT INTO strategy_configs (name, description, triggers, filters, logic_tree, apply_to, is_active)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        strategy.get("name", "Migrated Strategy"),
        "从 YAML 迁移的策略配置",
        json.dumps(triggers),
        json.dumps(filters),
        json.dumps(strategy.get("logic_tree", {"type": "AND", "children": []})),
        json.dumps(apply_to),
        1 if strategy.get("is_global", False) else 0
    ))

    print(f"  ✓ 策略配置迁移完成：{strategy.get('name', 'Unknown')}")


async def verify_migration(conn: aiosqlite.Connection) -> dict:
    """验证迁移结果"""
    print("\n正在验证迁移结果...")

    verification = {}

    # 验证策略配置
    async with conn.execute("SELECT COUNT(*) FROM strategy_configs") as cursor:
        count = await cursor.fetchone()
        verification["strategy_configs"] = count[0]
        print(f"  - 策略配置：{count[0]} 条")

    # 验证风控配置
    async with conn.execute("SELECT COUNT(*) FROM risk_configs WHERE id = 1") as cursor:
        count = await cursor.fetchone()
        verification["risk_configs"] = "OK" if count[0] == 1 else "MISSING"
        print(f"  - 风控配置：{'OK' if count[0] == 1 else 'MISSING'}")

    # 验证系统配置
    async with conn.execute("SELECT COUNT(*) FROM system_configs WHERE id = 1") as cursor:
        count = await cursor.fetchone()
        verification["system_configs"] = "OK" if count[0] == 1 else "MISSING"
        print(f"  - 系统配置：{'OK' if count[0] == 1 else 'MISSING'}")

    # 验证币池配置
    async with conn.execute("SELECT COUNT(*) FROM symbol_configs") as cursor:
        count = await cursor.fetchone()
        verification["symbol_configs"] = count[0]
        print(f"  - 币池配置：{count[0]} 条")

    # 验证通知配置
    async with conn.execute("SELECT COUNT(*) FROM notification_configs") as cursor:
        count = await cursor.fetchone()
        verification["notification_configs"] = count[0]
        print(f"  - 通知配置：{count[0]} 条")

    # 验证历史触发器
    async with conn.execute("SELECT COUNT(*) FROM config_history") as cursor:
        count = await cursor.fetchone()
        verification["config_history"] = count[0]
        print(f"  - 历史记录：{count[0]} 条")

    return verification


async def main() -> None:
    """主函数"""
    print("=" * 60)
    print("配置迁移工具 - YAML to SQLite")
    print("=" * 60)

    db_path = Path(DB_PATH)

    # 检查数据库是否存在
    if not db_path.exists():
        print(f"\n错误：数据库不存在：{db_path}")
        print("请先运行：python scripts/init_config_db.py")
        sys.exit(1)

    # 检查 YAML 配置文件
    if not CORE_YAML_PATH.exists() and not USER_YAML_PATH.exists():
        print(f"\n错误：YAML 配置文件不存在")
        print(f"  - {CORE_YAML_PATH}")
        print(f"  - {USER_YAML_PATH}")
        sys.exit(1)

    print(f"\n数据库路径：{db_path.absolute()}")
    print(f"核心配置：{CORE_YAML_PATH}")
    print(f"用户配置：{USER_YAML_PATH}")

    # 加载 YAML 配置
    print("\n正在加载 YAML 配置文件...")
    core_config = load_yaml_file(CORE_YAML_PATH)
    user_config = load_yaml_file(USER_YAML_PATH)
    print(f"  ✓ 核心配置加载完成：{len(core_config)} 个配置项")
    print(f"  ✓ 用户配置加载完成：{len(user_config)} 个配置项")

    async with aiosqlite.connect(db_path) as conn:
        # 启用外键约束
        await conn.execute("PRAGMA foreign_keys = ON")

        # 创建迁移前快照
        print("\n正在创建迁移前快照...")
        snapshot_id = await create_migration_snapshot(
            conn,
            "YAML 配置迁移前的备份"
        )

        # 执行迁移
        print("\n" + "=" * 60)
        print("开始迁移配置...")
        print("=" * 60 + "\n")

        await migrate_system_config(conn, core_config)
        await migrate_risk_config(conn, user_config)
        await migrate_symbol_config(conn, core_config)
        await migrate_notification_config(conn, user_config)
        await migrate_strategy_config(conn, core_config, user_config)

        # 提交更改
        await conn.commit()

        # 验证迁移结果
        print("\n" + "=" * 60)
        verification = await verify_migration(conn)

        # 检查迁移是否成功
        all_ok = (
            verification.get("strategy_configs", 0) >= 1 and
            verification.get("risk_configs") == "OK" and
            verification.get("system_configs") == "OK" and
            verification.get("symbol_configs", 0) >= 1
        )

        if all_ok:
            print("\n" + "=" * 60)
            print("迁移成功！")
            print("=" * 60)
        else:
            print("\n" + "=" * 60)
            print("迁移完成，但部分配置可能缺失")
            print("=" * 60)
            print("\n请检查上述输出确认缺失的配置项")


if __name__ == "__main__":
    asyncio.run(main())
