#!/bin/bash
# 前端部署脚本 - 构建并上传 dist 到服务器

set -e

echo "=========================================="
echo "  前端部署脚本"
echo "=========================================="

# 1. 本地构建前端
echo "[1/4] 本地构建前端..."
cd web-front
npm install --legacy-peer-deps
npm run build
cd ..

# 2. 创建临时部署目录
echo "[2/4] 准备部署文件..."
mkdir -p /tmp/monitor-dog-dist
cp -r web-front/dist/* /tmp/monitor-dog-dist/
cp web-front/nginx.conf /tmp/monitor-dog-dist/

# 3. 上传到服务器
echo "[3/4] 上传到服务器..."
scp -r /tmp/monitor-dog-dist/* vetur:/usr/local/monitorDog/dist/

# 4. 在服务器上构建并启动前端容器
echo "[4/4] 在服务器上构建并启动前端..."
ssh vetur "
cd /usr/local/monitorDog
docker build -f Dockerfile.frontend -t monitordog-frontend .
docker stop monitor-dog-frontend 2>/dev/null || true
docker rm monitor-dog-frontend 2>/dev/null || true
docker run -d --name monitor-dog-frontend -p 80:80 --network monitor-dog-network monitordog-frontend
"

# 清理临时文件
rm -rf /tmp/monitor-dog-dist

echo ""
echo "=========================================="
echo "  前端部署完成!"
echo "=========================================="
echo "访问地址：http://服务器 IP"
