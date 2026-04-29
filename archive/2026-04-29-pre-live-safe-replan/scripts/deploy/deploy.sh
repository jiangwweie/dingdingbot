#!/bin/bash
# 盯盘狗 🐶 Docker 部署脚本
# 用于在服务器上清理、构建和运行 Docker 容器

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
PROJECT_NAME="monitor-dog"
DEPLOY_DIR="/usr/local/monitorDog"

echo "=========================================="
echo "  盯盘狗 🐶 Docker 部署脚本"
echo "=========================================="
echo ""

# Function to print colored messages
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    print_error "请使用 sudo 运行此脚本"
    exit 1
fi

# Create deployment directory
print_info "创建部署目录：$DEPLOY_DIR"
mkdir -p $DEPLOY_DIR
cd $DEPLOY_DIR

# Pull latest code from git
print_info "从 Git 仓库拉取最新代码..."
if [ -d ".git" ]; then
    git pull origin main
else
    print_warning "目录不是 Git 仓库，请确认是否已克隆仓库"
    read -p "是否现在克隆仓库？(y/n): " clone
    if [ "$clone" = "y" ]; then
        read -p "输入 Git 仓库地址：" repo_url
        git clone $repo_url .
    fi
fi

# Stop existing containers
print_info "停止现有容器..."
docker compose down || print_warning "没有运行中的容器"

# Remove existing containers
print_info "删除现有容器..."
docker rm -f ${PROJECT_NAME}-backend 2>/dev/null || true
docker rm -f ${PROJECT_NAME}-frontend 2>/dev/null || true

# Remove existing images
print_info "删除现有镜像..."
docker rmi -f ${PROJECT_NAME}-backend 2>/dev/null || true
docker rmi -f ${PROJECT_NAME}-frontend 2>/dev/null || true

# Create necessary directories
print_info "创建数据目录..."
mkdir -p ./config ./data ./logs

# Copy config files if not exist
if [ ! -f "./config/user.yaml" ]; then
    print_warning "配置文件不存在，请手动配置 config/user.yaml"
    print_info "从示例文件复制..."
    if [ -f "./config/user.yaml.example" ]; then
        cp ./config/user.yaml.example ./config/user.yaml
    fi
fi

# Build new images
print_info "构建 Docker 镜像..."
docker compose build --no-cache

# Start containers
print_info "启动容器..."
docker compose up -d

# Wait for services to start
print_info "等待服务启动..."
sleep 10

# Check container status
print_info "检查容器状态..."
docker compose ps

# Check logs
echo ""
print_info "最近日志:"
docker compose logs --tail=20

echo ""
echo "=========================================="
echo "  🎉 部署完成!"
echo "=========================================="
echo ""
echo "访问地址:"
echo "  前端：http://$(hostname -I | awk '{print $1}')"
echo "  API:  http://$(hostname -I | awk '{print $1}'):8000"
echo ""
echo "常用命令:"
echo "  查看状态：docker compose ps"
echo "  查看日志：docker compose logs -f"
echo "  重启服务：docker compose restart"
echo "  停止服务：docker compose down"
echo ""
