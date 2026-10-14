# BRC-RECON-RELIABILITY-01：对账可靠性修复详细设计

日期：**2026-10-14**。状态：**本地修复已实施，联合精确认证待完成，未部署**。
来源：Owner 本线程明确要求对账修复与 **SOR-1H 联合上线**。

## 目标与硬边界

消除重复催办导致的对账饥饿，统一 Universe 权威事务锁序，安全丢弃失效认证
Claim，并用现有 Owner Monitor 暴露持续停滞。这是生产缺陷修复，不增加策略功能。

- 不改变策略、止损、资金、Selection 数值算法、交易规则或既有 Ticket 退出语义。
- 保持一个 Kernel、一条 PostgreSQL 权威链、四个常驻 Worker；不增加第二账本或服务。
- 网络 I/O 在事务外；每个交易所写仍需 durable Exchange Command。
- 无主动平仓、ENTRY 恢复、凭据修改、SQL 修补、兼容 Reader 或门槛绕过。
- 在 focused `codex/*` 分支实现与评审后合入 dev，不直接在 dev 开发。

## 已知事实与未闭合证据

| 项目 | 已知证据 | 仍需补齐 |
| --- | --- | --- |
| 对账饥饿 | Lifecycle mismatch 重写 due=now；selector 按最早 due 排序；实时采样看到 OP 向后移动；OP 后来正常终态 | 真 PG 复现重复催办与三 Ticket 并发，无需重演全部历史 |
| Universe 死锁 | PG server log 显示 Universe 行锁与安装 advisory lock 循环；hashtext 安装键=963081765 | 第二个生产事务的具体入口及全部已持锁资源映射 |
| 历史修复 | e2973d9f 统一 Instrument→Certification，未覆盖安装锁／Universe 锁对 | 按生产版本与联合候选重新检查跨 Repository 边界 |
| Claim 失效 | 原 owner／lease／Universe 条件 UPDATE 失败抛 RuntimeError；Worker 未捕获而退出 | 合法重领、Universe 更替、锁等待等实际原因，不能断言那次一定由锁等待造成 |
| 监控缺口 | OP 停滞时 Incident=0，重启恢复进程但不保证终态 | 在当前 Monitor 中定位可用字段／事件及最小持久化需求 |

来源：本线程 10 月 13–14 日 Tokyo journal、PostgreSQL server log、实时 PG／
交易所只读查询与当前源码。历史故障证据是诊断来源，不是当前部署授权或实时状态。
实施前应固定脱敏证据副本、时间范围及校验和，不能依赖轮转日志长期保留。

## R1：专用对账催办语义

### 接口与原子更新

在 Aggregate repository port 新增 `expedite_reconciliation(ticket_id, due_at_ms)`，
仅替换 Lifecycle mismatch 分支的对账催办。普通 `schedule_next_check` 不改。
Domain 不执行 SQL；PG 实现使用单条有条件原子 UPDATE：

```sql
reconciliation_due_at_ms = LEAST(
    COALESCE(reconciliation_due_at_ms, updated_at_ms),
    :due_at_ms
)
```

**空值语义与现有 selector 一致**：selector 已用 updated_at_ms 作为 due fallback，
因此催办不能把一个已经等待的 NULL-due Ticket 重置为现在。真实有效时间由数据库
现有列和调用方正值校验提供；不写额外“催办完成”事件。

### 竞争与失效

- 只针对当前可对账的非终态状态；并发终态时不得重新排入队列或重开预算。
- 保留已有更早 due；首次未来 due 可提前。正常对账成功／失败后仍可安排下一次检查。
- 现有关键对账 selector 没有持久 Claim 租约；不能把 routine Settlement／Review
  的未来租约误当成允许被催办清除的值。催办范围不包含这些 routine 状态。
- 并发更新按行锁串行化。对账在后提交时可设置下一检查，随后真实不一致仍可再催办；
  不用无限保持过期时间替代完整处理。

## R2：Universe 事务锁序

### 统一资源顺序与事务边界

**所有会调用安装／激活／回退且使用 Install Lock 的事务，必须在第一次可能冲突的
行锁或 UPDATE 之前取得 Install Lock**。不能仅把 try_activate 内的一行挪到顶部：
调用者此前已拿锁时，方法内部再调整仍无效。

事务顺序为：Install Lock → 该操作明确的权威行锁序 → 身份／版本／lease／proof
重校验 → 状态转换 → 原子提交。权威行锁具体顺序须依完整调用图固定；至少保留
已验证的 Instrument→Certification、Owner→Selection 及稳定身份排序，不猜造一条
与已有调用图冲突的全局列表。

实施审计清单：

1. install、try_activate AUTO／CERTIFY_CURRENT／CERTIFY_STAGED、Generic、Static、
   Dynamic pair、Fallback、abandon，以及其外层 coordinator／proof／recovery 事务。
2. 跨 Repository 的 FOR UPDATE、UPDATE、触发器、副作用函数、comparison／Episode
   锁；记录每条路径的首次锁、后续锁、调用者已持锁与回退分支。
3. 在事务边界显式取得共同锁；内部同事务重复取得只可作为一致性断言／复用，
   不将其当作修复锁序的替代。
4. 不持事务跨行情读取；不把 Install Lock 扩展到普通无 Universe 变更的持仓对账。
5. 不删除必要行锁、不全局 SKIP LOCKED、不使用无限重试掩盖反序。

### 故障与证据门槛

死锁 SQLSTATE 40P01 必须完整回滚事务。任何有界重试都在新 UoW 内重新读取身份，
不得继续使用旧 proof／Claim；不重放可能已产生外部效果的操作。
本设计首选修复资源顺序，不对所有 Worker 统一吞异常。

**合并门槛**：把生产死锁双方 SQL、锁对象和实际调用入口对应到代码，并用真实
PostgreSQL 屏障控制交错复现。若确切第二路径尚未映射，修复只可标为候选，不能 PASS。
同一审计必须包含 SOR-1H 新 pair 的路径，避免联合上线后再次暴露。

## R3：认证 Claim 安全失效

增加具名的 Claim 失效结果／异常，仅处理确证的任务竞争或过期：

1. 保存阶段核验 owner、lease 身份、Universe 身份以及数据库实际保存时刻的租约
   有效性；不能拿网络读取开始时刻证明提交时 lease 仍有效。
2. 更新未命中时分类合法重领、租约已过期／合法 Universe 替换、身份矛盾与数据库错误。
   只有前三者中的正常失效属于 superseded；身份矛盾仍阻断并显式报告。
3. 失效旧结果整笔回滚，包括提前 upsert 的 InstrumentRules、Instrument projection、
   Certification 和 Monitor；不能部分保存或继续 advance Universe。
4. 对确证 superseded 返回正常 Worker 状态，由正式 claim selector 后续重新领取；
   不抢回 lease、不覆盖新 owner、不无限重试、不随意延长默认 60 秒租约。
5. 网络仍在事务外，重领必须使用新事实。deadlock／连接错误等与 Claim 竞争分开处理。

## R4：最小业务停滞监控

复用 `brc_monitor_current`／既有 Monitor events；以 exact Ticket／Claim／Worker 身份
显示原因与最近进展。先沿现有调度读取已选对象；如需额外查询，使用索引、明确
时间下界和批量上限，不扫描全历史，不每 tick append 同一事件或生成报告文件。

| 信号 | 保存的最小证据 | 清除条件 |
| --- | --- | --- |
| mismatch 持续 | 首次真实 mismatch 时刻、连续读数、最近进展、Ticket | 已匹配或终态 |
| 关键对账过期 | 原 due／首次等待，不受重复催办重置 | 对账实际推进 |
| Settlement／Review 停留 | 进入阶段时刻与有效进展，而非普通调度更新时间 | 进入下一阶段／终态 |
| 重复 Claim 失效 | 现有身份上的有界频率／持续区间 | 新 Claim 成功或窗口结束 |
| Worker 重复失败 | 可读取的失败来源和有界时间窗口 | 恢复且正常窗口结束 |

### 阈值与 Worker 失败观察

- 阈值写为命名配置，由 poll、timeout、lease 和正常阶段预算推导；实现时固定
  推导值并验证负例，不预设一个无依据的固定分钟数。
- 至少连续多个真实快照才能判断 external-flat/internal-live，单次网络失败不算事故。
- Worker 进程已退出时不能依靠它自己写成功 Monitor。实现前核对现有 Observer／
  监控路径可否读取 systemd／journal 或失败事实；禁止为此新建守护服务。
  若新增跨进程失败观察所需持久字段，应明确列入 schema 设计与测试，不伪称已有。
- 先提供 Owner 可见异常，不把所有排队都升级 Incident；不得因监控触发自动平仓。

## 分项实施与必要验收

| 任务 | RED 条件与 GREEN 验收 | 允许修改边界 |
| --- | --- | --- |
| R1 | 重复催办推进 due、三 Ticket 被遗漏；修复后 NULL／未来／已到期／并发终态与正常重试均正确 | ports、PG aggregates、Lifecycle、相关定向测试 |
| R2 | 生产形状交错产生循环；修复后双事务完成、权威一致，身份漂移／timeout fail-closed | Universe／Selection repositories、必要外层 UoW 入口、真 PG 并发测试 |
| R3 | 过期旧 Claim 部分写入或 Worker 退出；修复后旧写全回滚、新 Claim 可推进，身份错误不被吞掉 | certification application／repository／Worker、定向 PG 测试 |
| R4 | 进程存活、事故为零而业务长期停滞；修复后 exact 原因 Owner 可见，恢复清除，瞬时等待不告警 | 现有 Monitor／Worker 观察路径及必要持久字段 |

联合链回归：Runner 外部自然平仓 → Reconciliation → 清理残余订单 → Settlement →
Review → terminal、预算／Netting Domain 释放；并发其他受保护持仓仍继续。
Recording venue 验证无重复 ENTRY、无错误取消其他 Ticket 保护、无提前容量释放。

每项只做必要 RED/GREEN 和受影响集成；不运行收益回测、参数搜索或额外 long soak。
完成后冻结**一个联合候选**，按正式 Release portfolio 做一次精确认证及 Owner API／
frontend 相关层验证，不能用旧 SOR-1H 认证冒充联合补丁认证。

## 数据与联合发布

**预期 R1–R3 不需新 schema；R4 是否需列在实现前确认**。若已有投影不足，迁移
必须明列新增字段和 source-preservation 证据；不能静默扩展或增加第二权威。
未发布 0011 的修改必须遵循当前前向链与正式 preservation 验证，不能分叉。

1. 修复、审查、生产死锁证据映射及联合精确认证通过后，才进入可部署状态。
2. 所有持仓自然退出、挂单／未决命令／活动预算／Incident 与非终态 Ticket 满足
   flat／quiescent；停止点还需满足运行任务和 source preservation 官方门槛。
3. **最新 Owner 指令要求部署前等待确认**，覆盖此前自动部署授权；不得部署旧
   832e1bf3 或只含 SOR-1H 的候选。监控任务保持暂停。
4. 通过官方部署工具执行 0010→0011 和软件发布，不带仓迁移，不提前恢复 ENTRY。
5. postflight 核对精确 code/schema/seed、保存源终态 lineage、四服务及 API、Owner
   新开仓暂停、旧 SOR ENTRY-disabled、新 pair 独立 paused、监控状态及无残留异常。
6. 迁移后只按正式 fix-forward 恢复，不降级 schema，不用旧代码读取新库。
   若持仓期间需先发布同 schema 抢修，须单独设计范围；不混成本次带仓迁移。

## 完成定义与尚未完成事项

**设计完成不等于修复完成**。Done 要求四分项证据、锁链映射、联合 exact 认证、
源 lineage 保留和生产 postflight，不能以 OP 曾自动终态或 Incident=0 替代。

证据补齐结果见下节：死锁资源链已直接核验并映射到可执行入口；历史 backend PID
与完整 Python stack 的逐项对应、Claim 那次失效的旧身份仍缺日志，必须如实保留。
R4 最小持久化与 Worker 失败来源仍待实施前确认；R2 的真实应用路径并发回归
仍是合并硬门槛，不能用下述简化 SQL 探针冒充通过。

本轮仅交付设计；未修改生产代码、数据库或服务。ALPHA-02、策略启用和收益研究
不混入此可靠性补丁。

## 生产证据补充（2026-10-14）

### E1：死锁双方 SQL 与可执行路径

**直接日志事实**：14:56:55，北京时间，PG backend 4151186 持有安装锁、等待
Universe 行锁；backend 4152932 持有冲突事务中的 Universe 行锁，等待安装 advisory
lock 963081765。对账异常参数指定 **MI v16**
`universe:36df22fd484f3096ae4b31e4:v16`。

对账路径已由完整异常栈确认：
`run_reconciliation_worker_once → _run_housekeeping_once → _certify_one_due_instrument
→ advance_strategy_universe → try_activate → _lock_installs → Universe FOR UPDATE`。

**反向可执行路径**（核对生产 57ad9fcc 源码，非只看最新 dev）：
`_coordinate_generic_generation(STAGED, retargeted Vacuum)
→ prepare_generic_recovered_activation_proof
→ get_generation_universe_targets(for_update=True)
→ advance_strategy_universe(ACTIVATE_GENERIC)
→ _activate_generic → _lock_installs`。
普通 STAGED／CERTIFY_STAGED 也先取得目标 Universe 行锁，再调用安装锁入口，
failure／retarget／abandon 类嵌套调用另有同类路径，R2 必须一并审查。

**生产交叉对应**：MI v16 在14:33:57进入 STAGED，其 Vacuum 沿用前代围栏，
因此走 recovered activation 分支；14:56:45–14:57:15 同期 Observation MI component
记录 `require_generic_recovered_activation_proof` 的失败定位。v16 后于15:30被新
Selection 替代。数据库对象、状态、时序和调用路径均一致。

**证据限制**：PG 历史日志只记录各事务当前 SQL，没有保存其全部前序 SQL；
Observation 日志未记录 backend PID。故不能宣称已得到 backend 4152932 的完整
Python stack，也不能只凭时间关联排除所有其他反序入口。已足够制定锁序补丁，
合并仍须真实应用路径并发回归覆盖，而非扩大日志开启生产全 SQL 记录。

### E2：Claim 失效不能等同于时间过期

**直接日志事实**：13:42:07 的异常发生在 `save_instrument_certification` 的
UPDATE rowcount != 1 分支。生产 SQL 比较 owner、lease 时间字段和 lease Universe
是否仍与 target 相同，**没有实际保存时刻与 lease expiry 的大小比较**。
因此“时间过了60秒”本身不会令该 UPDATE 变成0；必须发生字段变化／记录消失。
R3 增加提交时有效性检查属于补足约束，不是描述已有行为。

**相邻生命周期证据**：

| 北京时间 | 事实 | 来源 |
| --- | --- | --- |
| 13:40:37.225 | CPM v8 因 MATERIALIZATION_TIMEOUT 废弃 | Universe 行／FAILED_CLOSED event |
| 13:42:06.049 | BRF2 v8 因 MATERIALIZATION_TIMEOUT 废弃 | Universe 行／FAILED_CLOSED event |
| 13:42:07.156 | 认证旧 Claim UPDATE 未命中并退出 | Worker 异常栈 |

生产 `abandon()` 原子清除该 Universe 的 Certification lease owner／expiry／UID，
合法重领也会改变旧 Claim 身份。**BRF2 废弃距异常约1.1秒，是直接支持的候选原因**，
但异常未保存失败 target 的 instrument／UID／旧 owner／lease，不能确证它属于 BRF2。

**历史证据缺口**：log_statement=none、log_min_duration_statement=-1、
log_lock_waits=off；Claim 当前行已覆盖，领取／失效没有 append-only 明细。
因此无法恢复该次旧 Claim，也无法证明锁等待是否促成它的失效。不得假称延长
租约能解决。实现需覆盖废弃撤销、合法重领和真实租约过期三种安全失效。

### E3：必要的本地 SQL 探针

在一次性本地 PostgreSQL 测试库、两连接中重现相同安装键和行锁的反向交错，
得到 **SQLSTATE 40P01**；另一个事务在牺牲事务回滚后继续完成。
使用相同 Claim 等值谓词验证：字段不变 UPDATE 1；abandon 清除字段后 UPDATE 0。
临时数据库已删除，没有生产写或交易所写。

这是**资源顺序和 CAS 条件的探针**，不是 Kernel 应用链验收，不替代 R2/R3 真 PG
回归或联合候选认证。脱敏原始摘要与探针输出保存在本地 display-only
`.local/reconciliation-evidence-20261014/`，不提交原始运行日志。

## 本地修复实施记录

- 专用 expedite 保留原到期年龄，普通 retry/lease 语义不变。
- coordinator 从外层 UoW 先取安装锁，嵌套激活／恢复／废弃复用同一锁；
  普通 Entry／事实权威读只保留行锁，不能在已持行锁后补取安装锁。
- Claim 在 Instrument→Certification 锁后核验数据库权威时钟；失效事务整体回滚，
  不推进 Universe，不接受过期事实，缺失／矛盾身份保持异常。
- Monitor 复用现有表，保留首次等待；覆盖持仓不一致、关键对账过期、Closure 停滞、
  重复40P01及Claim失效。终态清除提示，无新schema／服务／资金或策略变化。
- 仅已回滚的40P01返回 database_retry，下一自然tick重读；其他数据库错误仍抛出。
- 验证覆盖真实PG重复催办、三Ticket公平性、并发retry、旧Claim回滚、保存时过期、
  MI实际路径锁竞争；最终发布证据只认冻结提交的正式认证。
- 原始日志、本地验证日志均为display-only，不提交为runtime权威。
- 当前仅本地实现；生产未改动，部署前等待Owner明确确认。

## 暂停状态下的部署静止性补充

Owner 明确要求不恢复 ENTRY。部署前保持 Policy 暂停、Entry 服务禁用与写围栏。
已全平后停止准备／认证写入，未完成 Generation 只能由原版本正式 coordinator 在
真实 deadline 到达后终结，不能提前伪造失败或 SQL 清理。

0010→0011 新增精确 negative-fence 静止性证明：终态 FAILED_CLOSED、lease 清空、
真实排空与失败／RECOVERY_REQUIRED 事件、目标全部 abandoned 且无启用 scope、
原 baseline 仍 current、同 Selection epoch/control、正式 Owner Policy pause lineage、
无 Ticket／position／command／budget／Incident 负债。Policy 为 true 或任一证据缺失
仍阻断。预检与迁移锁定后共用证明；锁保护全部证明依赖行。

这是保留负围栏的暂停迁移，不是解除围栏、授予恢复 Authority 或 ENTRY。失败历史、
原意图与全部源行原样保留，后续自然运行仍需正式新周期与真实恢复证明。
仅0010源升级使用新增证明，旧迁移默认行为不变；不修改旧SOR禁用或任何资金参数。
新候选必须重新取得精确R4/R2/R1认证，原315aa28b认证不覆盖本次迁移补充。
