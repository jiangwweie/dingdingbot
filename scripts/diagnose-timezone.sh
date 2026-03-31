#!/bin/bash
# 时间显示问题诊断脚本
# 用法：在服务器上执行 ./diagnose-timezone.sh

echo "======================================"
echo "  时间显示问题诊断报告"
echo "======================================"
echo ""

# 1. 系统时区信息
echo "【1】系统时区信息"
echo "--------------------------------------"
if command -v timedatectl &> /dev/null; then
    timedatectl
else
    date -R
fi
echo ""

# 2. 当前时间
echo "【2】当前时间"
echo "--------------------------------------"
echo "UTC:    $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "Local:  $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo ""

# 3. Python 时间戳
echo "【3】Python 时间戳验证"
echo "--------------------------------------"
python3 << 'EOF'
from datetime import datetime, timezone
import time

# 当前 UTC 时间戳（毫秒）
utc_ts_ms = int(time.time() * 1000)
print(f"当前 UTC 时间戳 (ms): {utc_ts_ms}")

# UTC 时间
utc_dt = datetime.fromtimestamp(utc_ts_ms / 1000, tz=timezone.utc)
print(f"UTC 时间：{utc_dt}")

# 系统本地时间
local_dt = datetime.fromtimestamp(utc_ts_ms / 1000)
print(f"本地时间：{local_dt}")

# 北京时间
beijing_dt = datetime.fromtimestamp(utc_ts_ms / 1000, tz=timezone.utc).replace(tzinfo=None)
from datetime import timedelta
beijing_dt = beijing_dt + timedelta(hours=8)
print(f"北京时间 (UTC+8): {beijing_dt}")
EOF
echo ""

# 4. 数据库中的 kline_timestamp
echo "【4】数据库查询 (signal id=291)"
echo "--------------------------------------"
DB_PATH="/root/dingdingbot/data/signals.db"
if [ -f "$DB_PATH" ]; then
    sqlite3 "$DB_PATH" "SELECT id, kline_timestamp, created_at, symbol, timeframe FROM signals WHERE id = 291;"

    # 获取 kline_timestamp 并转换
    TS=$(sqlite3 "$DB_PATH" "SELECT kline_timestamp FROM signals WHERE id = 291;")
    if [ -n "$TS" ]; then
        echo ""
        echo "时间戳分析:"
        echo "  kline_timestamp (ms): $TS"
        python3 << PYEOF
ts = $TS
from datetime import datetime, timezone, timedelta

utc_dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
beijing_dt = utc_dt + timedelta(hours=8)
tokyo_dt = utc_dt + timedelta(hours=9)

print(f"  UTC 时间：{utc_dt.strftime('%Y-%m-%d %H:%M:%S')}")
print(f"  北京时间：{beijing_dt.strftime('%Y-%m-%d %H:%M:%S')} (UTC+8)")
print(f"  东京时间：{tokyo_dt.strftime('%Y-%m-%d %H:%M:%S')} (UTC+9)")
PYEOF
    fi
else
    echo "数据库未找到：$DB_PATH"
fi
echo ""

# 5. 后端日志中的时间戳
echo "【5】后端日志最近 10 条"
echo "--------------------------------------"
LOG_PATH="/root/dingdingbot/logs/app.log"
if [ -f "$LOG_PATH" ]; then
    tail -10 "$LOG_PATH"
else
    echo "日志文件未找到：$LOG_PATH"
fi
echo ""

# 6. 币安 API 返回的 K 线时间戳
echo "【6】币安 API K 线时间戳（实时获取）"
echo "--------------------------------------"
python3 << 'EOF'
import asyncio
import ccxt.async_support as ccxt

async def fetch_kline():
    exchange = ccxt.binanceusdm({'options': {'defaultType': 'swap'}})
    try:
        ohlcv = await exchange.fetch_ohlcv('BNB/USDT:USDT', '15m', limit=5)
        print("最近 5 根 K 线 (timestamp, open, high, low, close, volume):")
        for k in ohlcv:
            ts = k[0]
            from datetime import datetime, timezone, timedelta
            utc_dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
            beijing_dt = utc_dt + timedelta(hours=8)
            print(f"  TS: {ts}")
            print(f"      UTC: {utc_dt.strftime('%H:%M:%S')} | 北京：{beijing_dt.strftime('%H:%M:%S')}")
    finally:
        await exchange.close()

asyncio.run(fetch_kline())
EOF
echo ""

echo "======================================"
echo "  诊断报告完成"
echo "======================================"
