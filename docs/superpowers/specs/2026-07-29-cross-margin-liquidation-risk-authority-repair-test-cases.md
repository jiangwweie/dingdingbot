---
title: Cross-Margin Stop-Stress Authority Repair Test Cases
status: PROPOSED_OWNER_REVIEW
authority: NOT_CURRENT_AUTHORITY
date: 2026-07-29
revision: 2
design: 2026-07-29-cross-margin-liquidation-risk-authority-repair-design.md
---

# Cross-Margin Stop-Stress Authority Repair Test Cases

## 目的

本文档把 revision 2 设计转换为可执行断言。Owner 确认后，实施必须先观察
RED，再修改生产代码。

本文件定义 **81 个语义场景**，不是要求编写 81 个重复测试函数。Long/Short、
零值/错误方向、bracket 边界和故障矩阵必须使用 `pytest.mark.parametrize`
或 typed fixture 复用，避免复制测试代码。

本地测试不得连接真实交易所、修改 Tokyo、启动 Entry 或创建真实订单。

## 测试分层

| 层 | 主要目标 | 禁止的捷径 |
| --- | --- | --- |
| Domain | 压力区间、margin surplus、typed invariants | mock Domain 内部实现 |
| Adapter | 官方字段到 AccountRiskSnapshot 的唯一映射 | 两套 parser、字段 fallback |
| Application | Claim/Dispatch/Post-fill 复用同一 proof | 复制公式 |
| PostgreSQL | Event/Aggregate/Incident/Command 原子性 | DML 伪造终态 |
| Full-chain | Signal 到 Review 的真实生产边界 | 下游 fixture 冒充上游 |
| Architecture | 无旧权威、胶水、第二执行链 | 只检查 happy path |

所有金融值使用 `Decimal`。网络 I/O 必须在事务外，所有 Exchange mutation
必须 durable-before-dispatch。

## 拟议测试文件

| 文件 | 边界 |
| --- | --- |
| `tests/trading_kernel/unit/test_cross_margin_stress.py` | 纯 Domain 压力证明 |
| `tests/trading_kernel/unit/test_capacity_sizing.py` | Claim 复用 proof |
| `tests/trading_kernel/unit/test_entry_dispatch_preflight.py` | dispatch action-time proof |
| `tests/trading_kernel/unit/test_post_fill_risk.py` | actual Stop Risk 与 stress 分离 |
| `tests/trading_kernel/unit/test_venue_adapter.py` | 唯一 AccountRiskSnapshot parser |
| `tests/trading_kernel/unit/test_reducer.py` | pending/result Event/effects |
| `tests/trading_kernel/integration/test_ticket_lifecycle_maintenance.py` | Stop-first、Incident、重试 |
| `tests/trading_kernel/integration/test_schema_baseline.py` | `0003` flat-only schema |
| `tests/trading_kernel/full_chain/test_cross_margin_post_fill_stress.py` | P0 事故与完整链 |
| `tests/trading_kernel/full_chain/test_multi_position_certification.py` | 多仓位、双 Side |
| `tests/trading_kernel/architecture/test_cross_margin_risk_authority.py` | 单一模型和无胶水 |

## A. Domain 压力证明

以下 Side 对称场景使用同一参数化测试。

| ID | 场景 | 必须断言 |
| --- | --- | --- |
| STR-001 | Long/Short 单仓位，全区间 surplus 为正 | `passed`，stress price 和 minimum surplus 精确 |
| STR-002 | Long/Short 在 Initial Stop 前已经触及维护边界 | `failed` |
| STR-003 | Initial Stop 安全，但 Stop 外压力区间触及边界 | `failed` |
| STR-004 | 最小 surplus 恰好为零 | `failed`；通过条件必须严格大于零 |
| STR-005 | Long raw stress price 小于零 | clamp 到 `0` 并冻结 flag |
| STR-006 | Short stress price 正常向上扩展 | 不应用 Long clamp |
| STR-007 | 当前 mark 已越过 Initial Stop | `failed` |
| STR-008 | 同合约 Long/Short 同时存在 | 两个 Side 均进入 projected UPNL/MM |
| STR-009 | 相反 Side 完全或部分对冲 | 不净成无 Side 身份仓位 |
| STR-010 | 当前账户 totals 扣除交易所 UPNL/MM | base 使用 snapshot 原值；base maintenance 为负时 contradictory |
| STR-011 | 区间跨一个或多个 bracket | 检查所有边界端点，选择真实 minimum |
| STR-012 | bracket floor/cap 恰好落在 stress/stop | 端点去重后只计算一次 |
| STR-013 | bracket gap、重叠、未排序或不唯一 | `facts_contradictory` |
| STR-014 | symbol coefficient 缺失、非法或未认证 | `facts_contradictory` |
| STR-015 | 余额、价格、数量、UPNL、MM 非有限或身份重复 | typed model 拒绝 |
| STR-016 | canonical digest 参数化 | 输入顺序变化时不变；任一金融/身份字段变化时必须改变 |

## B. Claim 与 Dispatch 单一权威

| ID | 场景 | 必须断言 |
| --- | --- | --- |
| AUT-001 | Flat instrument 新 Long/Short | Claim 使用同一 `evaluate_cross_margin_stress()` |
| AUT-002 | 已有相反 Side，新建目标 Side | hypothetical positions 包含两边 |
| AUT-003 | Claim facts unavailable/contradictory/failed | 无 Claim、Ticket、Command |
| AUT-004 | Dispatch action-time proof 与 Claim 一致 | 允许 durable ENTRY dispatch |
| AUT-005 | Dispatch 时 balance、position、bracket 或 mode 变化 | 重新计算；失败则 ENTRY 终态拒绝 |
| AUT-006 | Claim 与 Dispatch 输入完全相同 | proof payload 和 digest 完全一致 |
| AUT-007 | 策略、Universe 不同但风险事实相同 | 结果相同，策略不能覆盖风险决策 |

## C. Adapter 与账户模式

| ID | 场景 | 必须断言 |
| --- | --- | --- |
| ADP-001 | USD-M Account `multiAssetsMargin=false` | `standard_usdm_single_asset` |
| ADP-002 | Multi-Assets、Portfolio adapter、非 USDT settlement | snapshot 拒绝 |
| ADP-003 | Hedge/Cross/固定 `5x` 精确匹配 | snapshot 成功 |
| ADP-004 | One-way、Isolated 或 leverage mismatch | snapshot 拒绝 |
| ADP-005 | Account totals 与精确 Long/Short UPNL/MM | 同一 account response 原样映射，并与 positionRisk identity/quantity 交叉验证 |
| ADP-006 | target position row 缺 UPNL、MM、entry 或 Side | snapshot unavailable/contradictory，不补默认值 |
| ADP-007 | bracket `cum` 与 coefficient | 完整进入 typed rules 和 digest |
| ADP-008 | raw liquidation `"0"` 或 not-side-directional 正数 | 原样保存 observation，不改变 risk digest |
| ADP-009 | raw liquidation 缺失与非法数字 | 两种 Monitor 状态明确区分；canonical snapshot/proof 仍可成功 |
| ADP-010 | Entry composite 与 Post-fill narrow read | 复用同一 `_read_account_risk_snapshot()`；无第二 parser |

ADP-010 必须使用 spy/call assertion 证明共享解析器被复用，而不只做 source
string 搜索。

## D. Post-Fill 生命周期

| ID | 场景 | 必须断言 |
| --- | --- | --- |
| PFL-001 | 完整 Entry Fill | `EntryFilled` 记录 fill/Stop risk/raw observation，不包含 stress proof |
| PFL-002 | Fill 后 risk source 立即超时 | Initial Stop 仍先持久化、提交和确认 |
| PFL-003 | Stop 方向错误 | 立即 durable Controlled Flatten；不创建无效 Stop |
| PFL-004 | actual Stop Risk 超硬上限 | Initial Stop 后一个 durable Flatten |
| PFL-005 | Initial Stop 确认且 Stop Risk 可接受 | 进入 `post_fill_risk_pending`，保留 Entry Lane，无 TP1 |
| PFL-006 | facts unavailable/contradictory | 无 Trade Event；幂等 Incident/Monitor/due-at |
| PFL-007 | unavailable 重复十次并重启 | 无 Event spam、无 Command、Stop 和 pending 状态不变 |
| PFL-008 | stress `passed` | 一个 `PostFillStressAssessed`，解决 Incident，释放 lane，准备一个 TP1 |
| PFL-009 | stress `failed` | 一个结果 Event，打开 failed Incident，准备一个 Flatten，无 TP1 |
| PFL-010 | failed 后 Flatten 尚未闭环 | account-capacity block 和 Entry Lane 不提前释放 |
| PFL-011 | failed 后 external flat、无残单并 ReconciliationMatched | 解决 failed Incident，释放 lane/budget/domain |
| PFL-012 | result commit/dispatch 前后故障与重复运行 | expected version + durable command 保证至多一个结果和 Command generation |

## E. ETH/AVAX P0 回归

| ID | 事故夹具 | 必须断言 |
| --- | --- | --- |
| REG-001 | ETH Long raw liquidation=`0`，stress passed | Initial Stop -> TP1；无误 Flatten |
| REG-002 | ETH Long raw=`0`，facts unavailable | 保持 Stop、阻止 Entry、无 TP1/Flatten |
| REG-003 | AVAX Long entry=`6.60`、stop=`6.383`、raw=`14.076`，stress passed | raw 仅审计；无误 Flatten |
| REG-004 | 同一 AVAX raw，但 margin surplus failed | 只有 stress proof 可以触发保护后 Flatten |
| REG-005 | 只改变 raw observation，canonical facts 不变 | proof、Event 和 Command decision 完全不变 |

事故 fixture 是脱敏语义样本，不声称重建当时完整账户历史。

## F. 多仓位与调度

| ID | 场景 | 必须断言 |
| --- | --- | --- |
| MUL-001 | BTC 已保护，新增 ETH Long/Short | ETH proof 使用账户 totals，BTC 作为固定 base |
| MUL-002 | 同合约相反 Side 已保护，新增目标 Side | 两边进入同一精确合约压力函数 |
| MUL-003 | 同 Netting Domain 已有 Ticket | 在 projector 前拒绝 |
| MUL-004 | 一个 Ticket risk facts unavailable | 阻止新 Entry，其他 protected/runner Ticket 继续管理 |
| MUL-005 | 一个 Ticket stress failed | 只为该 Ticket 创建 Flatten，不改写其他 Stop |
| MUL-006 | 多个 risk-pending Ticket | 现有 due-at selector 按精确 Ticket 有界推进 |
| MUL-007 | 两个活跃 Ticket 加 Settlement/Review | overdue closure 优先，不重新产生调度饥饿 |

## G. PostgreSQL 与迁移

| ID | 场景 | 必须断言 |
| --- | --- | --- |
| DB-001 | 空库迁移到 `0003_cross_margin_stop_stress` | schema identity/allowlist 一致 |
| DB-002 | 任一 Ticket/Event/Command/Position/Incident/Review 存在 | migration 拒绝并完整回滚 |
| DB-003 | 官方 flat-runtime reset 后表为空 | migration 成功 |
| DB-004 | schema inspection | 所有旧 liquidation root/ratio 字段和 Policy 字段消失 |
| DB-005 | Claim/Ticket/Aggregate/Event round-trip | 新最小 projection 和完整 typed evidence 可复算 |
| DB-006 | unavailable/contradictory retry transaction | 只 upsert Incident/Monitor/due-at，不追加 Event |
| DB-007 | assessed result fault injection | Event、Aggregate、Incident effect、Command 原子提交或全回滚 |
| DB-008 | Event registry/reload | 新 Event union、repository registry、Aggregate 状态一致 |

## H. Full-Chain

| ID | 完整场景 | 必须链路 |
| --- | --- | --- |
| CHN-001 | 正常 Long/Short 参数化 | Signal -> Claim stress -> Ticket -> ENTRY -> Fill -> Stop -> stress passed -> TP1 -> runner -> flat -> Settlement -> Review |
| CHN-002 | ETH raw zero 与 AVAX not-side-directional 参数化 | 正常闭环，无误 Flatten |
| CHN-003 | post-fill unavailable 后恢复 passed | Stop 全程存在；无早发 TP1；恢复后闭环 |
| CHN-004 | post-fill unavailable 后恢复 failed | Stop 全程存在；一个 Flatten；闭环 |
| CHN-005 | 同合约 Long/Short | 两 Ticket、两保护链、一个账户 snapshot 语义 |
| CHN-006 | 三个不同 Netting Domain | Entry 串行，Lifecycle/Reconciliation 并发，不串 Ticket |
| CHN-007 | risk pending + protected + closure | Settlement/Review 公平、actualOrderId、GTX、BNB Review 全部不回归 |

每个 Full-chain 场景必须共同断言：

```text
one Exposure Episode -> one Ticket
one ENTRY command generation
Initial Stop before TP1 or post-fill Flatten
every exchange mutation has one durable Command
raw venue liquidation observation has zero command authority
snapshot/model/rules/policy/fill/stop identities frozen
unknown outcome never blindly resent
external flat and no residual order
budget/domain/lane released at the correct terminal boundary
Settlement and Review complete
zero unresolved Ticket Incident
```

## I. 架构、性能与无胶水

| ID | 边界 | 必须断言 |
| --- | --- | --- |
| ARC-001 | Source scan | 只有 `cross_margin_stress.py` 实现压力函数 |
| ARC-002 | Retirement | 无 root solver、旧 liquidation authority、alias、dual read/write |
| ARC-003 | Facts | Entry composite 与 Post-fill 使用同一 AccountRiskSnapshot 类型/parser |
| ARC-004 | Domain purity | 不导入 Application；无 SQLAlchemy、venue、filesystem、subprocess、web 或 float |
| ARC-005 | Transactions | 所有账户网络读取发生在 PostgreSQL transaction 外 |
| ARC-006 | Commands | Stop、TP1、Flatten 均 durable-before-dispatch |
| ARC-007 | Runtime | 不新增 worker、timer、queue 或第二 selector |
| ARC-008 | Performance | bounded calls/points/query；retry 不 busy-loop；零运行文件 |
| ARC-009 | Regression | Settlement/Review fairness、order attribution、GTX、BNB、Universe 全部绿色 |

## Required RED 顺序

Owner 再次确认后按以下顺序实施：

1. `REG-001 / REG-003`：当前 raw 值会误触发 Flatten；
2. `PFL-002 / PFL-005`：Fill、Stop 与 stress 尚未分离；
3. `AUT-006 / ARC-001`：Claim/Dispatch 存在重复公式；
4. `STR-008 / STR-011`：双 Side 和 bracket 边界尚无统一 stress evaluator；
5. `ADP-005 / ADP-010`：当前事实模型缺 UPNL/MM 且未共享；
6. `PFL-006 / MUL-007`：Incident retry 和公平调度缺少新状态覆盖；
7. `DB-004 / DB-008`：旧 schema/Event registry 尚未替换；
8. `CHN-001` 至 `CHN-007`：完整链和既有 P1 回归尚未闭合。

禁止通过修改期望值、删除 safety assertion、`xfail`、skip 或下游 DML
fixture 制造绿色。

## 本地验证

### Targeted

```bash
uv run pytest -q \
  tests/trading_kernel/unit/test_cross_margin_stress.py \
  tests/trading_kernel/unit/test_capacity_sizing.py \
  tests/trading_kernel/unit/test_entry_dispatch_preflight.py \
  tests/trading_kernel/unit/test_post_fill_risk.py \
  tests/trading_kernel/unit/test_venue_adapter.py \
  tests/trading_kernel/unit/test_reducer.py

uv run pytest -q \
  tests/trading_kernel/integration/test_ticket_lifecycle_maintenance.py \
  tests/trading_kernel/integration/test_schema_baseline.py \
  tests/trading_kernel/full_chain/test_cross_margin_post_fill_stress.py \
  tests/trading_kernel/full_chain/test_multi_position_certification.py \
  tests/trading_kernel/full_chain/test_multi_ticket_closure_fairness.py
```

### Full certification

```bash
uv run pytest -q \
  tests/trading_kernel/unit \
  tests/trading_kernel/integration \
  tests/trading_kernel/full_chain \
  tests/trading_kernel/architecture

uv run ruff check \
  src/trading_kernel \
  tests/trading_kernel \
  scripts/trading_kernel

uv run --with mypy mypy \
  --config-file mypy.ini \
  src/trading_kernel \
  scripts/trading_kernel

uv run python scripts/audit_production_runtime_file_io.py
git diff --check
```

PostgreSQL 集成测试使用 disposable Docker PostgreSQL，从空库迁移并验证
flat-only refusal。禁止连接 Tokyo 代替本地测试。

## 生产验收门

生产验收仍需独立 Owner 部署确认：

1. Entry `inactive/disabled` 且 write fence 存在；
2. 旧持仓、订单、Ticket、Incident、Settlement、Review 全部闭环；
3. 外部 flat、无 residual order；
4. flat-runtime reset 和 `0002/0003` preflight；
5. 唯一目标 commit/schema；
6. Observation、Lifecycle、Reconciliation 先启动；
7. readonly 认证 standard USD-M single-asset、USDT、Hedge、Cross、固定 `5x`、
   Universe、Policy、rules；
8. Entry 保持 fenced；
9. Owner 独立确认后恢复 Entry；
10. 首笔自然 Ticket 完成 Claim、dispatch、Fill、Stop、stress、TP1/runner、
    Reconciliation、Settlement 和 Review。

## 完成证据

本地实现只有同时满足以下条件才可声明完成：

- 所有缺失行为族有保存的 RED 证据；
- 81 个语义场景通过参数化、集成和 Full-chain 覆盖；
- 零新增 skip/xfail；
- ETH/AVAX 事故回归通过；
- stress failed 与 facts unavailable/contradictory 分支通过；
- 多仓位、双 Side、公平调度、Settlement/Review 通过；
- fresh schema 成功，非 flat migration 原子失败；
- Ruff、Mypy、架构和文件 I/O 门通过；
- diff 证明无 root solver、旧 authority、兼容胶水和第二执行链；
- Tokyo Entry 未因本地完成而自动恢复。
