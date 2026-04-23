# Sim-0 真实模拟盘全链路验证报告

> 日期：2026-04-23  
> 范围：Sim-0.2 ~ Sim-0.5  
> 环境：Binance USDT-M Testnet  
> Symbol：`BTC/USDT:USDT`  
> 配置真源：`.env` + 当前兼容配置库 `data/v3_dev.db`  
> 结论：阶段性通过，可以进入“分阶段观察/复盘”节奏

---

## 1. 验证结论

Sim-0.2 到 Sim-0.5 已完成真实 runtime 验证。

最终通过链路：

```text
主程序真实启动
 -> PG execution_intents 初始化
 -> PG execution_recovery_tasks 初始化
 -> 启动对账
 -> breaker 重建
 -> SignalPipeline warmup
 -> 受控 K 线进入真实策略/过滤器
 -> 风控与仓位计算
 -> ExecutionOrchestrator
 -> testnet ENTRY 市价成交
 -> TP1 / TP2 / SL 保护单挂载
 -> ExecutionIntent 写入 PG completed
 -> 重启后启动对账通过
```

最终有效样本：

| 项目 | 结果 |
| --- | --- |
| `intent_id` | `intent_4e8a039bf40d` |
| `signal_id` | `sig_414dcf21a402` |
| ENTRY 本地订单 | `ord_03edf75f` |
| ENTRY 交易所订单 | `13065557075` |
| intent 最终状态 | `completed` |
| TP1 | `ord_TP1_a4c42d55` / `13065557100` |
| TP2 | `ord_TP2_d7c94570` / `13065557123` |
| SL | `ord_sl_e4750340` / `1000000056203980` |
| PG active recovery tasks | `0` |
| breaker symbols | `[]` |

---

## 2. 分阶段结果

### Sim-0.2 主程序真实启动

结果：通过。

关键事实：

1. `ExchangeGateway` 初始化成功。
2. `PgExecutionRecoveryRepository` 初始化成功。
3. Phase 4.3 启动对账执行成功。
4. Phase 4.4 breaker 从 PG active recovery tasks 重建成功。
5. `SignalPipeline` warmup 成功。
6. REST API server 启动成功。

### Sim-0.3 信号到 testnet ENTRY

结果：通过。

关键事实：

1. 使用真实主程序 runtime，而不是手工拼装组件。
2. 受控 K 线进入真实 `SignalPipeline`。
3. 当前冻结策略 `01` 触发 `LONG` 信号。
4. `CapitalProtection` 前置检查通过。
5. ENTRY 市价单提交到 Binance testnet。
6. ENTRY 订单成交，交易所订单 ID 为 `13065557075`。

### Sim-0.4 保护单挂载

结果：通过。

关键事实：

1. ENTRY 成交后自动挂载保护单。
2. TP1 / TP2 / SL 均提交成功。
3. 本地订单链存在 `parent_order_id` 关联。
4. intent 最终写入 PG `completed`。
5. 未产生 PG recovery task。
6. 未触发 breaker。

### Sim-0.5 重启对账与恢复

结果：通过。

关键事实：

1. 清理受控验证仓位和保护单后，重启探针启动成功。
2. 启动对账候选订单 `0`。
3. 对账失败 `0`。
4. PG active recovery tasks `0`。
5. breaker 重建后为空。
6. 系统进入 ready。

---

## 3. 验证期间发现并修复的问题

### 3.1 `SignalPipeline` 风险计算未 await

问题：

`SignalPipeline._calculate_risk()` 是同步函数，但调用了 async 的 `RiskCalculator.calculate_signal_result()`，真实信号触发后会拿到 coroutine 而不是 `SignalResult`。

修复：

1. `_calculate_risk()` 改为 async。
2. `process_kline()` 中改为 `await self._calculate_risk(...)`。
3. 对应单测改为 async。

### 3.2 市价 ENTRY 成交后缺失真实成交均价

问题：

Binance testnet 市价单 `create_order()` 返回 `FILLED` 时，不一定包含可靠 `average`。保护单生成依赖 ENTRY 的真实成交均价，缺失时会导致 `Position.entry_price=None`。

修复：

1. `OrderPlacementResult` 增加 `filled_qty` / `average_exec_price`。
2. `ExchangeGateway.place_order()` 解析 `filled` / `average`。
3. `ExecutionOrchestrator` 在 `FILLED` 但缺少均价时，立即 `fetch_order()` 获取交易所真实订单快照。
4. 若仍拿不到均价，拒绝挂保护单并标记失败。

### 3.3 PG intent 状态枚举写入格式错误

问题：

PG `execution_intents.status` check constraint 只允许 `pending/completed/...`，但仓储写入了 `ExecutionIntentStatus.FAILED` 这种 `str(enum)` 格式。

修复：

`PgExecutionIntentRepository._to_orm()` 改为写入 `.value`。

### 3.4 PG intent 与 SQLite orders 的跨库外键冲突

问题：

当前 Sim-0 冻结策略是：

1. `CORE_EXECUTION_INTENT_BACKEND=postgres`
2. `CORE_ORDER_BACKEND=sqlite`

但 PG `execution_intents.order_id` 对 PG `orders.id` 有外键。由于 orders 仍在 SQLite，intent 写 PG 时会触发外键失败。

修复：

1. 移除 `execution_intents.order_id -> orders.id` 的 PG 外键。
2. 移除 `execution_recovery_tasks.related_order_id -> orders.id` 的 PG 外键。
3. 保留 `order_id` / `related_order_id` 作为跨库逻辑引用。
4. 同步更新 `pg_models.py` 和 PG baseline SQL。

---

## 4. 清理动作

受控验证期间产生过真实 testnet 小仓位和保护单。验证结束后已清理：

1. 取消 testnet open TP orders。
2. 使用 reduce-only 市价单平掉 BTC testnet 小仓位。
3. 清理后 testnet BTC open orders 为空。
4. 清理后 testnet BTC position 为空。
5. 本地对应保护单状态更新为 `CANCELED`，避免重启对账重复扫旧单。

---

## 5. 残余风险

### R1：尝试记录队列仍有 Decimal JSON 序列化错误

启动与信号处理过程中出现：

```text
Failed to flush attempts batch: Object of type Decimal is not JSON serializable
```

影响判断：

1. 不阻塞 ENTRY / TP / SL / intent 主链。
2. 会影响 signal attempt 诊断记录完整性。
3. 建议列为下一阶段 P1 修复。

### R2：Sim-0 runtime 脚本是验证脚本，不应成为生产入口

`scripts/sim0_runtime_chain_check.py` 仅用于受控验证真实 runtime 链路。它会同步 `.env` 到兼容配置库，并注入受控 K 线。

后续自然模拟盘运行应直接使用：

```bash
set -a
source .env
set +a
PYTHONPATH=/Users/jiangwei/Documents/final ./venv/bin/python3 src/main.py
```

### R3：配置系统仍存在 `.env` 与兼容配置库双层关系

Sim-0 运行配置原则已经确定为 `.env`，但当前主程序仍通过 `ConfigManager` 从 `data/v3_dev.db` 读取 exchange/notification/system 配置。因此验证脚本在启动前会把 `.env` 同步进兼容配置库。

建议后续单独规划“运行配置 env 覆盖层”或“配置库废弃路径”，不要在 Sim-0 继续扩大。

---

## 6. 当前准入判断

Sim-0 真实链路已达到阶段性准入：

1. 可启动。
2. 可触发信号。
3. 可下 testnet ENTRY。
4. 可挂 TP/SL。
5. 可写 PG intent completed。
6. 可重启对账。
7. 可清理验证仓位。

下一步建议不是继续一口气扩功能，而是进入**分阶段观察**：

1. 先修 `Decimal JSON` attempt 记录问题。
2. 再启动自然模拟盘观察窗口。
3. 每完成一个观察阶段暂停汇报，不连续推进。
