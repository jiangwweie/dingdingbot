#!/usr/bin/env python3
"""
批量导入币安 K 线数据到 SQLite 数据库

功能:
1. 遍历 ~/Documents/data/ 目录下所有 ZIP 文件
2. 解压并读取 CSV 数据
3. 转换为 CCXT 格式交易对
4. 批量插入到 klines 表 (幂等性：INSERT OR IGNORE)
5. 验证导入数据完整性

使用示例:
    python3 scripts/etl/import_all_klines.py
"""

import sys
import os
import zipfile
import asyncio
from pathlib import Path
from decimal import Decimal
from datetime import datetime
from typing import List, Dict, Tuple
import tempfile
import shutil

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
from sqlalchemy import create_engine, text, insert
from sqlalchemy.orm import sessionmaker

from src.infrastructure.v3_orm import KlineORM, Base


# ============================================================
# 配置
# ============================================================

# 数据源目录
SOURCE_DIR = Path.home() / "Documents" / "data"

# 数据库路径
DATABASE_URL = "sqlite+aiosqlite:///./data/v3_dev.db"
SYNC_DATABASE_URL = "sqlite:///./data/v3_dev.db"

# 批量插入大小
BATCH_SIZE = 5000

# 币安符号到 CCXT 符号映射
SYMBOL_MAP = {
    "BTCUSDT": "BTC/USDT:USDT",
    "ETHUSDT": "ETH/USDT:USDT",
    "SOLUSDT": "SOL/USDT:USDT",
}


# ============================================================
# 数据解析
# ============================================================

def parse_zip_filename(filename: str) -> Dict:
    """
    解析 ZIP 文件名

    格式：SYMBOL-TIMEFRAME-YEAR-MONTH.zip
    示例：BTCUSDT-15m-2024-01.zip

    返回:
        {
            'symbol': 'BTCUSDT',
            'timeframe': '15m',
            'year': 2024,
            'month': 1,
        }
    """
    base = filename.replace('.zip', '')
    parts = base.split('-')

    if len(parts) < 4:
        return None

    # 处理可能包含连字符的交易对名称 (如 BTC-USDT)
    timeframe_idx = 1
    for i, part in enumerate(parts[1:], 1):
        if part.endswith('m') or part.endswith('h') or part.endswith('d') or part.endswith('w'):
            timeframe_idx = i
            break

    symbol = '-'.join(parts[:timeframe_idx])
    timeframe = parts[timeframe_idx]
    year = int(parts[timeframe_idx + 1])
    month = int(parts[timeframe_idx + 2]) if len(parts) > timeframe_idx + 2 else None

    return {
        'symbol': symbol,
        'timeframe': timeframe,
        'year': year,
        'month': month,
    }


def binance_symbol_to_ccxt(binance_symbol: str) -> str:
    """将币安符号转换为 CCXT 格式"""
    if binance_symbol in SYMBOL_MAP:
        return SYMBOL_MAP[binance_symbol]

    # 默认处理
    if binance_symbol.endswith('USDT'):
        base = binance_symbol[:-4]
        return f"{base}/USDT:USDT"
    return f"{binance_symbol}/USDT:USDT"


# ============================================================
# 导入服务
# ============================================================

class KlineImporter:
    """K 线数据导入服务"""

    def __init__(self, db_url: str = SYNC_DATABASE_URL):
        self.db_url = db_url
        self.engine = create_engine(db_url)
        self.Session = sessionmaker(bind=self.engine)

    def initialize_tables(self):
        """初始化数据库表"""
        Base.metadata.create_all(self.engine)
        print("✅ 数据库表已创建/验证")

        # 创建索引
        with self.engine.begin() as conn:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_klines_symbol_tf_ts "
                "ON klines(symbol, timeframe, timestamp)"
            ))
            conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_klines_symbol_timeframe_timestamp "
                "ON klines(symbol, timeframe, timestamp)"
            ))
        print("✅ 索引已创建")

    def import_zip(
        self,
        zip_path: Path,
        batch_size: int = BATCH_SIZE,
    ) -> Dict:
        """
        导入单个 ZIP 文件

        返回:
            {
                'success': bool,
                'rows_imported': int,
                'errors': List[str],
                'file': str,
            }
        """
        result = {
            'success': False,
            'rows_imported': 0,
            'errors': [],
            'file': str(zip_path),
        }

        if not zip_path.exists():
            result['errors'].append(f"文件不存在：{zip_path}")
            return result

        # 解析文件名
        info = parse_zip_filename(zip_path.name)
        if info is None:
            result['errors'].append(f"无法解析文件名：{zip_path.name}")
            return result

        # 转换为 CCXT 格式
        ccxt_symbol = binance_symbol_to_ccxt(info['symbol'])
        timeframe = info['timeframe']

        temp_csv = None

        try:
            # 解压 ZIP
            with zipfile.ZipFile(zip_path, 'r') as zf:
                csv_files = [f for f in zf.namelist() if f.endswith('.csv')]
                if not csv_files:
                    result['errors'].append('ZIP 中没有 CSV 文件')
                    return result

                # 提取 CSV 到临时文件
                temp_dir = tempfile.mkdtemp()
                temp_csv = Path(temp_dir) / csv_files[0]
                with open(temp_csv, 'wb') as f:
                    f.write(zf.read(csv_files[0]))

            # 读取 CSV (有表头)
            df = pd.read_csv(temp_csv)

            # 确保列名正确
            column_mapping = {
                'quote_asset_volume': 'quote_volume',
                'number_of_trades': 'count',
                'taker_buy_base_volume': 'taker_buy_volume',
                'taker_buy_quote_volume': 'taker_buy_quote_volume',
            }
            df = df.rename(columns=column_mapping)

            # 转换为 KlineORM 记录
            records = []
            for _, row in df.iterrows():
                records.append({
                    'symbol': ccxt_symbol,
                    'timeframe': timeframe,
                    'timestamp': int(row['open_time']),
                    'open': Decimal(str(row['open'])),
                    'high': Decimal(str(row['high'])),
                    'low': Decimal(str(row['low'])),
                    'close': Decimal(str(row['close'])),
                    'volume': Decimal(str(row['volume'])),
                    'is_closed': True,
                })

            # 批量插入
            with self.Session() as session:
                total_imported = 0

                for i in range(0, len(records), batch_size):
                    batch = records[i:i + batch_size]

                    # 使用 INSERT OR IGNORE 实现幂等性
                    session.execute(
                        insert(KlineORM).prefix_with('OR IGNORE').values(batch)
                    )
                    total_imported += len(batch)

                session.commit()

            result['success'] = True
            result['rows_imported'] = len(records)

        except Exception as e:
            result['errors'].append(str(e))

        finally:
            # 清理临时文件
            if temp_csv and temp_csv.parent.exists():
                shutil.rmtree(temp_csv.parent)

        return result

    def discover_all_zips(self, source_dir: Path) -> List[Path]:
        """发现所有 ZIP 文件"""
        zips = []

        for symbol_dir in source_dir.iterdir():
            if not symbol_dir.is_dir():
                continue

            for tf_dir in symbol_dir.iterdir():
                if not tf_dir.is_dir():
                    continue

                for zip_file in tf_dir.glob("*.zip"):
                    zips.append(zip_file)

        return sorted(zips)

    def batch_import(
        self,
        source_dir: Path,
        batch_size: int = BATCH_SIZE,
    ) -> Dict:
        """批量导入所有 ZIP 文件"""
        print(f"\n{'='*60}")
        print(f"批量导入 K 线数据")
        print(f"{'='*60}")
        print(f"数据源：{source_dir}")
        print(f"数据库：{self.db_url}")

        # 初始化表
        self.initialize_tables()

        # 发现所有 ZIP 文件
        all_zips = self.discover_all_zips(source_dir)
        print(f"发现 {len(all_zips)} 个 ZIP 文件")

        results = {
            'total_files': len(all_zips),
            'success_count': 0,
            'failed_count': 0,
            'total_rows': 0,
            'details': [],
        }

        # 导入每个文件
        for i, zip_path in enumerate(all_zips, 1):
            result = self.import_zip(zip_path, batch_size=batch_size)
            results['details'].append(result)

            status = "✅" if result['success'] else "❌"
            if result['success']:
                results['success_count'] += 1
                results['total_rows'] += result['rows_imported']
                print(f"[{i}/{len(all_zips)}] {status} {zip_path.name}: {result['rows_imported']:,} 行")
            else:
                results['failed_count'] += 1
                print(f"[{i}/{len(all_zips)}] {status} {zip_path.name}: {result['errors']}")

        return results


# ============================================================
# 验证服务
# ============================================================

class ImportValidator:
    """导入数据验证器"""

    def __init__(self, db_url: str = SYNC_DATABASE_URL):
        self.db_url = db_url
        self.engine = create_engine(db_url)

    def validate(self) -> Dict:
        """验证导入数据"""
        print(f"\n{'='*60}")
        print(f"验证导入数据")
        print(f"{'='*60}")

        with self.engine.connect() as conn:
            # 总记录数
            result = conn.execute(text("SELECT COUNT(*) FROM klines"))
            total = result.scalar()
            print(f"总记录数：{total:,}")

            # 按交易对和周期分组统计
            result = conn.execute(text("""
                SELECT symbol, timeframe, COUNT(*) as count,
                       MIN(timestamp) as min_ts, MAX(timestamp) as max_ts
                FROM klines
                GROUP BY symbol, timeframe
                ORDER BY symbol, timeframe
            """))

            print(f"\n按交易对/周期分组:")
            print(f"{'='*80}")
            print(f"{'交易对':<20} {'周期':<10} {'记录数':<15} {'时间范围'}")
            print(f"{'='*80}")

            stats = []
            for row in result:
                symbol, timeframe, count, min_ts, max_ts = row
                min_date = datetime.fromtimestamp(min_ts / 1000).strftime('%Y-%m-%d') if min_ts else 'N/A'
                max_date = datetime.fromtimestamp(max_ts / 1000).strftime('%Y-%m-%d') if max_ts else 'N/A'

                print(f"{symbol:<20} {timeframe:<10} {count:>10,}     {min_date} ~ {max_date}")
                stats.append({
                    'symbol': symbol,
                    'timeframe': timeframe,
                    'count': count,
                    'min_ts': min_ts,
                    'max_ts': max_ts,
                })

            return {
                'total_records': total,
                'stats': stats,
            }


# ============================================================
# CLI 入口
# ============================================================

def main():
    """主函数"""
    print("\n" + "="*60)
    print("币安 K 线数据批量导入工具")
    print("="*60)

    # 检查数据源
    if not SOURCE_DIR.exists():
        print(f"错误：数据源目录不存在：{SOURCE_DIR}")
        sys.exit(1)

    print(f"数据源目录：{SOURCE_DIR}")

    # 创建导入器
    importer = KlineImporter()

    # 执行批量导入
    results = importer.batch_import(SOURCE_DIR)

    # 打印汇总
    print(f"\n{'='*60}")
    print(f"导入汇总")
    print(f"{'='*60}")
    print(f"总文件数：{results['total_files']}")
    print(f"成功：{results['success_count']} ✅")
    print(f"失败：{results['failed_count']} ❌")
    print(f"总导入行数：{results['total_rows']:,}")

    if results['failed_count'] > 0:
        print(f"\n失败文件列表:")
        failed = [d for d in results['details'] if not d['success']]
        for f in failed[:10]:
            print(f"  - {Path(f['file']).name}: {f['errors']}")
        if len(failed) > 10:
            print(f"  ... 还有 {len(failed) - 10} 个")

    # 验证导入
    validator = ImportValidator()
    stats = validator.validate()

    print(f"\n{'='*60}")
    print(f"导入完成!")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
