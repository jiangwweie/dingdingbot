---
title: Crypto Strategy Universe General Capability Design
status: OWNER_REVIEW_REQUIRED
authority: NOT_CURRENT_AUTHORITY
date: 2026-07-28
revision: 2
---

# Crypto Strategy Universe General Capability Design

## 决策门

本文档描述 **加密合约 StrategyUniverse 通用能力** 的完整目标设计。
当前仅允许编写和审查文档，不授权修改生产代码、测试代码、PostgreSQL、
Tokyo 服务或交易所状态。

只有 Owner 明确确认本文档、实施计划和测试用例后，才允许按测试优先顺序
开始编码。最终生产标的清单不属于当前设计输入；每个策略组的最终清单将在
生产播种前由 Owner 固定。

当前代码、PostgreSQL、交易所只读事实和 `docs/current/*` 仍是唯一运行权威。

## 核心结论

本次改造建立一个 **静态策略语义 + 版本化无序 Universe + 单一 Trading
Kernel** 的结构：

```text
静态 Strategy Registry
  只定义策略、事件、方向、Facts、保护和退出语义

版本化 StrategyUniverse
  只定义某个 Event 当前允许产生新 Signal 的合约集合

Trading Kernel
  继续负责 Signal、Claim、Ticket、命令、订单、持仓、结算和 Review
```

该结构不增加动态 Python 插件加载、不建设通用工作流引擎、不引入美股运行
链、不自动修改交易所杠杆或保证金模式，也不建立兼容旧候选池的双轨读取。

### 业务结果

1. **每个策略 Event 使用独立标的池**，目标规模为 **8 个**，硬上限为
   **10 个**。
2. **Universe 只表达资格**；配置顺序、数据库插入顺序和查询顺序都不构成
   交易优先级。
3. 一次配置提交后，系统自动完成 **只读认证、市场数据预热、原子激活**。
4. 标的池切换只影响新的 Signal 和 Entry；已经存在的 Ticket 继续沿冻结
   的订单和持仓链闭环。
5. 新合约若需要交易所侧设置，系统只写 PostgreSQL Monitor
   **`NEEDS_INTERVENTION`**，并携带稳定的
   `owner_action_required` blocker code，由代理汇报；Owner 手工处理后，
   系统只读复核并自动继续。
6. 相关性计算、聚类、拒绝和动态降仓全部不进入本次运行时实现，只保留在
   研究设计中。
7. 美股合约接入继续暂缓，当前主线不播种、不调度、不认证任何美股标的。

## 已知客观事实

### 当前运行链

当前系统只有一条生产交易链：

```text
Observation
-> StrategySignal
-> Readiness/Authority
-> CapacityClaim
-> immutable Ticket
-> durable Exchange Command
-> protected lifecycle
-> reconciliation
-> settlement
-> review
```

四个持久 Worker 分别拥有 Observation、Entry、Lifecycle 和 Reconciliation
职责。生产 Worker 共享 `CPUQuota=100%`、`MemoryMax=1G` 和
`TasksMax=128` 资源边界；健康空闲运行不得创建 JSON 或 Markdown 文件。
（来源：`docs/current/TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md`）

### 当前候选标的耦合

当前 `RegisteredStrategyContract` 同时持有策略语义和
`candidate_instruments`，标的成员还带有 `priority_rank`。Registry seed、
Runtime Authority seed、Observation、Entry 查询和生产 Adapter 构造均从
这份静态列表派生。

当前 Entry 候选排序还包含 `candidate_scope_priority`；因此配置顺序会实际
影响交易竞争结果。这与 Owner 已确认的“Universe 顺序不构成优先级”不一致。

当前生产 Adapter 还校验固定的唯一标的数量。这意味着增加一个未编入代码的
合约并不是纯配置动作。

### 当前策略注册合同

现行 Registry 合同把 `candidate_instruments` 列为 Registry 字段，同时明确
Registry 不得创建 Signal、Ticket、命令、订单或持仓。
（来源：`docs/current/strategy-group-handoffs/STRATEGYGROUP_REGISTRY_CONTRACT.md`）

本文档获批并完成实现后，需要同步修订该当前合同：候选资格将由 PostgreSQL
StrategyUniverse 拥有，Registry 不再拥有成员清单。

### 当前部署边界

Owner 已明确当前工程验证阶段采用 **全平后部署**：

```text
P1 Settlement fairness / exact order attribution 修复先独立验收
-> SOL/AVAX 等剩余交易所持仓和订单自然全平
-> closure-only、Entry fenced 发布
-> BTC 通过正常事件链完成 Settlement/Review
-> 所有持仓和 Ticket 完整闭环
-> 停止旧版本
-> 前向迁移和播种
-> 启动安全 Worker
-> 只读认证
-> 最后启用 Entry
```

因此本次设计不承担旧运行 Ticket、旧 Signal、旧候选池或旧表结构的运行时
兼容责任。Universe `0002` 不得与 P1 closure-only 发布合并；部署前必须
满足现行 flat-release 和 exchange-flat 门，并证明不存在
`SETTLEMENT_PENDING`、`REVIEW_PENDING` 或不完整 Review。
（衔接设计：
[`2026-07-28-reconciliation-settlement-review-attribution-repair-design.md`](2026-07-28-reconciliation-settlement-review-attribution-repair-design.md)）

## 基于事实的架构判断

### 为什么不能只增加一层配置胶水

如果只在当前 Registry 外面套一层 JSON/YAML 或映射器，系统会同时保留
静态候选清单、配置清单、候选 Scope 和 Adapter 映射四份成员事实。结果是：

- 不同入口可能读到不同标的池；
- 旧 Signal 在切换后仍可能进入 Entry；
- 新合约仍需要修改 Adapter 代码；
- 优先级语义可能继续从行顺序泄漏；
- Ticket 无法证明创建时使用了哪个资格集合；
- 每次扩展都需要再增加同步代码。

因此本次选择 **删除重复权威并移动职责**，而不是添加兼容层。

### 方案比较

| 方案 | 资格权威 | 切换是否改代码 | 运行复杂度 | 追溯能力 | 结论 |
| --- | --- | ---: | ---: | ---: | --- |
| 保留 Registry 静态清单，仅扩大币种 | Registry 代码 | 是 | 低 | 低 | 拒绝 |
| 外置配置覆盖 Registry | 代码与配置双权威 | 否 | 高 | 中 | 拒绝 |
| 版本化 PostgreSQL Universe，Registry 只管语义 | PostgreSQL 单权威 | 否 | 中且有界 | 高 | 采用 |
| 动态插件平台与通用工作流引擎 | 插件包与编排平台 | 否 | 很高 | 高 | 拒绝 |

## 目标职责模型

### 三层职责

| 层 | 唯一职责 | 允许变化 | 明确禁止 |
| --- | --- | --- | --- |
| **Strategy Registry** | 策略组、事件、方向、Facts、信号、保护与退出语义 | 策略语义升级时随代码发布 | 候选成员、成员顺序、运行激活 |
| **StrategyUniverse** | Event 的无序候选资格集合、认证、预热和当前激活指针 | 低频配置切换 | 信号公式、下单、持仓和退出 |
| **Trading Kernel** | Signal 到 Review 的唯一执行和审计链 | 内核工程升级 | 从配置文件直接下单、策略旁路 |

### 不新增 StrategyPlugin 包装层

当前代码已经有静态 detector 注册和 Strategy Registry。为避免胶水层，本次
不再创建一个仅转发 `detector_for()`、Registry 和 Universe 的
`StrategyPlugin` 对象。

新增策略仍按显式工程接入完成：

1. 增加纯 detector 和 Facts；
2. 注册不可变 Strategy/Event 语义；
3. 完成策略测试；
4. 单独提交该 Event 的 Universe 配置。

“可插拔”在这里表示 **静态策略组可以独立启停并拥有独立 Universe**，不表示
运行时动态导入未知 Python 代码。

## 不变量

### Universe 不变量

1. 一个 Universe 只属于一个 `event_spec_id`。
2. 成员集合必须为 **1 至 10 个**不同的 Binance USD-M USDT 永续合约。
3. 成员集合是数学集合；输入顺序不进入 semantic digest。
4. 同一 Event、同一成员集合的重复提交是幂等操作，不创建新版本。
5. 一个 Event 同时最多一个 Active Universe。
6. 全系统同时最多一个 Warming Universe，以限制认证和行情预热负载。
7. 未完成认证和预热的 Universe 不得激活。
8. 激活必须在单个 PostgreSQL 事务内切换当前指针和 Scope 权限。
9. Active Universe 持续可用，直到新版本完整激活；不存在半切换状态。
10. Retired Universe 永远不能重新变成 Active；相同集合以后重新采用时创建
    新版本。只有当前 Active 或 Warming 集合相同的重复提交才幂等命中。

### 交易链不变量

1. Warming Scope **只读市场数据，不产生 Signal**。
2. 只有 Active Universe 成员的 Active Scope 可以产生新 Signal。
3. Entry 在创建 Claim/Ticket 前重新校验 Signal 对应 Universe 仍是当前版本。
4. ENTRY 命令派发前再次校验当前 Universe，关闭“切换与派发竞争”窗口。
5. Universe 切换不删除旧 Signal；旧 Signal被明确标记为不再具备 Entry 资格。
6. Universe 切换不修改已有 Claim、Ticket、命令、订单、持仓和退出规则。
7. 已移除标的上的已有 Ticket 继续由 Lifecycle 和 Reconciliation 处理。
8. 每个 Ticket 继续遵守 Netting Domain、资金预算、止损、5x 和 Cross 边界。
9. 每次交易所写入仍必须先有一个 durable Exchange Command。
10. Universe 逻辑不得新增直接交易所写入口。

### 人工动作不变量

1. 系统不得为 Universe 接入创建 `SET_LEVERAGE` 或保证金模式修改命令。
2. 系统只读确认产品状态、账户持仓模式、Cross 和精确 **5x**。
3. 确定性配置不匹配写入 Monitor `NEEDS_INTERVENTION`，certification
   状态和 blocker code 明确标记 `owner_action_required`。
4. 短暂网络失败只进入自动重试，不伪装成人工待办。
5. Owner 完成交易所设置后不需要导入文件或填写数据库；下一次只读认证自动
   消除阻塞并继续预热/激活。

## 领域模型

### StrategyUniverseVersion

```python
class StrategyUniverseVersion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    universe_version_id: str
    strategy_group_id: str
    event_spec_id: str
    universe_version: int
    exchange_instrument_ids: tuple[str, ...]
    semantic_digest: str
    lifecycle_state: Literal["warming", "active", "retired"]
    installed_at_ms: int
```

领域构造器必须：

- 规范化并按 canonical instrument id 排序；
- 拒绝重复成员、空集合和超过 10 个成员；
- 拒绝非 `binance-usdm:*USDT:perpetual` 标识；
- 使用排序后的成员集合计算 digest；
- 不保存 `rank`、`weight` 或列表顺序。

### UniverseCurrent

```python
class UniverseCurrent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_spec_id: str
    universe_version_id: str
    semantic_digest: str
    activation_generation: int
    activated_at_ms: int
```

`activation_generation` 只用于并发 CAS 和读取新鲜度，不是策略版本。

### InstrumentCertification

```python
class InstrumentCertification(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    runtime_profile_id: str
    exchange_instrument_id: str
    status: Literal[
        "eligible",
        "owner_action_required",
        "temporarily_unavailable",
    ]
    product_rules_digest: str | None
    configured_leverage: int | None
    margin_mode: str | None
    position_mode: str | None
    blocker_code: str | None
    observed_at_ms: int
    valid_until_ms: int
```

认证是账户和 Runtime Profile 相关的当前投影，不是永久合约属性。产品规则仍
写入现有 `brc_instrument_rules_current`。

### RuntimeScopeSnapshot

现有单一 `enabled` 需要替换为两个明确权限：

```text
observation_enabled
entry_enabled
```

| Scope 状态 | observation_enabled | entry_enabled | 行为 |
| --- | ---: | ---: | --- |
| Warming | true | false | 获取闭合行情并证明 Facts 就绪，不发 Signal |
| Active | true | true | 正常 Observation 和 Signal |
| Retired | false | false | 不再调度，不影响已有 Ticket |

Scope 还冻结 `universe_version_id`、`warm_ready_at_ms`、
`warm_readiness_digest` 和 `warm_valid_until_ms`。

## 标的身份与 Adapter

### 问题

当前 Adapter 依赖启动时构造的固定 instrument map，并校验固定唯一数量。
即使 PostgreSQL 成员可以变化，未知合约仍无法在不改代码的情况下转换为
CCXT symbol。

### 决策

引入一个 **严格、纯函数式 Binance USD-M InstrumentCodec**：

```text
binance-usdm:BTCUSDT:perpetual
-> BTC/USDT:USDT
```

Codec 只解析固定产品语法，不读取 Universe，也不访问 PostgreSQL。它允许
Adapter 按 Ticket 或 Scope 冻结的 canonical id 解析任何已认证 USDT 永续
合约。

该 Codec 不是通用多交易所抽象。未来真的接入第二 Venue 或第二产品类型时，
再增加显式 codec 并由 `venue_id + contract_type` 选择；当前不提前建设动态
路由平台。

### 结果

- 新 Universe 标的不再要求修改 Adapter 映射；
- 已移除标的上的旧 Ticket 仍可解析并完成退出；
- Runtime 不需要每次交易所请求前查 PostgreSQL；
- 不再存在 `_EXPECTED_UNIQUE_INSTRUMENTS` 一类固定数量断言。

## PostgreSQL 权威模型

### 表结构

| 表或现有对象 | 类型 | 职责 | 数据增长 |
| --- | --- | --- | --- |
| `brc_strategy_universe_versions` | 新增、不可变为主 | 版本身份、digest、生命周期时间 | 每次有效切换 1 行 |
| `brc_strategy_universe_members` | 新增、不可变 | 无序成员集合 | 每版本最多 10 行 |
| `brc_strategy_universe_current` | 新增、当前投影 | 每个 Event 的唯一 Active 指针 | 每个 Event 1 行 |
| `brc_instrument_certification_current` | 新增、当前投影 | Profile + instrument 的最新只读认证 | 每个已知 instrument 1 行 |
| `brc_comparative_projection_current` | 新增、当前投影 | MPG/MI 每个闭合周期的共享比较输入 | 每个比较 Event/版本 1 行 |
| `brc_runtime_scopes_current` | 修改、调度投影 | Warming/Active 调度和 readiness | 每版本每成员最多 1 行，Retired 行不再进入调度索引 |
| `brc_instruments` | 修改、身份目录 | 已知 canonical instrument 与认证前状态 | 每个见过的 instrument 1 行 |
| Signal/Claim/Ticket 表 | 修改、交易账本 | 冻结 Universe 因果身份 | 每笔链路 1 行 |

### 删除重复权威

`brc_strategy_candidate_scopes` 应从新基线删除。它的成员资格职责由
`brc_strategy_universe_members` 接管，调度职责由
`brc_runtime_scopes_current` 接管。

Registry seed 不再写候选成员。Runtime Authority seed 不再根据 Registry
展开静态 Scope。生产播种改为：

```text
静态策略语义 seed
-> Runtime Profile / Owner Policy seed
-> Owner 确认后的 Universe 配置提交
-> 自动认证、预热和激活
```

### 约束和索引

1. `event_spec_id + universe_version` 唯一。
2. 对 `lifecycle_state IN ('warming', 'active')` 的
   `event_spec_id + semantic_digest` 建部分唯一索引；当前相同集合幂等，已
   retired 集合以后可以形成新的版本身份。
3. `universe_version_id + exchange_instrument_id` 为成员主键。
4. `brc_strategy_universe_current.event_spec_id` 为主键。
5. 对 `lifecycle_state = 'warming'` 建立常量表达式部分唯一索引，保证全局
   同时最多一个 Warming 版本。
6. Runtime Scope 调度继续使用
   `(observation_enabled, next_observation_due_at_ms, lease_expires_at_ms)` 有界索引。
7. Signal/Claim/Ticket 的 Universe 字段在本次 flat-only 前向迁移后为
   **非空**，不增加 nullable 兼容分支。

### 最小交易追溯字段

新产生的 Signal、CapacityClaim 和 Ticket 都冻结：

```text
universe_version_id
universe_semantic_digest
```

订单、成交、仓位、Settlement 和 Review 继续通过 Ticket 关联，不重复写
Universe 字段。完整因果路径为：

```text
UniverseVersion
-> StrategySignal
-> CapacityClaim
-> Ticket
-> ExchangeCommand
-> venue order / trade fill / position
-> Settlement
-> Review
```

该模型满足本项目关注的持仓、订单和成交追溯，同时避免为低频配置动作建设
重型审计平台。

## Owner Policy 与资格边界

当前 Owner Policy scope 若冻结具体 `runtime_scope_ids`，每次 Universe 切换
都必须升级 Policy，形成第二份成员权威。

新设计把 Owner Policy scope 调整为稳定的：

```text
runtime_profile_id
allowed_event_spec_ids
supported_side / capital / leverage / margin boundaries
```

成员资格在 Entry 时通过 `brc_strategy_universe_current` 和成员表校验。标的池
变化不升级 Owner Policy；资本比例、容量、5x、Cross 或支持 Event 变化才是
Policy 变化。

## 自动接入状态机

### 配置提交

唯一写入口为：

```text
scripts/trading_kernel/configure_strategy_universe.py
  --runtime-profile-id ...
  --event-spec-id ...
  --instrument BTCUSDT
  --instrument ...
```

脚本将短 symbol 规范化为 canonical id，调用应用用例并写 PostgreSQL。输入
文件、Markdown、生成报告和本地缓存都不是 Runtime Authority。

一次合法提交完成：

1. 验证 Event 已注册且启用；
2. 验证 1 至 10 个唯一 USDT 永续成员；
3. 计算无序 digest；
4. 对新 canonical id 创建 `pending_certification` instrument identity；若已有
   行的 Venue/symbol/product identity 冲突则整次拒绝；
5. 幂等获取或创建 Warming Universe；
6. 创建该版本的 Warming Runtime Scopes；
7. 提交后由现有 Worker 自动推进。

`pending_certification` 只表示系统认识该身份，不表示具有交易资格。认证通过
后才把 instrument 当前状态和精确规则更新为 active；Codec 能解析同样不构成
激活依据。

### 认证职责

**Reconciliation Worker** 已持有账户和交易所只读真相职责，因此在完成
Ticket 安全优先工作后，每个 cadence 最多推进一个到期的 instrument
certification。

认证的网络 I/O 必须在数据库事务外：

```text
短事务 claim 一个 certification target
-> 关闭事务
-> 读取 exchange product/account facts
-> 纯函数分类
-> 短事务写 current certification + Monitor
-> 尝试 DB-only activation
```

认证至少验证：

- canonical id 和 Venue/Product 类型一致；
- 合约处于可交易状态；
- tick size、step size、最小数量/名义价值完整且为正；
-账户支持独立 long/short position sides；
- exact instrument 配置为 Cross；
- exact instrument 配置杠杆为 **5x**；
- 没有无法归属给 BRC Ticket 的既有仓位或开放订单。

已有 BRC Ticket 不阻止配置或激活；同一 Netting Domain 的新 Entry 仍由现有
Ticket ownership 校验拒绝。

### 预热职责

**Observation Worker** 继续拥有闭合市场数据和 Facts。Warming Scope 复用
相同的数据读取和 Facts 验证，但硬性禁止 signal ingestion。

一个 Scope 只有在以下条件全部成立时才标记 warm-ready：

1. detector 所需窗口完整；
2. 最新 bar 已闭合且在 Event freshness 内；
3. typed Facts 可成功构造；
4. comparative Event 的共享投影与同一 Universe/闭合周期一致；
5. readiness digest 和有效期已持久化。

激活后不追溯触发预热期间的信号；只有下一次 Active Observation 才能产生
新 Signal。

### 原子激活

认证或预热写入后都可以调用 DB-only `try_activate_universe()`。它在一个
事务内：

1. 锁定 Warming 版本和该 Event 的 current pointer；
2. 重新检查每个成员认证仍有效；
3. 重新检查每个 Scope warm readiness 仍有效；
4. 将旧 Active Scopes 的两个权限都置为 false；
5. 将新 Scopes 的两个权限都置为 true；
6. 更新 current pointer 和 generation；
7. 将旧版本标记 retired，新版本标记 active；
8. 提交全部状态或全部回滚。

激活事务不访问交易所、不读取行情、不创建 Signal，也不修改 Ticket。

## Monitor 语义

### 确定性 Owner 待办

下列情况写 `brc_monitor_current`，复用现有 Owner 状态
**`NEEDS_INTERVENTION`**；certification status 使用
`owner_action_required`：

- exact instrument leverage 不是 5x；
- margin mode 不是 Cross；
-账户未开启独立 long/short sides；
- 合约状态或规则表明该产品不能进入当前 Profile；
- 存在无法归属给 BRC Ticket 的仓位或开放订单。

Monitor key 使用：

```text
strategy-universe:{universe_version_id}:{exchange_instrument_id}
```

payload 只含非敏感只读事实、阻塞码、观测时间和下一次复核时间。代理据此
向 Owner 汇报。

### 暂时性失败

网络超时、限流、交易所暂时不可用、行情缺口等状态只更新下一次重试时间，
不写人工待办。重复相同阻塞不得形成无界 Monitor Event 或日志风暴。

### 恢复

当下一次只读认证满足要求：

1. certification 变为 eligible；
2. 对应 Monitor current 标记 resolved；
3. append-only Monitor event 保留状态变化；
4. 自动继续 `try_activate_universe()`。

Owner 不需要导入任何内容。

## 比较策略的性能设计

### 当前风险

MPG 和 MI 需要比较同一池中所有成员。如果每个候选 Scope 都重新拉取整个
Universe，N 个成员会产生近似 **O(N²)** 的重复行情读取。池规模为 8 时，
一个闭合周期可能从 8 份成员读取膨胀为约 64 份。

### 决策

对 MPG/MI 引入 **共享 Comparative Projection**：

```text
event_spec_id
+ universe_version_id
+ closed_bar_time
-> 一次读取每个成员
-> 生成一个不可变 typed comparison payload + digest
-> 每个 candidate scope 读取同一投影
```

该投影是 Observation 的事实投影，不是第二个信号引擎。Detector 仍使用现有
`ComparativeStrengthSnapshot` 语义，Signal 仍由各 Scope 的正式
Observation 路径产生。

### 有界复杂度

| 场景 | 当前潜在复杂度 | 新设计上界 | 说明 |
| --- | ---: | ---: | --- |
| Direct Event 单周期行情读取 | O(N) | O(N) | 每个成员一次 |
| Comparative Event 单周期行情读取 | O(N²) | O(N) | 共享投影 |
| Active Scope 数 | 静态 22 | 最多 60 | 6 个 Event × 10 |
| Warming Scope 数 | 不适用 | 最多 10 | 全局一个 Warming Universe |
| 总可调度 Scope | 静态 22 | 最多 70 | Active + Warming 硬上限 |

目标配置 **6 × 8** 时 Active Scope 为 48；一个 10 成员 Warming 版本期间
最多 58 个可调度 Scope。

## 性能合同

### Runtime 行为

1. 不增加第五个 systemd Worker。
2. Observation 仍每次只 claim 一个到期 Scope；使用
   `FOR UPDATE SKIP LOCKED` 和精确索引。
3. Reconciliation 的 Ticket 安全和未知结果恢复优先级高于 Universe
   certification；每个 cadence 最多认证一个 instrument。
4. 同一 instrument 的认证通过 `next_check_at_ms` 限流；确定性人工待办
   默认不高于每 5 分钟复核一次，暂时性失败使用有界退避。
5. 激活事务只扫描最多 10 个成员和 10 个 Scope。
6. Entry 查询只读取 ready Signal、当前 Universe、Owner Policy 和当前
   ownership；不得扫描历史 Universe 或完整 Signal 历史。
7. Adapter 使用纯 Codec，不在每个市场或订单请求前访问 PostgreSQL。
8. 健康空闲 cadence 继续产生零运行时文件。
9. 所有网络 I/O 保持在事务外，并使用现有 timeout 边界。

### 验收边界

实现后的本地和 Tokyo 只读验收必须同时证明：

- PostgreSQL 关键查询使用预期索引且返回行数受 10/70 上限约束；
- Comparative Event 每个成员每个闭合周期最多一次共享投影读取；
- 四 Worker 仍位于现有共享 slice；
- 空闲 CPU 低于现行合同的 10% 警戒线；
- 空闲内存低于 `MemoryMax` 的 80%；
- task count 低于 `TasksMax` 的 50%；
- Worker restart counter 不增长；
- 不产生定时报告文件、无界日志或 Monitor 风暴。

生产实测数值只写入 `docs/current/MAIN_CONTROL_ROADMAP.md`，不复制到本文档。

## 并发与故障恢复

### 配置并发

- 相同 Event、相同集合并发提交：唯一约束使两者收敛到同一版本。
- 不同集合并发提交：全局 Warming 唯一约束只接受一个；另一提交明确返回
  `WARMING_UNIVERSE_ALREADY_EXISTS`，不排队隐藏执行。
- 激活竞争：current pointer generation 使用 CAS；失败方重读状态，不重复
  激活。

### Worker 崩溃

- certification claim 和 Scope claim 都使用租约与到期时间；
- 网络调用前数据库事务已关闭；
- 崩溃后租约到期即可重试；
- 重试只更新 current 投影，不创建重复 Universe；
- 激活事务要么完整提交，要么 Active Universe 完全不变。

### Universe 切换与 Signal 竞争

```text
旧 Scope 刚生成 Signal
-> 新 Universe 激活
-> Entry 读取 Signal
-> current Universe revalidation 失败
-> Signal 不创建 Claim/Ticket
```

如果 Ticket 已经在激活前原子创建，则 Ticket 合法存在并继续闭环。派发前的
第二次 revalidation 只允许当前 Universe；若在 Ticket 创建后、ENTRY 派发前
发生切换，ENTRY 被拒绝并走现有无暴露终止/释放路径，绝不补发。

### 活跃 Ticket 与移除标的

Universe 不是持仓所有权。Lifecycle 和 Reconciliation 按 Ticket 冻结的
canonical instrument id 工作，不依赖 Active Scope。移除成员不会：

- 强平或取消其已有保护；
- 停止 runner；
- 改写 Exit Policy；
- 释放尚未闭环的预算或 Netting Domain；
- 阻止 Settlement 和 Review。

## 失败矩阵

| 失败 | 当前 Active Universe | 新 Signal | 自动恢复 | Owner 动作 |
| --- | --- | --- | --- | --- |
| 配置重复/超过 10 | 不变 | 正常旧池 | 提交被拒绝 | 修正配置 |
| 未知或停牌产品 | 不变 | 正常旧池 | 周期只读复核 | 视阻塞码处理 |
| leverage 非 5x | 不变 | 正常旧池 | 手工设置后自动复核 | 交易所手工设置 |
| margin 非 Cross | 不变 | 正常旧池 | 手工设置后自动复核 | 交易所手工设置 |
| 网络超时/限流 | 不变 | 正常旧池 | 有界退避 | 无 |
| 市场窗口不足 | 不变 | 正常旧池 | Observation 继续预热 | 无 |
| Comparative 投影缺成员 | 不变 | 正常旧池 | 重建完整投影 | 无 |
| Worker 中途崩溃 | 不变 | 正常旧池 | 租约到期重试 | 无 |
| 激活事务失败 | 不变 | 正常旧池 | 全事务重试 | 无 |
| 切换后旧 Signal 被 Entry 读取 | 新池已 active | 旧 Signal 不合格 | 正常调度 | 无 |

## 审计与追溯

### 主要目标

本项目的审计目标是回答：

1. 哪个策略 Event 在什么 Universe 资格下生成了 Signal；
2. 哪个 Claim 和 Ticket 获得了资金与 Netting Domain；
3. 哪个 durable Command 产生了哪个订单；
4. 哪些成交形成和结束了哪笔持仓；
5. Settlement 和 Review 如何归因到原 Ticket。

### 查询路径

```text
Ticket
-> CapacityClaim
-> StrategySignal
-> StrategyUniverseVersion + members + digest

Ticket
-> ExchangeCommands
-> command attempts / venue order identity
-> trade fills
-> protected position lifecycle
-> Reconciliation
-> Settlement
-> Review
```

Universe 激活时间和版本状态足以说明当时的资格，不建设“谁点击了配置按钮”
或“每一次 CLI 操作”的独立运维审计系统。Monitor 只保留阻塞和恢复事实。

## 代码结构与规范

### 计划新增的明确模块

| 文件 | 单一职责 | 禁止内容 |
| --- | --- | --- |
| `domain/strategy_universe.py` | 无序成员、digest、状态不变量 | SQLAlchemy、时钟、网络 |
| `domain/instrument_identity.py` | canonical id 与 CCXT symbol 严格转换 | 数据库、Universe 查询 |
| `domain/instrument_certification.py` | 只读事实的纯认证分类 | 交易所写入、Monitor 写入 |
| `application/install_strategy_universe.py` | 配置安装用例 | 网络 I/O、激活旁路 |
| `application/advance_strategy_universe.py` | 认证/预热后的 DB-only 激活协调 | detector、交易所写入 |
| `application/project_comparative_universe.py` | MPG/MI 共享投影 | Signal 旁路 |
| `infrastructure/pg_universe_repository.py` | Universe 版本、成员、current 和认证持久化 | Venue client、业务推断 |
| `scripts/trading_kernel/configure_strategy_universe.py` | 单一配置提交入口 | 文件权威、直接 SQL、交易所写入 |

### 计划修改的既有模块

| 模块 | 结构性修改 | 不采用的做法 |
| --- | --- | --- |
| `strategy_registry.py` | 删除候选成员和优先级 | 保留旧字段做兼容 |
| `observe_strategy_scope.py` | Warming 禁止 Signal；读取 Universe/投影 | 分叉第二 Observation |
| `pg_signal_repository.py` | 当前 Universe join；删除成员优先级 | 双读旧候选表 |
| `arbitration.py` | 删除 candidate scope priority | 用配置顺序替代 |
| `production_runtime.py` | 删除固定成员 map/count | 每次请求查库 |
| `venue_adapter.py` | 使用严格 InstrumentCodec | 未认证 symbol 猜测 |
| `runtime_authority_seed.py` | Policy 绑定 Event，不展开成员 | 每次切池升级 Policy |
| `pg_models.py` / migration | 单一新 schema | nullable 兼容列、fallback |

### 可读性约束

1. 领域对象全部使用 frozen、named Pydantic model 和 `extra="forbid"`。
2. 金融数值使用 `Decimal`；数量上限和 generation 使用验证后的整数。
3. 使用 `UniverseInstallRequest`、`InstrumentCertificationFacts` 等命名模型，
   不传递无类型 dict。
4. 状态机转移集中在一个纯函数或一个明确 use case，不散落在 Worker。
5. PostgreSQL repository 只表达存取，不决定认证或业务状态。
6. Worker 只编排优先级、claim、I/O 和 use case，不复制状态机。
7. 单文件超过现有可读性阈值时按稳定职责拆分，不按每张表机械拆 repository。
8. 不增加 generic `Manager`、`Helper`、`Facade`、事件总线或 service locator。
9. 不使用配置文件、环境变量或行顺序承载隐含交易语义。
10. 所有拒绝必须有稳定 reason code，日志仅提供上下文。

## 明确不做

- 美股合约 Runtime、交易时间、Corporate Action、参考标的和美股数据源；
- 相关性矩阵、聚类、相关性拒绝或动态降仓；
- 动态 Python 插件发现、热加载、A/B 版本并行；
- Universe 成员权重、排名或隐式优先级；
- 自动设置 leverage、margin mode 或 position mode；
- 新推送平台、Owner Console 或配置审批工作流；
- 活跃持仓跨 schema/版本迁移；
- 旧 Candidate Scope 兼容读取；
- 研究文件或本地 JSON/YAML 作为 Runtime Authority；
- 为配置动作建设重型运维审计。

## 生产播种边界

当前实现阶段只交付通用能力和非生产 fixture。不会在默认生产 seed 中写入
新的最终成员集合，也不会启用新的 Entry。

生产播种必须在单独的 Owner 确认门后执行：

1. P1 fairness/order attribution 版本已完成验收；
2. BTC-like pending closure 已通过正常 Event/Reducer/UoW 达到 terminal；
3. 所有 Ticket、仓位、订单、Settlement 和 Review 已闭环；
4. Owner 固定每个 Event 的最终 1 至 10 个成员，目标为 8；
5. 代理提交配置；
6. 自动认证和预热完成；
7. 只读证据证明每个成员为 Binance USD-M USDT perpetual、Cross、5x；
8. schema、runtime identity、Policy、Universe current 一致；
9. Safety Workers 先启动，Entry 最后启用。

## 编码前 Owner 确认清单

本文档将以下结构视为一个整体确认项：

1. **删除候选顺序语义**，Entry 只保留 Owner Policy 优先级和时间/事件稳定
   排序；
2. **删除 `brc_strategy_candidate_scopes` 重复权威**，不保留兼容层；
3. **Registry 与 Owner Policy 不再保存具体成员**，Universe 成为唯一资格
   权威；
4. **复用四个 Worker**：Reconciliation 做只读 instrument certification，
   Observation 做市场预热；
5. **增加五个有界 PostgreSQL 对象**，其中历史增长只发生在 Universe version
   和 member 表；
6. **MPG/MI 使用共享比较投影**，避免池扩大后的 O(N²) 行情读取；
7. **Signal、Claim、Ticket 冻结 Universe 身份**，订单和持仓继续通过 Ticket
   追溯；
8. **当前阶段只实现加密 USDT 永续通用能力**，最终成员清单延后至生产播种。

Owner 确认本文档、配套实施计划和测试用例后，编码仍必须从 RED 测试开始，
不得先写生产实现。
