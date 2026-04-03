#!/bin/bash
# ============================================================
# 盯盘狗 🐶 - 一键停止脚本
# 用法：./stop.sh
# 功能：一键停止前后端所有服务
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🐶 盯盘狗 - 停止服务"
echo "========================================"

# 停止后端
echo -n "📋 停止后端服务... "
if [ -f "logs/backend.pid" ]; then
    PID=$(cat logs/backend.pid 2>/dev/null)
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        kill "$PID" 2>/dev/null
        sleep 1
        # 如果还在运行，强制停止
        if kill -0 "$PID" 2>/dev/null; then
            kill -9 "$PID" 2>/dev/null
        fi
        echo "✅ 后端 (PID $PID) 已停止"
    else
        echo "⚠️  后端服务未运行"
    fi
    rm -f logs/backend.pid
else
    # 备用方案：清理可能的进程
    if pkill -f "python3.*src.main" 2>/dev/null; then
        echo "✅ 清理了残留后端进程"
    else
        echo "⚠️  后端服务未运行"
    fi
fi

# 停止前端
echo -n "📋 停止前端服务... "
if [ -f "logs/frontend.pid" ]; then
    PID=$(cat logs/frontend.pid 2>/dev/null)
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        # 先杀子进程（node/vite）
        pkill -P "$PID" 2>/dev/null || true
        sleep 0.5
        kill "$PID" 2>/dev/null
        sleep 0.5
        # 如果还在运行，强制停止
        if kill -0 "$PID" 2>/dev/null; then
            kill -9 "$PID" 2>/dev/null
        fi
        echo "✅ 前端 (PID $PID) 已停止"
    else
        echo "⚠️  前端服务未运行"
    fi
    rm -f logs/frontend.pid
else
    # 备用方案：清理可能的进程
    if pkill -f "vite.*--port" 2>/dev/null; then
        echo "✅ 清理了残留前端进程"
    else
        echo "⚠️  前端服务未运行"
    fi
fi

# 清理端口占用（备用方案）
echo ""
echo "🧹 清理可能的端口占用..."
for PORT in 8000 5173; do
    PIDS=$(lsof -ti:$PORT 2>/dev/null)
    if [ -n "$PIDS" ]; then
        echo "   端口 $PORT 被占用，清理中..."
        echo "$PIDS" | xargs kill -9 2>/dev/null || true
        echo "   ✅ 端口 $PORT 已释放"
    fi
done

# 清理 uvicorn 进程
pkill -f "uvicorn.*src.interfaces.api" 2>/dev/null || true

echo ""
echo "========================================"
echo "✅ 所有服务已停止"
echo "========================================"
