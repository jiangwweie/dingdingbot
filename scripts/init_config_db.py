#!/usr/bin/env python3
"""
盯盘狗 🐶 配置数据库初始化脚本

用途：
1. 执行 DDL 创建表结构
2. 插入默认配置数据
3. 验证初始化结果

使用方式:
    python scripts/init_config_db.py
"""

import sqlite3
import json
import sys
from pathlib import Path
from datetime import datetime
from uuid import uuid4


# ============================================================
# 常量定义
# ============================================================

DB_PATH = Path(__file__).parent.parent / "data" / "config.db"
SQL_PATH = Path(__file__).parent.parent / "src" / "infrastructure" / "db" / "config_tables.sql"

# 默认系统配置
DEFAULT_SYSTEM_CONFIG = {
    "id": "global",
    "core_symbols": json.dumps([
        "BTC/USDT:USDT",
        "ETH/USDT:USDT",
        "SOL/USDT:USDT",
        "BNB/USDT:USDT"
    ], ensure_ascii=False),
    "ema_period": 60,
    "mtf_ema_period": 60,
    "mtf_mapping": json.dumps({
        "15m": "1h",
        "1h": "4h",
        "4h": "1d",
        "1d": "1w"
    }, ensure_ascii=False),
    "signal_cooldown_seconds": 14400,
    "queue_batch_size": 10,
    "queue_flush_interval": 5.0,
    "queue_max_size": 1000,
    "warmup_history_bars": 100,
    "atr_filter_enabled": True,
    "atr_period": 14,
    "atr_min_ratio": 0.5,
}

# 默认风控配置
DEFAULT_RISK_CONFIG = {
    "id": "global",
    "max_loss_percent": 0.01,      # 1%
    "max_leverage": 10,
    "max_total_exposure": 0.8,     # 80%
    "daily_max_trades": None,      # 不限制
    "daily_max_loss": None,        # 不限制
    "max_position_hold_time": None,  # 不限制
    "cooldown_minutes": 240,       # 4 小时
}

# 默认核心币种
DEFAULT_SYMBOLS = [
    {
        "symbol": "BTC/USDT:USDT",
        "is_active": True,
        "is_core": True,
        "min_quantity": 0.00001000,
        "price_precision": 2,
        "quantity_precision": 5,
    },
    {
        "symbol": "ETH/USDT:USDT",
        "is_active": True,
        "is_core": True,
        "min_quantity": 0.00010000,
        "price_precision": 2,
        "quantity_precision": 4,
    },
    {
        "symbol": "SOL/USDT:USDT",
        "is_active": True,
        "is_core": True,
        "min_quantity": 0.01000000,
        "price_precision": 3,
        "quantity_precision": 2,
    },
    {
        "symbol": "BNB/USDT:USDT",
        "is_active": True,
        "is_core": True,
        "min_quantity": 0.00100000,
        "price_precision": 2,
        "quantity_precision": 3,
    },
]

# 默认通知配置 (飞书)
DEFAULT_NOTIFICATION = {
    "id": str(uuid4()),
    "channel_type": "feishu",
    "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/PLACEHOLDER",
    "is_active": False,  # 默认禁用，需用户配置
    "notify_on_signal": True,
    "notify_on_order": True,
    "notify_on_error": True,
}


# ============================================================
# 工具函数
# ============================================================

def print_section(title: str):
    """打印分隔线"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_row(count: int, table: str):
    """打印插入结果"""
    print(f"  ✓ {table}: {count} 条记录")


# ============================================================
# 数据库操作
# ============================================================

def init_database(conn: sqlite3.Connection):
    """执行 DDL 创建表结构"""
    print_section("步骤 1: 执行 DDL 创建表结构")

    with open(SQL_PATH, "r", encoding="utf-8") as f:
        ddl_sql = f.read()

    cursor = conn.cursor()
    cursor.executescript(ddl_sql)
    conn.commit()

    print("  ✓ 7 张表创建完成:")
    print("    - strategies (策略配置)")
    print("    - risk_configs (风控配置)")
    print("    - system_configs (系统配置)")
    print("    - symbols (币池配置)")
    print("    - notifications (通知配置)")
    print("    - config_snapshots (配置快照)")
    print("    - config_history (配置历史)")


def insert_system_config(conn: sqlite3.Connection) -> int:
    """插入默认系统配置"""
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO system_configs (
            id, core_symbols, ema_period, mtf_ema_period, mtf_mapping,
            signal_cooldown_seconds, queue_batch_size, queue_flush_interval,
            queue_max_size, warmup_history_bars, atr_filter_enabled,
            atr_period, atr_min_ratio, created_at, updated_at
        ) VALUES (
            :id, :core_symbols, :ema_period, :mtf_ema_period, :mtf_mapping,
            :signal_cooldown_seconds, :queue_batch_size, :queue_flush_interval,
            :queue_max_size, :warmup_history_bars, :atr_filter_enabled,
            :atr_period, :atr_min_ratio, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )
    """, DEFAULT_SYSTEM_CONFIG)
    conn.commit()
    return cursor.rowcount


def insert_risk_config(conn: sqlite3.Connection) -> int:
    """插入默认风控配置"""
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO risk_configs (
            id, max_loss_percent, max_leverage, max_total_exposure,
            daily_max_trades, daily_max_loss, max_position_hold_time,
            cooldown_minutes, created_at, updated_at
        ) VALUES (
            :id, :max_loss_percent, :max_leverage, :max_total_exposure,
            :daily_max_trades, :daily_max_loss, :max_position_hold_time,
            :cooldown_minutes, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )
    """, DEFAULT_RISK_CONFIG)
    conn.commit()
    return cursor.rowcount


def insert_symbols(conn: sqlite3.Connection) -> int:
    """插入默认核心币种"""
    cursor = conn.cursor()
    cursor.executemany("""
        INSERT OR REPLACE INTO symbols (
            symbol, is_active, is_core, min_quantity,
            price_precision, quantity_precision, created_at, updated_at
        ) VALUES (
            :symbol, :is_active, :is_core, :min_quantity,
            :price_precision, :quantity_precision, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )
    """, DEFAULT_SYMBOLS)
    conn.commit()
    return cursor.rowcount


def insert_notification(conn: sqlite3.Connection) -> int:
    """插入默认通知配置"""
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO notifications (
            id, channel_type, webhook_url, is_active,
            notify_on_signal, notify_on_order, notify_on_error,
            created_at, updated_at
        ) VALUES (
            :id, :channel_type, :webhook_url, :is_active,
            :notify_on_signal, :notify_on_order, :notify_on_error,
            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )
    """, DEFAULT_NOTIFICATION)
    conn.commit()
    return cursor.rowcount


def verify_initialization(conn: sqlite3.Connection):
    """验证初始化结果"""
    print_section("步骤 3: 验证初始化结果")

    cursor = conn.cursor()

    # 统计表记录数
    tables = [
        "strategies",
        "risk_configs",
        "system_configs",
        "symbols",
        "notifications",
        "config_snapshots",
        "config_history",
    ]

    for table in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        print_row(count, table)

    # 验证核心配置
    print_section("核心配置验证")

    # 系统配置
    cursor.execute("SELECT core_symbols FROM system_configs WHERE id = 'global'")
    core_symbols = json.loads(cursor.fetchone()[0])
    print(f"  ✓ 核心币种：{core_symbols}")

    # 风控配置
    cursor.execute("""
        SELECT max_loss_percent, max_leverage, max_total_exposure, cooldown_minutes
        FROM risk_configs WHERE id = 'global'
    """)
    row = cursor.fetchone()
    print(f"  ✓ 风控参数：")
    print(f"    - 最大损失：{row[0] * 100}%")
    print(f"    - 最大杠杆：{row[1]}x")
    print(f"    - 最大敞口：{row[2] * 100}%")
    print(f"    - 冷却时间：{row[3]} 分钟")

    # 币池配置
    cursor.execute("SELECT symbol, is_core FROM symbols ORDER BY is_core DESC, symbol")
    symbols = cursor.fetchall()
    core_count = sum(1 for s in symbols if s[1])
    print(f"  ✓ 币池配置：{len(symbols)} 个币种 (核心：{core_count})")


# ============================================================
# 主函数
# ============================================================

def main():
    """主函数"""
    print_section("🐶 盯盘狗配置数据库初始化")
    print(f"  数据库路径：{DB_PATH.absolute()}")
    print(f"  DDL 路径：{SQL_PATH.absolute()}")
    print(f"  执行时间：{datetime.now().isoformat()}")

    # 确保数据目录存在
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    # 检查 DDL 文件是否存在
    if not SQL_PATH.exists():
        print(f"\n  ❌ DDL 文件不存在：{SQL_PATH}")
        sys.exit(1)

    try:
        # 连接数据库
        conn = sqlite3.connect(DB_PATH)
        print(f"\n  ✓ 数据库连接成功")

        # 执行 DDL
        init_database(conn)

        # 插入默认数据
        print_section("步骤 2: 插入默认数据")

        print_row(insert_system_config(conn), "system_configs")
        print_row(insert_risk_config(conn), "risk_configs")
        print_row(insert_symbols(conn), "symbols")
        print_row(insert_notification(conn), "notifications")

        # 验证初始化
        verify_initialization(conn)

        # 完成
        print_section("初始化完成 ✅")
        print(f"  数据库文件：{DB_PATH.absolute()}")
        print("\n  下一步:")
        print("  1. 配置飞书 Webhook URL:")
        print(f"     UPDATE notifications SET webhook_url='YOUR_WEBHOOK_URL' WHERE channel_type='feishu';")
        print("  2. 创建策略配置:")
        print("     INSERT INTO strategies (id, name, trigger_config, filter_configs, symbols, timeframes) VALUES (...);")

        conn.close()
        return 0

    except sqlite3.Error as e:
        print(f"\n  ❌ 数据库错误：{e}")
        return 1
    except Exception as e:
        print(f"\n  ❌ 未知错误：{e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
