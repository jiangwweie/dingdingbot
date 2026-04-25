# Sim-1 Docker 部署就绪度审查 - 执行摘要

**审查日期**: 2026-04-25
**Verdict**: **Conditionally Ready** (有条件就绪)

---

## 核心结论

当前仓库**无法直接** `docker compose up` 成功，存在：
- **3 个 P0 构建期阻塞项**（必须修复）
- **3 个 P1 启动期阻塞项**（必须配置）
- **3 个 P2 运行期风险**（建议优化）

**修复工作量**: 约 2-3 小时（不含 PostgreSQL 部署）

---

## 阻塞项清单

### P0 - 构建期失败（立即修复）

| ID | 问题 | 文件:行号 |
|----|------|-----------|
| P0-1 | 前端 dist 目录不存在 | `docker/Dockerfile.frontend:14` |
| P0-2 | docker-compose context 路径错误 | `docker/docker-compose.yml:7-8` |
| P0-3 | config 目录缺少 core.yaml | `docker/Dockerfile.backend:27` |

### P1 - 启动期失败（必须配置）

| ID | 问题 | 文件:行号 |
|----|------|-----------|
| P1-1 | 缺少 `PG_DATABASE_URL` 环境变量 | `src/main.py:343` |
| P1-2 | 缺少 Exchange API 密钥 | `src/main.py:349-351` |
| P1-3 | runtime profile 未初始化 | `scripts/seed_sim1_runtime_profile.py` |

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
# 必须执行
python scripts/seed_sim1_runtime_profile.py
```

---

## 快速修复步骤

### 1. 修复构建期阻塞项（30 分钟）

```bash
# 1. 创建配置文件
cp config/core.yaml.reference config/core.yaml

cat > config/user.yaml <<EOF
exchange:
  name: binance
  testnet: true
timeframes:
  - "1h"
  - "4h"
notification:
  channels:
    - type: feishu
risk:
  max_loss_percent: 0.01
  max_leverage: 20
EOF

# 2. 修复 docker-compose.yml
sed -i '' 's/context: \./context: \.\./' docker/docker-compose.yml

# 3. 构建前端
cd web-front && npm install && npm run build && cd ..
```

### 2. 修复启动期阻塞项（1-2 小时）

```bash
# 1. 配置 PostgreSQL（外部或 docker-compose）
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
# 构建并启动
docker compose -f docker/docker-compose.yml build
docker compose -f docker/docker-compose.yml up -d

# 检查日志
docker compose -f docker/docker-compose.yml logs -f backend

# 健康检查
curl http://localhost:8000/api/health
```

---

## 前端入口选择

**正确入口**: `web-front/` ✅

**问题**: 缺少 `dist/` 构建产物

**解决方案**:
```bash
cd web-front
npm install
npm run build
# dist/ 目录会生成
```

**旧 Dockerfile 状态**: 未失效，但需要预构建

---

## 风险提示

### 🔴 高风险

1. **PostgreSQL 必须可用**: Sim-1 强制要求，无法降级到 SQLite
2. **API Key 权限检查**: 启动时验证无提现权限
3. **Runtime Profile 冻结**: `is_readonly=True`，研究链无法反向污染

### 🟡 中风险

1. **前端未构建**: 需手动 `npm run build`
2. **环境变量泄露**: `.env` 文件需加入 `.gitignore`
3. **数据库迁移**: v3_dev.db 已有 196MB 数据

---

## 详细报告

完整审查报告: `docs/planning/sim1_docker_readiness_review.md`

---

**审查人**: Claude Code (Sonnet 4.6)
**文档版本**: v1.0
