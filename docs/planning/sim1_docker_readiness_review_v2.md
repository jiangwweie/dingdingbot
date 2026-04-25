# Sim-1 模拟盘 Docker 部署就绪度审查报告（修订版）

**审查日期**: 2026-04-25
**审查范围**: /Users/jiangwei/Documents/final
**主线目标**: Sim-1 冻结 runtime（ETH 1h + 4h MTF, LONG-only）进入自然模拟盘观察窗口
**硬约束**: YAML 已彻底废弃，不再作为启动配置来源

---

## 执行摘要

**Verdict**: **Conditionally Ready** (有条件就绪)

**核心结论**: 当前仓库**可以** `docker build` 成功，但存在 2 个 P0 启动期阻塞项、1 个 P1 运行期配置错误。修复后可进入 Sim-1 观察窗口。

**修复工作量估算**: 约 1-2 小时（不含 PostgreSQL 部署）。

**重要纠正**:
- ✅ 前端 dist 目录已存在（`web-front/dist/` 有 index.html 和 assets/）
- ✅ config 目录存在，`COPY config/` 不会失败（只是复制参考文件）
- ❌ YAML 文件不再是启动必需条件（代码已改为 DB 驱动）

---

## 1. 当前仓库 Docker 构建可行性分析

### ✅ 可以构建成功（纠正上一版错误判断）

**证据**:

| 项目 | 状态 | 证据 |
|------|------|------|
| 前端 dist | ✅ 已存在 | `web-front/dist/index.html` 和 `web-front/dist/assets/` 存在 |
| config 目录 | ✅ 已存在 | `config/` 目录包含 `.reference`/`.example`/`.bak` 文件 |
| YAML 文件 | ✅ 不必需 | `src/application/config_manager.py:908` 注释："No YAML file fallback — DB or defaults only." |

**构建期无阻塞项**，但存在以下问题：

---

## 2. 阻塞项分级清单（修订版）

### P0 - 启动期失败（必须修复）

| ID | 文件:行号 | 问题 | 影响 |
|----|-----------|------|------|
| **P0-1** | `docker/docker-compose.yml:30` | 健康检查路径错误：`/health` 应为 `/api/health` | 容器健康检查失败，可能被误判为 unhealthy |
| **P0-2** | `docker/docker-compose.yml:7-8` | build context 路径错误：`.` 应为 `..` | Dockerfile 无法找到 `src/` 和 `config/` 目录 |

### P1 - 启动期失败（必须配置）

| ID | 文件:行号 | 问题 | 影响 |
|----|-----------|------|------|
| **P1-1** | `src/main.py:343` | 缺少环境变量 `PG_DATABASE_URL` | Sim-1 强制要求 PostgreSQL |
| **P1-2** | `src/main.py:349-351` | 缺少环境变量 `EXCHANGE_API_KEY/SECRET/WEBHOOK` | 启动时 FatalStartupError |
| **P1-3** | `scripts/seed_sim1_runtime_profile.py` | runtime profile 未初始化 | Phase 1.1 解析失败 |

### P2 - 运行期风险（建议修复）

| ID | 文件:行号 | 问题 | 影响 |
|----|-----------|------|------|
| P2-1 | `docker/docker-compose.yml:15` | config 只读挂载 | 无法热重载配置（不影响 Sim-1 冻结策略） |
| P2-2 | `src/interfaces/api.py:832` | /api/health 端点无依赖检查 | 容器健康检查可能误报 |
| P2-3 | `docker/Dockerfile.backend:27` | `COPY config/` 复制无用文件 | 镜像包含冗余文件（不影响启动） |

---

## 3. 失败阶段分类（修订版）

### 构建期失败（docker build 时立即失败）

**无构建期阻塞项** ✅

**纠正说明**:
- 上一版错误判断 P0-1（前端 dist 不存在）：实际 `web-front/dist/` 已存在
- 上一版错误判断 P0-3（config 目录缺少 core.yaml）：config 目录存在，且 YAML 不再是启动必需

### 启动期失败（容器启动后进程退出）

- **P0-1**: 健康检查路径错误 → 容器状态误判（不影响进程启动）
- **P0-2**: docker-compose context 错误 → `docker build` 找不到源码目录
- **P1-1**: PostgreSQL 环境变量缺失 → `FatalStartupError("F-003")`
- **P1-2**: Exchange API 密钥缺失 → `FatalStartupError("F-003")`
- **P1-3**: runtime profile 不存在 → `ValueError("runtime profile not found")`

### 运行期风险（启动后可能异常）

- **P2-1**: 配置只读挂载 → 热重载功能失效（不影响 Sim-1 冻结策略）
- **P2-2**: 健康检查无依赖 → 容器状态误判（数据库断开仍返回 200）
- **P2-3**: COPY config/ 冗余 → 镜像包含无用文件（不影响功能）

---

## 4. YAML 残留专项审查

### 4.1 启动链路残留

**结论**: ✅ **无启动依赖**

**证据**:

```python
# src/application/config_manager.py:908
"""Build default core configuration (hardcoded defaults).
Used when DB is not yet initialized or unavailable.
No YAML file fallback — DB or defaults only.
"""
```

```python
# src/main.py:201-202
config_manager = load_all_configs()
await config_manager.initialize_from_db()  # ✅ 从 DB 初始化
```

**残留代码**（不影响启动）:

| 文件:行号 | 残留类型 | 影响 | 建议动作 |
|-----------|----------|------|----------|
| `src/application/config_manager.py:1760` | `import_from_yaml()` 方法 | 仅用于手动导入 | 保留（备份工具） |
| `src/application/config_manager.py:1876` | `export_to_yaml()` 方法 | 仅用于手动导出 | 保留（备份工具） |
| `src/application/config_manager.py:2027` | `load_all_configs()` 注释 | 注释误导 | **修改文案** |
| `src/application/signal_pipeline.py:88` | 注释 "from core.yaml" | 注释过时 | **删除注释** |

### 4.2 接口残留

**结论**: ⚠️ **存在 YAML 导入/导出接口（非启动必需）**

| 文件:行号 | 残留类型 | 影响 | 建议动作 |
|-----------|----------|------|----------|
| `src/interfaces/api.py:1419` | YAML 导入接口 | 可选功能 | 保留（备份工具） |
| `src/interfaces/api.py:1476` | YAML 导出接口 | 可选功能 | 保留（备份工具） |
| `src/interfaces/api_v1_config.py:1682` | YAML 导入接口 | 可选功能 | 保留（备份工具） |

**说明**: 这些接口用于手动导入/导出配置备份，不影响 Sim-1 启动。

### 4.3 文档残留

**结论**: ❌ **大量过时文档引用 YAML**

| 文件:行号 | 残留类型 | 影响 | 建议动作 |
|-----------|----------|------|----------|
| `docs/tasks/archive/*.md` | 多处引用 `config/core.yaml` | 误导维护者 | **添加废弃说明** |
| `docs/adr/2026-04-14-*.md` | 提及 "没有 YAML 配置文件" | 正确描述 | 保留 |
| `CLAUDE.md` | 未提及 YAML 废弃 | 误导 | **补充说明** |

### 4.4 注释残留

**结论**: ⚠️ **存在误导性注释**

| 文件:行号 | 残留内容 | 影响 | 建议动作 |
|-----------|----------|------|----------|
| `src/application/config_manager.py:217` | "Backward compatibility with YAML files" | 误导 | **修改为 "YAML import/export utilities"** |
| `src/application/config_manager.py:254` | "config_dir: ... for backward compatibility" | 误导 | **修改为 "config_dir: legacy parameter (unused)"** |
| `src/application/signal_pipeline.py:88` | "Queue configuration from core.yaml" | 过时 | **删除注释** |
| `src/infrastructure/notifier.py:618` | "channels_config from user.yaml" | 过时 | **修改为 "from DB config"** |

---

## 5. YAML 去味清单

### 启动链路残留（不影响 Sim-1）

| 文件路径 + 行号 | 残留类型 | 是否影响 Sim-1 | 建议动作 |
|----------------|----------|----------------|----------|
| `src/application/config_manager.py:1760` | `import_from_yaml()` 方法 | ❌ 不影响 | 保留（备份工具） |
| `src/application/config_manager.py:1876` | `export_to_yaml()` 方法 | ❌ 不影响 | 保留（备份工具） |
| `src/application/config_manager.py:2027` | `load_all_configs()` 注释 | ❌ 不影响 | **修改文案** |

### 接口残留（不影响 Sim-1）

| 文件路径 + 行号 | 残留类型 | 是否影响 Sim-1 | 建议动作 |
|----------------|----------|----------------|----------|
| `src/interfaces/api.py:1419` | YAML 导入接口 | ❌ 不影响 | 保留（备份工具） |
| `src/interfaces/api.py:1476` | YAML 导出接口 | ❌ 不影响 | 保留（备份工具） |

### 文档残留（误导维护者）

| 文件路径 + 行号 | 残留类型 | 是否影响 Sim-1 | 建议动作 |
|----------------|----------|----------------|----------|
| `docs/tasks/archive/S2-5-ATR 过滤器实现.md:193` | 引用 `config/core.yaml` | ❌ 不影响 | **添加废弃说明** |
| `docs/tasks/archive/S4-2-异步 IO 队列优化.md:45` | 引用 `config/core.yaml` | ❌ 不影响 | **添加废弃说明** |
| `docs/tasks/archive/2026-03-25-子任务B-*.md:6` | 引用 `user.yaml` | ❌ 不影响 | **添加废弃说明** |

### 注释残留（误导维护者）

| 文件路径 + 行号 | 残留类型 | 是否影响 Sim-1 | 建议动作 |
|----------------|----------|----------------|----------|
| `src/application/config_manager.py:217` | "Backward compatibility with YAML files" | ❌ 不影响 | **修改为 "YAML import/export utilities"** |
| `src/application/config_manager.py:254` | "config_dir: ... for backward compatibility" | ❌ 不影响 | **修改为 "legacy parameter (unused)"** |
| `src/application/signal_pipeline.py:88` | "Queue configuration from core.yaml" | ❌ 不影响 | **删除注释** |
| `src/infrastructure/notifier.py:618` | "channels_config from user.yaml" | ❌ 不影响 | **修改为 "from DB config"** |

---

## 6. Sim-1 容器部署最小必需条件（修订版）

### 6.1 环境变量（必须配置）

```bash
# Sim-1 强制要求（src/application/runtime_config.py:51-54）
CORE_EXECUTION_INTENT_BACKEND=postgres

# PostgreSQL 连接（src/main.py:343）
PG_DATABASE_URL=postgresql://user:pass@host:5432/dbname

# 交易所 API（src/main.py:349-350）
EXCHANGE_NAME=binance
EXCHANGE_TESTNET=true
EXCHANGE_API_KEY=your_api_key
EXCHANGE_API_SECRET=your_api_secret

# 飞书告警（src/main.py:351）
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx

# 可选（src/main.py:212）
RUNTIME_PROFILE=sim1_eth_runtime  # 默认值
BACKEND_PORT=8000                 # 默认值
```

### 6.2 持久化卷（建议配置）

```yaml
volumes:
  # SQLite 数据库（旧链路兼容）
  - ./data:/app/data

  # 日志持久化
  - ./logs:/app/logs

  # PostgreSQL 数据（如果使用容器化 PG）
  postgres_data:
```

### 6.3 PostgreSQL / SQLite 角色分工

| 数据类型 | 默认 Backend | Sim-1 要求 | 环境变量 |
|----------|--------------|------------|----------|
| execution_intent | **postgres** | **强制 postgres** | `CORE_EXECUTION_INTENT_BACKEND=postgres` |
| orders | sqlite | 可选 postgres | `CORE_ORDER_BACKEND=sqlite` |
| positions | sqlite | 可选 postgres | `CORE_POSITION_BACKEND=sqlite` |
| signals | sqlite | 不涉及 | N/A |
| config | sqlite | 不涉及 | N/A |

### 6.4 runtime profile seed（必须执行）

```bash
# 1. 确保 PostgreSQL 已启动并创建数据库
createdb -h localhost -U postgres v3_sim1

# 2. Seed sim1_eth_runtime profile
python scripts/seed_sim1_runtime_profile.py
```

### 6.5 交易所/API 权限（必须配置）

**权限要求**:
- ✅ **交易权限**（读取行情 + 下单）
- ❌ **提现权限**（严禁，启动时会检查）

**Sim-1 配置**:
```bash
EXCHANGE_TESTNET=true  # ✅ 使用测试网
```

### 6.6 飞书告警（必须配置）

**用途**:
- 系统启动/关闭通知
- FatalStartupError 告警
- CapitalProtection 触发告警

---

## 7. 前端入口选择（确认）

**正确入口**: `web-front/` ✅

**证据**:
- `docker/Dockerfile.frontend:11` 引用 `web-front/nginx.conf`
- `web-front/dist/` 目录已存在（包含 index.html 和 assets/）

**nginx 配置正确**:
```nginx
# web-front/nginx.conf:23-33
location /api {
    proxy_pass http://backend:8000;  # ✅ 正确代理到后端
}
```

---

## 8. 最小改造方案（修订版）

### 设计原则

1. ✅ **不引入 runtime 可写能力**（保持冻结策略）
2. ✅ **不破坏 research/runtime 隔离**（runtime profile 只读）
3. ✅ **优先后端和只读观察面稳定运行**（前端可选）

### 修复步骤（按执行顺序）

#### 阶段 1: 修复启动期阻塞项（P0，预计 30 分钟）

**Step 1.1: 修复 docker-compose.yml context 路径**

```yaml
# docker/docker-compose.yml
services:
  backend:
    build:
      context: ..           # ✅ 改为上级目录（项目根目录）
      dockerfile: docker/Dockerfile.backend

  frontend:
    build:
      context: ..           # ✅ 改为上级目录
      dockerfile: docker/Dockerfile.frontend
```

**Step 1.2: 修复健康检查路径**

```yaml
# docker/docker-compose.yml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/api/health"]  # ✅ 改为 /api/health
```

#### 阶段 2: 修复启动期阻塞项（P1，预计 1-2 小时）

**Step 2.1: 配置 PostgreSQL**

**选项 A: 使用外部 PostgreSQL（推荐）**

```bash
# 创建 Sim-1 数据库
createdb -h <pg_host> -U <pg_user> v3_sim1

# 设置环境变量
export PG_DATABASE_URL="postgresql://<user>:<pass>@<host>:5432/v3_sim1"
```

**选项 B: 使用 docker-compose PostgreSQL**

```yaml
# docker/docker-compose.yml
services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: v3
      POSTGRES_PASSWORD: v3_password
      POSTGRES_DB: v3_sim1
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - monitor-dog-network

  backend:
    depends_on:
      - postgres
    environment:
      - PG_DATABASE_URL=postgresql://v3:v3_password@postgres:5432/v3_sim1

volumes:
  postgres_data:
```

**Step 2.2: 配置环境变量**

```bash
# 创建 .env 文件（不要提交到 git）
cat > .env <<EOF
# Sim-1 强制要求
CORE_EXECUTION_INTENT_BACKEND=postgres

# PostgreSQL
PG_DATABASE_URL=postgresql://v3:v3_password@postgres:5432/v3_sim1

# 交易所 API（测试网）
EXCHANGE_NAME=binance
EXCHANGE_TESTNET=true
EXCHANGE_API_KEY=your_testnet_api_key
EXCHANGE_API_SECRET=your_testnet_api_secret

# 飞书告警
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx

# Runtime Profile
RUNTIME_PROFILE=sim1_eth_runtime
EOF
```

**Step 2.3: Seed runtime profile**

```bash
# 方式 1: 直接运行脚本
python scripts/seed_sim1_runtime_profile.py

# 方式 2: 在容器启动时自动执行（修改 Dockerfile.backend）
# 在 CMD 之前添加：
# RUN python scripts/seed_sim1_runtime_profile.py
```

#### 阶段 3: 验证部署（测试）

```bash
# 构建镜像
docker compose -f docker/docker-compose.yml build

# 启动服务
docker compose -f docker/docker-compose.yml up -d

# 查看日志
docker compose -f docker/docker-compose.yml logs -f backend

# 健康检查
curl http://localhost:8000/api/health
```

---

## 9. Readiness Verdict（修订版）

### 最终判定: **Conditionally Ready** (有条件就绪)

**理由**:
- ✅ 代码架构支持 Sim-1 冻结策略（runtime_config.py 强制约束）
- ✅ 启动流程完整（main.py Phase 1-9）
- ✅ 前端配置正确（nginx proxy_pass）
- ✅ 前端 dist 已存在（纠正上一版错误判断）
- ✅ YAML 不再是启动必需（纠正上一版错误判断）
- ❌ 存在 2 个 P0 启动期阻塞项（可修复）
- ❌ 存在 3 个 P1 启动期阻塞项（需配置）

**修复后状态**: **Ready for Sim-1 Observation Window**

---

## 10. 修复 Checklist（按执行顺序）

### ✅ 阶段 1: 启动期修复（P0，预计 30 分钟）

- [ ] **P0-2**: 修改 `docker/docker-compose.yml` context 路径（`.` → `..`）
- [ ] **P0-1**: 修改 `docker/docker-compose.yml` 健康检查路径（`/health` → `/api/health`）
- [ ] **验证**: `docker compose -f docker/docker-compose.yml build` 成功

### ✅ 阶段 2: 启动期修复（P1，预计 1-2 小时）

- [ ] **P1-1**: 部署 PostgreSQL 或配置外部 PG 连接
- [ ] **P1-1**: 创建 Sim-1 数据库（`createdb v3_sim1`）
- [ ] **P1-2**: 配置环境变量（`.env` 文件）
  - [ ] `PG_DATABASE_URL`
  - [ ] `CORE_EXECUTION_INTENT_BACKEND=postgres`
  - [ ] `EXCHANGE_API_KEY` / `EXCHANGE_API_SECRET`
  - [ ] `FEISHU_WEBHOOK_URL`
- [ ] **P1-3**: 运行 `scripts/seed_sim1_runtime_profile.py`
- [ ] **验证**: `docker compose -f docker/docker-compose.yml up -d` 启动成功

### ⚠️ 阶段 3: 运行期优化（P2，可选）

- [ ] **P2-2**: 增强 `/api/health` 端点依赖检查（数据库连接状态）
- [ ] **P2-3**: 移除 `docker/Dockerfile.backend:27` 的 `COPY config/`（可选）
- [ ] **验证**: 模拟盘观察窗口稳定运行 24 小时

---

## 11. 建议修改文件清单

### 必须修改（P0/P1）

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `docker/docker-compose.yml` | **修改** | context 路径 `.` → `..`，健康检查 `/health` → `/api/health` |
| `.env` | **新建** | 环境变量配置（不提交 git） |

### 可选修改（P2）

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `docker/Dockerfile.backend` | **修改** | 移除 `COPY config/`（可选） |
| `src/interfaces/api.py` | **修改** | 增强 `/api/health` 端点依赖检查 |

### YAML 去味修改（后续清理）

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `src/application/config_manager.py:217` | **修改注释** | "Backward compatibility" → "YAML import/export utilities" |
| `src/application/config_manager.py:254` | **修改注释** | "for backward compatibility" → "legacy parameter (unused)" |
| `src/application/signal_pipeline.py:88` | **删除注释** | 删除 "from core.yaml" 注释 |
| `src/infrastructure/notifier.py:618` | **修改注释** | "from user.yaml" → "from DB config" |
| `docs/tasks/archive/*.md` | **添加说明** | 在文件顶部添加 "YAML 已废弃" 说明 |

---

## 12. "必须现在修" vs "可以后续清理"

### 必须现在修（阻塞 Sim-1 部署）

| ID | 问题 | 文件 | 优先级 |
|----|------|------|--------|
| P0-2 | docker-compose context 路径错误 | `docker/docker-compose.yml` | P0 |
| P0-1 | 健康检查路径错误 | `docker/docker-compose.yml` | P0 |
| P1-1 | 缺少 PostgreSQL 配置 | `.env` | P1 |
| P1-2 | 缺少 Exchange API 密钥 | `.env` | P1 |
| P1-3 | runtime profile 未初始化 | `scripts/seed_sim1_runtime_profile.py` | P1 |

### 可以后续清理（不影响 Sim-1）

| ID | 问题 | 文件 | 优先级 |
|----|------|------|--------|
| P2-2 | 健康检查无依赖检查 | `src/interfaces/api.py` | P2 |
| P2-3 | COPY config/ 冗余 | `docker/Dockerfile.backend` | P2 |
| YAML-1 | 注释 "Backward compatibility" | `src/application/config_manager.py:217` | P3 |
| YAML-2 | 注释 "from core.yaml" | `src/application/signal_pipeline.py:88` | P3 |
| YAML-3 | 文档引用 YAML | `docs/tasks/archive/*.md` | P3 |

---

## 13. 风险提示

### 🔴 高风险

1. **PostgreSQL 必须可用**: Sim-1 强制要求 `CORE_EXECUTION_INTENT_BACKEND=postgres`，无法降级到 SQLite
2. **API Key 权限检查**: 启动时会验证无提现权限，配置错误会导致 FatalStartupError
3. **Runtime Profile 冻结**: `is_readonly=True`，研究链无法反向污染 runtime

### 🟡 中风险

1. **环境变量泄露**: `.env` 文件包含敏感信息，确保 `.gitignore` 已配置
2. **数据库迁移**: v3_dev.db 已有 196MB 数据，需确认是否需要迁移

### 🟢 低风险

1. **Config 只读挂载**: 不影响 Sim-1 冻结策略，热重载功能非必需
2. **健康检查简化**: 当前 `/api/health` 端点无依赖检查，可能误报容器健康
3. **YAML 残留注释**: 不影响功能，但可能误导维护者

---

**审查完成时间**: 2026-04-25
**审查人**: Claude Code (Sonnet 4.6)
**文档版本**: v2.0 (修订版)
