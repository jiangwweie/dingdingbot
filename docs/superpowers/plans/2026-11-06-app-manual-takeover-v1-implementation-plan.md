# AMT-01 App 人工接管 V1 实施计划

> **阅读说明**：本文保留设计/实施时的决策、缺口、分支与阶段证据。起始功能分支 `codex/app-manual-takeover-v1` 已作为历史保留，人工产品集成分支为 `manual-dev`。文中的“未部署”“待确认”属于当时阶段，不能覆盖后续Owner授权或当作当前未完成清单。当前代码、生产身份、Owner状态与自然App验收统一见[正式路线图](../../current/MAIN_CONTROL_ROADMAP.md)；Owner允许在自然交易中完成真实App验收，不能据旧阶段重新要求测试订单。

日期：**2026-11-06，Asia/Shanghai**。
状态：**Owner于2026-11-06授权开始本地实施与测试；前置程序接入与受影响验证已完成；等待进入完整验证与发布隔离的确认。**
工作分支：**`codex/app-manual-takeover-v1`**。
依据：[Owner 结论](../specs/2026-11-06-app-manual-takeover-v1-owner-decisions.md)、
[详细设计](../specs/2026-11-06-app-manual-takeover-v1-detailed-design.md)。

## 1. 目标与授权范围

**新服务器默认执行现有全自动交易；识别到Owner在交易所App的有效操作后，
整笔交易永久转人工管理，程序不再主动处置其退出，但保持只读同步、账务与风险准入。**

最终交付需同时证明：

- 未干预时自动TP1/Runner及原安全链正常。
- 未成交人工挂单、同ID改单、撤单、部分减仓均能识别，接管不可逆。
- 接管后原订单保留，系统新交易所写入为零，重启/旧命令结果不恢复管理。
- 人工仓占用被真实计算，残留订单不遗漏，同标的多空不能同时准入。
- 独立新环境可安装、认证、启动，与Tokyo无账户/数据库/凭据或发布混用。

### 1.1 本轮与后续授权

Owner已明确“可以 开始执行”，授权新产品分支的本地编码与测试；不把此授权扩大为Tokyo变更或新服务器部署。
后续明确启动实施后，当前任务主代理顺序执行，不为每个正常实现步骤重复请求批准。
新服务器部署、实盘验收按当时明确授权与行动时门槛执行。

不创建新聊天，不自动委派或并行修改共享Kernel文件；若以后明确授权委派，再按任务卡
拆分独立边界。新代码只在本产品线，禁止合并到Tokyo的`dev`或重启其服务。

## 2. 当前代码与最早缺口

**已有**：正式信号→Claim→Ticket→durable Command，自动初始止损/TP1/Runner，
PG current/event链、独立Owner API、持久化Worker、对账结算和精确提交发布认证。

**最早缺口**：现有订单快照没有完整可比较条款，也没有证明所有App订单变化都可补采的
证据链；因此不能先写“检测数量变化即接管”然后宣称能力成立。

详细代码依据见设计第2节。当前生产状态不由本计划推断；本轮未进行服务器核验。
原始Ticket保持不可变，管理权放在Aggregate/Trade Events，不创建第二条交易链。

## 3. 工作顺序与负责边界

**依赖顺序：M0 → M1 → M2 → M3 → M4 → M5 → M6 → M7 → M8 → M9。**
M3与M4、M5共享核心文件，必须顺序集成。默认负责人均为当前任务主代理。

| 任务 | 交付物 | 主要允许边界 | 前置依赖 | 状态 |
| --- | --- | --- | --- | --- |
| M0 证据与接口能力 | App操作覆盖矩阵、现有行为基线、环境隔离方案 | 只读适配审阅、协议fixtures、计划记录 | Owner启动实施 | 进行中 |
| M1 权威模型与迁移 | 管理权模型、事件、表/约束、唯一标的占用 | domain、pg_models、迁移、identity/seed | M0能力覆盖明确；不依赖账户验证的基础模型先行 | 前置接入完成，整体待验 |
| M2 采集与归因 | 完整订单条款、事件/历史补采、游标和归因器 | venue adapter、ports、Reconciliation、相关仓储 | M1 | 采集已接入，实账户覆盖待验 |
| M3 接管与写入限制 | 接管原子事务、所有写入口限制、持久化状态 | reducer/UoW/dispatch/lifecycle/controlled exit | M2 | 前置接入及定向验证完成 |
| M4 人工只读生命周期 | 部分退出、残留订单、正常终结与基础账务 | reconcile、scheduler、仓储、结算/Review | M3 | 前置实现及受影响验证完成 |
| M5 风险和标的互斥 | 人工占用、未知风险阻断、禁止同标的双向 | admission、claim、ticket、preflight、预算仓储 | M4 | 前置实现及受影响验证完成 |
| M6 Owner展示与通知 | 管理状态、事实健康、现有挂单与通知去重 | Owner DTO/API/V2、monitor/notice | M4、M5 | 前置实现及受影响验证完成 |
| M7 集成与审查 | 验收矩阵、无干预对照、全部路径写入审计 | 受影响测试、分支合同 | M1–M6 | 未开始 |
| M8 精确候选认证 | R4及配套API/Static证书、新环境安装演练 | 官方认证、发布与本地演练 | M7、候选冻结 | 未开始 |
| M9 新环境部署验收 | 身份/配置/服务postflight、自然验收记录 | 明确的新目标服务器和账户 | 单独部署授权、M8 | 未开始 |

所有任务禁止修改Tokyo运行控制、扩大风险/策略范围、绕过正式下单路径、
伪造未来时钟/Signal/Ticket或向交易所下测试单。

## 4. M0 能力核实与范围冻结

### 目标

证明“只要有效操作就接管，不等成交”的观测来源可实现，不用快照轮询替代动作历史。

### 动作

1. 刷新git/worktree/真实进程与其他任务边界，保留无关修改；确认仍在本产品分支。
2. 读取Owner结论、当前Kernel合同、测试及最近公共修复，列出需要移植和应排除的改动。
3. 梳理 ordinary/conditional订单API、修改/撤单记录、条件单执行订单映射、账户事件订阅；
   以供应商官方文档、当前SDK代码及可取得的脱敏只读记录验证，文档说明不等于账户已验证。
4. 覆盖新增未成交即撤销、同ID改回原值、断线期间操作、close-position、双向账户等语义。
5. 明确保留时限、分页、去重、序号、自动过期/强平与人为撤销的可区分程度。
6. 建立无干预自动路径基线，核实部分TP1成交问题；不得把其异常自动归为人工干预。
7. 冻结产品身份与部署隔离方案；新账户只在正式授权后启用，不复制Tokyo授权记录。

### RED与完成证据

- 新协议测试证明当前`VenueOrderSnapshot`无法描述同ID改价/改量。
- 构造“采样间新增又撤销”“改价又改回”有效变化，旧快照判定漏报的测试必须失败。
- 输出每种操作对应的实际可用事实源、未验证项和采集上限，作为M2的输入。

### 停止条件

若某种允许操作在供应商可用事实中无法观察，记录准确限制，不将需求降为“成交才接管”。
该问题阻断功能发布，不通过新增Owner按钮或伪造历史来隐藏。

## 5. M1 模型、约束与前向迁移

### 允许文件

现有`domain/aggregate.py`、`events.py`、`reducer.py`、`commands.py`、`effects.py`；
拟新增`domain/trade_management.py`、`domain/external_order_observation.py`；
`infrastructure/pg_models.py`、`pg_repositories.py`、`pg_unit_of_work.py`、
必要的新精确仓储、`runtime_identity.py`、`runtime_authority_seed.py`和新迁移。
新增路径需落在现有Kernel边界，不能生成并行应用。

### 实施内容

- 管理权AUTO/REVIEW_REQUIRED/MANUAL与revision，人工不可逆；不改原始Ticket。
- 事件与证据引用、manual open/flat waiting状态、事实健康字段。
- 外部订单current、变化证据、覆盖游标和标的占用表的精确字段/索引/唯一约束。
- 对接管生效时间、交易所动作时间、接收时间分别建模，不混用时间。
- 历史自动记录初始化为AUTO，新实例不复制旧运行数据；MANUAL记录未来迁移必须保全。
- 新产品identity进入机器/PG/认证，配置丢失或schema不同不能默认为AUTO运行。
- 使用最小写权限；Owner API不能写管理权或修改外部证据。

### RED / 完成 / 停止

| 项目 | 要求 |
| --- | --- |
| RED | MANUAL回退、重复证据二次接管、错误Ticket引用、迁移丢历史均失败 |
| 完成 | Domain/PG约束一致；空库安装、非空停写升级、digest保全、重复运行结果明确 |
| 停止 | migration修改历史revision、活动仓位接管迁移、旧schema fallback、管理权双current |

迁移编号在开工时按真实head确定；不能在计划里提前占用一个可能冲突的编号。

## 6. M2 外部事实采集与归因

### 允许文件

`domain/position.py`与新增观测模型；`application/ports.py`、`runtime_facts.py`；
`infrastructure/venue_adapter.py`、`binance_order_attribution.py`、`production_runtime.py`；
Reconciliation中的采集调度和相关仓储。不得修改策略Detector。

### 实施内容

1. 类型化价格、触发价、原始/成交数量、订单类型、side、close-position语义、namespace及时间。
2. 实现M0验证过的事件订阅/REST补采，既读系统订单也读账户内相关外部订单。
3. 每轮有界读取，覆盖不完整时显式标记；游标仅在证据保存成功后前进。
4. 归因器输出system/natural/external/unresolved/out-of-scope，匹配durable命令和条款。
5. 处理条件单ID与执行订单ID关联，不能仅靠client ID前缀或订单消失。
6. 断线补采、去重、乱序、相同ID不同条款、先取消后重挂均可重放验证。

### RED与验收

- 同ID改单、未成交新增/撤销立即external，不等position quantity变化。
- 自身Runner换止损、自然TP1、系统取消不误报。
- 强平/自动过期/历史缺口不伪装成人工；重复与迟到不会覆盖新投影。
- 100/200条分页边界、普通/条件任一页缺失不能宣称完整。
- HTTP和账户订阅日志无凭据，断线不会无限占用CPU或无限增长文件。
- 证明网络I/O不在PG事务内；正常无变化采样无追加Trade Event。

完成证据包括协议fixtures、Recording Source和只读协议验证，不使用真实资金制造动作。

## 7. M3 接管事务与全部写权限入口

### 允许文件

拟新增`application/observe_trade_management.py`；现有reducer、UoW、command仓储、
`dispatch_exchange_command.py`、`maintain_ticket_lifecycle.py`、Lifecycle/Reconciliation接口；
受影响的controlled exit、Owner flatten和Selection drain调用点。

### 实施内容

- 单事务写证据、管理权事件、current、未发命令superseded和Owner projection。
- 接管后不修改交易所旧订单；正常MANUAL不创建OpenIncident冒充异常。
- REVIEW_REQUIRED只有取得完备系统解释才能恢复AUTO；MANUAL无返回路径。
- 所有产生effects和发送命令入口统一检查管理权，不能只在scheduler过滤。
- 已发送/未知命令继续只读核实，不能标为未发送或盲重发；其返回不派生人工仓新写入。
- 初始保护阶段外部操作作为交付异常核实，不能使用旧数量盲目挂保护。
- 明确Owner flatten对人工仓的跳过结果，部署drain不能关闭人工仓。

### 重点验证

**不增加人机并发产品流程，但必须证明已识别接管后的权限有效。**

- 接管提交后，queued旧TP、Runner、cancel、controlled exit通过所有入口均零发送。
- 接管后原TP1自然成交，只有事实更新，无保本/换stop/cancel-old-stop effects。
- 丢响应/重启后MANUAL保持，重复通知有稳定去重键。
- 接管事务中断全部回滚，或完整提交，不留下UI人工但Worker自动的半状态。
- 旧未知命令查明结果后不重新生成退出计划，未决ENTRY lane不被误释放。
- 初始保护已确认而尚未生成TP1时接管，不因跳过旧TP1步骤永久占住Lane；
  Lane释放与预算/标的占用分离，只有真实入场结果闭合才可释放。

完成依据为真实PG集成测试与Recording Venue计数；禁止把异常吞掉当作“无动作”。

## 8. M4 人工对账、结算与旧路径退出

### 允许文件

`application/reconcile_ticket.py`、`reconciliation_scheduler.py`、结算与基础Review用例；
`interfaces/reconciliation_worker.py`；positions/events/budget/monitor仓储与必要domain事件。

### 实施内容

- MANUAL从固定TP1数量校验路径退出，按实际成交和订单更新当前剩余仓位。
- 人工订单不是需自动清理的unowned orphan；范围外订单则独立表达，不自动吞入Ticket。
- 记录外部成交引用，使手动平仓可有真实费用/成交账目；缺失则显式不可用。
- `manual flat pending orders`不撤挂单，不伪终态，不释放可重新进入的标的占用。
- Owner撤完后只读收尾，终态、基础Review、预算释放和Owner投影原子一致。
- 部分减仓、改单只改变current和对应事件，冻结Ticket初始数量/止损不重写。

### RED与完成

- 任意比例减仓/同订单多次部分成交不抛固定TP1数量错误。
- 外部全平且有普通/条件残单时，系统cancel调用次数为0，标的不能重新进入。
- 最终确认归零及订单终态后，结算恰好一次，重复采样不重复释放预算。
- 缺历史、数量增加或归属矛盾时不得自动结束或建立虚假成交。
- 保留原自动终态测试，并证明本次没有把历史partial TP1缺陷标为“已修复”。

## 9. M5 风险占用与同标的互斥

### 允许文件

`application/build_capacity_claim.py`、`issue_ready_signal.py`、`issue_ticket.py`、
`revalidate_entry_dispatch.py`；现有risk/admission/budget仓储及新增标的锁；
不修改Owner风险限额、信号算法或交易所账户模式。

### 实施内容

- 人工接管不释放所有Reservation，保留真实占用，按设计第9节更新保守风险。
- 原初始风险与当前实际风险分离；利润侧stop不抵扣其他仓风险。
- 多档/重叠保护无法可靠分配时阻断新增，不能按所有订单名义数量相加认定保护完整。
- account实际保证金与现有Reservation组合避免重复扣算。
- Claim、Ticket及最终ENTRY发送都核对标的两方向占用，包含残留挂单和范围外订单。
- 手动平仓不重置旧Signal消费，不建立第二ENTRY generation；新机会保持原策略rearm。

### 最小数值与事务测试

| 场景 | 预期 |
| --- | --- |
| 接管但不减仓 | 初始占用不凭管理权变更消失 |
| 减仓一半且保护有效 | 可证明的剩余占用更新，不重复释放 |
| stop拉远 | 采用更高实际风险，占用不足阻断新增，不自动退出人工仓 |
| stop保本/盈利侧 | 不产生负预算，不无限释放 |
| 两个全量stop重叠/只保护部分仓位 | 不把名义订单量当真实覆盖，未知时阻断 |
| 两个策略同时申请同标的多空 | 真实PG下最多一个Ticket成功 |
| 原仓平了但条件单尚在 | 标的仍不可新开 |
| 数据断档/人工增仓 | 新增受限，无自动平仓或旧Ticket补仓 |

不增加每日亏损熔断；对数据/风险不明的新增准入限制不能被误写成新增日亏损政策。

## 10. M6 展示、通知与操作范围

### 允许文件

`application/owner_console/models.py`、`overview.py`、`trades.py`；
`infrastructure/pg_owner_read_repository.py`；现有HTTP DTO/OpenAPI与
`frontend/owner-console-v2/src/`相关页面/类型/测试；monitor/notice现有路径。

### 实施内容

- 显示自动、待核实、人工、已平待清理、结束；人工状态跨重启保留。
- 区分原始入场stop与当前实际stop；多档订单不伪装成一个精确保护价。
- 显示现存TP1/止损仍有效，人工仓程序不会继续保本/Runner管理。
- 接管确认与关键风险通知去重；普通频繁改价不刷屏。
- 无“交回自动”按钮、无接管前TOTP流程、无人工收益归因或操作建议页面。
- 既有全平入口明确列出人工仓跳过项，不能展示“全部已平”却有人工仓仍在。
- 只读API不修复状态、不写管理权或触发对账。

### 完成证据

DTO/查询/HTTP/UI测试和浏览器人工管理样例检查；未知事实有明确文本，
无凭据泄露，无假保护、假平仓、假交付。

## 11. M7 综合验证、审查和合同更新

### 文件与审查范围

审查从入口到最终venue调用，包括旧命令结果、orphan cleanup、Selection drain、
Owner flatten、维护工具，不能只审查新增文件。修改新分支适用合同与架构测试，
明确同标的双向禁入和人工托管状态，不要求Tokyo合同跟着改变。

### 验收映射

| 设计验收 | 计划任务 | 主要证据 |
| --- | --- | --- |
| A01、A08 | M2、M3、M7 | 无干预完整链及自身事件归因 |
| A02–A05、A07 | M0–M4 | 协议覆盖、外部历史、重启/补采 |
| A06、A11 | M3、M4 | 所有入口零新venue mutation |
| A09、A13 | M4、M5 | 清理前占用、无重复ENTRY、终态账务 |
| A10、A12、A14 | M5 | 数值风险、标的双向唯一性、预算释放 |
| A15、A16 | M2–M5 | 交付异常与范围外变化 |
| A17 | M1、M8、M9 | 保全、产品身份、错目标部署拒绝 |
| A18 | M6、M7 | UI/通知与PG真实状态一致 |

所有必要生产行为遵循RED→GREEN→review。新增测试保护不同失败条件，
不为增加数量而复制现有场景。不得放宽发送窗口、事实时限、保护断言或账户身份来通过。

### 建议验证命令

以下路径来自现有仓库；新测试路径在对应任务中创建后加入受影响切片。

```bash
.venv/bin/python -m pytest -q tests/trading_kernel/unit tests/trading_kernel/architecture
.venv/bin/python -m pytest -q tests/trading_kernel/integration/test_command_dispatch.py tests/trading_kernel/integration/test_ticket_lifecycle_maintenance.py tests/trading_kernel/integration/test_unknown_outcome_reconciliation.py tests/trading_kernel/integration/test_capacity_claim_to_ticket.py
.venv/bin/ruff check src/trading_kernel scripts/trading_kernel tests/trading_kernel migrations/trading_kernel
.venv/bin/mypy src/trading_kernel scripts/trading_kernel
git diff --check
```

文档阶段只执行文档/架构引用检查，不将上述工程测试记为已运行。
测试数据库使用仓库指定的可丢弃环境，不能连接生产。环境异常修环境，不弱化门槛。

## 12. M8 发布身份、新环境演练与精确认证

### 交付

1. 完成新产品部署目标防误用：服务器、账户、数据库、产品标记显式匹配。
   发布不能默认使用Tokyo target；相关脚本先在本地fake backend验证拒绝错误目标。
2. 新账户空库安装、seed、当前Universe准备、认证、Owner控制、五个写入者库存全部演练。
3. 迁移演练覆盖自动与人工终态历史保全；仍有活动人工仓时发布明确等待，不能自动drain。
4. 冻结最终commit；按最高受影响等级R4运行官方Kernel认证，配套API/Static分别认证。
5. 本地候选保持clean且精确HEAD一致，文档收口不要让部署误用旧SHA证书。

```bash
.venv/bin/python scripts/trading_kernel/certify_release_candidate.py --release-level R4
.venv/bin/python scripts/owner_console/certify_release_candidate.py
.venv/bin/python scripts/owner_console/certify_static_release_candidate.py
```

如当前认证依赖Golden/core-parity数据缓存，使用仓库认可的数据源与环境，不跳过该步骤。
认证失败先定位再修复，代码变化形成新候选；相同候选等待外部部署条件时不重复全套认证。

### 审查停止项

- 任一MANUAL写权限遗漏、错账户/错产品部署、未知结果重发。
- 不能识别允许的未成交/同ID操作，却声称全覆盖。
- “账户零仓”但残留订单或未决命令被忽略。
- 管理权回退、人工占用消失、反方向新单越过标的约束。
- 本分支的生产测试只靠模拟，未披露真实验证边界。

## 13. M9 新服务器部署与自然验收

### 部署前条件

Owner明确授权新目标部署；独立服务器/子账户/凭据已通过正常配置；
精确候选认证、行动时内部/交易所flat、无未决命令/Incident/预算债务和所需准备状态通过。
新环境没有从Tokyo复制活动运行数据。配置保持Owner认可的现有风险范围，不因seed默认值
静默改变风险或开启暂停策略。初始ENTRY保持关闭，正式授权另走正常控制路径。

### 执行与postflight

- 采用已经为新目标验证的官方流程，不临时绕过服务互斥、迁移保全或运行身份。
- 核验四个Worker与Owner API、产品commit/schema/seed、账号、只读交易所事实及控制保全。
- 新账户启用后观察自然信号，不手工构造Signal/Ticket或测试下单。
- 无干预自然交易验证完整自动路径；Owner在正常使用中作出的App干预验证接管与保留挂单。
- 运行模式、风险占用、接管通知、后续零系统写入、Owner清理后的终结分别留证。
- 无自然机会或Owner未操作时，写“实盘接管待验证”，不把软件部署当功能实盘验收。
- 保留Tokyo无变更证据，不改它的策略、凭据、持仓或服务。

### 回退与故障

发生故障先停止受影响的新自动准入并核实；已人工接管的仓位不因故障改回自动。
新schema已写入时fix-forward，不回退到不理解MANUAL状态的旧二进制。
不得通过强平人工仓、删订单、删历史、改SQL来制造部署或验收条件。

## 14. 证据账本与完成标准

实施日志与脱敏诊断放入忽略的任务目录；设计/执行状态及解释性文档正常提交。
日志不可保存凭据或DSN，不是运行authority。每阶段记录：

- 精确代码/测试范围、有效RED、GREEN命令与结果。
- 审查发现及解决证据、未验证的协议或实盘边界。
- 新增/变更schema、产品身份、控制保全和原自动行为对照。
- 发布证书对应SHA、新环境postflight、自然交易与接管验收分别列明。

**实现完成**：M1–M7全部必要验收通过，未解决阻断项为零。
**可发布**：M8精确证书和部署门槛齐全，不等于已经发布。
**软件部署完成**：M9postflight通过，不等于已有自然接管证据。
**实盘功能验收完成**：自然自动交易和Owner真实App接管均有直接证据，
无接管后系统新写入，终态残留清理/结算边界有对应验证。

## 15. 当前计划状态

2026-11-07更新：[前置实现交付记录](2026-11-07-app-manual-takeover-prevalidation-handoff.md)。
Owner要求在“完整验证与发布隔离”前等待确认；M7完整验收、M8、M9未执行。
以下为前一批基础实现历史，不代表当前最新进度。

已开始M0协议核实及首批纯模型/协议测试，见[M0证据记录](2026-11-06-app-manual-takeover-v1-protocol-evidence.md)。
尚未完成数据库、Worker接入或完整交易链，更未进行服务器采购/配置或部署。
各阶段完成须以实际测试和证据为准，计划中的命令不是已经通过的结果。
