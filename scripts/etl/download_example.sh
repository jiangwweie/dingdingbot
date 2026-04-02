#!/bin/bash
# 币安合约 K 线数据下载示例
# 下载 BTC 2023-01 到 2026-02 的 15min, 1h, 4h, 1d 数据

set -e

echo "============================================================"
echo "币安合约 K 线数据下载脚本"
echo "============================================================"

# 配置
SYMBOL="BTCUSDT"
TIMEFRAMES="15m,1h,4h,1d"
START_DATE="2023-01"
END_DATE="2026-02"
OUTPUT_DIR="$HOME/Documents/data"

echo ""
echo "交易对：$SYMBOL"
echo "时间周期：$TIMEFRAMES"
echo "时间范围：$START_DATE 至 $END_DATE"
echo "输出目录：$OUTPUT_DIR"
echo ""

# 切换到脚本所在目录
cd "$(dirname "$0")"

# 运行下载器
python3 binance_downloader.py batch \
    --symbol "$SYMBOL" \
    --timeframes "$TIMEFRAMES" \
    --start "$START_DATE" \
    --end "$END_DATE" \
    --output "$OUTPUT_DIR"

echo ""
echo "============================================================"
echo "下载完成！"
echo "============================================================"
