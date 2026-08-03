# Portfolio Admission Observability 测试设计

> 日期：2026-08-03
> 对应设计：`2026-08-03-portfolio-admission-observability-design.md`
> 原则：每条用例必须能指出一个会使它失败的真实生产缺陷；生产行为必须先 RED、后 GREEN。

## 1. 测试层级

| 层级 | 目标 | 数据边界 |
|---|---|---|
| Unit | Episode reducer、Policy、Family、direction、materialization、MFE/MAE 纯规则 | frozen Pydantic + Decimal |
| Integration | PostgreSQL 唯一性、事务、查询边界、Migration、Seed | disposable PostgreSQL |
| Full chain | Observation→Signal→Decision→Claim/Ticket 或拒绝→Shadow | recording venue/public market fake |
| Architecture | 单一执行链、Schema head、无旧 reader/dual write、无文件权威 | tracked source scan + executable checks |
| Deployment | exact `0002 -> 0003`、全平、Entry-last/Entry-off、保存清单 | fake backend + local release rehearsal |

## 2. Episode Identity

| ID | 缺陷变异 | 输入 | 预期断言 |
|---|---|---|---|
| EPI-001 | 连续 true 每小时创建新 Episode | CPM v2 连续两个闭合 1h 都 TRIGGERED | 第二次复用同一 Episode；Signal insert 为 duplicate |
| EPI-002 | false 未重新武装 | CPM v2 true→false→true | 第三次创建新的 Episode ID |
| EPI-003 | 无效 Observation 错误 re-arm | true→INVALID→true | 仍复用原 Episode |
| EPI-004 | Warming 污染 Episode state | Warming TRIGGERED/NOT_TRIGGERED | Episode projection 零写入 |
| EPI-005 | Universe replacement 重置连续 Episode | 同 Event v2、同 instrument，Universe replacement 后继续 true | Episode ID 不变 |
| EPI-006 | Event version replacement 复用旧 Episode | CPM v1→v2 | v2 domain 与 v1 不同 |
| EPI-007 | SOR recross 创建新 Episode | 同一 Session inside→recross | 仍为同一 Session Episode |
| EPI-008 | SOR 新 Session 没有 re-arm | 次日 Session | 新 Episode ID |
| EPI-009 | Live/Replay Episode reducer 不一致 | 同一 closed-candle 序列 | 状态和 Episode ID 完全一致 |
| EPI-010 | 并发 Observation 产生两个 rising-edge Episode | 相同 domain/version 两事务竞争 | row lock 后最多一个新 Episode |

## 3. AdmissionDecision

| ID | 缺陷变异 | 场景 | 预期断言 |
|---|---|---|---|
| ADM-001 | admitted Ticket 没有 Decision | 正常准入 | Decision、Claim、Ticket、Reservation、ENTRY Command 同事务存在 |
| ADM-002 | rejected Signal 没有原因 | Family 满 | `rejected + exposure_family_capacity_exhausted` |
| ADM-003 | Decision 重复 | 同一 Signal 再次处理 | `signal_event_id` 唯一；不创建第二条 Decision |
| ADM-004 | 候选摘要排序不稳定 | 同一 candidate set 不同输入顺序 | candidate set digest 相同 |
| ADM-005 | candidate set 无界 | 65 candidates | 明确拒绝，不执行全历史查询 |
| ADM-006 | rejected Decision 创建 Command | capacity rejection | Ticket、Reservation、Command 均为零 |
| ADM-007 | Decision 写失败但 Ticket 保留 | 注入 Decision insert failure | 整个 issuance transaction rollback |
| ADM-008 | readiness blocked 但 Decision 缺失 | action-time policy mismatch | Readiness 和 rejected Decision 同时提交 |
| ADM-009 | action facts timeout 被误作产品拒绝 | public/account facts timeout | blocker 为 observation_unavailable；无 Shadow |
| ADM-010 | 旧选择在网络读取后不再 rank 1 仍下单 | 更高优先候选在期间出现 | 原 Signal 不发 Ticket，不写终态拒绝，可在后续重新仲裁 |
| ADM-011 | Decision digest 忽略关键字段 | 改变 policy/family/candidate digest 任一字段 | decision digest 改变 |
| ADM-012 | Decision 允许额外未类型化字段 | malformed snapshot | Pydantic `extra=forbid` 拒绝 |

## 4. Policy v4 与 Capacity

| ID | 缺陷变异 | 场景 | 预期断言 |
|---|---|---|---|
| CAP-001 | 单 Ticket 仍使用 3% | 空账户 | planned stop-risk 上限为 wallet 的 2% |
| CAP-002 | 总风险超过 6% | 已有 4% 同方向风险，申请 2% | 总风险最多 6% |
| CAP-003 | 同方向超过 4% | 已有 4% long，新的 long | directional_risk_exhausted |
| CAP-004 | 方向限制错误阻止反向 | 已有 4% long，申请 short | short 可在其他 gate 通过时接纳 |
| CAP-005 | Family limit 未执行 | 已有 CPM long_continuation，申请 MPG | family rejection |
| CAP-006 | Family 字符串由 StrategyGroup 猜测 | Registry mapping 改变 | admission 使用冻结 Event mapping |
| CAP-007 | opening_range 只能一笔 | 已有一个 SOR，第二个 SOR | Family limit 2 下仍可接纳 |
| CAP-008 | 第三个残余小 Ticket 仍创建 | 剩余风险小于目标 50% | budget_exhausted；binding=min_materialization_ratio；无 Ticket |
| CAP-009 | 恰好 50% 被错误拒绝 | 可用预算等于 minimum | 可以继续 sizing |
| CAP-010 | margin cap 仍为 45% | 空账户 | 单 Ticket initial margin 上限 30% |
| CAP-011 | active Family usage 未冻结 | Claim 创建后改变 active set | Claim 保留 action-time family count/limit |
| CAP-012 | Ticket 丢失 Family lineage | admitted | Claim 与 Ticket exposure_family 完全一致 |
| CAP-013 | 历史 v1 Ticket 被重算 2% | migration 后读取历史 | 原风险、数量、Policy version 不变，仅确定回填 Family |
| CAP-014 | unknown family permissive fallback | Event 没有合法 family | fail closed，不创建 Claim |

## 5. Shadow Outcome

| ID | 缺陷变异 | 场景 | 预期断言 |
|---|---|---|---|
| SHD-001 | admitted Signal 创建 Shadow | admitted Decision | Shadow count 为零 |
| SHD-002 | infrastructure rejection 创建误导 Shadow | action facts timeout | Shadow count 为零 |
| SHD-003 | Family rejection 没有 Shadow | 有有效 entry/stop | 创建一条 pending Shadow |
| SHD-004 | Shadow 创建真实 Ticket | pending Shadow | Ticket/Reservation/Command count 不变 |
| SHD-005 | long MFE/MAE 方向算反 | hand-checked OHLC | MFE/MAE R 与字面量一致 |
| SHD-006 | short MFE/MAE 方向算反 | hand-checked OHLC | MFE/MAE R 与字面量一致 |
| SHD-007 | 未闭合或未来 candle 被消费 | horizon 前后混合数据 | 只使用 horizon 内闭合 candles |
| SHD-008 | 正常 Observation 被 Shadow 抢占 | 同时有 due scope 和 due Shadow | 先处理 Strategy Scope |
| SHD-009 | 一次处理无界 Shadow jobs | 多个 due jobs | 每个 idle tick 最多 claim 1 条 |
| SHD-010 | Shadow 网络调用发生在 PG 事务内 | recording source + connection guard | fetch 时没有 open UoW transaction |
| SHD-011 | 重试创建重复 outcome | lease 到期重试 | 同 admission_decision_id 仍只有一条 current outcome |
| SHD-012 | 24h 1h 请求越界 | 1h Strategy | limit=24 |
| SHD-013 | SOR Session 请求越界 | 15m SOR | limit≤96 且 horizon 为冻结 Session end |
| SHD-014 | 零 stop distance 产生除零 | entry=stop | outcome unavailable，明确 reason |
| SHD-015 | Shadow 被误报为净收益 | readonly output | evaluation_kind 明确为 fixed_horizon_excursion_v1 |

## 6. 关键全链 Replay

### 6.1 昨夜组合时序

| 时间 | Event | 预期结果 | First blocker |
|---|---|---|---|
| 00:00 | CPM BNB Long | admitted，2% risk | 无 |
| 02:00 | CPM DOGE Long | rejected | exposure_family_capacity_exhausted |
| 07:00 | BRF2 ETH Short | admitted，2% risk | 无 |
| 09:15 | 第一名 SOR Short | admitted，最多 2% risk | 无 |
| 09:15 | 其余 SOR Short | rejected | budget_exhausted 或 opening_range/directional 约束的稳定 first blocker |

断言：

1. 最终 Active Ticket 最多 3；
2. gross stop risk 最多 6%；
3. long stop risk 最多 4%，short stop risk 最多 4%；
4. long_continuation 最多 1；
5. 每个最终处理的 Signal 有 AdmissionDecision；
6. 所有 rejected 机会没有 Exchange Command；
7. 有效组合拒绝创建 pending Shadow；
8. 已有 Ticket Lifecycle 不受影响。

### 6.2 连续触发与重新武装

```text
CPM BNB true 00:00
-> true 01:00
-> false 02:00
-> true 03:00
```

预期：00:00 与 01:00 属于同一 Episode；03:00 属于第二个 Episode。若第一个 Episode 已有 Ticket，01:00 不得产生第二个 Ticket。

## 7. PostgreSQL 与事务测试

| ID | 对象 | 必须验证 |
|---|---|---|
| PG-001 | episode current | exact domain PK、row lock、monotonic projection version |
| PG-002 | admission decisions | signal unique、digest format、admitted/rejected shape check |
| PG-003 | shadow current | admission unique、lease shape、terminal field shape |
| PG-004 | owner policy | 2/6/3、30/90、50%、4%、family limits check constraints |
| PG-005 | claim/ticket | exposure family 和新增 action-time lineage 非空 |
| PG-006 | bounded selectors | active≤3、candidate≤64、shadow claim limit=1 |
| PG-007 | issuance atomicity | Decision failure rolls back Claim/Ticket/Command |
| PG-008 | rejection atomicity | Decision 和 Readiness blocker 同事务 |

## 8. Migration 测试

| ID | 起点 | 操作 | 预期 |
|---|---|---|---|
| MIG-001 | empty PostgreSQL | upgrade head | `0003_portfolio_admission_observability` |
| MIG-002 | production-shaped 0002 terminal history | upgrade 0003 | source-column manifest 完全一致 |
| MIG-003 | production-shaped 0002 | upgrade | v1/v2/v3 Registry lineage均可解析，当前版本指向 vNext |
| MIG-004 | production-shaped 0002 | upgrade | Policy v4 且 Entry disabled |
| MIG-005 | production-shaped 0002 | upgrade | 历史 Ticket/Claim Family 确定回填，金融字段不变 |
| MIG-006 | 0003 | downgrade 0002 | 明确拒绝 |
| MIG-007 | non-flat 0002 | deploy compatible_upgrade | migration 前阻止 |
| MIG-008 | preservation mismatch | deploy | Entry fenced，目标版本 fix-forward |
| MIG-009 | wrong source revision | deploy | service stop 前阻止 |

## 9. Deployment 测试

| ID | 缺陷变异 | 预期 |
|---|---|---|
| DEP-001 | regular mode 尝试跨 Schema | 拒绝 |
| DEP-002 | compatible source 不是精确 0002 | 拒绝 |
| DEP-003 | 使用 `--enable-entry` 部署本轮 RC | 发布计划拒绝或验收任务禁止 |
| DEP-004 | 迁移后安全 worker 未全部 active | postflight 失败，Entry 保持 fenced |
| DEP-005 | Registry/Policy/Schema identity 任一不同 | postflight 失败 |
| DEP-006 | Shadow pending 存在 | 不阻止 safety worker；不授权 Entry |
| DEP-007 | Active Ticket/order/reservation/incident 任一非零 | migration 前阻止 |
| DEP-008 | source preservation digest 不同 | 发布失败并保持 fence |

## 10. Architecture 测试

必须证明：

1. `src/trading_kernel` 仍是唯一生产执行包；
2. Episode projection 只由 Observation 写；
3. Family mapping 只来自 Registry，limit 只来自 Owner Policy；
4. Shadow Outcome 不导入 Ticket、Command dispatch 或 venue write adapter；
5. Domain 模块不导入 SQLAlchemy、filesystem、subprocess、web framework；
6. Production idle cadence 不创建 JSON/Markdown；
7. Schema 只有一个 head；
8. 没有 `0002` runtime reader fallback、dual write 或 downgrade；
9. `max_strategy_group_concurrent_tickets` 不再是 current admission authority；
10. current 文档中的 Policy、Schema 与链路口径一致。

## 11. 验证命令

实现过程中按任务运行 focused RED/GREEN；最终至少运行：

```text
pytest tests/trading_kernel/unit -q
pytest tests/trading_kernel/integration -q
pytest tests/trading_kernel/full_chain -q
pytest tests/trading_kernel/architecture -q
pytest tests/trading_kernel -q
ruff check src/trading_kernel scripts/trading_kernel tests/trading_kernel migrations/trading_kernel
mypy src/trading_kernel scripts/trading_kernel
git diff --check
```

若 PostgreSQL、Binance 或本机依赖导致某项不能运行，必须明确报告实际跳过项，不得用 focused tests 推断全部通过。
