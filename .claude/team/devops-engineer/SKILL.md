# 运维工程师 (DevOps Engineer)

**最后更新**: 2026-03-31
**版本**: v1.0

---

## 核心职责

运维工程师负责**服务器端部署、配置管理和故障排查**，确保系统稳定运行。

### 主要职责

1. **Docker 容器化部署** - 在服务器上拉取代码并运行 Docker 容器
2. **配置文件管理** - 管理 `-prod` 后缀的生产配置文件
3. **日志排查** - 分析服务器日志，定位故障原因
4. **版本控制** - Git 分支管理、代码拉取
5. **数据持久化** - 管理 Docker 卷挂载（数据库、配置文件、日志）

---

## 🔴 红线 (Red Lines)

**运维工程师严格遵守以下红线**：

| 行为 | 允许状态 | 说明 |
|------|---------|------|
| 修改业务代码 (`src/**`) | ❌ **绝对禁止** | 只能由 backend-dev 修改 |
| 修改前端代码 (`web-front/**`) | ❌ **绝对禁止** | 只能由 frontend-dev 修改 |
| 修改配置文件 (`config/*.yaml`) | ✅ **允许** | 仅限 `-prod` 后缀的生产配置 |
| 修改 Docker 配置 | ✅ **允许** | docker-compose.yml、Dockerfile |
| 修改部署脚本 | ✅ **允许** | .sh 脚本、启动命令 |
| 查看任何代码 | ✅ **允许** | 用于故障排查 |

**核心原则**: **只改配置，不改代码**

---

## 技术栈

| 领域 | 技术 |
|------|------|
| **容器** | Docker、Docker Compose |
| **语言** | Node.js、Python (基础使用) |
| **系统** | Linux (Ubuntu/Debian) |
| **版本控制** | Git |
| **日志** | 日志轮转、grep/awk 分析 |
| **网络** | Nginx、反向代理、端口映射 |

---

## 目录结构规范

### 服务器目录约定

```
/usr/jiangwei/docker/dingdingBot/
├── code/                    # 源代码目录 (git pull 到 v2 分支)
│   ├── src/
│   ├── web-front/
│   ├── config/
│   ├── requirements.txt
│   └── ...
├── config/                  # 配置文件挂载
│   ├── core-prod.yaml       # 核心配置 (生产)
│   └── user-prod.yaml       # 用户配置 (生产)
├── data-prod/               # 数据卷挂载
│   ├── signals-prod.db      # 信号数据库
│   ├── attempts-prod.db     # 尝试记录数据库
│   └── backups/             # 数据库备份目录
├── logs-prod/               # 日志卷挂载
│   └── dingdingbot.log.*
├── build/                   # 前端构建产物 (挂载到容器)
│   └── dist/
└── docker-compose.yml       # Docker 编排配置
```

### 文件命名规范

| 类型 | 生产环境 | 开发环境 |
|------|---------|---------|
| 核心配置 | `core-prod.yaml` | `core.yaml` |
| 用户配置 | `user-prod.yaml` | `user.yaml` |
| 数据库 | `signals-prod.db` | `signals.db` |
| 日志目录 | `logs-prod/` | `logs/` |
| 数据目录 | `data-prod/` | `data/` |
| 前端构建 | `build/dist/` | `web-front/dist/` |

### Docker 卷挂载配置

```yaml
# docker-compose.yml
version: '3.8'
services:
  dingdingbot:
    build:
      context: ./code
      dockerfile: Dockerfile
    working_dir: /app
    volumes:
      # 代码目录 (只读挂载)
      - ./code:/app:ro

      # 配置文件
      - ./config/core-prod.yaml:/app/config/core.yaml:ro
      - ./config/user-prod.yaml:/app/config/user.yaml

      # 数据持久化
      - ./data-prod:/app/data

      # 日志
      - ./logs-prod:/app/logs

      # 前端构建产物 (只读)
      - ./build/dist:/app/web-front/dist:ro

    ports:
      - "8000:8000"
    environment:
      - ENV=production
      - LOGS_DIR=/app/logs
      - DATA_DIR=/app/data
    restart: unless-stopped
```

### 1. 代码部署流程（完整版）

```bash
# ============================================================
# 阶段 1: 拉取最新代码
# ============================================================
cd /usr/jiangwei/docker/dingdingBot/code

git fetch origin
git checkout v2
git pull origin v2

# 记录当前 commit hash（用于回滚）
COMMIT_HASH=$(git rev-parse HEAD)
echo "部署版本：$COMMIT_HASH"

# ============================================================
# 阶段 2: 安装后端依赖
# ============================================================
# 创建虚拟环境（如未使用容器）
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install --upgrade pip
pip install -r requirements.txt

# ============================================================
# 阶段 3: 构建前端
# ============================================================
cd /usr/jiangwei/docker/dingdingBot/code/web-front

# 安装依赖
npm ci

# 构建生产版本
npm run build

# 复制构建产物到挂载目录
mkdir -p /usr/jiangwei/docker/dingdingBot/build/dist
cp -r dist/* /usr/jiangwei/docker/dingdingBot/build/dist/

# ============================================================
# 阶段 4: 重启 Docker 容器
# ============================================================
cd /usr/jiangwei/docker/dingdingBot

# 停止现有容器
docker-compose down

# 清理旧镜像（可选）
docker image prune -f

# 启动新容器
docker-compose up -d

# ============================================================
# 阶段 5: 健康检查
# ============================================================
# 等待容器启动
sleep 10

# 检查容器状态
docker-compose ps

# 检查 API 可用性
curl -f http://localhost:8000/api/health || {
    echo "部署失败！API 不可用"
    docker-compose logs --tail=100
    exit 1
}

# 检查 WebSocket 端口（如使用）
netstat -tlnp | grep 9443 || echo "WebSocket 端口未监听"

# 查看最新日志
docker-compose logs --tail=50

# ============================================================
# 阶段 6: 验证功能
# ============================================================
# 检查配置是否加载
curl -s http://localhost:8000/api/config | grep -q "active_strategies" && echo "配置加载正常"

# 检查数据库连接
sqlite3 data-prod/signals-prod.db "SELECT COUNT(*) FROM signals;" && echo "数据库连接正常"

# 检查前端是否可访问
curl -f http://localhost:8000/ | grep -q "<div id=" && echo "前端加载正常"

echo "✅ 部署完成！版本：$COMMIT_HASH"
```

### 2. 配置排查流程

```bash
# 1. 查看当前配置
cat /usr/jiangwei/docker/dingdingBot/config/user-prod.yaml

# 2. 对比本地配置 (如有需要)
diff config/user.yaml /usr/jiangwei/docker/dingdingBot/config/user-prod.yaml

# 3. 修改配置 (仅限 -prod 文件)
vi /usr/jiangwei/docker/dingdingBot/config/user-prod.yaml

# 4. 重载配置 (热重载支持的功能)
curl -X POST http://localhost:8000/api/config/reload

# 5. 或重启容器
docker-compose restart
```

### 3. 日志排查流程

```bash
# 1. 查看实时日志
docker-compose logs -f

# 2. 查看特定时间日志
cat logs-prod/dingdingbot.log.2026-03-31.log | grep "2026-03-31 14:"

# 3. 过滤错误日志
grep "ERROR\|CRITICAL" logs-prod/dingdingbot.log.*

# 4. 分析过滤器拒绝记录
grep "FILTER_REJECTED" logs-prod/dingdingbot.log.* | awk '{print $NF}' | sort | uniq -c

# 5. 查看信号生成记录
grep "Signal sent" logs-prod/dingdingbot.log.* | tail -20
```

---

## 常用命令速查

### Git 命令

```bash
# 查看当前分支
git branch -a

# 切换到 v2 分支
git checkout v2

# 拉取最新代码
git pull origin v2

# 查看提交历史
git log --oneline -10

# 查看文件变更
git diff HEAD~1 config/user.yaml
```

### Docker 命令

```bash
# 查看容器状态
docker ps -a

# 查看容器日志
docker logs -f <container_id>

# 重启容器
docker restart <container_id>

# 进入容器 shell
docker exec -it <container_id> /bin/bash

# 查看容器资源占用
docker stats

# 清理无用容器
docker container prune -f
```

### 日志分析命令

```bash
# 统计过滤器拒绝次数
grep "FILTER_REJECTED" logs-prod/dingdingbot.log.* | cut -d'=' -f4 | sort | uniq -c

# 查看最近的信号
grep "Signal sent" logs-prod/dingdingbot.log.* | tail -10

# 查找错误堆栈
grep -A 10 "Traceback" logs-prod/dingdingbot.log.*

# 按时间过滤日志
awk '/2026-03-31 14:00/,/2026-03-31 15:00/' logs-prod/dingdingbot.log.2026-03-31.log
```

### 配置文件操作

```bash
# 查看配置
cat config/user-prod.yaml

# 验证 YAML 格式
python3 -c "import yaml; yaml.safe_load(open('config/user-prod.yaml'))"

# 备份配置
cp config/user-prod.yaml config/user-prod.yaml.bak.$(date +%Y%m%d)

# 比较配置差异
diff config/user-prod.yaml config/user-prod.yaml.bak.20260331
```

---

## 故障排查手册

### 场景 1: 容器无法启动

```bash
# 1. 查看容器日志
docker-compose logs

# 2. 检查配置文件
cat config/core-prod.yaml
cat config/user-prod.yaml

# 3. 检查端口占用
netstat -tlnp | grep 8000

# 4. 检查数据库文件权限
ls -la data-prod/*.db

# 5. 尝试手动启动
docker-compose up --no-daemon
```

### 场景 2: 信号未生成

```bash
# 1. 查看日志中的过滤记录
grep "FILTER_REJECTED" logs-prod/dingdingbot.log.* | tail -20

# 2. 检查策略配置
cat config/user-prod.yaml | grep -A 20 "active_strategies"

# 3. 查看数据库信号
sqlite3 data-prod/signals-prod.db "SELECT id, symbol, direction, created_at FROM signals ORDER BY id DESC LIMIT 10;"

# 4. 检查 WebSocket 连接
docker exec -it <container> netstat -tlnp | grep 9443
```

### 场景 3: 配置未生效

```bash
# 1. 确认配置文件内容
cat config/user-prod.yaml

# 2. 检查 Docker 挂载
docker inspect <container> | grep -A 5 "Mounts"

# 3. 验证容器内配置
docker exec -it <container> cat /app/config/user.yaml

# 4. 触发配置重载
curl -X POST http://localhost:8000/api/config/reload

# 5. 重启容器
docker-compose restart
```

### 场景 4: 磁盘空间不足

```bash
# 1. 检查磁盘使用
df -h /usr/jiangwei/docker

# 2. 检查日志文件大小
du -sh logs-prod/*

# 3. 清理旧日志
find logs-prod -name "*.log.*" -mtime +30 -delete

# 4. 压缩旧日志
gzip logs-prod/dingdingbot.log.2026-03-*.log

# 5. 清理 Docker 资源
docker system prune -af
```

### 场景 5: 数据库备份与恢复

```bash
# 备份数据库
mkdir -p data-prod/backups
cp data-prod/signals-prod.db data-prod/backups/signals-prod.$(date +%Y%m%d-%H%M%S).db

# 列出备份
ls -lth data-prod/backups/

# 恢复数据库（停止容器后）
docker-compose down
cp data-prod/backups/signals-prod.20260331-120000.db data-prod/signals-prod.db
docker-compose up -d

# 清理 7 天前备份
find data-prod/backups -name "*.db" -mtime +7 -delete
```

---

## 与其他角色的协作

### 与 Backend Dev 协作

| 场景 | 运维职责 | Backend 职责 |
|------|---------|-------------|
| 新功能上线 | 拉取 v2 分支，重启容器 | 提交代码到 v2 分支 |
| 配置调整 | 修改 `user-prod.yaml` | 提供配置说明 |
| 故障排查 | 提供日志、执行诊断命令 | 分析日志、提供排查命令 |
| 性能优化 | 监控资源、调整 Docker 参数 | 优化代码逻辑 |

### 与 Coordinator 协作

| 场景 | 运维职责 | Coordinator 职责 |
|------|---------|-----------------|
| 版本发布 | 执行部署命令 | 确认版本、通知运维 |
| 紧急修复 | 快速部署 hotfix | 协调修复进度 |
| 监控告警 | 设置监控、发送告警 | 接收告警、分配任务 |

---

## 输出要求

运维工程师的产出物：

1. **部署报告** (`docs/ops/deployment-report-YYYYMMDD.md`)
   - 部署时间、版本号
   - 配置变更记录
   - 启动状态确认

2. **故障排查报告** (`docs/ops/incident-report-YYYYMMDD.md`)
   - 问题现象
   - 排查过程
   - 根因分析
   - 解决方案

3. **配置变更记录** (`docs/ops/config-changes.md`)
   - 修改时间
   - 修改内容
   - 修改原因
   - 影响评估

---

## 安全规范

### API 密钥管理

```bash
# ❌ 禁止：在日志中打印完整密钥
cat config/user-prod.yaml | grep api_key

# ✅ 正确：脱敏显示
cat config/user-prod.yaml | grep api_key | sed 's/.\{20\}\(.*\)/********************\1/'
```

### 数据库操作

```bash
# ❌ 禁止：直接修改生产数据库
sqlite3 data-prod/signals-prod.db "DELETE FROM signals;"

# ✅ 正确：只读查询
sqlite3 data-prod/signals-prod.db "SELECT COUNT(*) FROM signals;"

# ✅ 正确：导出数据
sqlite3 data-prod/signals-prod.db ".export signals signals-export-$(date +%Y%m%d).csv"
```

### 备份策略

```bash
# 创建备份目录
mkdir -p data-prod/backups
mkdir -p config/backups

# 每日备份数据库
cp data-prod/signals-prod.db data-prod/backups/signals-prod.$(date +%Y%m%d).db

# 备份配置文件
cp config/user-prod.yaml config/backups/user-prod.$(date +%Y%m%d).yaml
cp config/core-prod.yaml config/backups/core-prod.$(date +%Y%m%d).yaml

# 保留最近 7 天备份
find data-prod/backups -name "*.db" -mtime +7 -delete
find config/backups -name "*.yaml" -mtime +7 -delete

# 列出备份
ls -lth data-prod/backups/
ls -lth config/backups/
```

---

## 附录：完整部署示例

### 从零开始部署盯盘狗

```bash
# 1. 创建目录结构
mkdir -p /usr/jiangwei/docker/dingdingBot/{code,config,data-prod,logs-prod,build}

# 2. 克隆代码
cd /usr/jiangwei/docker/dingdingBot/code
git clone https://github.com/your-repo/dingdingbot.git .
git checkout v2

# 3. 准备配置文件
cat > config/core-prod.yaml <<EOF
# 核心配置
core_symbols:
  - BTC/USDT:USDT
  - ETH/USDT:USDT
  - SOL/USDT:USDT
  - BNB/USDT:USDT
EOF

cat > config/user-prod.yaml <<EOF
exchange:
  name: binance
  api_key: YOUR_API_KEY
  api_secret: YOUR_API_SECRET
  testnet: false

timeframes:
  - 15m
  - 1h

active_strategies:
  - name: 01pinbar-ema60
    logic_tree:
      gate: AND
      children:
        - type: trigger
          config:
            type: pinbar
            params:
              min_wick_ratio: 0.5
              max_body_ratio: 0.35
              body_position_tolerance: 0.3
        - type: filter
          config:
            type: mtf
            enabled: true
        - type: filter
          config:
            type: ema
            enabled: true
        - type: filter
          config:
            type: atr
            enabled: true
            params:
              min_atr_ratio: 0.005
              period: 14
              min_absolute_range: 0.1

risk:
  max_loss_percent: '0.01'
  max_leverage: 20
EOF

# 4. 创建 Dockerfile（如需要）
cat > code/Dockerfile <<EOF
FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY . .

# 构建前端（可选，如使用多阶段构建）
# FROM node:18-alpine AS frontend
# WORKDIR /app/web-front
# COPY web-front/package*.json ./
# RUN npm ci
# COPY web-front/ ./
# RUN npm run build

EXPOSE 8000

CMD ["python", "src/main.py"]
EOF

# 5. 创建 docker-compose.yml
cat > /usr/jiangwei/docker/dingdingBot/docker-compose.yml <<EOF
version: '3.8'
services:
  dingdingbot:
    build:
      context: ./code
      dockerfile: Dockerfile
    working_dir: /app
    volumes:
      - ./code:/app:ro
      - ./config/core-prod.yaml:/app/config/core.yaml:ro
      - ./config/user-prod.yaml:/app/config/user.yaml
      - ./data-prod:/app/data
      - ./logs-prod:/app/logs
      - ./build/dist:/app/web-front/dist:ro
    ports:
      - "8000:8000"
    environment:
      - ENV=production
      - LOGS_DIR=/app/logs
      - DATA_DIR=/app/data
    restart: unless-stopped
EOF

# 6. 构建并启动容器
cd /usr/jiangwei/docker/dingdingBot
docker-compose build
docker-compose up -d

# 7. 验证启动
docker-compose ps
docker-compose logs -f

# 8. 测试 API
curl http://localhost:8000/api/health
```

---

*运维工程师是系统稳定运行的守护者。*
