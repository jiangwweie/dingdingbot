# Sim-1 Docker 部署就绪度审查 - 执行摘要（修订版）

**审查日期**: 2026-04-25
**Verdict**: **Conditionally Ready** (有条件就绪)
**硬约束**: YAML 已彻底废弃，不再作为启动配置来源

---

## 核心结论（纠正版）

当前仓库**可以** `docker build` 成功，但存在 2 个 P0 启动期阻塞项、3 个 P1 启动期阻塞项。修复工作量约 1-2 小时。

**重要纠正**（相比 v1 版本）:
- ✅ 前端 dist 目录已存在（`gemimi-web-front/dist/` 有 index.html 和 assets/）
- ✅ config 目录存在，`COPY config/` 不会失败
- ✅ YAML 文件不再是启动必需条件（代码已改为 DB 驱动）

---

## 阻塞项清单（修订版）

### P0 - 启动期失败（必须修复）

| ID | 问题 | 文件:行号 | 影响 |
|----|------|-----------|------|
| **P0-1** | 健康检查路径错误 | `docker/docker-compose.yml:30` | 容器健康检查失败 |
| **P0-2** | docker-compose context 路径错误 | `docker/docker-compose.yml:7-8` | Dockerfile 无法找到源码 |

**证据**:
```yaml
# docker/docker-compose.yml:30
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/health"]  # ❌ 应为 /api/health

# docker/docker-compose.yml:7-8
build:
  context: .              # ❌ 应为 ..
  dockerfile: Dockerfile.backend
```

### P1 - 启动期失败（必须配置）

| ID | 问题 | 文件:行号 |
|----|------|-----------|
| **P1-1** | 缺少 `PG_DATABASE_URL` 环境变量 | `src/main.py:343` |
| **P1-2** | 缺少 Exchange API 密钥 | `src/main.py:349-351` |
| **P1-3** | runtime profile 未初始化 | `scripts/seed_sim1_runtime_profile.py` |

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

### PostgreSQL 要求

**Sim-1 强制约束**: `CORE_EXECUTION_INTENT_BACKEND=postgres`

```python
# src/application/runtime_config.py:51-54
if self.core_execution_intent_backend != "postgres":
    raise ValueError("Sim-1 requires CORE_EXECUTION_INTENT_BACKEND=postgres")
```

### Runtime Profile Seed

```bash
python scripts/seed_sim1_runtime_profile.py
```

---

## 快速修复步骤（修订版）

### 1. 修复 P0 阻塞项（30 分钟）

```bash
# 1. 修复 docker-compose.yml
sed -i '' 's/context: \./context: \.\./' docker/docker-compose.yml
sed -i '' 's|http://localhost:8000/health|http://localhost:8000/api/health|' docker/docker-compose.yml

# 2. 验证构建
docker compose -f docker/docker-compose.yml build
```

### 2. 修复 P1 阻塞项（1-2 小时）

```bash
# 1. 配置 PostgreSQL
createdb -h localhost -U postgres v3_sim1

# 2. 创建 .env 文件
cat > .env <<EOF
CORE_EXECUTION_INTENT_BACKEND=postgres
PG_DATABASE_URL=postgresql://postgres:password@localhost:5432/v3_sim1
EXCHANGE_NAME=binance
EXCHANGE_TESTNET=true
EXCHANGE_API_KEY=your_key
EXCHANGE_API_SECRET=your_secret
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
EOF

# 3. Seed runtime profile
python scripts/seed_sim1_runtime_profile.py
```

### 3. 验证部署

```bash
# 启动服务
docker compose -f docker/docker-compose.yml up -d

# 检查日志
docker compose -f docker/docker-compose.yml logs -f backend

# 健康检查
curl http://localhost:8000/api/health
```

---

## 前端入口确认

**正确入口**: `gemimi-web-front/` ✅

**证据**:
- `docker/Dockerfile.frontend:11` 引用 `gemimi-web-front/nginx.conf`
- `gemimi-web-front/dist/` 目录已存在（包含 index.html 和 assets/）

---

## "必须现在修" vs "可以后续清理"

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

## 最小改动文件清单

### 必须修改（P0/P1）

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `docker/docker-compose.yml` | **修改** | context 路径 + 健康检查路径 |
| `.env` | **新建** | 环境变量配置（不提交 git） |

### 可选修改（P2/P3）

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `src/interfaces/api.py` | **修改** | 增强 `/api/health` 端点依赖检查 |
| `docker/Dockerfile.backend` | **修改** | 移除 `COPY config/`（可选） |
| `src/application/config_manager.py` | **修改注释** | 修改误导性注释 |
| `docs/tasks/archive/*.md` | **添加说明** | 添加 YAML 废弃说明 |

---

## 风险提示

### 🔴 高风险

1. **PostgreSQL 必须可用**: Sim-1 强制要求，无法降级到 SQLite
2. **API Key 权限检查**: 启动时验证无提现权限
3. **Runtime Profile 冻结**: `is_readonly=True`，研究链无法反向污染

### 🟡 中风险

1. **环境变量泄露**: `.env` 文件需加入 `.gitignore`
2. **数据库迁移**: v3_dev.db 已有 196MB 数据

### 🟢 低风险

1. **YAML 残留注释**: 不影响功能，但可能误导维护者

---

## 详细报告

- **完整审查报告**: `docs/planning/sim1_docker_readiness_review_v2.md`
- **YAML 去味清单**: `docs/planning/yaml_deprecation_checklist.md`

---

**审查人**: Claude Code (Sonnet 4.6)
**文档版本**: v2.0 (修订版)
