#!/usr/bin/env python3
"""
导入 1w 周线数据到数据库

从 ~/Documents/data/binance/ 目录读取下载的 ZIP 文件，
解压并导入到 SQLite 数据库。
"""

import asyncio
import csv
import io
import os
import zipfile
from decimal import Decimal
from pathlib import Path
from typing import List, Tuple

import aiosqlite

DB_PATH = "data/v3_dev.db"
DATA_DIR = Path.home() / "Documents" / "data" / "binance"

SYMBOL_MAP = {
    "BTCUSDT": "BTC/USDT:USDT",
    "ETHUSDT": "ETH/USDT:USDT",
    "SOLUSDT": "SOL/USDT:USDT",
}


def parse_kline_csv(zip_path: str, local_symbol: str) -> List[Tuple]:
    """解析 ZIP 文件中的 K 线数据"""
    records = []

    with zipfile.ZipFile(zip_path, 'r') as zf:
        csv_filename = zip_path.split('/')[-1].replace('.zip', '.csv')

        with zf.open(csv_filename) as f:
            content = f.read().decode('utf-8')
            reader = csv.reader(io.StringIO(content))

            # 跳过表头
            next(reader, None)

            for row in reader:
                if len(row) < 11:
                    continue

                # Binance K 线格式
                # [0] open_time, [1] open, [2] high, [3] low, [4] close,
                # [5] volume, [6] close_time, [7] quote_volume, ...
                timestamp = int(row[0])
                open_price = float(row[1])
                high = float(row[2])
                low = float(row[3])
                close = float(row[4])
                volume = float(row[5])

                records.append((
                    local_symbol,
                    "1w",
                    timestamp,
                    open_price,
                    high,
                    low,
                    close,
                    volume,
                    1,  # is_closed = True (历史数据都是已闭合的)
                    timestamp,  # created_at
                ))

    return records


async def import_1w_data():
    """导入所有 1w 数据"""
    async with aiosqlite.connect(DB_PATH) as db:
        total_imported = 0

        for binance_symbol, local_symbol in SYMBOL_MAP.items():
            symbol_dir = DATA_DIR / binance_symbol / "1w"

            if not symbol_dir.exists():
                print(f"跳过 {binance_symbol}: 目录不存在")
                continue

            zip_files = list(symbol_dir.glob("*.zip"))
            print(f"\n{binance_symbol}: 找到 {len(zip_files)} 个文件")

            for zip_file in zip_files:
                try:
                    records = parse_kline_csv(str(zip_file), local_symbol)

                    if records:
                        await db.executemany("""
                            INSERT OR REPLACE INTO klines
                            (symbol, timeframe, timestamp, open, high, low, close, volume, is_closed, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, records)

                        print(f"  {zip_file.name}: {len(records)} 条")
                        total_imported += len(records)

                except Exception as e:
                    print(f"  {zip_file.name}: 错误 - {e}")

        await db.commit()

    print(f"\n总计导入: {total_imported} 条 1w K 线数据")


if __name__ == "__main__":
    asyncio.run(import_1w_data())
