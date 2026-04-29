#!/bin/bash
# 盯盘狗 - 前后端统一停止脚本
# 功能：停止前后端进程、清理端口、清理PID文件、显示状态

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 项目根目录
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# PID文件
PID_DIR="$PROJECT_ROOT/.pids"
BACKEND_PID="$PID_DIR/backend.pid"
FRONTEND_PID="$PID_DIR/frontend.pid"

# 固定端口配置
BACKEND_PORT=8000
FRONTEND_PORT=3000

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}   盯盘狗 - 停止脚本${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# ============================================
# 停止后端
# ============================================
echo -e "${YELLOW}[1/2] 停止后端...${NC}"

# 方法1: 通过PID文件停止
if [ -f "$BACKEND_PID" ]; then
    BACKEND_PID_NUM=$(cat "$BACKEND_PID")

    # 检查进程是否存在
    if ps -p $BACKEND_PID_NUM > /dev/null 2>&1; then
        # 尝试优雅停止（SIGTERM）
        kill $BACKEND_PID_NUM 2>/dev/null || true

        # 等待3秒
        sleep 3

        # 检查进程是否已停止
        if ps -p $BACKEND_PID_NUM > /dev/null 2>&1; then
            echo -e "${YELLOW}⚠ 进程未响应SIGTERM，使用SIGKILL强制停止...${NC}"
            kill -9 $BACKEND_PID_NUM 2>/dev/null || true
            sleep 1
        fi

        # 最终检查
        if ps -p $BACKEND_PID_NUM > /dev/null 2>&1; then
            echo -e "${RED}✗ 后端进程停止失败 (PID: $BACKEND_PID_NUM)${NC}"
        else
            echo -e "${GREEN}✓ 后端已停止 (PID: $BACKEND_PID_NUM)${NC}"
        fi
    else
        echo -e "${YELLOW}⚠ 后端进程已不存在 (PID: $BACKEND_PID_NUM)${NC}"
    fi

    # 清理PID文件
    rm -f "$BACKEND_PID"
    echo -e "${GREEN}✓ PID文件已清理${NC}"
fi

# 方法2: 通过端口号停止（确保彻底清理）
BACKEND_PORT_PID=$(lsof -ti:$BACKEND_PORT 2>/dev/null || echo "")
if [ -n "$BACKEND_PORT_PID" ]; then
    echo -e "${YELLOW}⚠ 发现端口 $BACKEND_PORT 仍被占用 (PID: $BACKEND_PORT_PID)，正在清理...${NC}"
    kill -9 $BACKEND_PORT_PID 2>/dev/null || true
    sleep 1
    echo -e "${GREEN}✓ 已强制停止占用端口的进程${NC}"
fi

# 最终验证端口释放
BACKEND_CHECK=$(lsof -ti:$BACKEND_PORT 2>/dev/null || echo "")
if [ -z "$BACKEND_CHECK" ]; then
    echo -e "${GREEN}✓ 后端端口 $BACKEND_PORT 已释放${NC}"
else
    echo -e "${RED}✗ 后端端口 $BACKEND_PORT 仍被占用，请手动处理: kill -9 $BACKEND_CHECK${NC}"
fi

echo ""

# ============================================
# 停止前端
# ============================================
echo -e "${YELLOW}[2/2] 停止前端...${NC}"

# 方法1: 通过PID文件停止
if [ -f "$FRONTEND_PID" ]; then
    FRONTEND_PID_NUM=$(cat "$FRONTEND_PID")

    # 检查进程是否存在
    if ps -p $FRONTEND_PID_NUM > /dev/null 2>&1; then
        # 尝试优雅停止（SIGTERM）
        kill $FRONTEND_PID_NUM 2>/dev/null || true

        # 等待3秒
        sleep 3

        # 检查进程是否已停止
        if ps -p $FRONTEND_PID_NUM > /dev/null 2>&1; then
            echo -e "${YELLOW}⚠ 进程未响应SIGTERM，使用SIGKILL强制停止...${NC}"
            kill -9 $FRONTEND_PID_NUM 2>/dev/null || true
            sleep 1
        fi

        # 最终检查
        if ps -p $FRONTEND_PID_NUM > /dev/null 2>&1; then
            echo -e "${RED}✗ 前端进程停止失败 (PID: $FRONTEND_PID_NUM)${NC}"
        else
            echo -e "${GREEN}✓ 前端已停止 (PID: $FRONTEND_PID_NUM)${NC}"
        fi
    else
        echo -e "${YELLOW}⚠ 前端进程已不存在 (PID: $FRONTEND_PID_NUM)${NC}"
    fi

    # 清理PID文件
    rm -f "$FRONTEND_PID"
    echo -e "${GREEN}✓ PID文件已清理${NC}"
fi

# 方法2: 通过端口号停止（确保彻底清理）
FRONTEND_PORT_PID=$(lsof -ti:$FRONTEND_PORT 2>/dev/null || echo "")
if [ -n "$FRONTEND_PORT_PID" ]; then
    echo -e "${YELLOW}⚠ 发现端口 $FRONTEND_PORT 仍被占用 (PID: $FRONTEND_PORT_PID)，正在清理...${NC}"
    kill -9 $FRONTEND_PORT_PID 2>/dev/null || true
    sleep 1
    echo -e "${GREEN}✓ 已强制停止占用端口的进程${NC}"
fi

# 最终验证端口释放
FRONTEND_CHECK=$(lsof -ti:$FRONTEND_PORT 2>/dev/null || echo "")
if [ -z "$FRONTEND_CHECK" ]; then
    echo -e "${GREEN}✓ 前端端口 $FRONTEND_PORT 已释放${NC}"
else
    echo -e "${RED}✗ 前端端口 $FRONTEND_PORT 仍被占用，请手动处理: kill -9 $FRONTEND_CHECK${NC}"
fi

echo ""

# ============================================
# 清理僵尸进程
# ============================================
echo -e "${YELLOW}清理僵尸进程...${NC}"

# 查找并停止所有 node 进程（前端相关）
NODE_PIDS=$(pgrep -f "vite.*port=$FRONTEND_PORT" 2>/dev/null || echo "")
if [ -n "$NODE_PIDS" ]; then
    echo -e "${YELLOW}发现残留 Vite 进程，正在清理...${NC}"
    for pid in $NODE_PIDS; do
        if ps -p $pid > /dev/null 2>&1; then
            kill $pid 2>/dev/null || true
        fi
    done
    echo -e "${GREEN}✓ Vite 进程已清理${NC}"
fi

# 查找并停止所有 Python main.py 进程（后端相关）
PYTHON_PIDS=$(pgrep -f "python.*src/main.py" 2>/dev/null || echo "")
if [ -n "$PYTHON_PIDS" ]; then
    echo -e "${YELLOW}发现残留 Python 进程，正在清理...${NC}"
    for pid in $PYTHON_PIDS; do
        if ps -p $pid > /dev/null 2>&1; then
            kill $pid 2>/dev/null || true
        fi
    done
    echo -e "${GREEN}✓ Python 进程已清理${NC}"
fi

echo ""

# ============================================
# 停止完成
# ============================================
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}   ✓ 停止完成${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 最终端口状态验证
BACKEND_STATUS=$(lsof -ti:$BACKEND_PORT 2>/dev/null || echo "")
FRONTEND_STATUS=$(lsof -ti:$FRONTEND_PORT 2>/dev/null || echo "")

if [ -z "$BACKEND_STATUS" ] && [ -z "$FRONTEND_STATUS" ]; then
    echo -e "${GREEN}✓ 所有服务已完全停止${NC}"
    echo -e "${GREEN}  端口 $BACKEND_PORT (后端): 未被占用${NC}"
    echo -e "${GREEN}  端口 $FRONTEND_PORT (前端): 未被占用${NC}"
else
    if [ -n "$BACKEND_STATUS" ]; then
        echo -e "${RED}⚠ 端口 $BACKEND_PORT 仍被占用 (PID: $BACKEND_STATUS)${NC}"
        echo -e "${YELLOW}  请手动停止: kill -9 $BACKEND_STATUS${NC}"
    fi
    if [ -n "$FRONTEND_STATUS" ]; then
        echo -e "${RED}⚠ 端口 $FRONTEND_PORT 仍被占用 (PID: $FRONTEND_STATUS)${NC}"
        echo -e "${YELLOW}  请手动停止: kill -9 $FRONTEND_STATUS${NC}"
    fi
fi

echo ""
echo -e "${YELLOW}重新启动:${NC}"
echo -e "${GREEN}  ./scripts/start.sh${NC}"
echo ""