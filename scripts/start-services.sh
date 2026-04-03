#!/bin/bash
# 快速启动前后端服务脚本

set -e

echo "🐶 盯盘狗 - 启动开发服务"
echo "================================"

# 创建日志目录
mkdir -p logs

# 启动后端服务
echo "[1/3] 启动后端 API 服务..."
cd "$(dirname "$0")/.."
source venv/bin/activate 2>/dev/null || true
python src/main.py > logs/backend.log 2>&1 &
BACKEND_PID=$!
echo "      后端 PID: $BACKEND_PID"
echo "      日志：logs/backend.log"

# 等待后端启动
sleep 3

# 检查后端是否正常启动
if ps -p $BACKEND_PID > /dev/null; then
    echo "      ✅ 后端服务已启动"
else
    echo "      ❌ 后端服务启动失败，请查看 logs/backend.log"
    exit 1
fi

# 启动前端服务
echo "[2/3] 启动前端开发服务..."
cd web-front
npm run dev > ../logs/frontend.log 2>&1 &
FRONTEND_PID=$!
echo "      前端 PID: $FRONTEND_PID"
echo "      日志：logs/frontend.log"

# 等待前端启动
sleep 5

echo "[3/3] 服务启动完成"
echo "================================"
echo ""
echo "后端 API: http://localhost:8000"
echo "前端服务：http://localhost:5173"
echo ""
echo "按 Ctrl+C 停止所有服务"
echo ""

# 保存 PID 文件
echo "$BACKEND_PID" > ../logs/backend.pid
echo "$FRONTEND_PID" > ../logs/frontend.pid

# 等待用户中断
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo '服务已停止'; exit 0" INT TERM

# 保持运行
wait
