---
title: Crypto Strategy Universe General Capability Test Cases
status: OWNER_REVIEW_REQUIRED
authority: NOT_CURRENT_AUTHORITY
date: 2026-07-28
design: 2026-07-28-crypto-strategy-universe-design.md
plan: ../plans/2026-07-28-crypto-strategy-universe-implementation.md
---

# Crypto Strategy Universe General Capability Test Cases

## 当前状态

本文档只定义 **待实现测试规格**。当前没有创建或修改任何
`tests/**/*.py`，也没有把下列用例标记为通过。

Owner 确认设计、实施计划和本测试规格后，实施必须先让相应用例因缺失行为
产生预期 RED，再修改生产代码。

## 测试目标

测试必须共同证明：

1. Universe 是唯一、无序、版本化的候选资格权威；
2. 配置提交后自动认证、预热、原子激活；
3. Universe 切换不能绕过 Signal、Claim、Ticket 和 durable Command 链；
4. 已有 Ticket 不依赖当前 Universe，能够完整保护、退出和结算；
5. 新合约接入不要求修改 detector、Registry 或 Adapter 静态映射；
6. 交易所设置只读复核，系统不自动修改 5x/Cross；
7. 池规模扩大到硬上限时，查询、行情读取、CPU、内存和任务数仍有界；
8. 架构中不出现双权威、兼容 fallback、平行服务或胶水转发层。

## 测试层级与证据

| 层级 | 主要证明 | 允许替身 | 不足以单独证明 |
| --- | --- | --- | --- |
| **Unit** | 纯模型、digest、认证分类、状态决策 | typed fixture、fake clock value | PostgreSQL 约束、事务和并发 |
| **PostgreSQL Integration** | DDL、锁、CAS、UOW、幂等、查询边界 | fake Venue | 完整生产 producer 链 |
| **Worker Integration** | cadence、租约、网络事务边界、Monitor | recording Venue adapter | Ticket 全生命周期 |
| **Full Chain** | 配置到 Signal/Ticket/订单追溯和故障恢复 | fake exchange mutation/read truth | Tokyo 实际资源状态 |
| **Architecture/Static** | 依赖、禁用 API、无文件、无双读 | source/AST/schema scan | 运行时性能 |
| **Performance Acceptance** | 调用次数、query plan、资源边界 | counting market source | 策略收益 |

## 测试纪律

- Financial values 使用 `Decimal`。
- 核心 fixture 使用 frozen named models，不用自由 dict 伪造应用边界。
- PostgreSQL 行为使用 disposable PostgreSQL，不用 SQLite 替代。
- Venue mutation 全部使用 recording fake；本地测试禁止真实交易所写。
- Full-chain fixture 必须从正式配置/Observation/Entry producer 进入，不直写
  Signal、Ticket 或 command 中间表。
- 每个用例同时断言预期状态和禁止副作用。
- 对网络调用断言次数、端点类别和事务是否已关闭。
- 对并发使用真实 PostgreSQL connection/transaction，不用单线程顺序模拟。
- 对失败注入断言旧 Active Universe 和已有 Ticket 仍完整。
- 性能测试断言调用/查询上界，不使用易抖动的毫秒级单元基准替代结构证据。

## 计划测试文件

| 文件 | 层级 | 覆盖范围 |
| --- | --- | --- |
| `unit/test_strategy_universe.py` | Unit | 集合、digest、版本和状态 |
| `unit/test_instrument_identity.py` | Unit | canonical id / CCXT codec |
| `unit/test_instrument_certification.py` | Unit | 只读认证分类 |
| `unit/test_arbitration.py` | Unit | 无成员顺序优先级 |
| `unit/test_advance_strategy_universe.py` | Unit | 激活决策 |
| `integration/test_strategy_universe_schema.py` | PostgreSQL | DDL 和约束 |
| `integration/test_strategy_universe_repository.py` | PostgreSQL | 安装、幂等、current |
| `integration/test_universe_certification_worker.py` | Worker | Reconciliation 认证 |
| `integration/test_universe_warming.py` | Worker | Observation 预热 |
| `integration/test_comparative_universe_projection.py` | PostgreSQL | 共享比较投影 |
| `integration/test_strategy_universe_activation.py` | PostgreSQL | 原子激活 |
| `integration/test_universe_signal_eligibility.py` | PostgreSQL | Signal/Entry 资格 |
| `integration/test_dynamic_instrument_routing.py` | Integration | 未编入 Registry 的新合约 |
| `full_chain/test_crypto_universe_replacement.py` | Full Chain | 正常切换和 Ticket 因果 |
| `full_chain/test_crypto_universe_failure_recovery.py` | Full Chain | 故障和恢复 |
| `architecture/test_strategy_universe_architecture.py` | Static | 单一权威和禁用边界 |
| `integration/test_strategy_universe_query_bounds.py` | Performance | 查询与行数上界 |
| `integration/test_universe_market_call_bounds.py` | Performance | 行情读取 O(N) |

## A. Universe 领域不变量

| ID | 场景 / 动作 | 必须断言 | 禁止副作用 |
| --- | --- | --- | --- |
| UNI-DOM-001 | 用 8 个唯一 canonical ids 构造 Universe | frozen model 成功；成员 canonical sorted | 不保留输入顺序 |
| UNI-DOM-002 | 同一 8 成员使用相反输入顺序 | semantic digest 完全相同 | 不产生 rank/weight |
| UNI-DOM-003 | 删除一个成员 | digest 改变 | Strategy semantic hash 不改变 |
| UNI-DOM-004 | 增加一个成员 | digest 改变 | Owner Policy identity 不改变 |
| UNI-DOM-005 | 输入空集合 | validation error | 不产生半成品对象 |
| UNI-DOM-006 | 输入 11 个成员 | validation error | 不静默截断为 10 |
| UNI-DOM-007 | 输入相同成员两次 | validation error | 不自动去重后接受 |
| UNI-DOM-008 | 输入 1 个成员 | 合法；硬下限包含 1 | 不强制目标值 8 |
| UNI-DOM-009 | 输入 10 个成员 | 合法；硬上限包含 10 | 不产生第 11 个 Scope |
| UNI-DOM-010 | 输入非法 lifecycle state | validation error | 不回退到 warming |
| UNI-DOM-011 | 对 frozen model 赋值 | 拒绝变更 | digest 不漂移 |
| UNI-DOM-012 | Event 与 StrategyGroup 语义归属不匹配 | install 决策拒绝 | 不写 version/member/scope |

## B. Instrument identity 与动态路由

| ID | 场景 / 动作 | 必须断言 | 禁止副作用 |
| --- | --- | --- | --- |
| ID-001 | 解析 `binance-usdm:BTCUSDT:perpetual` | venue、symbol、quote、type 完整 | 不查数据库 |
| ID-002 | 转换 BTC canonical id | 得到 `BTC/USDT:USDT` | 不读 Registry |
| ID-003 | 解析含数字 base 的 USDT 合约 | 保留精确 base | 不误拆 quote |
| ID-004 | 输入小写或带空格 id | 严格拒绝 | 不隐式修正交易身份 |
| ID-005 | 输入非 USDT quote | 拒绝 | 不进入当前 Profile |
| ID-006 | 输入 spot/options/未知 type | 拒绝 | 不猜测 perpetual |
| ID-007 | 输入未知 venue | 拒绝 | 不走默认 Binance |
| ID-008 | 一个 Registry 未列出的合法 canonical id | Codec 成功解析 | 不代表认证通过 |
| ID-009 | 已从 Active Universe 移除的 Ticket id | Lifecycle/Adapter 仍能解析 | 不要求恢复旧 Universe |
| ID-010 | 非法 id 进入 Venue mutation | mutation 前 fail closed | Venue 调用次数为零 |

## C. Instrument certification

| ID | 场景 / 动作 | 必须断言 | 禁止副作用 |
| --- | --- | --- | --- |
| CERT-001 | 产品交易中、规则完整、hedge、Cross、5x、无 unowned exposure | status `eligible`；有效期和 digest 完整 | 不写交易所 |
| CERT-002 | leverage 为 3x | `owner_action_required` + 稳定 blocker | 不自动设为 5x |
| CERT-003 | leverage 为 10x | 同样 owner action | 不把上限解释为允许值 |
| CERT-004 | margin mode 为 isolated | owner action | 不自动切 Cross |
| CERT-005 | 账户为 one-way mode | owner action | 不自动切 hedge mode |
| CERT-006 | product status 非 trading | owner action/明确不可接入 | 不创建 Active Scope |
| CERT-007 | 缺 tick size | certification 不 eligible | 不以默认精度补齐 |
| CERT-008 | step size 为 0/负数 | certification 不 eligible | 不生成 order rules |
| CERT-009 | min qty/min notional 缺失 | certification 不 eligible | 不猜测 |
| CERT-010 | 存在 unowned position | owner action + identity blocker | 不接管持仓 |
| CERT-011 | 存在 unowned open order | owner action + identity blocker | 不取消订单 |
| CERT-012 | 存在 exact BRC-owned active Ticket | certification 可 eligible | Entry 仍由 Netting Domain 阻塞 |
| CERT-013 | exchange timeout | `temporarily_unavailable` | 不写 owner action |
| CERT-014 | rate limit | 暂时失败 + next check | 不忙循环 |
| CERT-015 | 同一 facts 重复分类 | digest/status 完全确定 | 不依赖当前时钟 |
| CERT-016 | facts 带未知字段 | frozen boundary 拒绝 | 不吞掉 venue schema drift |

## D. Schema、约束与迁移

| ID | 场景 / 动作 | 必须断言 | 禁止副作用 |
| --- | --- | --- | --- |
| DB-001 | 空数据库升级 `0001 -> 0002` | 五个新对象、字段、FK、索引完整 | 不创建 legacy 表 |
| DB-002 | 非 flat runtime 尝试迁移 | precondition fail closed | 不做部分 DDL/DML |
| DB-003 | 插入重复 event/version | unique violation | 不覆盖原版本 |
| DB-004 | 当前 active/warming 同 event+digest 重复 | 部分唯一索引拒绝 | 不产生两个同义 current |
| DB-005 | 原版本 retired 后相同 digest 新版本 | 允许新版本身份 | 不重新激活 retired 行 |
| DB-006 | 同版本重复 member | PK/unique violation | 不产生重复 Scope |
| DB-007 | 两个全局 warming 版本 | 部分唯一约束拒绝 | 不同时预热两个池 |
| DB-008 | 一个 Event 两个 current pointer | PK 拒绝 | 不产生双 active |
| DB-009 | member 引用不存在 instrument | FK 拒绝 | 不产生 orphan |
| DB-010 | runtime scope 缺 Universe id | non-null 拒绝 | 不允许 legacy scope |
| DB-011 | Signal/Claim/Ticket 缺 Universe identity | non-null 拒绝 | 不允许无归因交易链 |
| DB-012 | 删除 `brc_strategy_candidate_scopes` 后扫描 schema | 表完全不存在 | 不保留 view/alias/fallback |
| DB-013 | Warming scope 权限组合 | observation true / entry false | 不允许 entry true |
| DB-014 | Active scope 权限组合 | 两者 true | 不允许 active 但无 observation |
| DB-015 | Retired scope 权限组合 | 两者 false | 不再进入 due selector |
| DB-016 | 新 canonical id 写 instrument directory | 初始为 pending certification | 不默认 active |

## E. Install、版本和 Repository

| ID | 场景 / 动作 | 必须断言 | 禁止副作用 |
| --- | --- | --- | --- |
| INS-001 | 首次提交 8 成员 | 1 version、8 members、8 warming scopes | 不改 current pointer |
| INS-002 | 相同 Event/集合重复提交 | 返回同一 active/warming version | 不新增行 |
| INS-003 | 相同成员不同顺序重复提交 | 同一 digest/version | 不改变语义 |
| INS-004 | Active 集合与提交集合相同 | 返回 already-active | 不进入 warming |
| INS-005 | 已有 Active A，提交新集合 B | A 保持 active，B warming | 不提前关闭 A |
| INS-006 | 全局已有另一个 Warming | 返回稳定冲突码 | 不隐藏排队 |
| INS-007 | version 插入后 member 插入失败 | 整事务回滚 | 无 orphan version |
| INS-008 | member 完成后 scope 插入失败 | 整事务回滚 | 无半安装池 |
| INS-009 | 并发提交相同集合 | 两调用收敛一个版本 | 不暴露 unique error 给正常调用 |
| INS-010 | 并发提交不同集合 | 仅一个 warming | loser 无部分数据 |
| INS-011 | repository get current | 只读一个 Event current + digest | 不扫描历史版本 |
| INS-012 | repository get members | 最多 10 行 canonical sorted | 不返回 rank |
| INS-013 | 新 instrument identity 与已有 Venue/symbol 冲突 | 整次提交拒绝 | 不覆盖目录行 |
| INS-014 | certification 成功 | instrument 状态和 rules 原子 active | 不靠 Codec 自动激活 |

## F. Registry、Owner Policy 与 arbitration

| ID | 场景 / 动作 | 必须断言 | 禁止副作用 |
| --- | --- | --- | --- |
| REG-001 | 读取 RegisteredStrategyContract | 无 candidate list/rank 字段 | 不提供兼容 property |
| REG-002 | 策略 Registry seed | 只播种策略/Event 语义 | 不写 Universe member |
| REG-003 | 修改 Universe | Strategy semantic hash 不变 | 不创建 StrategyVersion |
| REG-004 | 修改 detector/threshold | Strategy/Event revision 改变 | 不伪装为 Universe 变化 |
| POL-001 | Owner Policy seed | scope 使用 allowed Event ids | 不保存 runtime scope ids |
| POL-002 | 修改 Universe | Owner Policy version 不变 | 不复制成员 |
| POL-003 | 修改 5x/资本/容量 | Owner Policy version 改变 | 不修改 Universe digest |
| ARB-001 | 两 Signal 只因成员输入顺序不同 | 结果不受输入顺序影响 | 无 candidate priority |
| ARB-002 | 两 Signal Owner Policy priority 不同 | 仍按 Policy 排序 | Universe 不覆盖 Policy |
| ARB-003 | Policy priority 相同、时间不同 | 按 occurrence/observation 时间 | 不按数据库行顺序 |
| ARB-004 | 时间完全相同 | signal id 提供稳定 tie-break | 结果可重复 |
| ARB-005 | 源码/SQL scan | 无 `candidate_scope_priority` | 无 `priority_rank` join/order |

## G. 认证 Worker 与 Monitor

| ID | 场景 / 动作 | 必须断言 | 禁止副作用 |
| --- | --- | --- | --- |
| WRK-CERT-001 | 同时有 Ticket reconciliation 和认证目标 | Ticket 安全工作先执行 | 认证不延迟安全闭环 |
| WRK-CERT-002 | 无安全工作、有到期认证 | 每 cadence claim 最多一个 | 不批量打满 Venue |
| WRK-CERT-003 | claim 完成后读取 Venue | 数据库事务已关闭 | 网络不占锁 |
| WRK-CERT-004 | Venue timeout | lease/next check 可恢复 | 不持有永久 claim |
| WRK-CERT-005 | Worker 在网络后、persist 前崩溃 | 租约到期重新读取 | 不假定成功 |
| WRK-CERT-006 | leverage blocker 首次出现 | Monitor current + event 一次 | 不发推送平台 |
| WRK-CERT-007 | 相同 blocker 重复出现 | current 更新时间有界 | 不产生 event/log 风暴 |
| WRK-CERT-008 | blocker 内容改变 | append 状态变化 event | 不覆盖历史变化 |
| WRK-CERT-009 | Owner 手工设置后复核通过 | certification eligible；Monitor resolved | 不要求导入 |
| WRK-CERT-010 | transient error 恢复 | 自动继续 | 不留 owner action |
| WRK-CERT-011 | 认证通过但未预热 | 不激活 | 不跳过 Observation |
| WRK-CERT-012 | 认证流程 source scan | 无 leverage/margin/position mutation | 无新增 mutation kind |

## H. Warming 与 Comparative Projection

| ID | 场景 / 动作 | 必须断言 | 禁止副作用 |
| --- | --- | --- | --- |
| WARM-001 | Warming direct scope 窗口完整 | warm-ready + digest | Signal 写入次数为零 |
| WARM-002 | Warming detector 条件恰好触发 | 仍只 ready | 不追发 Signal |
| WARM-003 | 缺一个所需 bar | not ready + next due | 不用部分 Facts |
| WARM-004 | 最新 bar 未闭合 | not ready | 不读取未来数据 |
| WARM-005 | Facts 过期 | readiness 不可激活 | 不沿用旧 ready |
| WARM-006 | Worker 在 market read 后崩溃 | lease 到期恢复 | 不产生 Signal |
| WARM-007 | Active scope 同样输入 | 保持原 Signal producer 语义 | 不走第二 detector |
| WARM-008 | Universe 激活后第一次新闭合 observation | 可以产生新 Signal | 不用 warming trigger 回放 |
| CMP-001 | 8 成员 MPG 一个闭合周期 | 每成员最多一次 market read | 不发生 64 次读取 |
| CMP-002 | 10 成员 MI 一个闭合周期 | 总读取 O(10) | 不随 candidate scopes 平方增长 |
| CMP-003 | 所有 scope 读同一 projection | key/digest/close 完全一致 | 不各自重建 |
| CMP-004 | projection 缺一个成员 | 所有相关 scope fail closed | 不做部分排名 |
| CMP-005 | 成员 close time 不一致 | projection 拒绝 | 不混合周期 |
| CMP-006 | projection digest 与 current Universe 不同 | scope 不消费 | 不沿用旧池比较 |
| CMP-007 | 同 key 并发 projector | 一个 current 投影 | 不重复 market fetch 提交 |
| CMP-008 | Direct strategy | 不创建 comparative projection | 不增加无意义表写 |

## I. 原子激活

| ID | 场景 / 动作 | 必须断言 | 禁止副作用 |
| --- | --- | --- | --- |
| ACT-001 | 全成员 eligible + warm-ready | 新池 active、旧池 retired、pointer +1 | 单事务完成 |
| ACT-002 | 一个成员 certification missing | 返回 not-ready | 旧池不变 |
| ACT-003 | 一个成员 owner action | 不激活 | 旧池继续 Signal |
| ACT-004 | 一个 readiness missing | 不激活 | 不部分启用新 scope |
| ACT-005 | 一个 readiness 已过期 | 不激活 | 不相信陈旧预热 |
| ACT-006 | comparative projection incomplete | 不激活 | 不绕过投影 |
| ACT-007 | 在关闭旧 scopes 后注入异常 | 全事务回滚 | 旧池仍完整 active |
| ACT-008 | 在开启新 scopes 后注入异常 | 全事务回滚 | 无半 active 新池 |
| ACT-009 | 在更新 pointer 后注入异常 | 全事务回滚 | generation 不增长 |
| ACT-010 | 两 Worker 同时 try activate | 一个成功、一个 already-active/reload | generation 只增 1 |
| ACT-011 | 对已 active version 重试 | 幂等 no-op | 不追加重复 activation |
| ACT-012 | 激活事务 instrumentation | 零网络、零行情、零 Signal/Ticket | 不越过 DB-only 边界 |

## J. Signal、Entry、Ticket 与订单因果

| ID | 场景 / 动作 | 必须断言 | 禁止副作用 |
| --- | --- | --- | --- |
| ENT-001 | Active member scope 产生 Signal | 冻结 current version id/digest | 不读 Registry 成员 |
| ENT-002 | Warming member scope 尝试 Signal | 拒绝 | Signal 行为零 |
| ENT-003 | 非 current version scope 尝试 Signal | 拒绝 | 不靠 enabled 旧值漏过 |
| ENT-004 | Active Universe 不含 instrument | 拒绝 | 不产生 Claim |
| ENT-005 | Signal 后、Entry 前切换 | readiness 不合格 | 无 Claim/Ticket/command |
| ENT-006 | Claim 构建中 current generation 改变 | 原子 revalidation 失败 | 不占预算 |
| ENT-007 | Ticket issue 前 current 改变 | issue 失败/释放 | 不留下半 Ticket |
| ENT-008 | Ticket 已 issue、dispatch 前切换 | durable command 不调用 Venue并终止 | 不盲目发 ENTRY |
| ENT-009 | Ticket 在切换前已完成 ENTRY fill | Ticket 正常保护/退出 | 不因移除强平 |
| ENT-010 | Claim 与 Signal Universe id 不同 | validation error | 不冻结错误归因 |
| ENT-011 | Ticket 与 Claim digest 不同 | validation error | 不创建 command |
| ENT-012 | 正常 chain | Signal/Claim/Ticket Universe identity 一致 | 不重复写到 fill |
| ENT-013 | 同 instrument 已有 active Ticket | Netting Domain 拒绝 | certification eligible 不绕过 |
| ENT-014 | 两 Event 都含同 instrument | 各自 Universe 合法 | 仍受资金/Netting Domain |
| ENT-015 | opposite sides 同 instrument | 按现有独立 side 语义 | Universe 不合并 sides |

## K. 已有 Ticket 与审计追溯

| ID | 场景 / 动作 | 必须断言 | 禁止副作用 |
| --- | --- | --- | --- |
| AUD-001 | 从 Ticket 查询来源 | 精确 Claim、Signal、Universe version/member | 不依赖当前池 |
| AUD-002 | 从 Ticket 查询订单 | durable command 与 venue order identity 完整 | 不用 symbol 模糊匹配 |
| AUD-003 | 从订单查询成交/持仓 | exact Ticket lineage | 不按时间猜归属 |
| AUD-004 | 已移除 instrument 的 position_protected Ticket | Stop/TP1 lifecycle 正常 | 不恢复旧 scope |
| AUD-005 | 已移除 instrument 的 runner Ticket | runner Stop/exit 正常 | 不要求 active membership |
| AUD-006 | 已移除 instrument 的 unknown command | Reconciliation 精确恢复 | 不因 Codec map 缺失 |
| AUD-007 | Ticket terminal | Settlement/Review 仍关联冻结 Universe | 不读 latest Universe |
| AUD-008 | 同策略以后重用相同成员集合 | 新 Universe id、相同 semantic digest 可区分 | 不重写旧 Ticket |
| AUD-009 | 查询当时资格 | version members 与 frozen digest 相符 | 不依赖 CLI 日志 |
| AUD-010 | Monitor 操作历史缺少人工点击身份 | 交易链审计仍完整 | 不伪造运维审计 |

## L. Full-chain 正常场景

| ID | 场景 | 必须经过的真实链 | 最终断言 |
| --- | --- | --- | --- |
| CHN-001 | 首个 8 成员 Universe | configure -> install -> certify -> warm -> activate | 8 active scopes；零 Signal during warm |
| CHN-002 | A 池替换为 B 池 | A active -> B warming -> B active -> A retired | 无不可用窗口、无双 active |
| CHN-003 | Registry 未出现的新合约 | configure -> Codec -> certification -> warm -> Signal | 不改 detector/Adapter map |
| CHN-004 | 新合约需要 Owner 设置 | blocker -> Monitor -> 手工外部状态变化 -> reread -> activate | 系统 exchange writes 为零 |
| CHN-005 | SOR-LONG 与 SOR-SHORT 独立池 | 各自 install/active | 成员互不污染 |
| CHN-006 | 六 Event 各 8 成员 | 48 active scopes | current pointer 各自精确 |
| CHN-007 | 10 成员硬上限 | complete activation | 10 scopes、无第 11 行 |
| CHN-008 | 切换中旧池发 Signal | current revalidation | 旧 Signal 无 Ticket |
| CHN-009 | 切换中已有 protected Ticket | 新 Entry 使用新池；旧 Ticket lifecycle | 最终 Settlement/Review 完整 |
| CHN-010 | MPG/MI 各 8 成员 | shared projection -> detector -> Signal | 每 Event 每成员一次读取 |
| CHN-011 | Universe Signal 成功入场 | Signal -> Claim -> Ticket -> durable ENTRY -> fill/protection | 全链 Universe/Ticket 可追溯 |
| CHN-012 | Signal 未中选 | arbitration 无成员顺序 | 不创建 Claim/Ticket |

## M. 故障与恢复

| ID | 故障注入 | 必须恢复行为 | 禁止结果 |
| --- | --- | --- | --- |
| FLT-001 | install member 中途 DB exception | 全安装回滚 | 半 Universe |
| FLT-002 | certification claim 后 Worker kill | lease expiry 重试 | 永久 warming |
| FLT-003 | authenticated read timeout | bounded backoff | owner action 误报 |
| FLT-004 | Monitor persist exception | certification/Monitor 同事务一致 | eligible 但 blocker 未闭 |
| FLT-005 | market read partial failure | scope not ready | 部分 Facts 激活 |
| FLT-006 | comparative projector crash | 同 key 重建 | 混合旧/新成员 |
| FLT-007 | activation transaction deadlock/abort | PostgreSQL retry 后单次成功 | pointer 与 scopes 分裂 |
| FLT-008 | current pointer CAS loser | reload 幂等退出 | generation 重复 |
| FLT-009 | old Signal race | Entry current join 拒绝 | 旧池成交 |
| FLT-010 | dispatch revalidation race | Venue call zero；Ticket 无暴露闭环 | blind ENTRY |
| FLT-011 | Universe repository temporarily unavailable | Worker 安全重试 | Lifecycle/Reconciliation 停止 |
| FLT-012 | Warming 长期不完成 | 旧 Active 持续运行 | 自动降级旧池 |
| FLT-013 | deterministic blocker 长期存在 | 有界复核 + stable Monitor | 日志/事件风暴 |
| FLT-014 | process restart | 从 PostgreSQL current/warming 恢复 | 依赖内存缓存状态 |
| FLT-015 | active Ticket instrument 已不在 Universe | lifecycle/reconciliation 继续 | orphan position |

## N. 性能与查询上界

| ID | 负载 / 检查 | 必须断言 | 警戒或上界 |
| --- | --- | --- | --- |
| PERF-001 | 6 Event × 10 Active | due selector 命中索引 | 最多 60 active scopes |
| PERF-002 | 加 1 个 10 成员 Warming | 总调度有界 | 最多 70 scopes |
| PERF-003 | Observation tick | claim 一行 | 不扫描所有历史 scopes |
| PERF-004 | Certification tick | claim 一 instrument | 不批量 Venue read |
| PERF-005 | Activation validation | exact version members/scopes | 每类最多 10 行 |
| PERF-006 | Entry ready candidate query | current Universe join + bounded candidates | 不扫描 retired versions |
| PERF-007 | 10 成员 comparative event | counting source | 每成员/close 最多 1 read |
| PERF-008 | Direct event | counting source | O(N) |
| PERF-009 | Adapter request | Codec instrumentation | 0 PostgreSQL lookup/request |
| PERF-010 | Healthy idle cadence | filesystem audit | 0 JSON/Markdown outputs |
| PERF-011 | Tokyo read-only observation | shared slice CPU | 低于现行 10% warning |
| PERF-012 | Tokyo read-only observation | memory/tasks/restarts | memory <80%、tasks <50%、restart 不增 |

## O. 架构和代码规范反回归

| ID | 静态检查 | 必须断言 | 禁止模式 |
| --- | --- | --- | --- |
| ARC-001 | Registry source/model | 不含 candidate members | compatibility property |
| ARC-002 | PostgreSQL schema/source | 不含 candidate scope 表 | view/alias 双读 |
| ARC-003 | Arbitration source/SQL | 不含 candidate priority | 配置顺序 order by |
| ARC-004 | Runtime source | 不含固定 instrument count/map | 新合约改代码 |
| ARC-005 | Worker/service units | 仍只有四个职责服务 | Universe 第五服务 |
| ARC-006 | Domain import scan | 无 SQLAlchemy/Venue/filesystem/subprocess | infrastructure 泄漏 |
| ARC-007 | Application mutation scan | Universe 无 order dispatch API | 平行执行链 |
| ARC-008 | Venue adapter scan | 无 SET_LEVERAGE/margin/position mutation 新入口 | 自动交易所设置 |
| ARC-009 | Network instrumentation | transaction 关闭后才调用 Venue/market | 锁内 I/O |
| ARC-010 | Runtime file-I/O audit | cadence 零文件 | JSON/YAML/Markdown authority |
| ARC-011 | Model scan | 核心 boundary frozen + extra forbid | 自由 dict |
| ARC-012 | Financial model scan | Decimal | float 金融计算 |
| ARC-013 | Repository review | persistence 不决定认证业务 | god repository/service |
| ARC-014 | Worker review | 编排不复制状态机 | 分散 if/else |
| ARC-015 | Asset scope scan | 无 US-equity runtime/seed | 未授权美股接入 |
| ARC-016 | Correlation scan | 无运行时 clustering/rejection/downsize | 偷带相关性策略 |
| ARC-017 | Schema compatibility scan | 无 nullable legacy/fallback/dual write | 历史包袱 |
| ARC-018 | Docs authority test | current 文档只在实现后更新 | 设计文档冒充运行权威 |

## P. 生产播种前门

下列项目是未来生产动作验收，不属于当前通用能力编码测试：

| ID | 前置事实 | 必须证据 | 未满足时 |
| --- | --- | --- | --- |
| DEP-001 | Owner 固定每个 Event 最终清单 | 明确 1..10 个 canonical ids | 不播种 |
| DEP-002 | 所有 Ticket/position/order flat | PostgreSQL + exchange exact truth | 不迁移 |
| DEP-003 | schema/runtime identity 一致 | immutable commit/tag/revision | 不启动 writer |
| DEP-004 | 每成员 Cross/5x/hedge/trading | 只读 certification | Monitor/人工处理 |
| DEP-005 | Safety Workers postflight 正常 | Observation/Lifecycle/Reconciliation active | Entry 不启动 |
| DEP-006 | current Universe 与 Scope 一致 | pointer/digest/member/readiness | Entry 不启用 |
| DEP-007 | 资源警戒线内 | CPU/memory/tasks/restarts/filesystem | 只读诊断 |
| DEP-008 | Owner 单独确认生产播种/Entry | action-time 授权 | 保持 blocked |

## RED 实施顺序

1. `UNI-DOM-*`、`ID-*`、`CERT-*`；
2. `DB-*`、`INS-*`；
3. `REG-*`、`POL-*`、`ARB-*`；
4. `WRK-CERT-*`；
5. `WARM-*`、`CMP-*`；
6. `ACT-*`；
7. `ENT-*`、`AUD-*`；
8. `CHN-*`、`FLT-*`；
9. `PERF-*`、`ARC-*`。

每一组 RED 必须因为目标行为尚未实现而失败；fixture 错误、连接错误、import
路径错误和环境未准备不算有效 RED。

## 本地完整验证

```bash
python3 -m pytest -q \
  tests/trading_kernel/unit \
  tests/trading_kernel/integration \
  tests/trading_kernel/full_chain \
  tests/trading_kernel/architecture

python3 -m ruff check \
  src/trading_kernel \
  tests/trading_kernel \
  scripts/trading_kernel

python3 -m mypy src/trading_kernel

python3 scripts/trading_kernel/audit_runtime_file_io.py

git diff --check
```

完整验证必须使用 PostgreSQL integration/full-chain 证据；不能用单点 unit
green、SQLite、手工 SQL 截图或生成报告替代。

## 通过定义

本测试规格只有在所有适用用例均有自动化实现、完整 suite 通过、失败注入
恢复可重复、查询与调用上界被执行性断言覆盖时，才可从
`OWNER_REVIEW_REQUIRED` 进入本地已验收状态。

生产播种和 Tokyo 部署仍需独立 Owner 确认，不能由本地测试通过自动授权。
