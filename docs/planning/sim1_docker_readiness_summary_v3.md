# Sim-1 Docker 部署就绪度审查 - 执行摘要（修订版 v3）

**审查日期**: 2026-04-25
**Verdict**: **Not Ready** (未就绪)
**硬约束**:
1. YAML 已彻底废弃，不再作为启动配置来源
2. 前端处于重构期（gemimi-web-front 是重构主线，web-front 是旧前端）
3. 数据库处于 SQLite + PostgreSQL 共存切换期（非全量 PG 迁移）

---

## 当前阶段边界

**前端状态**:
- **旧前端**: `web-front/`（当前 Docker 服务的前端）
- **重构主线**: `gemimi-web-front/`（未在 Docker 中使用）
- **Dockerfile.frontend**: 服务 `web-front/`（`docker/Dockerfile.frontend:11`）

**数据库状态**:
- **execution_intent**: PostgreSQL 强制（Sim-1 要求）
- **orders/positions**: SQLite 默认（可配置为 PG）
- **signals/config**: SQLite（旧链路兼容）
- **v3_dev.db**: 196MB（主数据库）

**Sim-1 主线优先级**:
- **P0**: 后端模拟盘观察路径（backend + readonly observation）
- **P1**: 前端只读观察面（可选，可降级）
- **P2**: 前端切换到 gemimi-web-front（后续重构）

---

## 核心结论（修订版）

当前仓库**无法**直接 `docker compose up` 成功，存在 **5 个 P0 启动期阻塞项**（backend 相关）。前端问题降级为 P1。修复工作量约 1-2 小时。

**最大风险**: 容器读取错误挂载目录 + 拿不到环境变量，导致 runtime profile not found 和 FatalStartupError。

**重要纠正**（相比 v2 版本）:
- ❌ **P0-NEW-1**: bind mount 路径错误（`./config` → 应为 `../config`）
- ❌ **P0-NEW-2**: dockerfile 路径未同步修改（context 改后 dockerfile 路径也需改）
- ❌ **P0-NEW-3**: 环境变量未注入容器（宿主机 .env 不等于容器内可读）
- ⚠️ **P1-NEW**: 前端仍服务旧前端（web-front），但非 Sim-1 阻塞项

---

## P0 阻塞项清单（修订版）

| ID | 问题 | 文件:行号 | 影响 |
|----|------|-----------|------|
| **P0-1** | bind mount 路径错误 | `docker/docker-compose.yml:14-19` | 容器挂载到空目录，runtime profile not found |
| **P0-2** | context 改后 dockerfile 路径未同步 | `docker/docker-compose.yml:7-8` | `docker build` 找不到 Dockerfile |
| **P0-3** | 健康检查路径错误 | `docker/docker-compose.yml:30` | 容器健康检查失败 |
| **P0-4** | 环境变量未注入容器 | `docker/docker-compose.yml:20-26` | FatalStartupError("F-003") |
| **P0-5** | runtime profile 未初始化 | `scripts/seed_sim1_runtime_profile.py` | ValueError("runtime profile not found") |

---

## P0 阻塞项详细证据

### P0-1: bind mount 路径错误

```yaml
# docker/docker-compose.yml:14-19
volumes:
  - ./config:/app/config:ro  # ❌ 相对 docker/ 目录，应为 ../config
  - ./data:/app/data         # ❌ 相对 docker/ 目录，应为 ../data
  - ./logs:/app/logs         # ❌ 相对 docker/ 目录，应为 ../logs
```

**证据**:
```bash
# docker/ 目录下不存在 config/data/logs
$ ls -la docker/ | grep -E "config|data|logs"
# 无输出

# 仓库根目录下存在 config/data/logs
$ ls -la . | grep -E "config|data|logs"
drwxr-xr-x    8 jiangwei  staff    256  4月 23 20:55 config
drwxr-xr-x   22 jiangwei  staff    704  4月 24 09:36 data
drwxr-xr-x   15 jiangwei  staff    480  4月 24 16:29 logs
```

**修复**:
```yaml
volumes:
  - ../config:/app/config:ro  # ✅ 相对仓库根目录
  - ../data:/app/data         # ✅ 相对仓库根目录
  - ../logs:/app/logs         # ✅ 相对仓库根目录
```

### P0-2: dockerfile 路径未同步

```yaml
# docker/docker-compose.yml:7-8
build:
  context: .              # ❌ 应为 ..
  dockerfile: Dockerfile.backend  # ❌ context 改后应为 docker/Dockerfile.backend
```

**修复**:
```yaml
build:
  context: ..                      # ✅ 指向仓库根目录
  dockerfile: docker/Dockerfile.backend  # ✅ 相对仓库根目录
```

### P0-4: 环境变量未注入容器

```yaml
# docker/docker-compose.yml:20-26
environment:
  - TZ=Asia/Shanghai
  - PYTHONPATH=/app
  - DATABASE_URL=sqlite+aiosqlite:///./data/v3_dev.db
  - SQL_ECHO=false
  # ❌ 缺少 PG_DATABASE_URL、EXCHANGE_API_KEY、EXCHANGE_API_SECRET、FEISHU_WEBHOOK_URL、RUNTIME_PROFILE、CORE_EXECUTION_INTENT_BACKEND
```

**修复方案 A: 使用 env_file（推荐）**
```yaml
services:
  backend:
    env_file:
      - ../.env  # ✅ 从宿主机读取 .env 文件
```

**修复方案 B: 显式注入环境变量**
```yaml
services:
  backend:
    environment:
      - PG_DATABASE_URL=${PG_DATABASE_URL}
      - EXCHANGE_API_KEY=${EXCHANGE_API_KEY}
      - EXCHANGE_API_SECRET=${EXCHANGE_API_SECRET}
      - FEISHU_WEBHOOK_URL=${FEISHU_WEBHOOK_URL}
      - RUNTIME_PROFILE=${RUNTIME_PROFILE:-sim1_eth_runtime}
      - CORE_EXECUTION_INTENT_BACKEND=${CORE_EXECUTION_INTENT_BACKEND:-postgres}
```

---

## YAML 残留审查结果

### 结论: ✅ **YAML 已不参与启动流程**

**证据**:
```python
# src/application/config_manager.py:908
"""Build default core configuration (hardcoded defaults).
No YAML file fallback — DB or defaults only.
"""
```

### 残留清单

| 残留类型 | 数量 | 是否影响 Sim-1 | 建议动作 |
|----------|------|----------------|----------|
| 启动链路残留 | **0 个** | ❌ 不影响 | N/A |
| 接口残留 | **3 个** | ❌ 不影响 | 保留（备份工具） |
| 文档残留 | **40+ 个** | ❌ 不影响 | 添加废弃说明 |
| 注释残留 | **4 个** | ❌ 不影响 | 修改文案 |

**详细清单**: `docs/planning/yaml_deprecation_checklist.md`

---

## Sim-1 最小必需条件

### 环境变量（必须配置）

```bash
# Sim-1 强制要求
CORE_EXECUTION_INTENT_BACKEND=postgres

# PostgreSQL 连接
PG_DATABASE_URL=postgresql://user:pass@host:5432/v3_sim1

# 交易所 API（测试网）
EXCHANGE_NAME=binance
EXCHANGE_TESTNET=true
EXCHANGE_API_KEY=your_testnet_api_key
EXCHANGE_API_SECRET=your_testnet_api_secret

# 飞书告警
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx

# Runtime Profile
RUNTIME_PROFILE=sim1_eth_runtime
```

### 持久化卷（必须正确挂载）

```yaml
volumes:
  - ../config:/app/config:ro  # ✅ 相对仓库根目录
  - ../data:/app/data         # ✅ 相对仓库根目录（SQLite 数据库文件）
  - ../logs:/app/logs         # ✅ 相对仓库根目录
```

**重要**: `data/` 目录挂载仍然必需（v3_dev.db 已有 196MB 数据）。

### PostgreSQL / SQLite 共存状态

**Sim-1 强制约束**: `CORE_EXECUTION_INTENT_BACKEND=postgres`

```python
# src/application/runtime_config.py:51-54
if self.core_execution_intent_backend != "postgres":
    raise ValueError("Sim-1 requires CORE_EXECUTION_INTENT_BACKEND=postgres")
```

**数据库分工**:

| 数据类型 | 默认 Backend | Sim-1 要求 | 说明 |
|----------|--------------|------------|------|
| execution_intent | **postgres** | **强制 postgres** | Sim-1 强制要求 |
| orders | sqlite | 可选 postgres | 默认 SQLite |
| positions | sqlite | 可选 postgres | 默认 SQLite |
| signals | sqlite | 不涉及 | 旧链路兼容 |
| config | sqlite | 不涉及 | 旧链路兼容 |

**重要**: Sim-1 **不是**全量迁移到 PostgreSQL，`data/` 目录挂载仍然必需。

### Runtime Profile Seed

```bash
python scripts/seed_sim1_runtime_profile.py
```

---

## 快速修复步骤（修订版）

### 阶段 A: 先跑通 backend-only Sim-1 observation path（30 分钟）

**关键**: 只修改 backend 部分，frontend 可延后

```yaml
# docker/docker-compose.yml
services:
  backend:
    build:
      context: ..                      # ✅ 修改 1: context 路径
      dockerfile: docker/Dockerfile.backend  # ✅ 修改 2: dockerfile 路径
    volumes:
      - ../config:/app/config:ro      # ✅ 修改 3: volumes 路径
      - ../data:/app/data
      - ../logs:/app/logs
    env_file:
      - ../.env                        # ✅ 修改 4: 注入环境变量
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/health"]  # ✅ 修改 5: 健康检查路径
```

```dockerfile
# docker/Dockerfile.backend:42
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1  # ✅ 修改 6: 健康检查路径
```

**验证 backend 构建**:
```bash
docker compose -f docker/docker-compose.yml build backend
docker compose -f docker/docker-compose.yml up -d backend
curl http://localhost:8000/api/health
```

### 阶段 B: 配置环境变量（1-2 小时）

```bash
# 1. 配置 PostgreSQL
createdb -h localhost -U postgres v3_sim1

# 2. 创建 .env 文件（使用 postgresql+asyncpg:// 格式）
cat > .env <<EOF
CORE_EXECUTION_INTENT_BACKEND=postgres
PG_DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/v3_sim1
EXCHANGE_NAME=binance
EXCHANGE_TESTNET=true
EXCHANGE_API_KEY=your_key
EXCHANGE_API_SECRET=your_secret
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
RUNTIME_PROFILE=sim1_eth_runtime
EOF

# 3. Seed runtime profile（必须在仓库根目录执行）
cd /Users/jiangwei/Documents/final
python scripts/seed_sim1_runtime_profile.py
```

### 阶段 C: 再决定 frontend 接哪个目录（可延后）

**当前状态**: Dockerfile.frontend 服务旧前端 `web-front/`

**选项 A: 保持旧前端（快速启动）**
- 不修改 Dockerfile.frontend
- 前端观察面使用旧版 UI

**选项 B: 切换到重构主线（gemimi-web-front）**
- 修改 Dockerfile.frontend
- 需要先构建 gemimi-web-front

**选项 C: 暂不启动 frontend（当前推荐）**
- 只启动 backend 容器
- 通过 API 或日志观察 Sim-1 状态

**建议**: Sim-1 观察窗口优先 backend 稳定性，frontend 可暂时不启动或保持旧版。

### 阶段 D: 验证部署

```bash
# 验证配置
docker compose -f docker/docker-compose.yml config

# 构建镜像
docker compose -f docker/docker-compose.yml build

# 启动服务
docker compose -f docker/docker-compose.yml up -d

# 检查日志
docker compose -f docker/docker-compose.yml logs -f backend

# 健康检查
curl http://localhost:8000/api/health
```

---

## "必须现在修" vs "可以后续清理"

### 必须现在修（阻塞 Sim-1 部署）

| ID | 问题 | 文件 | 优先级 |
|----|------|------|--------|
| P0-1 | bind mount 路径错误 | `docker/docker-compose.yml` | P0 |
| P0-2 | context 和 dockerfile 路径错误（backend + frontend） | `docker/docker-compose.yml` | P0 |
| P0-3 | 健康检查路径错误（compose + Dockerfile.backend） | `docker/docker-compose.yml` + `docker/Dockerfile.backend` | P0 |
| P0-4 | 环境变量未注入容器 | `docker/docker-compose.yml` | P0 |
| P0-5 | runtime profile 未初始化 | `scripts/seed_sim1_runtime_profile.py` | P0 |
| P1-1 | PostgreSQL 配置 + .env 文件 | `.env` | P1 |
| P1-1 | 前端选择（web-front 或 gemimi-web-front） | `docker/Dockerfile.frontend` | P1 |

### 可以后续清理（不影响 Sim-1）

| ID | 问题 | 文件 | 优先级 |
|----|------|------|--------|
| P2-1 | 健康检查无依赖检查 | `src/interfaces/api.py` | P2 |
| P2-2 | COPY config/ 冗余 | `docker/Dockerfile.backend` | P2 |
| YAML-1 | 注释 "Backward compatibility" | `src/application/config_manager.py:217` | P3 |
| YAML-2 | 注释 "from core.yaml" | `src/application/signal_pipeline.py:88` | P3 |
| YAML-3 | 文档引用 YAML | `docs/tasks/archive/*.md` | P3 |

---

## 最小改动文件清单

### 必须修改（P0）

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `docker/docker-compose.yml` | **修改** | 1. context 路径<br>2. dockerfile 路径<br>3. volumes 路径<br>4. 健康检查路径<br>5. 环境变量注入 |
| `.env` | **新建** | 环境变量配置（不提交 git） |

### 必须执行（P0）

| 脚本 | 说明 |
|------|------|
| `scripts/seed_sim1_runtime_profile.py` | 初始化 runtime profile |

### 可选修改（P2）

| 文件 | 修改类型 |
|------|----------|
| `src/interfaces/api.py` | **修改**（增强健康检查） |
| `docker/Dockerfile.backend` | **修改**（移除 COPY config/） |

---

## 关键说明

### YAML 不是启动必需项

**证据**:
```python
# src/application/config_manager.py:908
"""Build default core configuration (hardcoded defaults).
No YAML file fallback — DB or defaults only.
"""
```

**结论**: ✅ YAML 已彻底废弃，不再作为启动配置来源。

### Docker readiness 当前最大风险

**风险 1**: 容器读取错误挂载目录
- bind mount 路径错误（`./config` → 应为 `../config`）
- 导致 runtime profile not found

**风险 2**: 容器拿不到环境变量
- 环境变量未注入容器
- 导致 FatalStartupError("F-003")

**修复优先级**: P0 > P1 > P2

---

## 风险提示

### 🔴 高风险

1. **bind mount 路径错误**: 容器挂载到空目录，runtime profile not found
2. **环境变量未注入**: FatalStartupError("F-003")
3. **PostgreSQL 必须可用**: Sim-1 强制要求，无法降级到 SQLite
4. **API Key 权限检查**: 启动时验证无提现权限
5. **Runtime Profile 冻结**: `is_readonly=True`，研究链无法反向污染

### 🟡 中风险

1. **环境变量泄露**: `.env` 文件需加入 `.gitignore`
2. **数据库迁移**: v3_dev.db 已有 196MB 数据

### 🟢 低风险

1. **YAML 残留注释**: 不影响功能，但可能误导维护者

---

## 详细报告

- **完整审查报告**: `docs/planning/sim1_docker_readiness_review_v3.md`
- **YAML 去味清单**: `docs/planning/yaml_deprecation_checklist.md`

---

**审查人**: Claude Code (Sonnet 4.6)
**文档版本**: v3.0 (修订版)
