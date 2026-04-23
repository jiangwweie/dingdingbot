# Sim-0 真实模拟盘全链路验证计划

> 日期：2026-04-23
> 状态：待执行
> 目标：验证真实模拟盘链路是否从行情/信号管道一路闭合到下单、WS 回写、对账、PG recovery 与 breaker

---

## 1. 背景

当前已完成的是**模拟盘准入冒烟验证**，不是完整真实链路验证。

已通过的准入冒烟包括：

1. 正常链路冒烟
2. `replace_sl_failed` 异常链路冒烟
3. 启动恢复冒烟
4. 熔断拦截冒烟

报告位置：

- `docs/reports/2026-04-23-sim-trading-readiness-smoke-check.md`

这证明当前执行恢复主链具备“可运行 + 可恢复 + 可拦截”的最小条件。

但还没有实证下面这条真实链路：

```text
真实/模拟行情
 -> SignalPipeline
 -> 策略识别
 -> filters
 -> 风控/仓位
 -> ExecutionOrchestrator
 -> ExchangeGateway testnet 下单
 -> WS 订单回写
 -> OrderLifecycle 状态推进
 -> StartupReconciliation 对账
 -> PG recovery / breaker / 飞书告警
```

Sim-0 的目标就是验证这条链路。

---

## 2. Sim-0 总目标

用最小范围证明系统可以在模拟盘环境里稳定跑通真实执行链。

Sim-0 不是策略优化阶段，也不是收益验证阶段。

Sim-0 只回答：

1. 系统能不能稳定启动
2. 信号能不能真实触发 testnet 下单
3. ENTRY / TP / SL / WS 回写是否一致
4. 启动对账和 PG recovery 是否可用
5. breaker 是否会误触发或漏触发

---

## 3. Sim-0 范围冻结

### 固定范围

1. 环境：testnet / 模拟盘
2. symbol：`BTC/USDT:USDT`
3. 策略：当前冻结主线策略
4. `CORE_EXECUTION_INTENT_BACKEND=postgres`
5. `CORE_ORDER_BACKEND=sqlite`
6. PG recovery：启用 `execution_recovery_tasks`
7. breaker：内存缓存，由 PG active recovery tasks 重建

### 明确不做

1. 不做回测精细化
2. 不做参数搜索扩展
3. 不热改 Sim-0 运行中的策略配置
4. 不扩大 symbol
5. 不切 `CORE_ORDER_BACKEND=postgres`
6. 不做前端/API 扩张

离线优化可以并行，但只能产出 Sim-1 候选，不能热改 Sim-0。

---

## 4. 任务拆分

### Sim-0.1 启动配置冻结

目标：确认跑的是我们要验证的版本。

检查项：

1. `PG_DATABASE_URL` 已配置
2. `CORE_EXECUTION_INTENT_BACKEND=postgres`
3. `CORE_ORDER_BACKEND=sqlite`
4. testnet / 模拟盘开关正确
5. symbol 只启用 `BTC/USDT:USDT`
6. 当前冻结策略参数已确认
7. 飞书 webhook 可用

产出：

- Sim-0 启动配置清单

---

### Sim-0.2 主程序真实启动

目标：验证启动链路没有阻塞问题。

检查项：

1. PG 初始化成功
2. `execution_recovery_tasks` 表可用
3. Phase 4.3 启动对账完成
4. Phase 4.4 breaker 重建完成
5. ExchangeGateway 初始化成功
6. WS 订阅成功
7. SignalPipeline 启动成功

产出：

- 启动日志摘要

---

### Sim-0.3 信号到下单链路验证

目标：证明不是只会 mock，而是真实信号链能触发 testnet 下单。

检查项：

1. K 线进入 SignalPipeline
2. 策略/过滤器产出有效 signal
3. CapitalProtection 通过
4. ExecutionIntent 写入 PG
5. ENTRY 订单创建
6. ENTRY 订单提交 testnet

产出：

- 一笔真实 testnet ENTRY 的链路记录

---

### Sim-0.4 WS 回写与保护单验证

目标：证明订单状态能回写，保护单能挂上。

检查项：

1. WS 收到 ENTRY 状态
2. OrderLifecycle 推进本地订单
3. TP/SL 被创建
4. 保护单 `exchange_order_id` 写回
5. 无重复 SL
6. 无裸奔仓位
7. 本地订单状态与交易所状态一致

产出：

- ENTRY + TP/SL 订单链记录

---

### Sim-0.5 对账与恢复验证

目标：证明重启后恢复链可以接上。

检查项：

1. 重启一次主程序
2. StartupReconciliation 扫描未完成订单
3. PG recovery task 状态正常
4. breaker 由 PG active tasks 重建
5. 没有旧 SQLite `pending_recovery` 逻辑残留
6. 启动摘要无旧字段 KeyError

产出：

- 重启后对账摘要

---

## 5. 通过标准

Sim-0 通过需要满足：

1. 主程序稳定启动
2. 至少 1 笔信号触发真实 testnet 下单
3. ENTRY / TP / SL 链路完整
4. WS 回写能推进状态
5. 重启后对账无异常
6. PG recovery task 没有异常 pending / failed
7. breaker 没有误触发或漏触发
8. 飞书告警能正常发出，或 mock 验证链路可用

---

## 6. 失败处理原则

如果 Sim-0 失败，不扩大范围，按优先级处理：

1. 订单状态不一致 / 裸奔风险：立即停，优先修执行链
2. recovery task 卡住：修恢复推进
3. breaker 误触发 / 漏触发：修 breaker 重建或判断
4. 告警缺失：修通知
5. 策略表现差：先记录，不在 Sim-0 修

---

## 7. Sim-0 之后

Sim-0 通过后再决定：

1. 是否进入 24h 稳定观察
2. 是否扩大 symbol
3. 是否启动 Sim-1
4. 是否把离线优化候选带入下一轮模拟盘
5. 是否评估 `CORE_ORDER_BACKEND=postgres`

Sim-0 不通过时，不进入策略优化接入，也不扩大 PG 迁移范围。
