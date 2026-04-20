# 实盘执行链风险与缺失功能分析

> 日期：2026-04-21
> 阶段定位：当前仍为**回测优化阶段**，本文档为后续测试盘/实盘准备的架构备忘
> 使用方式：当前不作为主任务执行清单，只作为后续进入实盘阶段前的专项核对材料

---

## 一、结论摘要

当前系统已经具备较完整的实盘组件基础：

- `ExchangeGateway`：真实下单/撤单、订单推送、成交数量推进
- `OrderLifecycleService`：订单状态机、审计日志、状态推进
- `OrderRepository`：订单持久化与订单链追踪
- `ReconciliationService`：启动对账、孤儿单/幽灵单处理
- `CapitalProtectionManager`：下单前资金保护与参数合理性检查

但系统当前的主要风险不在“有没有这些组件”，而在：

**自动执行主链尚未完全收口为单一、稳定、可验证的闭环。**

换句话说，当前更像：

- 回测链路完整
- 实盘组件齐备
- 但“信号 -> 下单 -> 成交 -> 保护单 -> 仓位 -> 对账”的统一编排器不够清晰

因此，后续一旦从回测优化切到测试盘准备，优先级应先落在执行链收口，而不是继续扩展更多策略参数。

---

## 二、当前观察到的系统风险

### 2.1 执行入口分裂

当前至少存在两条较明显的主线：

- `main.py -> SignalPipeline`
  - 偏实时监控、信号处理、通知、状态更新
- `api.py -> ExchangeGateway / OrderLifecycleService`
  - 偏订单管理、手工/接口下单、订单生命周期

风险在于：

- 系统可能同时具备“会看信号”和“会下订单”的能力
- 但未必由同一条主链统一驱动
- 一旦未来接自动执行，容易出现逻辑散落在多个入口中，难以保证一致性

### 2.2 API 下单路径可能先打交易所，再补本地状态

当前 API 下单入口 `POST /api/v3/orders` 看起来直接调用：

- `gateway.place_order(...)`

而不是明确先走：

- `OrderLifecycleService.create_order()`
- 本地落库
- `submit_order()`
- 再提交交易所

风险在于：

- 交易所已有订单，但本地状态链未必完整
- 后续 WebSocket 回写、订单树、审计日志、对账恢复都会依赖“本地先存在订单”

### 2.3 WebSocket 回写协议需要专项核对

当前架构里：

- `ExchangeGateway` 注册了全局订单回调
- `OrderLifecycleService` 提供 `update_order_from_exchange(...)`

但需要重点核对：

- `ExchangeGateway` 回调给出的对象/参数格式
- 是否与 `OrderLifecycleService.update_order_from_exchange()` 的签名完全匹配
- 中间是否存在适配层

### 2.4 ENTRY 成交后保护单闭环不清晰

回测里这一段是完整的：

- ENTRY 成交
- 基于实际成交价生成 TP/SL
- OCO 与剩余数量同步

实盘里需要同样明确的链路：

- ENTRY fill event
- 读取实际成交均价/成交量
- 生成 TP/SL
- 提交 TP/SL 到交易所
- 等待 TP/SL 被交易所确认挂单

当前风险不是“系统做不到”，而是：

- 这条链的统一入口和主控点还不够清晰

### 2.5 Position / Order / Reconciliation 的单一真源不足够明确

当前系统同时存在：

- OrderRepository
- PositionManager
- ExchangeGateway WebSocket 更新
- ReconciliationService

这些组件各自都在推进状态，但需要更清楚地定义：

- 订单状态以谁为准
- 仓位状态由谁主导更新
- 对账是“兜底修复”还是“日常常态同步”

### 2.6 CapitalProtection 可能只覆盖 API 下单，而未必覆盖未来内部自动执行

`CapitalProtectionManager` 的能力本身较完整，但当前主要看到它挂在 API 下单前置检查。

如果未来自动执行链不是通过 API 触发，而是内部服务直接下单，则存在风险：

- API 受保护
- 自动执行链却可能绕开保护

### 2.7 订单与信号的绑定协议较脆弱

当前系统里订单、信号、交易所订单可能通过以下字段关联：

- `signal_id`
- `client_order_id`
- `exchange_order_id`

其中 `clientOrderId -> signal_id` 的映射尤其关键。若协议不统一，会影响订单树、TP/SL 继承关系、对账导入与归因一致性。

---

## 三、当前缺失的关键功能

### 3.1 统一的自动执行编排器

系统当前缺少一个明确的 orchestrator，把以下流程统一起来：

1. Signal Fired
2. Capital Protection Check
3. Create Local Order
4. Submit to Exchange
5. Receive WS/REST Update
6. ENTRY Filled
7. Generate TP/SL
8. Submit TP/SL
9. Update Position State
10. Reconcile if needed

### 3.2 实盘版 `handle_order_filled` 闭环

回测里已经有：

- `ENTRY filled -> handle_order_filled -> TP/SL`

实盘需要同样明确的一条自动链，而不是散在 WebSocket 回调、API 层、手工触发、对账补偿之间。

### 3.3 保护单提交状态机

不仅要“生成 TP/SL 订单对象”，还需要完整状态：

- generated
- submitted
- open
- partially_filled
- filled
- canceled
- rejected
- recovered_after_restart

### 3.4 自动执行模式的运行时入口

当前系统建议后续明确区分运行模式，例如：

- `monitor_only`
- `paper_execution`
- `live_execution`

这样可以避免 `main.py` 既像监控器又像执行器，API 与后台任务对系统边界理解不一致。

---

## 四、对当前阶段的建议

### 4.1 当前不切主线

当前仍处于回测优化阶段，因此建议：

- 不把这些实盘风险问题直接上升为当前主任务
- 只做文档化与风险清单沉淀
- 保留到“测试盘准备阶段”集中处理

### 4.2 进入测试盘前的最低门槛

后续如果进入测试盘准备，建议最低先补齐：

1. 统一执行入口
2. ENTRY fill -> TP/SL 自动挂载闭环
3. WS 回写协议核对
4. Local Order / Position / Reconciliation 单一真源规则
5. CapitalProtection 在自动执行链上的统一接入

---

## 五、建议的后续收口顺序（未来阶段）

### 阶段 L1：协议核对

- 核对 API 下单、本地生命周期、WebSocket 回写三者协议
- 确认 `signal_id / client_order_id / exchange_order_id` 的单一规则

### 阶段 L2：执行 orchestrator

- 增加统一执行编排器
- 把 Signal -> Entry -> Protection -> Position 串起来

### 阶段 L3：保护单闭环

- ENTRY fill 后自动生成并提交 TP/SL
- 明确保护单空窗监控

### 阶段 L4：状态一致性

- 明确 Order / Position / Reconciliation 的真源关系
- 定义恢复优先级

### 阶段 L5：测试盘验收

- 再开始按真实成交表现校准回测参数

---

## 六、结语

当前系统最需要警惕的，不是“没有实盘能力”，而是：

**实盘能力已经分散存在于多个组件中，但自动执行主链还没完全收成一条单一、稳定、可审计的执行闭环。**

这件事现在先记录，不抢占回测优化主线；但未来一旦进入测试盘准备，它应当成为优先级最高的工程收口任务之一。
