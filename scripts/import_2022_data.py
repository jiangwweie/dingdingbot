#!/usr/bin/env python3
"""
下载并导入 2022 年度 Binance 历史 K 线数据到本地数据库
"""
import asyncio
import csv
import io
import os
import shutil
import tempfile
import time
import urllib.request
import zipfile
from decimal import Decimal
from pathlib import Path
from typing import List, Tuple

import aiosqlite

from src.infrastructure.logger import logger

# ============================================================
# 配置
# ============================================================

DB_PATH = "data/v3_dev.db"
BASE_URL = "https://data.binance.vision/data/futures/um/monthly/klines"

# 2022 年度数据：1-12 月
MONTHS = [f"2022-{month:02d}" for month in range(1, 13)]

# 4 币种 × 4 周期 = 16 个文件 × 12 月 = 192 文件
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
TIMEFRAMES = ["15m", "1h", "4h", "1d"]

# 本地 symbol 格式（与 ExchangeGateway 一致）
SYMBOL_MAP = {
    "BTCUSDT": "BTC/USDT:USDT",
    "ETHUSDT": "ETH/USDT:USDT",
    "SOLUSDT": "SOL/USDT:USDT",
    "BNBUSDT": "BNB/USDT:USDT",
}


# ============================================================
# 下载
# ============================================================

def build_url(symbol: str, timeframe: str, month: str) -> str:
    """构建 Binance 数据 URL"""
    return f"{BASE_URL}/{symbol}/{timeframe}/{symbol}-{timeframe}-{month}.zip"


async def download_file(url: str, tmp_dir: str) -> str:
    """下载 ZIP 文件到临时目录"""
    filename = url.split("/")[-1]
    filepath = os.path.join(tmp_dir, filename)
    logger.info(f"  下载: {filename}")

    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as response:
        with open(filepath, "wb") as f:
            shutil.copyfileobj(response, f)

    size_kb = os.path.getsize(filepath) / 1024
    logger.info(f"  完成: {filename} ({size_kb:.1f} KB)")
    return filepath


# ============================================================
# 解析 CSV
# ============================================================

def parse_csv(zip_path: str, local_symbol: str, timeframe: str) -> List[Tuple]:
    """
    解析 Binance CSV 文件，返回 (symbol, timeframe, timestamp, open, high, low, close, volume, is_closed) 元组列表
    """
    rows = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        csv_name = zf.namelist()[0]  # 第一个文件即为 CSV
        with zf.open(csv_name) as csv_file:
            content = csv_file.read().decode("utf-8")
            reader = csv.reader(io.StringIO(content))
            first_row = True
            for line in reader:
                if not line or len(line) < 6:
                    continue
                # 跳过表头行
                if first_row:
                    first_row = False
                    try:
                        int(line[0])
                    except ValueError:
                        continue  # 表头行，跳过
                timestamp = int(line[0])
                open_price = Decimal(line[1])
                high_price = Decimal(line[2])
                low_price = Decimal(line[3])
                close_price = Decimal(line[4])
                volume = Decimal(line[5])

                rows.append((
                    local_symbol,
                    timeframe,
                    timestamp,
                    open_price,
                    high_price,
                    low_price,
                    close_price,
                    volume,
                    True,  # is_closed = True（历史数据均已收盘）
                ))

    logger.info(f"  解析: {len(rows)} 根 K 线")
    return rows


# ============================================================
# 导入数据库
# ============================================================

async def ensure_klines_table(db: aiosqlite.Connection) -> None:
    """创建 klines 表（如果不存在），与 KlineORM schema 保持一致"""
    await db.execute("""
        CREATE TABLE IF NOT EXISTS klines (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol    TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            timestamp INTEGER NOT NULL,
            open      TEXT NOT NULL,
            high      TEXT NOT NULL,
            low       TEXT NOT NULL,
            close     TEXT NOT NULL,
            volume    TEXT NOT NULL,
            is_closed INTEGER NOT NULL DEFAULT 1,
            created_at INTEGER NOT NULL
        )
    """)

    # 唯一索引（与 _save_klines 的 on_conflict_do_nothing 一致）
    await db.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_klines_unique
        ON klines(symbol, timeframe, timestamp)
    """)

    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_klines_symbol_tf
        ON klines(symbol, timeframe)
    """)

    await db.commit()


async def insert_klines(
    db: aiosqlite.Connection,
    rows: List[Tuple],
    batch_size: int = 500,
) -> int:
    """
    幂等性插入 K 线数据（INSERT OR IGNORE）

    返回: 实际插入的条数
    """
    now_ms = int(time.time() * 1000)
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        # Decimal 转为字符串存储（与 DecimalString 类型一致）
        # 包含 created_at 列（NOT NULL）
        values = [
            (r[0], r[1], r[2], str(r[3]), str(r[4]), str(r[5]), str(r[6]), str(r[7]), r[8], now_ms)
            for r in batch
        ]
        await db.executemany("""
            INSERT OR IGNORE INTO klines
                (symbol, timeframe, timestamp, open, high, low, close, volume, is_closed, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, values)

    await db.commit()
    return len(rows)


# ============================================================
# 主流程
# ============================================================

async def main():
    logger.info("=" * 60)
    logger.info("Binance 2022 年度历史 K 线数据导入")
    logger.info(f"  月份: 2022-01 至 2022-12")
    logger.info(f"  币种: {SYMBOLS}")
    logger.info(f"  周期: {TIMEFRAMES}")
    logger.info(f"  数据库: {DB_PATH}")
    logger.info("=" * 60)

    # 创建临时目录
    tmp_dir = tempfile.mkdtemp(prefix="binance_2022_klines_")
    logger.info(f"临时目录: {tmp_dir}")

    total_downloaded = 0
    total_parsed = 0
    total_inserted = 0
    total_skipped = 0  # 重复/已存在

    # 先创建数据库连接
    db = await aiosqlite.connect(DB_PATH)
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA synchronous=NORMAL")
    await ensure_klines_table(db)

    try:
        for month in MONTHS:
            logger.info(f"\n=== 处理月份: {month} ===")

            for symbol in SYMBOLS:
                for timeframe in TIMEFRAMES:
                    url = build_url(symbol, timeframe, month)
                    local_symbol = SYMBOL_MAP[symbol]

                    logger.info(f"\n--- {symbol} {timeframe} -> {local_symbol} ---")

                    # 1. 下载
                    try:
                        zip_path = await download_file(url, tmp_dir)
                        total_downloaded += 1
                    except urllib.error.HTTPError as e:
                        if e.code == 404:
                            logger.warning(f"  文件不存在 (404): {url}")
                            continue
                        else:
                            logger.error(f"  下载失败: {e}")
                            continue
                    except Exception as e:
                        logger.error(f"  下载错误: {e}")
                        continue

                    # 2. 解析
                    rows = parse_csv(zip_path, local_symbol, timeframe)
                    total_parsed += len(rows)

                    if not rows:
                        logger.warning(f"  跳过: 无数据")
                        continue

                    # 3. 导入（通过 COUNT 差值计算实际插入数）
                    cursor = await db.execute(
                        "SELECT COUNT(*) FROM klines WHERE symbol=? AND timeframe=?",
                        (local_symbol, timeframe),
                    )
                    count_before = (await cursor.fetchone())[0]

                    await insert_klines(db, rows)

                    cursor = await db.execute(
                        "SELECT COUNT(*) FROM klines WHERE symbol=? AND timeframe=?",
                        (local_symbol, timeframe),
                    )
                    count_after = (await cursor.fetchone())[0]
                    inserted_count = count_after - count_before
                    total_inserted += inserted_count
                    total_skipped += len(rows) - inserted_count

                    # 4. 验证
                    cursor = await db.execute(
                        "SELECT MIN(timestamp), MAX(timestamp), COUNT(*) FROM klines WHERE symbol=? AND timeframe=?",
                        (local_symbol, timeframe),
                    )
                    min_ts, max_ts, count = await cursor.fetchone()

                    from datetime import datetime, timezone

                    min_dt = datetime.fromtimestamp(min_ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
                    max_dt = datetime.fromtimestamp(max_ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")

                    logger.info(f"  导入: {inserted_count} 新 / {len(rows)} 总，"
                                f"跳过 {len(rows) - inserted_count} 重复")
                    logger.info(f"  范围: {min_dt} ~ {max_dt} (UTC)，共 {count} 条")

        # 汇总
        logger.info("\n" + "=" * 60)
        logger.info("2022 年度数据导入完成")
        logger.info(f"  下载文件: {total_downloaded}")
        logger.info(f"  解析 K 线: {total_parsed}")
        logger.info(f"  新增插入: {total_inserted}")
        logger.info(f"  跳过重复: {total_skipped}")
        logger.info("=" * 60)

    finally:
        # 关闭数据库
        await db.close()
        # 清理临时文件
        shutil.rmtree(tmp_dir, ignore_errors=True)
        logger.info(f"临时目录已清理: {tmp_dir}")


if __name__ == "__main__":
    asyncio.run(main())