# Phase 5 环境兼容性头脑风暴

**创建日期**: 2026-03-30
**讨论主题**: 多环境兼容性与部署策略
**状态**: 🧠 头脑风暴中

---

## 环境矩阵

| 环境 | 数据库 | 交易所 | 模式 | 用途 |
|------|--------|--------|------|------|
| **本地开发** | SQLite | Binance Testnet | 模拟/实盘 | 开发调试 |
| **测试服** | PostgreSQL | Binance Testnet | 实盘 | 集成测试 |
| **生产服** | PostgreSQL | Binance Production | 实盘 | 真实交易 |

---

## 兼容性议题

### 1. 数据库兼容性问题

#### 1.1 SQLite vs PostgreSQL 差异

| 问题 | SQLite | PostgreSQL | 影响 | 解决方案 |
|------|--------|------------|------|----------|
| **行级锁语法** | `BEGIN EXCLUSIVE` | `SELECT ... FOR UPDATE` | Phase 5 并发保护 | 使用 SQLAlchemy 抽象层 |
| **数据类型** | 弱类型 | 强类型 | 数据校验 | Pydantic 验证层 |
| **并发写入** | 单写入者 | 多写入者 | 性能差异 | 生产环境必须用 PostgreSQL |
| **自增 ID** | `AUTOINCREMENT` | `SERIAL` / `IDENTITY` | 迁移脚本 | Alembic 自动处理 |
| **时间戳** | Unix 整数 | `TIMESTAMP` | 时间处理 | 统一用 Unix 毫秒时间戳 |

**待讨论**:
- 是否需要 SQLite → PostgreSQL 数据迁移工具？
- 是否需要支持两种数据库的完整测试？

---

#### 1.2 Alembic 迁移策略

```python
# alembic/env.py

# 问题：如何根据环境自动选择数据库 URL？
# 方案 A: 环境变量
# 方案 B: 配置文件
# 方案 C: 启动参数
```

**建议**:
```bash
# 环境变量
DATABASE_URL=sqlite+aiosqlite:///./data/v3_dev.db      # 开发
DATABASE_URL=postgresql+asyncpg://user:pass@host/db   # 生产
```

---

### 2. 交易所兼容性问题

#### 2.1 多交易所支持矩阵

| 功能 | Binance | Bybit | OKX | 兼容性方案 |
|------|---------|-------|-----|-----------|
| **REST 下单** | ✅ | ✅ | ✅ | CCXT 统一接口 |
| **WebSocket 订单推送** | ✅ | ✅ | ✅ | CCXT.Pro |
| **reduce_only 参数** | ✅ `reduceOnly` | ✅ `reduce_only` | ✅ `posSide` | 适配层转换 |
| **测试网支持** | ✅ 完整 | ✅ 有限 | ❌ | 优先 Binance |
| **WebSocket 心跳** | 30s | 60s | 30s | 配置化 |
| **API 限流** | 1200 次/分 | 120 次/秒 | 20 次/秒 | 动态适配 |

**待讨论**:
- Phase 5 是否只支持 Binance？
- 还是需要同时支持 Bybit/OKX？

**建议**:
```yaml
# config/core.yaml

exchange:
  name: "binance"  # 可配置：binance / bybit / okx
  testnet: true    # 开发环境用测试网
```

---

#### 2.2 交易所 API 差异处理

```python
# 问题 1: 订单状态字段命名不一致
# Binance: "status": "FILLED"
# Bybit:  "order_status": "Filled"
# OKX:    "state": "live"

# 方案：CCXT 统一层 + 自定义适配
class ExchangeAdapter:
    def normalize_order_status(self, raw_status: str) -> OrderStatus:
        pass
```

---

### 3. 配置管理兼容性问题

#### 3.1 多环境配置策略

| 配置项 | 开发环境 | 测试环境 | 生产环境 |
|--------|----------|----------|----------|
| `EXCHANGE_NAME` | binance | binance | binance |
| `EXCHANGE_TESTNET` | true | true | false |
| `DATABASE_URL` | SQLite | PostgreSQL | PostgreSQL |
| `API_KEY` | 测试密钥 | 测试密钥 | 生产密钥 |
| `LOG_LEVEL` | DEBUG | INFO | WARNING |
| `RECONCILIATION_ON_STARTUP` | false | true | true |

**建议方案**:
```bash
# .env.development
EXCHANGE_TESTNET=true
DATABASE_URL=sqlite+aiosqlite:///./data/v3_dev.db
LOG_LEVEL=DEBUG

# .env.production
EXCHANGE_TESTNET=false
DATABASE_URL=postgresql+asyncpg://user:pass@host/db
LOG_LEVEL=WARNING
```

```python
# 配置加载
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    class Config:
        env_file = ".env"

    exchange_testnet: bool = True
    database_url: str
    log_level: str = "INFO"
```

---

#### 3.2 密钥管理

**问题**: 生产环境 API 密钥如何安全存储？

| 方案 | 优点 | 缺点 | 推荐度 |
|------|------|------|--------|
| `.env` 文件 | 简单 | 有泄露风险 | ⭐⭐ |
| 环境变量 | 较安全 | 部署复杂 | ⭐⭐⭐ |
| AWS Secrets Manager | 最安全 | 成本高 | ⭐⭐⭐⭐ |
| HashiCorp Vault | 最安全 | 运维复杂 | ⭐⭐⭐⭐ |

**建议**:
- 开发：`.env` 文件（不提交到 git）
- 测试：环境变量
- 生产：AWS Secrets Manager / Vault

---

### 4. 并发保护兼容性问题

#### 4.1 单进程 vs 多进程

| 场景 | 并发模型 | 锁机制 | 解决方案 |
|------|----------|--------|----------|
| **本地开发** | 单进程 | Asyncio Lock | 足够 |
| **测试服** | 单进程 | Asyncio Lock + DB 行锁 | 足够 |
| **生产服** | 多进程/多实例 | Asyncio Lock + DB 行锁 | 需要 DB 行锁 |

**关键点**:
- Asyncio Lock 仅在单进程内有效
- 生产环境必须依赖数据库行级锁（`SELECT FOR UPDATE`）
- SQLite 的 `BEGIN EXCLUSIVE` 模拟行锁，PostgreSQL 用 `FOR UPDATE`

---

#### 4.2 内存锁清理策略

```python
# 问题：_position_locks 字典长期运行会内存泄漏

# 方案 A: 平仓后立即清理（已实现）
if position.current_qty <= Decimal('0'):
    del self._position_locks[position_id]

# 方案 B: 定期清理（额外保护）
async def cleanup_stale_locks(self):
    for position_id in list(self._position_locks.keys()):
        if await self._is_position_closed(position_id):
            del self._position_locks[position_id]
```

---

### 5. WebSocket 兼容性问题

#### 5.1 重连策略差异

| 交易所 | 初始退避 | 最大退避 | 心跳超时 | 重连上限 |
|--------|----------|----------|----------|----------|
| Binance | 1s | 60s | 30s | ∞ |
| Bybit | 1s | 60s | 60s | ∞ |
| OKX | 1s | 60s | 30s | ∞ |

**建议配置化**:
```yaml
websocket:
  reconnect:
    initial_delay: 1  # 秒
    max_delay: 60     # 秒
    multiplier: 2     # 指数退避倍数
    heartbeat_timeout: 30  # 秒
```

---

#### 5.2 CCXT.Pro 版本兼容

**问题**: CCXT.Pro 已合并入主干 ccxt 库，但版本号如何对应？

| CCXT 版本 | CCXT.Pro 状态 |
|-----------|---------------|
| < 4.0.0 | 独立包 `ccxtpro` |
| >= 4.0.0 | 合并入 `ccxt` |

**建议**:
```txt
# requirements.txt
ccxt>=4.2.24  # 包含 CCXT.Pro 功能
```

```python
# 导入方式
import ccxt.pro as ccxtpro  # 从主干导入
```

---

### 6. 测试兼容性问题

#### 6.1 测试环境隔离

| 测试类型 | 数据库 | 交易所 | 执行频率 |
|----------|--------|--------|----------|
| 单元测试 | 内存 SQLite | Mock | 每次提交 |
| 集成测试 | 测试 PostgreSQL | Binance Testnet | 每日 |
| E2E 测试 | 测试 PostgreSQL | Binance Testnet | 每周 |

**建议**:
```python
# pytest 配置
[tool.pytest.ini_options]
markers = [
    "unit: 单元测试（无需外部依赖）",
    "integration: 集成测试（需要测试网）",
    "e2e: 端到端测试（需要测试网 + 完整环境）",
]
```

---

#### 6.2 Mock vs Real

| 模块 | 测试策略 | 说明 |
|------|----------|------|
| ExchangeGateway | Mock + Testnet | 单元测试用 Mock，集成测试用真实测试网 |
| Database | 内存 SQLite | 快速测试 |
| WebSocket | Mock Stream | 模拟推送事件 |

---

### 7. 日志与监控兼容性

#### 7.1 日志级别配置

| 环境 | 级别 | 输出 | 轮转 |
|------|------|------|------|
| 开发 | DEBUG | 控制台 + 文件 | 10MB |
| 测试 | INFO | 控制台 + 文件 | 50MB |
| 生产 | WARNING | 文件 + ELK | 100MB |

**建议配置**:
```yaml
logging:
  level: "INFO"  # 可覆盖：DEBUG / WARNING / ERROR
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  rotation:
    max_bytes: 52428800  # 50MB
    backup_count: 5
```

---

#### 7.2 监控指标兼容

| 指标 | 开发 | 测试 | 生产 |
|------|------|------|------|
| 订单延迟 | ✅ | ✅ | ✅ |
| WebSocket 重连 | ✅ | ✅ | ✅ |
| 内存锁数量 | ✅ | ✅ | ✅ |
| API 调用次数 | ❌ | ✅ | ✅ |
| 对账差异 | ❌ | ✅ | ✅ |

---

### 8. 部署兼容性问题

#### 8.1 Docker 环境

```dockerfile
# Dockerfile.development
FROM python:3.11-slim
ENV DATABASE_URL=sqlite+aiosqlite:///./data/v3_dev.db
ENV EXCHANGE_TESTNET=true

# Dockerfile.production
FROM python:3.11-slim
ENV DATABASE_URL=postgresql+asyncpg://user:pass@host/db
ENV EXCHANGE_TESTNET=false
```

---

#### 8.2 Docker Compose

```yaml
# docker-compose.yml
version: '3.8'

services:
  app:
    build:
      context: .
      dockerfile: Dockerfile.${ENV:-development}
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - EXCHANGE_TESTNET=${EXCHANGE_TESTNET:-true}
    volumes:
      - ./data:/app/data
    depends_on:
      - postgres

  postgres:
    image: postgres:15
    environment:
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

---

## 决策清单

### 已确认事项

| 编号 | 决策项 | 用户决策 | 状态 |
|------|--------|----------|------|
| D-001 | Phase 5 支持哪些交易所？ | Binance | ✅ 已确认 |
| D-002 | 生产环境数据库？ | PostgreSQL | ✅ 已确认 |
| D-003 | 密钥管理方案？ | 环境变量（东京 AWS） | ✅ 已确认 |
| D-004 | 是否需要数据迁移工具？ | 是（SQLite↔PostgreSQL） | ✅ 已确认 |
| D-005 | 是否支持多实例部署？ | 是（需要 DB 行锁） | ✅ 已确认 |
| D-006 | DCA 分批建仓？ | Phase 5 实现 | ✅ 已确认 |
| D-007 | 资金安全限制？ | Phase 5 实现 | ✅ 已确认 |
| D-008 | 告警渠道？ | 飞书 | ✅ 已确认 |
| D-009 | 生产服务器位置？ | 东京 AWS（预留香港切换） | ✅ 已确认 |

### 待确认事项

| 编号 | 决策项 | 选项 | 建议 | 状态 |
|------|--------|------|------|------|
| S-001 | 单笔最大损失限制 | % of balance | 1-2% | ⏳ |
| S-002 | 每日最大回撤限制 | % of balance | 5% | ⏳ |
| S-003 | 单次最大仓位 | % of balance | 10-20% | ⏳ |
| M-001 | 告警事件类型 | 订单失败/余额不足/断连/对账失败 | 全部 | ⏳ |

---

## 风险矩阵

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| SQLite 并发瓶颈 | 高 | 中 | 生产环境强制 PostgreSQL |
| 交易所 API 限流 | 中 | 高 | 动态适配 + 降级策略 |
| WebSocket 断连 | 中 | 高 | 自动重连 + 降级查询 |
| 密钥泄露 | 低 | 高 | 分环境策略 + Vault |
| 内存锁泄漏 | 中 | 中 | 平仓后清理 + 定期巡检 |

---

## 下一步行动

1. **确认交易所支持范围** (D-001)
2. **确认数据库策略** (D-002)
3. **确认密钥管理方案** (D-003)
4. **更新契约表** - 补充环境兼容说明
5. **更新配置管理** - 多环境配置支持

---

*头脑风暴文档 v1.0*
*2026-03-30*
