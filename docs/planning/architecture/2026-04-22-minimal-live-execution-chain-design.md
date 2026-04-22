# 最小实盘执行主链设计稿

> 日期：2026-04-22
> 阶段定位：测试盘 / 小仓位实盘前的最小执行主链设计
> 目标：把当前已冻结的 `ETH 1h LONG-only` 主线，整理到“随时可以进入模拟盘 / 小仓位验证”的工程状态

---

## 一、设计目标与非目标

### 1.1 设计目标

当前策略研究阶段已经基本收口，后续重点不再是继续加参数，而是把执行链整理成**单入口、可追踪、可恢复、可告警**的最小闭环。

本设计稿的目标是：

1. 明确自动执行的唯一主链
2. 明确各模块职责边界，避免执行逻辑散落
3. 明确 `ENTRY filled -> TP/SL 挂载` 的危险空窗状态
4. 为后续测试盘 / 小仓位实盘提供最小实现顺序

### 1.2 非目标

本稿**不处理**以下内容：

1. 不设计新的策略参数或 regime filter
2. 不把 API 下单链改造成自动执行入口
3. 不在第一版默认加入“保护单失败后自动强平”
4. 不试图一次性解决所有高级恢复与自愈逻辑

---

## 二、核心决策

### 2.1 自动执行入口

**决策**：自动执行必须由**信号触发**，但不直接走 API。

具体含义：

- `SignalPipeline` 是信号触发源
- API 只保留给手工操作 / 查询 / 调试 / 人工干预
- 自动执行主链由内部服务直接驱动

### 2.2 主编排层

**决策**：新增一个很薄的 `ExecutionOrchestrator`，负责整笔交易的执行编排。

其职责不是重做订单状态机，而是把现有能力串成单一闭环。

### 2.3 订单事实层

**决策**：继续复用 `OrderLifecycleService` 作为订单事实层。

它继续承担：

- 订单创建
- 状态机推进
- 订单仓库持久化
- 审计日志
- 交易所回写后的订单状态更新

### 2.4 API 定位

**决策**：`POST /api/v3/orders` 不再作为未来自动执行主链的一部分。

理由：

- 当前 API 下单路径直接调用 `gateway.place_order(...)`
- 存在“先打交易所、后补本地状态”的风险
- API 更适合作为人工控制与调试接口，而不是内部自动执行主控链

---

## 三、模块职责边界

### 3.1 SignalPipeline

负责：

1. 接收实时 K 线
2. 运行策略与过滤器
3. 做基础风控试算
4. 产出 `SignalResult`

不负责：

1. 不直接下单
2. 不负责 TP/SL 自动挂载
3. 不负责交易所状态恢复

### 3.2 ExecutionOrchestrator

负责：

1. 接收 `SignalResult`
2. 执行 `CapitalProtection` 检查
3. 创建 `ExecutionIntent`
4. 调用 `OrderLifecycleService.create_order()` 创建本地主单
5. 调用 `ExchangeGateway.place_order()` 提交 ENTRY
6. 回填 `exchange_order_id`
7. 监听 `ENTRY filled`
8. 生成并提交 TP/SL
9. 管理 `entry_filled_unprotected -> protected / recovery_required` 流程

不负责：

1. 不计算策略信号
2. 不重做订单状态机
3. 不直接承担复杂仓位计算逻辑

### 3.3 OrderLifecycleService

负责：

1. 管理订单从 `CREATED -> SUBMITTED -> OPEN -> FILLED/CANCELED/...`
2. 记录订单审计日志
3. 对外提供订单查询与状态推进接口
4. 接收交易所回写并更新订单事实

不负责：

1. 不决定是否应该执行这笔信号
2. 不决定 ENTRY 成交后是否挂 TP/SL
3. 不处理整笔交易的恢复策略

### 3.4 ExchangeGateway

负责：

1. 与交易所交互（下单 / 撤单 / 查询 / WS 推送）
2. 提供成交和订单更新原始事实

不负责：

1. 不维护整笔交易编排状态
2. 不承担业务决策

### 3.5 Reconciliation / CapitalProtection

`CapitalProtection`：

- 作为执行前保护检查
- 必须由 `ExecutionOrchestrator` 显式调用
- 不能只依赖 API 路径

`ReconciliationService`：

- 作为兜底修复层
- 不作为日常主驱动
- 重点处理重启恢复、孤儿单、未保护仓位等问题

### 3.6 信号层 TP 与执行层 TP/SL 的边界

**决策**：不新增专门的执行层 `TPP` / `take_profit_orders` 独立事实表。

当前系统里已经存在两层不同含义的 TP 数据，后续必须明确区分：

1. **信号层 TP**
   - 现有 `signal_take_profits` 表继续保留
   - 对应 `SignalResult.take_profit_levels`
   - 作用是研究记录、前端展示、建议目标位查看
   - 它不是交易所真实订单，也不承担生命周期管理

2. **执行层 TP/SL**
   - 真实执行的 `TP1 / TP2 / SL` 一律作为 `orders` 表中的子订单存在
   - 通过 `order_role`、`parent_order_id`、`group_id / oco_group_id` 组织订单树
   - 这些订单需要承接：
     - 本地订单状态机
     - `client_order_id / exchange_order_id`
     - WebSocket 回写
     - OCO / 父子关系
     - 审计日志
     - 对账恢复

一句话：

- `signal_take_profits` = **建议目标位**
- `orders(order_role=TP1/TP2/SL)` = **真实执行保护单 / 止盈单**

因此，后续 PG first scope 应迁移/重建的是执行层 `orders` 事实链，而不是额外设计一张重复语义的 TP 专表。

---

## 四、最小状态流

### 4.1 ExecutionIntent 状态流（建议）

第一版建议只维护一个很薄的执行意图层：

- `created`
- `blocked`
- `submitting`
- `submitted`
- `handed_off`
- `failed`

解释：

- `created`：系统决定要尝试执行这笔交易
- `blocked`：保护检查未通过，不进入交易所
- `submitting`：正在向交易所发 ENTRY
- `submitted`：交易所已接受 / 已拿到订单标识
- `handed_off`：已交给订单生命周期和后续保护单闭环
- `failed`：提交阶段失败

### 4.2 主链事件流

最小实盘执行主链如下：

1. `SignalPipeline` 产出 `SignalResult`
2. `ExecutionOrchestrator` 接收信号
3. 执行 `CapitalProtection`
4. 创建 `ExecutionIntent(created)`
5. 调 `OrderLifecycleService.create_order()` 创建本地主单
6. `ExecutionIntent -> submitting`
7. 调 `ExchangeGateway.place_order()` 提交 ENTRY
8. 回填 `exchange_order_id`
9. 推进订单到 `submitted/open`
10. 监听 `ENTRY filled`
11. 进入 `entry_filled_unprotected`
12. 基于真实成交价和成交量，生成 `orders` 子单（`TP1 / TP2 / SL`）并提交
13. 若保护单全部确认挂单，状态转为 `protected`
14. 若失败且短时重试后仍未完成，转为 `recovery_required`

---

## 五、高风险空窗状态

### 5.1 为什么必须单独定义

`ENTRY filled` 之后、`TP/SL` 尚未全部挂好之前，是整条实盘链最危险的状态：

- 真实仓位已存在
- 但保护单尚未全部生效
- 若系统把这个状态混在普通“处理中”里，就无法监控与恢复

### 5.2 明确状态：`entry_filled_unprotected`

建议在 `ExecutionOrchestrator` 中引入这个业务状态。

进入条件：

- ENTRY 已确认成交
- 但保护单尚未全部提交成功并确认 `open`

退出条件：

- 所有必须的 TP/SL 已成功挂单并确认
- 交易进入 `protected`

要求：

1. 进入该状态必须写高优先级日志
2. 必须触发监控 / 告警
3. 必须支持短时重试
4. 未退出前不能把该笔交易标记为“执行完成”

### 5.3 超时处理原则

第一版建议采用：

1. **短时自动重试**：立即 / 1 秒 / 3 秒等轻量重试
2. **失败后进入 `recovery_required`**
3. **高优先级告警**

第一版**不默认自动强平**，原因：

- 自动强平会引入新的复杂失败分支
- 当前阶段应先把危险状态识别、重试、告警做好
- 强平策略可作为第二阶段能力单独设计

---

## 六、当前已知代码风险（基于现有实现）

### 6.1 API 下单路径不适合作为自动执行主链

当前 `POST /api/v3/orders` 主流程仍直接调用：

- `gateway.place_order(...)`

这意味着自动执行若复用 API 路径，会面临：

- 交易所已有订单，但本地生命周期未必完整
- 后续 WS 回写 / 审计 / 对账 / 恢复都会受影响

### 6.2 ExchangeGateway -> OrderLifecycleService 的回写契约需专项核对

当前存在明显风险：

- `ExchangeGateway.set_global_order_callback()` 回调看起来传的是 `Order`
- `OrderLifecycleService.update_order_from_exchange()` 需要的是 `order_id + exchange_order_data`

这意味着现有 WS 回写协议可能并未完全对齐。

**这应作为第一优先级核对项。**

### 6.3 CapitalProtection 不能只挂在 API 前置检查

当前 `CapitalProtection` 明显主要用于 API 下单前置 dry-run / pre-check。

后续若自动执行不走 API，则必须由 `ExecutionOrchestrator` 显式调用，确保：

- 手工/API 有保护
- 自动执行也同样有保护

---

## 七、第一版实现顺序（推荐）

### P0：协议与边界收口

1. 明确 API 不进入自动执行主链
2. 明确 `SignalPipeline -> ExecutionOrchestrator -> OrderLifecycleService`
3. 核对并修正 WS 回写契约

### P1：最小执行链

1. 引入 `ExecutionIntent`
2. 建立 `SignalResult -> ExecutionIntent -> Entry Order` 主链
3. 实现执行前保护检查
4. 实现“先本地创建主单，再提交交易所”

### P2：保护单闭环

1. 监听 `ENTRY filled`
2. 生成并提交 TP/SL
3. 明确 `entry_filled_unprotected`
4. 完成 `protected / recovery_required` 状态流

### P3：恢复与验收

1. 对账识别未保护仓位
2. 重启恢复策略
3. 小仓位 / 模拟盘验收

---

## 八、第一版验收标准

第一版不求复杂，只求最小闭环成立：

1. 自动执行不经过 API
2. 每笔执行先有本地执行意图和本地主单
3. ENTRY 成交后能自动挂 TP/SL
4. `entry_filled_unprotected` 可见、可告警、可重试
5. 保护单挂载失败会进入 `recovery_required`
6. 整条链路有可追踪日志与审计记录

---

## 九、当前结论

**下一阶段的核心不是继续优化策略参数，而是把当前主线的实盘执行闭环收口。**

也就是说：

- 策略层：已基本冻结
- 执行层：仍需收口
- 风险最大的不是“信号是否继续赚钱”，而是“真实成交后保护单能否稳定接上”

因此，后续进入测试盘前，优先级应明确转为：

**WS 回写契约 -> ExecutionOrchestrator -> ENTRY/TP/SL 闭环**
