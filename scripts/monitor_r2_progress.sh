#!/bin/bash
# R2 搜索进度监控脚本

LOG_FILE="/tmp/r2_search.log"

if [ ! -f "$LOG_FILE" ]; then
    echo "❌ 日志文件不存在: $LOG_FILE"
    exit 1
fi

# 统计已完成配置数
COMPLETED=$(grep -c "PnL:" "$LOG_FILE" 2>/dev/null || echo "0")

# 统计错误数
ERRORS=$(grep -c "❌ 错误:" "$LOG_FILE" 2>/dev/null || echo "0")

# 获取当前进度
CURRENT=$(grep -o "\[[0-9]*/168\]" "$LOG_FILE" | tail -1 | tr -d '[]')

# 获取当前年份
CURRENT_YEAR=$(grep "搜索.*年最优配置" "$LOG_FILE" | tail -1 | grep -o "20[0-9][0-9]" || echo "未知")

# 获取最新结果
LATEST_PNL=$(grep "PnL:" "$LOG_FILE" | tail -1 | grep -o "PnL: [-0-9.]*" | awk '{print $2}')
LATEST_MAXDD=$(grep "PnL:" "$LOG_FILE" | tail -1 | grep -o "MaxDD: [-0-9.]*%" | awk '{print $2}')
LATEST_TRADES=$(grep "PnL:" "$LOG_FILE" | tail -1 | grep -o "Trades: [0-9]*" | awk '{print $2}')

# 计算进度百分比
if [ -n "$CURRENT" ]; then
    PROGRESS=$(echo "scale=1; $CURRENT / 168 * 100" | bc)
else
    PROGRESS="0"
fi

# 输出进度报告
echo "============================================================"
echo "R2 搜索进度报告 - $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================================"
echo ""
echo "📊 总体进度:"
echo "  - 已完成: ${COMPLETED}/168 配置 (${PROGRESS}%)"
echo "  - 错误数: ${ERRORS}"
echo "  - 当前年份: ${CURRENT_YEAR}"
echo ""
echo "📈 最新结果:"
echo "  - PnL: ${LATEST_PNL:-N/A} USDT"
echo "  - MaxDD: ${LATEST_MAXDD:-N/A}"
echo "  - Trades: ${LATEST_TRADES:-N/A}"
echo ""

# 预估剩余时间
if [ "$COMPLETED" -gt 0 ]; then
    # 计算平均耗时（假设每个配置约 30 秒）
    REMAINING=$((168 - COMPLETED))
    REMAINING_MINUTES=$(echo "scale=0; $REMAINING * 30 / 60" | bc)
    echo "⏱️  预估剩余时间: ~${REMAINING_MINUTES} 分钟"
fi

echo ""
echo "============================================================"
