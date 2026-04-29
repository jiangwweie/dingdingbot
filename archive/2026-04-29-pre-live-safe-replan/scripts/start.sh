#!/bin/bash
# 盯盘狗 - 前后端统一启动脚本
# 功能：检查依赖、自动清理端口、启动前后端、管理PID、输出日志

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 项目根目录
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# 日志和PID目录
LOG_DIR="$PROJECT_ROOT/logs"
PID_DIR="$PROJECT_ROOT/.pids"

# 日志文件
BACKEND_LOG="$LOG_DIR/backend.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"

# PID文件
BACKEND_PID="$PID_DIR/backend.pid"
FRONTEND_PID="$PID_DIR/frontend.pid"

# 固定端口配置
BACKEND_PORT=8000
FRONTEND_PORT=3000

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}   盯盘狗 - 启动脚本${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# ============================================
# 1. 检查目录
# ============================================
echo -e "${YELLOW}[1/7] 检查目录...${NC}"
mkdir -p "$LOG_DIR" "$PID_DIR"
echo -e "${GREEN}✓ 目录检查完成${NC}"
echo ""

# ============================================
# 2. 检查Python环境
# ============================================
echo -e "${YELLOW}[2/7] 检查Python环境...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}✗ Python3 未安装${NC}"
    echo -e "${YELLOW}请安装 Python 3.11+: brew install python@3.11${NC}"
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo -e "${GREEN}✓ Python 版本: $PYTHON_VERSION${NC}"
echo ""

# ============================================
# 3. 检查npm环境
# ============================================
echo -e "${YELLOW}[3/7] 检查npm环境...${NC}"
if ! command -v npm &> /dev/null; then
    echo -e "${RED}✗ npm 未安装${NC}"
    echo -e "${YELLOW}请安装 Node.js: brew install node${NC}"
    exit 1
fi

NPM_VERSION=$(npm --version 2>&1)
NODE_VERSION=$(node --version 2>&1)
echo -e "${GREEN}✓ Node 版本: $NODE_VERSION${NC}"
echo -e "${GREEN}✓ npm 版本: $NPM_VERSION${NC}"
echo ""

# ============================================
# 4. 自动清理端口（关键改进）
# ============================================
echo -e "${YELLOW}[4/7] 检查并清理端口...${NC}"

# 清理后端端口
BACKEND_PORT_PID=$(lsof -ti:$BACKEND_PORT 2>/dev/null || echo "")
if [ -n "$BACKEND_PORT_PID" ]; then
    echo -e "${YELLOW}⚠ 端口 $BACKEND_PORT 已被占用 (PID: $BACKEND_PORT_PID)，正在自动停止...${NC}"
    kill -9 $BACKEND_PORT_PID 2>/dev/null || true
    sleep 1
    echo -e "${GREEN}✓ 已清理端口 $BACKEND_PORT${NC}"
else
    echo -e "${GREEN}✓ 后端端口 $BACKEND_PORT 可用${NC}"
fi

# 清理前端端口
FRONTEND_PORT_PID=$(lsof -ti:$FRONTEND_PORT 2>/dev/null || echo "")
if [ -n "$FRONTEND_PORT_PID" ]; then
    echo -e "${YELLOW}⚠ 端口 $FRONTEND_PORT 已被占用 (PID: $FRONTEND_PORT_PID)，正在自动停止...${NC}"
    kill -9 $FRONTEND_PORT_PID 2>/dev/null || true
    sleep 1
    echo -e "${GREEN}✓ 已清理端口 $FRONTEND_PORT${NC}"
else
    echo -e "${GREEN}✓ 前端端口 $FRONTEND_PORT 可用${NC}"
fi

# 清理旧的PID文件
rm -f "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true

echo ""

# ============================================
# 5. 检查Python依赖
# ============================================
echo -e "${YELLOW}[5/7] 检查Python依赖...${NC}"
if [ ! -f "requirements.txt" ]; then
    echo -e "${RED}✗ requirements.txt 不存在${NC}"
    exit 1
fi

# 检查虚拟环境（可选）
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}⚠ 虚拟环境未创建${NC}"
    echo -e "${YELLOW}建议创建: python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt${NC}"
    echo ""

    # 检查依赖是否已安装
    MISSING_DEPS=$(python3 -c "
import sys
import pkg_resources

requirements = pkg_resources.parse_requirements(open('requirements.txt').readlines())
missing = [str(req) for req in requirements if not pkg_resources.working_set.find(pkg_resources.Requirement.parse(str(req)))]

if missing:
    print(' '.join(missing))
" 2>&1 || echo "")

    if [ -n "$MISSING_DEPS" ]; then
        echo -e "${RED}✗ Python依赖缺失: $MISSING_DEPS${NC}"
        echo -e "${YELLOW}请安装依赖: pip3 install -r requirements.txt${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}✓ 虚拟环境已创建${NC}"
fi

echo -e "${GREEN}✓ Python依赖检查完成${NC}"
echo ""

# ============================================
# 6. 前端已迁移
# ============================================
echo -e "${YELLOW}[6/7] 前端已迁移至 gemimi-web-front/，不再自动启动${NC}"
echo ""

# ============================================
# 7. 启动前后端
# ============================================
echo -e "${YELLOW}[7/7] 启动前后端...${NC}"
echo ""

# 清空日志文件
> "$BACKEND_LOG"
> "$FRONTEND_LOG"

# 启动后端
echo -e "${BLUE}启动后端...${NC}"
cd "$PROJECT_ROOT"

# 设置 PYTHONPATH（确保能找到 src 模块）
export PYTHONPATH="$PROJECT_ROOT"

# 检查是否在虚拟环境中
if [ -d "venv" ]; then
    source venv/bin/activate
    nohup python3 src/main.py > "$BACKEND_LOG" 2>&1 &
else
    nohup python3 src/main.py > "$BACKEND_LOG" 2>&1 &
fi

BACKEND_PID_NUM=$!
echo $BACKEND_PID_NUM > "$BACKEND_PID"

echo -e "${GREEN}✓ 后端已启动 (PID: $BACKEND_PID_NUM)${NC}"
echo -e "${GREEN}  日志: $BACKEND_LOG${NC}"
echo -e "${GREEN}  端口: $BACKEND_PORT${NC}"
echo ""

# 启动前端（已迁移至 gemimi-web-front/，需手动启动）
echo -e "${BLUE}前端已迁移至 gemimi-web-front/，需手动启动${NC}"
echo -e "${GREEN}  cd gemimi-web-front && npm run dev${NC}"
echo ""

cd "$PROJECT_ROOT"

# ============================================
# 启动完成
# ============================================
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}   ✓ 启动完成${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${YELLOW}访问地址:${NC}"
echo -e "${GREEN}  后端: http://localhost:$BACKEND_PORT${NC}"
echo -e "${GREEN}  API文档: http://localhost:$BACKEND_PORT/docs${NC}"
echo -e "${GREEN}  前端: cd gemimi-web-front && npm run dev${NC}"
echo ""
echo -e "${YELLOW}停止服务:${NC}"
echo -e "${GREEN}  ./scripts/stop.sh${NC}"
echo ""
echo -e "${YELLOW}查看日志:${NC}"
echo -e "${GREEN}  tail -f $BACKEND_LOG${NC}"
echo -e "${GREEN}  tail -f $FRONTEND_LOG${NC}"
echo ""

# 等待5秒，检查进程是否正常
sleep 5

# 检查后端进程
if ! ps -p $BACKEND_PID_NUM > /dev/null 2>&1; then
    echo -e "${RED}✗ 后端启动失败，请检查日志:${NC}"
    echo -e "${YELLOW}  tail -n 50 $BACKEND_LOG${NC}"
    exit 1
fi

echo -e "${GREEN}✓ 后端服务运行正常${NC}"
echo ""