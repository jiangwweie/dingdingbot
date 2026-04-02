#!/bin/bash
# ============================================================
# 盯盘狗 - 启动脚本
# 功能：停止旧服务并启动前后端，不会报错退出
# ============================================================

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ROOT_DIR="$(dirname "$DIR")"

# 默认端口
FRONTEND_PORT=5173
BACKEND_PORT=8000

# 加载 .env 配置（如果存在）
ENV_FILE="$ROOT_DIR/.env"
if [ -f "$ENV_FILE" ]; then
    while IFS='=' read -r key value; do
        # 跳过注释和空行
        case "$key" in
            \#*|"") continue ;;
        esac
        # 导出变量
        export "$key"="$value"
    done < <(grep -v '^#' "$ENV_FILE" 2>/dev/null | grep -v '^\s*$')

    # 使用配置中的端口（如果定义了）
    FRONTEND_PORT=${FRONTEND_PORT:-5173}
    BACKEND_PORT=${BACKEND_PORT:-8000}
fi

echo "========================================="
echo "盯盘狗 - 启动服务"
echo "========================================="
echo "后端端口：$BACKEND_PORT"
echo "前端端口：$FRONTEND_PORT"
echo "========================================="

# 先停止旧服务
echo "检查并停止旧服务..."
"$DIR/stop.sh"

# 等待端口释放
sleep 1

# ============================================================
# 启动后端
# ============================================================
echo ""
echo "启动后端服务..."
cd "$ROOT_DIR" || exit 1

# 激活虚拟环境（如果存在）
if [ -d "$ROOT_DIR/venv" ]; then
    source "$ROOT_DIR/venv/bin/activate"
fi

# 导出环境变量
export BACKEND_PORT=$BACKEND_PORT
export PYTHONPATH="$ROOT_DIR:$PYTHONPATH"

# 启动后端
nohup python3 -m src.main > "$ROOT_DIR/backend.log" 2>&1 &
BACKEND_PID=$!
echo $BACKEND_PID > "$ROOT_DIR/.backend.pid"

# 等待后端启动（最多 10 秒）
echo "等待后端启动..."
for i in {1..20}; do
    if kill -0 $BACKEND_PID 2>/dev/null; then
        # 进程还在运行
        if curl -s "http://localhost:$BACKEND_PORT/api/health" > /dev/null 2>&1; then
            echo "后端服务已就绪 (PID: $BACKEND_PID)"
            break
        fi
    else
        echo "后端进程已退出，查看日志："
        tail -20 "$ROOT_DIR/backend.log"
        exit 1
    fi
    sleep 0.5
done

# ============================================================
# 启动前端
# ============================================================
echo ""
echo "启动前端服务..."
cd "$ROOT_DIR/web-front" || exit 1

# 导出环境变量
export FRONTEND_PORT=$FRONTEND_PORT
export BACKEND_PORT=$BACKEND_PORT

# 启动前端（vite）
nohup npm run dev -- --port $FRONTEND_PORT > "$ROOT_DIR/frontend.log" 2>&1 &
FRONTEND_PID=$!
echo $FRONTEND_PID > "$ROOT_DIR/.frontend.pid"

# 等待前端启动（最多 15 秒）
echo "等待前端启动..."
for i in {1..30}; do
    if kill -0 $FRONTEND_PID 2>/dev/null; then
        # 进程还在运行
        if curl -s "http://localhost:$FRONTEND_PORT" > /dev/null 2>&1; then
            echo "前端服务已就绪 (PID: $FRONTEND_PID)"
            break
        fi
    else
        echo "前端进程已退出，查看日志："
        tail -20 "$ROOT_DIR/frontend.log"
        exit 1
    fi
    sleep 0.5
done

# ============================================================
# 启动完成
# ============================================================
echo ""
echo "========================================="
echo "盯盘狗 - 服务启动完成"
echo "========================================="
echo "前端 Dashboard: http://localhost:$FRONTEND_PORT"
echo "后端 API Health: http://localhost:$BACKEND_PORT/api/health"
echo "========================================="
echo ""
echo "停止服务：./scripts/stop.sh"
echo "查看日志：tail -f backend.log 或 tail -f frontend.log"
echo ""

# 始终成功退出
exit 0
