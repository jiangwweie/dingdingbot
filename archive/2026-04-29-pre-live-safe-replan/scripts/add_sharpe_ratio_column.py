#!/usr/bin/env python3
"""
添加 sharpe_ratio 列到 backtest_reports 表

使用方法:
    python scripts/add_sharpe_ratio_column.py

注意事项:
- 如果列已存在则跳过
- 幂等操作，可重复运行
"""
import asyncio
import sqlite3
from pathlib import Path
import sys

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

DB_PATH = Path("data/v3_dev.db")


async def add_sharpe_ratio_column():
    """
    添加 sharpe_ratio 列到 backtest_reports 表

    Returns:
        bool: 是否成功
    """
    if not DB_PATH.exists():
        print(f"❌ 数据库文件不存在：{DB_PATH}")
        return False

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    print("============================================================")
    print("添加 sharpe_ratio 列 - 数据库迁移")
    print("============================================================")
    print()

    # 检查列是否已存在
    cursor.execute("PRAGMA table_info(backtest_reports)")
    columns = [row[1] for row in cursor.fetchall()]

    if "sharpe_ratio" in columns:
        print("ℹ️  sharpe_ratio 列已存在，跳过迁移")
        print()
        print("============================================================")
        print("✅ 迁移已应用（幂等操作）")
        print("============================================================")
        conn.close()
        return True

    print("📦 步骤 1/2: 添加 sharpe_ratio 列...")

    # 添加列
    cursor.execute("ALTER TABLE backtest_reports ADD COLUMN sharpe_ratio REAL")
    conn.commit()

    print("✅ sharpe_ratio 列已添加")
    print()

    # 验证
    cursor.execute("PRAGMA table_info(backtest_reports)")
    columns = [row[1] for row in cursor.fetchall()]

    print("📦 步骤 2/2: 验证迁移...")
    print("------------------------------------------------------------")

    if "sharpe_ratio" in columns:
        print("✅ sharpe_ratio 列存在性验证通过")
    else:
        print("❌ sharpe_ratio 列验证失败")
        conn.close()
        return False

    conn.close()

    print()
    print("------------------------------------------------------------")
    print("✅ 迁移成功完成!")
    print()
    print("下一步:")
    print("1. 重启后端服务验证功能")
    print("2. 访问 /api/v3/backtest/reports 验证返回正常")
    print("============================================================")

    return True


async def main():
    """主函数"""
    try:
        success = await add_sharpe_ratio_column()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"❌ 迁移失败：{e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
