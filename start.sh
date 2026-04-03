#!/bin/bash
# ============================================================
# 盯盘狗 🐶 - 一键启动脚本
# 用法：./start.sh
# 功能：一键启动前后端所有服务
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🐶 盯盘狗 - 一键启动服务"
echo "========================================"

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo "❌ 虚拟环境不存在，请先创建："
    echo "   python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

# 检查 node_modules
if [ ! -d "web-front/node_modules" ]; then
    echo "⚠️  前端依赖未安装，正在安装..."
    cd web-front && npm install && cd ..
fi

# 停止旧服务
echo ""
echo "📋 步骤 1/3: 停止旧服务..."
./scripts/deploy/stop.sh 2>/dev/null || true
sleep 1

# 启动后端
echo ""
echo "📋 步骤 2/3: 启动后端服务..."
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

# 启动前端
echo ""
echo "📋 步骤 3/3: 启动前端服务..."
cd web-front
nohup npm run dev > ../logs/frontend.log 2>&1 &
FRONTEND_PID=$!
echo "$FRONTEND_PID" > ../logs/frontend.pid
cd ..
echo "   ✅ 前端已启动 (PID: $FRONTEND_PID)"
echo "   📄 日志：logs/frontend.log"

# 等待前端就绪
echo "   ⏳ 等待前端就绪..."
sleep 3
# 检查是否使用 3000 端口（从日志中读取实际端口）
FRONTEND_PORT=5173
if grep -q "http://localhost:3000" logs/frontend.log 2>/dev/null; then
    FRONTEND_PORT=3000
fi
for i in {1..20}; do
    if curl -s "http://localhost:$FRONTEND_PORT" > /dev/null 2>&1; then
        echo "   ✅ 前端服务已就绪 (端口：$FRONTEND_PORT)"
        break
    fi
    sleep 0.5
done

echo ""
echo "========================================"
echo "✅ 盯盘狗 - 所有服务已启动"
echo "========================================"
echo ""
# 显示实际的端口号
FRONTEND_PORT=5173
if grep -q "http://localhost:3000" logs/frontend.log 2>/dev/null; then
    FRONTEND_PORT=3000
fi
echo "📱 前端 Dashboard: http://localhost:$FRONTEND_PORT"
echo "🔌 后端 API:       http://localhost:8000"
echo "🏥 健康检查：     http://localhost:8000/api/health"
echo ""
echo "🛑 停止服务：./stop.sh"
echo "📊 查看日志：tail -f logs/backend.log"
echo "========================================"
