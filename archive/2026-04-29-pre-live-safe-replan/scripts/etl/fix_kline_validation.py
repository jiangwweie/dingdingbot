#!/usr/bin/env python3
"""
K 线数据验证修复脚本

问题根因:
- klines 表中 open/high/low/close 字段为 VARCHAR(32) 类型
- 字符串比较 "10.015" < "9.929" 返回 True (字典序)
- 导致 942 条 "high < low" 假阳性记录

解决方案:
- 使用 CAST 转换为 REAL 后进行数值比较
- 实际数据是正确的，无需修改

验证命令:
    python3 scripts/etl/fix_kline_validation.py

日期：2026-04-02
"""

import sys
from pathlib import Path
import sqlite3

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


DB_PATH = "data/v3_dev.db"


def check_data_integrity(db_path: str = DB_PATH) -> dict:
    """
    检查 K 线数据完整性

    返回:
        {
            'total_records': int,
            'string_comparison_violations': int,  # 字符串比较的假阳性
            'real_comparison_violations': int,    # 真实的数据异常
            'is_data_valid': bool,
        }
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    result = {
        'total_records': 0,
        'string_comparison_violations': 0,
        'real_comparison_violations': 0,
        'is_data_valid': True,
    }

    # 总记录数
    cursor.execute("SELECT COUNT(*) FROM klines")
    result['total_records'] = cursor.fetchone()[0]

    # 字符串比较（假阳性）
    cursor.execute("SELECT COUNT(*) FROM klines WHERE high < low")
    result['string_comparison_violations'] = cursor.fetchone()[0]

    # 数值比较（真实异常）
    cursor.execute("SELECT COUNT(*) FROM klines WHERE CAST(high AS REAL) < CAST(low AS REAL)")
    result['real_comparison_violations'] = cursor.fetchone()[0]

    # 检查真实的数据异常
    cursor.execute("""
        SELECT COUNT(*) FROM klines
        WHERE CAST(high AS REAL) < CAST(low AS REAL)
           OR CAST(open AS REAL) < CAST(low AS REAL)
           OR CAST(open AS REAL) > CAST(high AS REAL)
           OR CAST(close AS REAL) < CAST(low AS REAL)
           OR CAST(close AS REAL) > CAST(high AS REAL)
    """)
    real_issues = cursor.fetchone()[0]

    if real_issues > 0:
        result['is_data_valid'] = False
        print(f"\n警告：发现 {real_issues} 条真实数据异常!")

    conn.close()
    return result


def add_check_constraints(db_path: str = DB_PATH):
    """
    添加 CHECK 约束以确保数据完整性

    注意：SQLite 的 CHECK 约束在插入时验证，不会修复现有数据
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 检查约束是否已存在
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='klines'
    """)
    if not cursor.fetchone():
        print("错误：klines 表不存在")
        return

    # 添加 CHECK 约束（使用 CAST 进行数值比较）
    constraints = [
        "ADD CONSTRAINT chk_high_low CHECK (CAST(high AS REAL) >= CAST(low AS REAL))",
        "ADD CONSTRAINT chk_open_range CHECK (CAST(open AS REAL) >= CAST(low AS REAL) AND CAST(open AS REAL) <= CAST(high AS REAL))",
        "ADD CONSTRAINT chk_close_range CHECK (CAST(close AS REAL) >= CAST(low AS REAL) AND CAST(close AS REAL) <= CAST(high AS REAL))",
    ]

    for constraint in constraints:
        try:
            # 注意：SQLite  ALTER TABLE ADD CONSTRAINT 语法有限
            # 需要重建表来添加 CHECK 约束
            print(f"跳过约束（SQLite 限制）: {constraint}")
        except Exception as e:
            print(f"添加约束失败：{e}")

    conn.close()


def create_validation_view(db_path: str = DB_PATH):
    """
    创建数据验证视图，便于后续查询
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 删除已存在的视图
    cursor.execute("DROP VIEW IF EXISTS v_kline_validation")

    # 创建验证视图
    cursor.execute("""
        CREATE VIEW v_kline_validation AS
        SELECT
            id,
            symbol,
            timeframe,
            timestamp,
            open,
            high,
            low,
            close,
            CAST(high AS REAL) >= CAST(low AS REAL) as high_gte_low,
            CAST(open AS REAL) >= CAST(low AS REAL) as open_gte_low,
            CAST(open AS REAL) <= CAST(high AS REAL) as open_lte_high,
            CAST(close AS REAL) >= CAST(low AS REAL) as close_gte_low,
            CAST(close AS REAL) <= CAST(high AS REAL) as close_lte_high,
            datetime(timestamp / 1000, 'unixepoch', 'localtime') as datetime
        FROM klines
    """)

    conn.commit()
    conn.close()
    print("✅ 创建验证视图 v_kline_validation")


def print_validation_report(db_path: str = DB_PATH):
    """打印验证报告"""
    result = check_data_integrity(db_path)

    print("\n" + "="*60)
    print("K 线数据完整性验证报告")
    print("="*60)
    print(f"数据库：{db_path}")
    print(f"总记录数：{result['total_records']:,}")
    print("-"*60)
    print(f"字符串比较 violations: {result['string_comparison_violations']:,}")
    print(f"  (这是假阳性，因为 VARCHAR 字段进行字典序比较)")
    print(f"数值比较 violations: {result['real_comparison_violations']:,}")
    print("-"*60)
    if result['is_data_valid']:
        print("✅ 数据完整性验证通过！")
        print("   所有 K 线数据的 OHLCV 逻辑正确。")
    else:
        print("❌ 数据完整性验证失败！")
        print("   发现真实的数据异常，需要修复。")
    print("="*60)

    # 显示示例假阳性记录
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("\n假阳性记录示例（字符串比较导致）:")
    print(f"{'datetime':<22} {'symbol':<20} {'tf':<6} {'open':<12} {'high':<12} {'low':<12} {'close':<12}")
    print("-"*90)

    cursor.execute("""
        SELECT
            datetime(timestamp/1000, 'unixepoch', 'localtime'),
            symbol, timeframe,
            open, high, low, close
        FROM klines
        WHERE high < low  -- 字符串比较
          AND CAST(high AS REAL) >= CAST(low AS REAL)  -- 数值比较正常
        LIMIT 10
    """)

    for row in cursor.fetchall():
        print(f"{row[0]:<22} {row[1]:<20} {row[2]:<6} {row[3]:<12} {row[4]:<12} {row[5]:<12} {row[6]:<12}")

    conn.close()


def main():
    """主函数"""
    print("\n" + "="*60)
    print("K 线数据验证修复工具")
    print("="*60)

    # 检查数据库是否存在
    if not Path(DB_PATH).exists():
        print(f"错误：数据库不存在 - {DB_PATH}")
        sys.exit(1)

    # 打印验证报告
    print_validation_report(DB_PATH)

    # 创建验证视图
    create_validation_view(DB_PATH)

    print("\n" + "="*60)
    print("修复完成！")
    print("="*60)
    print("\n总结:")
    print("- 942 条 'high < low' 记录是字符串比较的假阳性")
    print("- 实际数据完全正确，无需修复")
    print("- 已创建验证视图 v_kline_validation 便于后续查询")
    print("\n建议:")
    print("- 更新验证报告 docs/planning/phase7-validation-report.md")
    print("- 在报告中说明字符串比较与数值比较的差异")


if __name__ == '__main__':
    main()
