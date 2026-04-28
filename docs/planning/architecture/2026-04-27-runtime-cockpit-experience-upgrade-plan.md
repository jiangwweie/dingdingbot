# 2026-04-27 Runtime Cockpit 体验升级规划

> 状态：规划中
> 范围：Runtime 模块前端体验与运行治理表达，不改变当前 PG execution truth
> 目标：把 Runtime 从“工程监控面板”升级为“资金、风险、执行因果链优先”的交易驾驶舱

---

## 1. 核心判断

Research 模块是实验室，允许失败、试错、比较、沉淀候选策略。

Runtime 模块是驾驶舱，核心任务不是解释系统架构，而是在模拟盘或实盘运行时回答三件事：

1. 钱现在安全吗？
2. 仓位和执行链有没有失控？
3. 一旦异常，用户能否快速判断并接管？

当前 Runtime UI 的主要问题不是数据完全缺失，而是表达仍偏 DevOps：

1. 首屏工程字段过多，例如 hash、backend summary、repo 类型等
2. 资金、盈亏、回撤、仓位暴露没有成为第一视觉层级
3. `signals -> intents -> orders -> positions` 的因果链没有被产品化表达
4. health/events 更像启动校验和日志面板，不像交易风险监控
5. 人工接管动作尚未形成分级设计，直接做“一键清仓”风险过高

因此 Runtime 下一阶段不应做装饰化大屏，也不应直接开放危险交易操作；应先建立可信、可读、可接管的交易驾驶舱。

---

## 2. 设计价值观

### 2.1 Money-Centric

Runtime 首屏必须优先回答资金问题：

1. 当前总权益
2. 未实现盈亏
3. 今日或本观察窗口盈亏
4. 最大回撤预算使用率
5. 当前仓位暴露
6. 保证金 / 杠杆风险

工程健康仍然重要，但应在“风险和资金摘要”之后呈现。

### 2.2 环境强隔离

SIM 和 LIVE 必须通过全局视觉语义区分：

1. 顶部环境条
2. 导航或 Header 色彩差异
3. 关键按钮文案差异
4. 操作确认弹窗中重复标明当前环境

目标是在 0.1 秒内让用户知道自己正在看模拟盘还是实盘，降低误操作风险。

### 2.3 异常优先

Runtime 不是报表系统。只要存在健康降级、熔断、订单恢复任务、交易所断连、通知不可用、PG 探针失败等异常，页面顶部应出现全局告警。

正常状态应低噪音，异常状态应高可见。

### 2.4 因果链优先

交易执行不是孤立对象。Runtime 必须能解释：

```text
Signal -> ExecutionIntent -> Order Chain -> Position -> Exit / Recovery
```

用户看到一个仓位时，应能反查：

1. 哪个信号触发
2. 是否经过风控拦截
3. 生成了哪些订单
4. 成交价格和建议价格差多少
5. 当前保护单是否完整

### 2.5 人工接管分级

人工接管是必要能力，但必须分层：

1. 暂停新信号 / 暂停新开仓
2. 单仓市价平仓
3. 全局紧急清仓

越危险的操作越需要后端幂等、二次确认、审计日志、失败恢复与明确状态反馈。

---

## 3. 页面级规划

### 3.1 `/runtime/portfolio`：资金与风险指挥中心

定位：Runtime 最重要的资金页面。

第一阶段优先增强：

1. KPI 看板
   - 总权益
   - 未实现盈亏
   - 当前保证金占用
   - 日内 / 观察窗口盈亏，如后端口径明确
   - 最大回撤预算使用率
2. 风险进度条
   - 使用率 `< 50%`：绿色
   - `50% - 80%`：黄色
   - `> 80%`：红色
3. 当前持仓表增强
   - 交易对
   - 方向
   - 数量
   - 开仓均价
   - 当前 mark price
   - 未实现盈亏
   - 浮动盈亏比例
   - 持仓时长
   - 保护单状态，如可得
4. 工程字段降级
   - repo / backend / hash 等不进入主视图

暂不直接做：

1. 全局一键清仓
2. “强平”文案按钮

后续可做：

1. 单仓市价平仓，必须二次确认
2. 持仓详情页展示对应信号和订单链

### 3.2 `/runtime/overview`：交易日状态摘要

定位：Runtime 首页，不是配置快照页。

第一阶段应重组为：

1. 顶部环境条
   - SIM / LIVE
   - runtime profile
   - 是否 frozen
2. 交易日摘要
   - 当前活跃仓位数
   - 今日成交笔数，如可得
   - 当前活跃信号数
   - 未完成 execution intents
   - pending / retrying recovery tasks
3. 系统心跳
   - exchange heartbeat
   - PG health
   - websocket / ticker freshness
   - notification health
4. 告警中心
   - health degraded
   - recovery blocking
   - stale data
   - circuit breaker active

降噪处理：

1. profile hash 折叠
2. backend summary 折叠
3. repo class / implementation details 折叠

### 3.3 `/signals` 与 `/execution`：信号到执行的因果链

定位：解释“为什么系统做了这个动作”。

`/signals` 第一阶段字段：

1. 生成时间
2. 交易对
3. 方向
4. 来源策略
5. 建议价格 / 风控参考
6. 状态
   - 等待执行
   - 已执行
   - 被风控拦截
   - 已过期
   - 已撤销 / superseded
7. 对应 intent / order 入口

`/execution` 第一阶段字段：

1. 委托时间
2. 对应 signal / intent
3. 订单角色
   - ENTRY
   - TP
   - SL
4. 订单类型
5. 请求数量
6. 已成交数量
7. 平均成交价
8. 建议价 / 委托价 / 成交价差异
9. 滑点提示，如可计算
10. 执行状态

滑点监控建议：

1. 第一阶段只展示差值和百分比
2. 超过阈值时黄色提示
3. 阈值先作为前端展示常量或只读配置，后续接 runtime profile

### 3.4 `/runtime/health` 与 `/runtime/events`：交易化监控

定位：从工程启动校验转为交易运行状态解释。

`/runtime/health` 应优先展示：

1. 交易所连接状态
2. 最新行情 / 账户快照新鲜度
3. PG 主线健康
4. Recovery blocking task
5. 熔断器状态
6. 通知通道状态

第二阶段再补：

1. 交易所 REST latency
2. API rate limit 使用率
3. WebSocket 延迟

`/runtime/events` 应做业务翻译：

| 工程事件 | UI 文案 |
| --- | --- |
| startup reconciliation passed | 系统对账完成 |
| no recovery task | 当前无待恢复执行任务 |
| pg health degraded | PostgreSQL 连接异常 |
| notification degraded | 通知通道异常 |
| circuit breaker active | 熔断器已阻止新开仓 |

---

## 4. 紧急控制面板分期

### Phase A：暂停新信号 / 新开仓

优先级最高，风险最低。

语义：

1. 停止接收或执行新的开仓信号
2. 不动现有仓位
3. 不撤保护单
4. 不停止只读观测

前端要求：

1. Header 常驻状态
2. 点击需要确认
3. 成功后页面明确显示“已暂停新开仓”
4. 所有相关操作写入事件日志

后端前置：

1. 明确 pause flag 存储位置
2. 执行链在创建 intent 或下单前检查 pause flag
3. 幂等

### Phase B：单仓市价平仓

在 portfolio 持仓表中提供。

要求：

1. 二次确认
2. 显示当前 symbol / direction / qty
3. 明确 SIM / LIVE
4. API 返回订单 ID 与执行状态
5. 失败时提示下一步动作

### Phase C：全局紧急清仓

暂不进入第一阶段。

只有在以下能力成熟后才开放：

1. 所有活跃仓位来源可信
2. 单仓平仓幂等稳定
3. 失败恢复路径清晰
4. 审计日志完整
5. LIVE 环境下强确认机制明确

---

## 5. 优先级路线

### P0：Runtime Cockpit 可读性与可信度

1. 全局 SIM / LIVE 环境条
2. Overview 首屏改为资金、风险、心跳、告警
3. Portfolio 增强风险 KPI 与持仓表
4. 工程字段默认折叠
5. 告警横幅统一化

### P1：交易因果链

1. Signals 状态中文化
2. Execution 列表接入 signal / intent / order chain
3. 滑点展示
4. 仓位反查信号和订单

### P2：人工接管基础

1. 暂停新开仓
2. 单仓市价平仓设计与接口
3. 审计事件落地

### P3：深度运行治理

1. API latency
2. rate limit 使用率
3. 熔断器 reset/resume
4. recovery task 可视化与手动处理
5. Feishu 运行日报 / 异常报告

---

## 6. 非目标

当前阶段不做：

1. 不把 Runtime 做成装饰化监控大屏
2. 不在第一阶段直接开放一键清仓
3. 不让前端直接修改 runtime profile
4. 不把 Research 参数编辑能力搬进 Runtime
5. 不把工程 hash / repo / backend implementation details 放回首屏
6. 不在没有后端口径前强行展示“精确 Daily PnL”

---

## 7. 验收标准

### 用户体验验收

1. 用户进入 Runtime 首页，3 秒内能判断当前是 SIM 还是 LIVE
2. 用户进入 Runtime 首页，首屏能看到资金、风险、心跳和异常摘要
3. 用户看到一个持仓，能理解当前盈亏、风险和持仓时长
4. 用户看到一个订单，能反查它对应的信号和执行意图
5. 异常状态不会藏在折叠面板或工程日志里

### 安全验收

1. 所有危险操作必须二次确认
2. LIVE 操作必须明确显示 LIVE 环境
3. 暂停 / 平仓类动作必须幂等
4. 操作必须有事件记录
5. 前端不能伪造“操作成功”，必须以后端状态为准

### 工程验收

1. 不改变 PG execution truth 的既有语义
2. 不引入 Research -> Runtime 的反向污染
3. 不新增前端直接写 runtime profile 的路径
4. Console 页面保持紧凑、可扫读、中文主文案

---

## 8. 与当前 Research UI 优化的关系

Research UI 优化和 Runtime Cockpit 优化是同一轮前端产品化工作的两条线，但边界不同：

| 模块 | 角色 | 核心问题 |
| --- | --- | --- |
| Research | 实验室 | 这个策略值不值得继续研究？ |
| Runtime | 驾驶舱 | 当前资金和执行链是否安全？ |

Research 可以容忍失败和试错；Runtime 必须强调资金敏感、异常即时、人工接管。

因此两条线可以共享视觉规范和组件能力，但不能共享业务动作：

1. Research 不能修改 runtime profile
2. Runtime 不做策略参数试验
3. Candidate promote 未来必须经过独立发布 / 冻结动作
4. Runtime 的暂停和平仓动作不属于 Research 管理范围

