#!/usr/bin/env python3
"""
Binance Vision 合约 K 线数据下载器

从 https://data.binance.vision 下载 U 本位合约 (USDS-M) K 线数据。

数据源格式:
https://data.binance.vision/data/futures/um/{frequency}/monthly/{SYMBOL}-{TIMEFRAME}-{YEAR}-{MONTH}.zip

示例:
https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1h/BTCUSDT-1h-2026-02.zip

使用示例:
    # 下载单个文件
    python3 binance_downloader.py download --symbol BTCUSDT --timeframe 1h --year 2026 --month 2

    # 批量下载指定日期范围
    python3 binance_downloader.py batch --symbol BTCUSDT --timeframes 15m,1h,4h,1d --start 2023-01 --end 2026-02

    # 下载多个交易对
    python3 binance_downloader.py multi --symbols BTCUSDT,ETHUSDT --timeframes 15m,1h,4h,1d --start 2023-01 --end 2026-02
"""

import sys
import os
import asyncio
import aiohttp
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Tuple
import argparse


# ============================================================
# 配置
# ============================================================

# 币安数据源基础 URL
BINANCE_BASE_URL = "https://data.binance.vision/data/futures/um"

# 时间周期映射 (URL 格式)
TIMEFRAME_URL_MAP = {
    '1m': '1m',
    '3m': '3m',
    '5m': '5m',
    '15m': '15m',
    '30m': '30m',
    '1h': '1h',
    '2h': '2h',
    '4h': '4h',
    '6h': '6h',
    '12h': '12h',
    '1d': '1d',
    '1w': '1w',
}

# 默认输出目录
DEFAULT_OUTPUT_DIR = Path.home() / "Documents" / "data" / "binance"

# 并发下载数
MAX_CONCURRENT_DOWNLOADS = 5

# 重试次数
MAX_RETRIES = 3

# 重试延迟 (秒)
RETRY_DELAY = 2


# ============================================================
# 下载器
# ============================================================

class BinanceDownloader:
    """币安合约 K 线数据下载器"""

    def __init__(self, output_dir: str = str(DEFAULT_OUTPUT_DIR)):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)

    def _build_url(self, symbol: str, timeframe: str, year: int, month: int) -> str:
        """构建下载 URL"""
        tf = TIMEFRAME_URL_MAP.get(timeframe, timeframe)
        filename = f"{symbol}-{tf}-{year}-{month:02d}.zip"
        # 注意：URL 结构包含 klines 目录
        return f"{BINANCE_BASE_URL}/monthly/klines/{symbol}/{tf}/{filename}"

    def _build_filepath(self, symbol: str, timeframe: str, year: int, month: int) -> Path:
        """构建本地保存路径"""
        tf = TIMEFRAME_URL_MAP.get(timeframe, timeframe)
        filename = f"{symbol}-{tf}-{year}-{month:02d}.zip"
        return self.output_dir / symbol / tf / filename

    async def _download_file(
        self,
        session: aiohttp.ClientSession,
        url: str,
        filepath: Path,
        symbol: str,
        timeframe: str,
        year: int,
        month: int,
    ) -> Tuple[bool, str]:
        """下载单个文件"""
        async with self._semaphore:
            for attempt in range(MAX_RETRIES):
                try:
                    # 检查文件是否已存在
                    if filepath.exists():
                        return True, f"文件已存在：{filepath}"

                    # 创建目录
                    filepath.parent.mkdir(parents=True, exist_ok=True)

                    # 下载
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=300)) as response:
                        if response.status == 404:
                            return False, f"文件不存在 (404): {url}"

                        response.raise_for_status()

                        # 读取内容
                        content = await response.read()

                        # 保存到临时文件
                        temp_filepath = filepath.with_suffix('.zip.tmp')
                        with open(temp_filepath, 'wb') as f:
                            f.write(content)

                        # 重命名为正式文件
                        temp_filepath.rename(filepath)

                        return True, f"下载成功：{filepath.name} ({len(content):,} bytes)"

                except asyncio.TimeoutError:
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                        continue
                    return False, f"下载超时：{url}"

                except aiohttp.ClientError as e:
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                        continue
                    return False, f"网络错误：{e}"

                except Exception as e:
                    return False, f"未知错误：{e}"

            return False, f"重试 {MAX_RETRIES} 次后失败"

    async def download_single(
        self,
        symbol: str,
        timeframe: str,
        year: int,
        month: int,
    ) -> Tuple[bool, str]:
        """下载单个文件"""
        url = self._build_url(symbol, timeframe, year, month)
        filepath = self._build_filepath(symbol, timeframe, year, month)

        async with aiohttp.ClientSession() as session:
            return await self._download_file(session, url, filepath, symbol, timeframe, year, month)

    async def download_batch(
        self,
        symbol: str,
        timeframes: List[str],
        start_year: int,
        start_month: int,
        end_year: int,
        end_month: int,
    ) -> dict:
        """批量下载指定时间范围"""
        # 生成所有年月组合
        months_to_download = []
        current_year, current_month = start_year, start_month

        while current_year < end_year or (current_year == end_year and current_month <= end_month):
            months_to_download.append((current_year, current_month))

            # 下一个月
            current_month += 1
            if current_month > 12:
                current_month = 1
                current_year += 1

        print(f"\n{'='*60}")
        print(f"下载计划")
        print(f"{'='*60}")
        print(f"交易对：{symbol}")
        print(f"时间周期：{timeframes}")
        print(f"时间范围：{start_year}-{start_month:02d} 至 {end_year}-{end_month:02d}")
        print(f"总文件数：{len(months_to_download) * len(timeframes)}")

        results = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'skipped': 0,
            'details': [],
        }

        async with aiohttp.ClientSession() as session:
            tasks = []

            for timeframe in timeframes:
                for year, month in months_to_download:
                    url = self._build_url(symbol, timeframe, year, month)
                    filepath = self._build_filepath(symbol, timeframe, year, month)

                    task = self._download_file(
                        session, url, filepath, symbol, timeframe, year, month
                    )
                    tasks.append(task)
                    results['total'] += 1

            # 并发下载
            for i, task in enumerate(asyncio.as_completed(tasks), 1):
                success, message = await task
                results['details'].append({
                    'success': success,
                    'message': message,
                })

                if success:
                    if "已存在" in message:
                        results['skipped'] += 1
                        print(f"[{i}/{results['total']}] ⏭️  {message}")
                    else:
                        results['success'] += 1
                        print(f"[{i}/{results['total']}] ✅ {message}")
                else:
                    results['failed'] += 1
                    print(f"[{i}/{results['total']}] ❌ {message}")

        return results

    async def download_multi_symbols(
        self,
        symbols: List[str],
        timeframes: List[str],
        start_year: int,
        start_month: int,
        end_year: int,
        end_month: int,
    ) -> dict:
        """下载多个交易对"""
        overall = {
            'symbols': {},
            'total_files': 0,
            'total_success': 0,
            'total_failed': 0,
            'total_skipped': 0,
        }

        for symbol in symbols:
            print(f"\n{'='*60}")
            print(f"开始下载 {symbol}")
            print(f"{'='*60}")

            result = await self.download_batch(
                symbol=symbol,
                timeframes=timeframes,
                start_year=start_year,
                start_month=start_month,
                end_year=end_year,
                end_month=end_month,
            )

            overall['symbols'][symbol] = result
            overall['total_files'] += result['total']
            overall['total_success'] += result['success']
            overall['total_failed'] += result['failed']
            overall['total_skipped'] += result['skipped']

        return overall


# ============================================================
# 辅助函数
# ============================================================

def parse_date_range(start: str, end: str) -> Tuple[int, int, int, int]:
    """解析日期范围 (YYYY-MM 格式)"""
    try:
        start_parts = start.split('-')
        end_parts = end.split('-')

        start_year, start_month = int(start_parts[0]), int(start_parts[1])
        end_year, end_month = int(end_parts[0]), int(end_parts[1])

        return start_year, start_month, end_year, end_month
    except (IndexError, ValueError):
        raise ValueError(f"日期格式应为 YYYY-MM，例如：2023-01")


def print_summary(overall: dict):
    """打印下载汇总"""
    print(f"\n{'='*60}")
    print(f"下载汇总")
    print(f"{'='*60}")
    print(f"总文件数：{overall['total_files']}")
    print(f"成功：{overall['total_success']} ✅")
    print(f"失败：{overall['total_failed']} ❌")
    print(f"跳过 (已存在): {overall['total_skipped']} ⏭️")

    for symbol, result in overall['symbols'].items():
        print(f"\n{symbol}:")
        print(f"  成功：{result['success']}, 失败：{result['failed']}, 跳过：{result['skipped']}")


# ============================================================
# CLI 入口
# ============================================================

async def main():
    parser = argparse.ArgumentParser(description='币安合约 K 线数据下载器')
    subparsers = parser.add_subparsers(dest='command', help='命令')

    # download 命令 - 下载单个文件
    download_parser = subparsers.add_parser('download', help='下载单个文件')
    download_parser.add_argument('--symbol', required=True, help='交易对 (例如：BTCUSDT)')
    download_parser.add_argument('--timeframe', required=True, help='时间周期 (例如：1h, 15m)')
    download_parser.add_argument('--year', type=int, required=True, help='年份')
    download_parser.add_argument('--month', type=int, required=True, help='月份')
    download_parser.add_argument('--output', help='输出目录')

    # batch 命令 - 批量下载
    batch_parser = subparsers.add_parser('batch', help='批量下载指定时间范围')
    batch_parser.add_argument('--symbol', required=True, help='交易对 (例如：BTCUSDT)')
    batch_parser.add_argument('--timeframes', required=True, help='时间周期列表 (例如：15m,1h,4h,1d)')
    batch_parser.add_argument('--start', required=True, help='开始日期 (YYYY-MM)')
    batch_parser.add_argument('--end', required=True, help='结束日期 (YYYY-MM)')
    batch_parser.add_argument('--output', help='输出目录')

    # multi 命令 - 多交易对下载
    multi_parser = subparsers.add_parser('multi', help='下载多个交易对')
    multi_parser.add_argument('--symbols', required=True, help='交易对列表 (例如：BTCUSDT,ETHUSDT,SOLUSDT)')
    multi_parser.add_argument('--timeframes', required=True, help='时间周期列表')
    multi_parser.add_argument('--start', required=True, help='开始日期 (YYYY-MM)')
    multi_parser.add_argument('--end', required=True, help='结束日期 (YYYY-MM)')
    multi_parser.add_argument('--output', help='输出目录')

    args = parser.parse_args()

    # 确定输出目录
    output_dir = args.output if args.output else str(DEFAULT_OUTPUT_DIR)
    downloader = BinanceDownloader(output_dir=output_dir)

    if args.command == 'download':
        # 下载单个文件
        success, message = await downloader.download_single(
            symbol=args.symbol,
            timeframe=args.timeframe,
            year=args.year,
            month=args.month,
        )
        print(message)
        sys.exit(0 if success else 1)

    elif args.command == 'batch':
        # 批量下载
        timeframes = [tf.strip() for tf in args.timeframes.split(',')]
        start_year, start_month, end_year, end_month = parse_date_range(args.start, args.end)

        result = await downloader.download_batch(
            symbol=args.symbol,
            timeframes=timeframes,
            start_year=start_year,
            start_month=start_month,
            end_year=end_year,
            end_month=end_month,
        )

        print(f"\n汇总:")
        print(f"  成功：{result['success']}, 失败：{result['failed']}, 跳过：{result['skipped']}")
        sys.exit(0 if result['failed'] == 0 else 1)

    elif args.command == 'multi':
        # 多交易对下载
        symbols = [s.strip() for s in args.symbols.split(',')]
        timeframes = [tf.strip() for tf in args.timeframes.split(',')]
        start_year, start_month, end_year, end_month = parse_date_range(args.start, args.end)

        overall = await downloader.download_multi_symbols(
            symbols=symbols,
            timeframes=timeframes,
            start_year=start_year,
            start_month=start_month,
            end_year=end_year,
            end_month=end_month,
        )

        print_summary(overall)
        sys.exit(0 if overall['total_failed'] == 0 else 1)

    else:
        parser.print_help()


if __name__ == '__main__':
    asyncio.run(main())
