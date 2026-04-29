#!/usr/bin/env python3
"""
Binance Vision CSV 到 SQLite ETL 工具

将币安 CSV 数据转换并导入到 v3.0 SQLite 数据库。

功能:
1. 批量解压 ZIP 压缩包
2. 验证 CSV 数据质量
3. 转换为 v3.0 KlineORM 格式
4. 批量导入 SQLite (幂等性处理)
5. 进度追踪和错误报告

使用示例:
    # 验证 CSV
    python3 etl_converter.py validate /Users/jiangwei/Downloads/data/temp/*.csv

    # 转换单个文件
    python3 etl_converter.py convert BTCUSDT-15m-2024-01.csv --symbol BTC/USDT:USDT

    # 批量转换目录
    python3 etl_converter.py batch /Users/jiangwei/Downloads/data/ --symbol BTC/USDT:USDT

    # 解压并转换 ZIP
    python3 etl_converter.py unzip-convert /Users/jiangwei/Downloads/data/BTCUSDT-15m-*.zip
"""

import sys
import os
import zipfile
import tempfile
import shutil
from pathlib import Path
from decimal import Decimal
from datetime import datetime
from typing import Optional, List
import asyncio

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import sessionmaker
from sqlalchemy import insert, delete

from src.infrastructure.v3_orm import KlineORM, Base


# ============================================================
# 配置
# ============================================================

DEFAULT_DB_PATH = "sqlite+aiosqlite:///data/backtests/market_data.db"
BATCH_SIZE = 10000  # 批量插入大小


# ============================================================
# 数据解析
# ============================================================

def parse_filename(filename: str) -> Optional[dict]:
    """
    解析币安文件名

    格式：SYMBOL-TIMEFRAME-YEAR-MONTH.csv
    示例：BTCUSDT-15m-2024-01.csv

    返回:
        {
            'symbol': 'BTCUSDT',
            'timeframe': '15m',
            'year': 2024,
            'month': 1,
        }
    """
    base = filename.replace('.csv', '')
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
    """
    将币安符号转换为 CCXT 格式

    币安：BTCUSDT
    CCXT: BTC/USDT:USDT (U 本位合约)

    注意：这里假设是 U 本位合约数据
    """
    # 移除可能的后缀
    if binance_symbol.endswith('USDT'):
        base = binance_symbol[:-4]
        return f"{base}/USDT:USDT"
    elif binance_symbol.endswith('USDC'):
        base = binance_symbol[:-4]
        return f"{base}/USDC:USDC"
    else:
        # 默认处理
        return f"{binance_symbol}/USDT:USDT"


# ============================================================
# ETL 核心逻辑
# ============================================================

class ETLService:
    """
    ETL 服务：CSV 到 SQLite 转换
    """

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._engine = None
        self._sync_engine = None
        self._async_session_maker = None

    def _get_engine(self):
        """获取异步数据库引擎"""
        if self._engine is None:
            self._engine = create_async_engine(
                self.db_path,
                echo=False,
                future=True,
            )
        return self._engine

    def _get_sync_engine(self):
        """获取同步数据库引擎（用于初始化表）"""
        if self._sync_engine is None:
            self._sync_engine = create_engine(
                self.db_path.replace('sqlite+aiosqlite', 'sqlite'),
                echo=False,
                future=True,
            )
        return self._sync_engine

    async def initialize_db(self):
        """初始化数据库表"""
        engine = self._get_sync_engine()
        Base.metadata.create_all(engine)
        print(f"✅ 数据库表已创建：{self.db_path}")

    async def create_indexes(self):
        """创建额外索引（如果需要）"""
        async with self._get_engine().begin() as conn:
            # 检查索引是否已存在
            result = await conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_klines_symbol_tf_ts'"
            ))
            if not result.fetchone():
                # 创建复合索引
                await conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS idx_klines_symbol_tf_ts "
                    "ON klines(symbol, timeframe, timestamp)"
                ))
                await conn.execute(text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_klines_symbol_timeframe_timestamp "
                    "ON klines(symbol, timeframe, timestamp)"
                ))
                print("✅ 索引已创建")

    async def convert_csv(
        self,
        csv_path: str,
        symbol: Optional[str] = None,
        timeframe: Optional[str] = None,
        batch_size: int = BATCH_SIZE,
    ) -> dict:
        """
        转换单个 CSV 文件到 SQLite

        Args:
            csv_path: CSV 文件路径
            symbol: 可选，覆盖文件名的交易对（CCXT 格式）
            timeframe: 可选，覆盖文件名的时间周期
            batch_size: 批量插入大小

        Returns:
            {
                'success': bool,
                'rows_imported': int,
                'errors': List[str],
            }
        """
        result = {
            'success': False,
            'rows_imported': 0,
            'errors': [],
            'file': csv_path,
        }

        csv_path = Path(csv_path)
        if not csv_path.exists():
            result['errors'].append(f"文件不存在：{csv_path}")
            return result

        # 解析文件名获取 symbol 和 timeframe
        info = parse_filename(csv_path.name)
        if info is None:
            result['errors'].append(f"无法解析文件名：{csv_path.name}")
            return result

        # 使用 CCXT 格式的交易对符号
        ccxt_symbol = symbol if symbol else binance_symbol_to_ccxt(info['symbol'])
        tf = timeframe if timeframe else info['timeframe']

        print(f"\n{'='*60}")
        print(f"转换：{csv_path.name}")
        print(f"  Symbol: {ccxt_symbol}")
        print(f"  Timeframe: {tf}")

        try:
            # 加载 CSV
            has_header = 'open_time' in open(csv_path).readline()
            if has_header:
                df = pd.read_csv(csv_path)
                # 标准化列名
                column_mapping = {
                    'quote_asset_volume': 'quote_volume',
                    'number_of_trades': 'count',
                    'taker_buy_base_volume': 'taker_buy_volume',
                    'taker_buy_quote_volume': 'taker_buy_quote_volume',
                }
                df = df.rename(columns=column_mapping)
            else:
                df = pd.read_csv(csv_path, names=[
                    'open_time', 'open', 'high', 'low', 'close', 'volume',
                    'close_time', 'quote_volume', 'count',
                    'taker_buy_volume', 'taker_buy_quote_volume', 'ignore'
                ])

            print(f"  原始行数：{len(df):,}")

            # 转换为 KlineORM 格式
            records = []
            for _, row in df.iterrows():
                records.append({
                    'symbol': ccxt_symbol,
                    'timeframe': tf,
                    'timestamp': int(row['open_time']),
                    'open': Decimal(str(row['open'])),
                    'high': Decimal(str(row['high'])),
                    'low': Decimal(str(row['low'])),
                    'close': Decimal(str(row['close'])),
                    'volume': Decimal(str(row['volume'])),
                    'is_closed': True,
                })

            # 批量插入
            async_session_maker = async_sessionmaker(
                self._get_engine(),
                class_=AsyncSession,
                expire_on_commit=False,
            )

            total_imported = 0

            async with async_session_maker() as session:
                # 使用 INSERT OR IGNORE 实现幂等性
                for i in range(0, len(records), batch_size):
                    batch = records[i:i + batch_size]

                    # 构建 INSERT OR IGNORE 语句
                    await session.execute(
                        insert(KlineORM).prefix_with('OR IGNORE').values(batch)
                    )

                    total_imported += len(batch)

                    if (i // batch_size + 1) % 10 == 0:
                        print(f"    已导入 {total_imported:,} / {len(records):,} 行")

                await session.commit()

            result['success'] = True
            result['rows_imported'] = len(records)

            print(f"  ✅ 导入成功：{len(records):,} 行")

        except Exception as e:
            result['errors'].append(str(e))
            print(f"  ❌ 转换失败：{e}")

        return result

    async def convert_zip(
        self,
        zip_path: str,
        symbol: Optional[str] = None,
        timeframe: Optional[str] = None,
        temp_dir: Optional[str] = None,
    ) -> dict:
        """
        解压 ZIP 并转换 CSV

        Args:
            zip_path: ZIP 文件路径
            symbol: 可选，覆盖交易对
            timeframe: 可选，覆盖时间周期
            temp_dir: 可选，临时目录

        Returns:
            转换结果
        """
        zip_path = Path(zip_path)
        if not zip_path.exists():
            return {
                'success': False,
                'errors': [f"文件不存在：{zip_path}"],
            }

        print(f"\n{'='*60}")
        print(f"处理 ZIP: {zip_path.name}")

        # 创建临时目录
        if temp_dir is None:
            temp_dir = tempfile.mkdtemp(prefix='etl_')

        temp_path = Path(temp_dir)
        csv_path = None

        try:
            # 解压 ZIP
            with zipfile.ZipFile(zip_path, 'r') as zf:
                csv_files = [f for f in zf.namelist() if f.endswith('.csv')]
                if not csv_files:
                    return {
                        'success': False,
                        'errors': ['ZIP 中没有 CSV 文件'],
                    }

                csv_name = csv_files[0]
                zf.extract(csv_name, temp_path)
                csv_path = temp_path / csv_name

            # 转换 CSV
            result = await self.convert_csv(
                str(csv_path),
                symbol=symbol,
                timeframe=timeframe,
            )

            return result

        finally:
            # 清理临时文件
            if temp_dir is None and temp_path.exists():
                shutil.rmtree(temp_path)

    async def batch_convert_directory(
        self,
        dir_path: str,
        symbol: Optional[str] = None,
        timeframe: Optional[str] = None,
        pattern: str = "*.zip",
    ) -> dict:
        """
        批量转换目录下所有 ZIP 文件

        Args:
            dir_path: 目录路径
            symbol: 可选，覆盖交易对
            timeframe: 可选，覆盖时间周期
            pattern: 文件匹配模式

        Returns:
            {
                'total_files': int,
                'success_count': int,
                'failed_count': int,
                'total_rows': int,
                'results': List[dict],
            }
        """
        dir_path = Path(dir_path)
        if not dir_path.exists():
            return {
                'success': False,
                'errors': [f"目录不存在：{dir_path}"],
            }

        zip_files = sorted(dir_path.glob(pattern))
        if not zip_files:
            return {
                'success': False,
                'errors': ['没有匹配的 ZIP 文件'],
            }

        result = {
            'total_files': len(zip_files),
            'success_count': 0,
            'failed_count': 0,
            'total_rows': 0,
            'results': [],
        }

        for i, zip_file in enumerate(zip_files, 1):
            print(f"\n[{i}/{len(zip_files)}] 处理 {zip_file.name}")

            zip_result = await self.convert_zip(
                str(zip_file),
                symbol=symbol,
                timeframe=timeframe,
            )

            result['results'].append(zip_result)

            if zip_result.get('success'):
                result['success_count'] += 1
                result['total_rows'] += zip_result.get('rows_imported', 0)
            else:
                result['failed_count'] += 1

        return result


# ============================================================
# CLI 入口
# ============================================================

async def main():
    import argparse

    parser = argparse.ArgumentParser(description='Binance CSV 到 SQLite ETL 工具')
    subparsers = parser.add_subparsers(dest='command', help='命令')

    # init 命令
    init_parser = subparsers.add_parser('init', help='初始化数据库')
    init_parser.add_argument('--db', default=DEFAULT_DB_PATH, help='数据库路径')

    # validate 命令
    validate_parser = subparsers.add_parser('validate', help='验证 CSV 文件')
    validate_parser.add_argument('path', help='CSV 文件路径')

    # convert 命令
    convert_parser = subparsers.add_parser('convert', help='转换单个 CSV 文件')
    convert_parser.add_argument('csv_path', help='CSV 文件路径')
    convert_parser.add_argument('--symbol', help='覆盖交易对 (CCXT 格式)')
    convert_parser.add_argument('--timeframe', help='覆盖时间周期')
    convert_parser.add_argument('--db', default=DEFAULT_DB_PATH, help='数据库路径')

    # unzip-convert 命令
    unzip_convert_parser = subparsers.add_parser('unzip-convert', help='解压并转换 ZIP')
    unzip_convert_parser.add_argument('zip_path', help='ZIP 文件路径')
    unzip_convert_parser.add_argument('--symbol', help='覆盖交易对')
    unzip_convert_parser.add_argument('--timeframe', help='覆盖时间周期')
    unzip_convert_parser.add_argument('--db', default=DEFAULT_DB_PATH, help='数据库路径')

    # batch 命令
    batch_parser = subparsers.add_parser('batch', help='批量转换目录')
    batch_parser.add_argument('dir_path', help='目录路径')
    batch_parser.add_argument('--symbol', help='覆盖交易对')
    batch_parser.add_argument('--timeframe', help='覆盖时间周期')
    batch_parser.add_argument('--pattern', default='*.zip', help='文件匹配模式')
    batch_parser.add_argument('--db', default=DEFAULT_DB_PATH, help='数据库路径')

    args = parser.parse_args()

    etl = ETLService(db_path=args.db if hasattr(args, 'db') else DEFAULT_DB_PATH)

    if args.command == 'init':
        await etl.initialize_db()
        await etl.create_indexes()

    elif args.command == 'validate':
        # 使用 validate_csv 脚本
        from scripts.etl.validate_csv import validate_csv
        result = validate_csv(args.path)

        if result['valid']:
            print("\n✅ 验证通过")
        else:
            print("\n❌ 验证失败")
            for error in result['errors']:
                print(f"  - {error}")

        if result['warnings']:
            print("\n⚠️  警告:")
            for warning in result['warnings'][:10]:
                print(f"  - {warning}")

    elif args.command == 'convert':
        await etl.initialize_db()
        result = await etl.convert_csv(
            args.csv_path,
            symbol=args.symbol,
            timeframe=args.timeframe,
        )

        if result['success']:
            print(f"\n✅ 转换完成：{result['rows_imported']:,} 行")
        else:
            print(f"\n❌ 转换失败:")
            for error in result['errors']:
                print(f"  - {error}")

    elif args.command == 'unzip-convert':
        await etl.initialize_db()
        result = await etl.convert_zip(
            args.zip_path,
            symbol=args.symbol,
            timeframe=args.timeframe,
        )

        if result['success']:
            print(f"\n✅ 转换完成：{result.get('rows_imported', 0):,} 行")
        else:
            print(f"\n❌ 转换失败:")
            for error in result.get('errors', []):
                print(f"  - {error}")

    elif args.command == 'batch':
        await etl.initialize_db()
        result = await etl.batch_convert_directory(
            args.dir_path,
            symbol=args.symbol,
            timeframe=args.timeframe,
            pattern=args.pattern,
        )

        print(f"\n{'='*60}")
        print(f"批量转换汇总")
        print(f"{'='*60}")
        print(f"总文件数：{result['total_files']}")
        print(f"成功：{result['success_count']} ✅")
        print(f"失败：{result['failed_count']} ❌")
        print(f"总导入行数：{result['total_rows']:,}")

        # 显示失败的文件
        failed = [r for r in result['results'] if not r.get('success')]
        if failed:
            print(f"\n失败文件列表:")
            for r in failed:
                print(f"  - {r.get('file', 'unknown')}: {r.get('errors', [])}")

    else:
        parser.print_help()


if __name__ == '__main__':
    asyncio.run(main())
