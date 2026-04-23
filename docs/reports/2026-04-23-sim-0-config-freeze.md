# Sim-0.1 启动配置冻结清单

> **冻结时间**: 2026-04-23
> **冻结目标**: 确认 Sim-0 真实全链路验证的配置基线
> **验证范围**: 行情/K线 -> SignalPipeline -> 策略/过滤器 -> 风控/仓位 -> ExecutionOrchestrator -> ExchangeGateway testnet 下单 -> WS 回写 -> OrderLifecycle -> StartupReconciliation -> PG recovery / breaker

---

## 配置检查结果

### 1. 环境变量检查

| 配置项 | 当前值 | Sim-0 预期 | 是否满足 |
|--------|--------|------------|----------|
| `PG_DATABASE_URL` | **未设置** | `postgresql+asyncpg://...` | ❌ **不满足** |
| `CORE_EXECUTION_INTENT_BACKEND` | 未设置（默认 `sqlite`） | `postgres` | ❌ **不满足** |
| `CORE_ORDER_BACKEND` | 未设置（默认 `sqlite`） | `sqlite` | ✅ 满足 |

**问题分析**:
- `PG_DATABASE_URL` 未配置，导致 `CORE_EXECUTION_INTENT_BACKEND` 默认为 `sqlite`
- 这不符合 Sim-0 验证 PG recovery 主线的要求

---

### 2. 配置文件检查

**配置文件**: `config/user.yaml`

#### 交易所配置

| 配置项 | 当前值 | Sim-0 预期 | 是否满足 |
|--------|--------|------------|----------|
| `exchange.name` | `binance` | `binance` | ✅ 满足 |
| `exchange.testnet` | **`false`** | `true` | ❌ **不满足** |
| `exchange.api_key` | 已配置 | testnet API key | ⚠️ 需确认是否为 testnet key |
| `exchange.api_secret` | 已配置 | testnet API secret | ⚠️ 需确认是否为 testnet secret |

**问题分析**:
- `testnet: false` 表示当前配置为**主网环境**，不符合 Sim-0 模拟盘验证要求
- API key/secret 需要确认是否为 testnet 专用密钥

#### Symbol 范围

| 配置项 | 当前值 | Sim-0 预期 | 是否满足 |
|--------|--------|------------|----------|
| `user_symbols` | `[]`（空） | `["BTC/USDT:USDT"]` | ⚠️ 需确认 |
| `core_symbols` | 未在 user.yaml 中定义 | `["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT"]` | ⚠️ 需确认 |

**说明**:
- `user_symbols` 为空，表示依赖系统默认 `core_symbols`
- Sim-0 建议冻结为单 symbol：`BTC/USDT:USDT`

#### 策略配置

| 配置项 | 当前值 | Sim-0 预期 | 是否满足 |
|--------|--------|------------|----------|
| `active_strategies` | 1 个策略（burst_9） | 冻结当前策略 | ✅ 满足 |
| `strategy.name` | `burst_9` | 保持不变 | ✅ 满足 |
| `strategy.trigger` | pinbar | 保持不变 | ✅ 满足 |

#### 风控配置

| 配置项 | 当前值 | Sim-0 预期 | 是否满足 |
|--------|--------|------------|----------|
| `risk.max_loss_percent` | `0.01` (1%) | 保持不变 | ✅ 满足 |
| `risk.max_leverage` | `125` | 保持不变 | ✅ 满足 |
| `risk.max_total_exposure` | `0.8` (80%) | 保持不变 | ✅ 满足 |

#### 通知配置

| 配置项 | 当前值 | Sim-0 预期 | 是否满足 |
|--------|--------|------------|----------|
| `notification.channels` | `[feishu]` | 开启飞书告警 | ✅ 满足 |
| `webhook_url` | `https://example.com/webhook` | 有效 webhook URL | ⚠️ 需确认是否为真实 URL |

**问题分析**:
- webhook_url 为示例 URL，需确认是否已替换为真实飞书 webhook

---

## 不满足项汇总

### ❌ 关键不满足项（阻塞 Sim-0.2）

1. **PG_DATABASE_URL 未配置**
   - 影响：ExecutionIntent 无法进入 PG 主线
   - 要求：配置 PostgreSQL DSN（testnet 环境）

2. **CORE_EXECUTION_INTENT_BACKEND 未设置为 postgres**
   - 影响：ExecutionIntent 默认走 sqlite，不符合 PG 主线验证要求
   - 要求：显式设置为 `postgres` 或配置 `PG_DATABASE_URL`

3. **exchange.testnet = false**
   - 影响：当前为主网配置，不符合模拟盘验证要求
   - 要求：设置为 `true`

### ⚠️ 需确认项（不阻塞但需验证）

1. **API key/secret 是否为 testnet 专用**
   - 建议：确认 API key 权限（仅交易，无提现）

2. **Symbol 范围冻结**
   - 建议：Sim-0 只验证 `BTC/USDT:USDT`

3. **飞书 webhook URL 是否有效**
   - 建议：确认 webhook 已正确配置

---

## Sim-0 固定范围确认

### 预期固定范围

| 配置项 | Sim-0 固定值 | 当前状态 |
|--------|--------------|----------|
| `CORE_EXECUTION_INTENT_BACKEND` | `postgres` | ❌ 未满足 |
| `CORE_ORDER_BACKEND` | `sqlite` | ✅ 已满足 |
| `exchange.testnet` | `true` | ❌ 未满足 |
| `symbol 范围` | `BTC/USDT:USDT` | ⚠️ 需确认 |
| `策略参数` | 冻结当前策略 | ✅ 已满足 |
| `飞书告警` | 开启 | ✅ 已满足 |

---

## 结论

### ❌ **不满足 Sim-0.1 要求**

当前配置存在 **3 个关键不满足项**，阻塞进入 Sim-0.2：

1. `PG_DATABASE_URL` 未配置
2. `CORE_EXECUTION_INTENT_BACKEND` 未设置为 `postgres`
3. `exchange.testnet` 为 `false`（主网环境）

### ❌ **不允许进入 Sim-0.2**

必须先修复关键不满足项：

1. 配置 `PG_DATABASE_URL`（PostgreSQL testnet DSN）
2. 设置 `CORE_EXECUTION_INTENT_BACKEND=postgres` 或依赖 `PG_DATABASE_URL` 自动推断
3. 修改 `config/user.yaml` 中 `exchange.testnet: true`
4. 确认 API key/secret 为 testnet 专用密钥

---

## 下一步建议

### Sim-0.1 补动作

1. **配置 PostgreSQL 数据库**
   - 设置 `PG_DATABASE_URL` 环境变量
   - 确保数据库已创建并可连接

2. **切换 testnet 环境**
   - 修改 `config/user.yaml` 中 `exchange.testnet: true`
   - 确认 API key/secret 为 testnet 密钥

3. **冻结 symbol 范围**
   - 建议 Sim-0 只验证 `BTC/USDT:USDT`

4. **确认飞书 webhook**
   - 确认 webhook URL 有效且已正确配置

### Sim-0.2 启动条件

满足以下条件后可进入 Sim-0.2：

- ✅ `PG_DATABASE_URL` 已配置
- ✅ `CORE_EXECUTION_INTENT_BACKEND=postgres`
- ✅ `exchange.testnet=true`
- ✅ API key/secret 为 testnet 密钥
- ✅ 飞书 webhook 有效

---

**检查人**: Claude Sonnet 4.6
**检查日期**: 2026-04-23