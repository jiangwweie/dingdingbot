#!/bin/bash
# ============================================================
# 盯盘狗 🐶 - 一键启动脚本
# 用法：./start.sh
# 功能：一键启动前后端所有服务
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🐶 盯盘狗 - 启动后端服务"
echo "========================================"

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo "❌ 虚拟环境不存在，请先创建："
    echo "   python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

# 前端已迁移至 gemimi-web-front/，不再自动启动

# 停止旧服务
echo ""
echo "📋 步骤 1/2: 停止旧服务..."
./stop.sh 2>/dev/null || {
    # 备用方案：直接清理进程
    pkill -f "python3.*src.main" 2>/dev/null || true
    pkill -f "vite.*--port" 2>/dev/null || true
    pkill -f "uvicorn.*src.interfaces.api" 2>/dev/null || true
    echo "   ✅ 旧服务已清理"
}
sleep 1

# 启动后端
echo ""
echo "📋 步骤 2/2: 启动后端服务..."
source venv/bin/activate
export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"
nohup python3 src/main.py > logs/backend.log 2>&1 &
BACKEND_PID=$!
echo "$BACKEND_PID" > logs/backend.pid
echo "   ✅ 后端已启动 (PID: $BACKEND_PID)"
echo "   📄 日志：logs/backend.log"

# 等待后端就绪
echo "   ⏳ 等待后端就绪..."
for i in {1..20}; do
    if curl -s "http://localhost:8000/api/health" > /dev/null 2>&1; then
        echo "   ✅ 后端服务已就绪"
        break
    fi
    sleep 0.5
done

echo ""
echo "========================================"
echo "✅ 盯盘狗 - 后端服务已启动"
echo "========================================"
echo ""
echo "🔌 后端 API:       http://localhost:8000"
echo "🏥 健康检查：     http://localhost:8000/api/health"
echo ""
echo "📱 前端控制台:     cd gemimi-web-front && npm run dev"
echo "🛑 停止服务：./stop.sh"
echo "📊 查看日志：tail -f logs/backend.log"
echo "========================================"
