---
title: SOR_DYNAMIC_INSTRUMENT_SELECTION_TRADING_V0_IMPLEMENTATION_PLAN
status: PLAN_APPROVED
date: 2026-08-23
phase: P3-X.3A
design_authority: ../specs/2026-08-20-sor-dynamic-instrument-selection-trading-v0-design.md
implementation_authority: CODE_AND_TEST_ONLY
active_execution_scope: DS-08
next_execution_gate: AUTOMATIC_SEQUENTIAL_ACCEPTANCE_DS_06_TO_DS_10
production_authority: NONE
---

# SOR Dynamic Instrument Selection & Trading V0 Implementation Plan

## 1. Objective

在唯一 Trading Kernel 内实现已经批准的 **SOR Dynamic Instrument Selection & Trading V0**，
使固定24-member Candidate Panel在每个`D 01:00 UTC` Selection decision boundary产生immutable
Snapshot，并由独立Materialization Coordinator通过StrategyUniverse、SelectionSessionAuthority、
Strategy Entry Vacuum和Authority Gap Audit安全决定当期Crypto SOR new-ENTRY资格。

本计划不改变SOR Alpha、Stop、TP1、Runner、Policy风险、杠杆、并发、资金或Netting Domain语义。
它不授权生产部署、Crypto `SOR-001` resume或真实资金动作。（来源：批准设计、Owner active-task
decision）

## 2. Plan Authority And Review Gate

当前状态固定为：

```text
design status: DESIGN_APPROVED
plan status: PLAN_APPROVED
implementation_authority: CODE_AND_TEST_ONLY
active execution scope: DS-08
next execution gate: AUTOMATIC_SEQUENTIAL_ACCEPTANCE_DS_06_TO_DS_10
production_authority: NONE
```

2026-08-23独立复核已经给出`PLAN_APPROVED`，允许本地代码、测试、Migration文件和认证工作，
但不授予任何生产动作。Owner明确授权的Task **DS-00**与**DS-01**已经完成；2026-08-24 Owner
进一步授权整个本地开发流程，允许在每张Task Card的RED/GREEN与比例验收通过后从DS-02顺序推进
至DS-10，不再逐卡等待确认。Migration执行、Tokyo部署、Crypto SOR resume和首次Dynamic
activation始终保持独立Gate。（来源：Owner提供的最终Plan复核意见、DS-00直接验证证据、
`DS00_APPROVED / ENTER_DS01=YES`决定、DS-01 focused acceptance与Owner active-task decision）

## 3. Known State

| Area | Current tracked fact | Planning consequence |
| --- | --- | --- |
| Runtime chain | Observation → StrategySignal → Readiness/Authority → CapacityClaim → immutable Ticket → durable Exchange Command → protected lifecycle → reconciliation → settlement → review | Dynamic Selection只能在StrategySignal之前控制资格，不建立第二执行链 |
| StrategyUniverse | 已有immutable versions/members、Warming/Active/Retired、current pointer和global warming slot | 扩展为`staged`与generation-owned serial warming，不重建Universe系统 |
| Schema | tracked forward chain当前结束于`0005_tradfi_instrument_center` | 新增单一forward-only `0006`；禁止downgrade、dual write和old-table reader |
| Workers | 四个persistent Worker是唯一runtime cadence | V0增加独立application tick/lease，但不强制第五个systemd service |
| Selection evidence | Frozen V0 Replay已通过历史定量Gate | 实现必须通过961×24 Golden parity；不允许重新调参 |
| Golden artifact | 已冻结完整961×24 member-level Decimal Golden与输入/源码/规则digest | DS-00完成；DS-01 Domain实现已逐行匹配23,064条Golden member digest |

来源：当前tracked code、`docs/current/PROJECT_INFORMATION_ARCHITECTURE.md`、批准设计。

## 4. Newly Frozen Edge Invariants

以下四项是实施第一批必须测试化的固定输入，不再作为开放架构问题。

### 4.1 First Static Activation Fallback

首次`static_baseline -> pending dynamic_selection`已经打开Vacuum后失败时：

```text
FALLBACK_PREVIOUS
continuity_source_kind = STATIC_BASELINE
authorized pair = exact previous Static pair
Gap Audit = COMPLETE and exact
first_eligible_close_time_ms = frozen future canonical close
selection_mode remains static_baseline
```

不得新增`FIRST_ACTIVATION_FALLBACK_STATIC`状态，也不得只resolve Vacuum后依赖旧Static pointer。
Static Observation在该transition-scoped Authority到期前必须消费相同Gap Audit、suppression与first
eligible close；该Authority不表示Dynamic activation成功。

### 4.2 Selection Decision Boundary

```text
SOR session_start_ms             = D 00:00 UTC
Selection decision boundary      = D 01:00 UTC
Selection/Authority Period start = D 01:00 UTC
first normal eligible close      = D 01:15 UTC
```

`session_start_ms`只拥有Episode/session identity。任何Worker在`D 00:00`运行都不得提前创建、替换或
到期当天Selection Authority。

### 4.3 VALID_EMPTY Is Non-Retroactive

`VALID_EMPTY`只从其Vacuum/Authority commit向前阻止new ENTRY：

- commit时unfinished ENTRY仍按Vacuum drain/cancel处理；
- 此前合法产生的Signal、CapacityClaim、AdmissionDecision、Ticket和fill事实不被改写；
- 已成交或已保护Ticket继续Initial Stop、TP1、Runner、Exit、Reconciliation、Settlement和Review；
- 不因`VALID_EMPTY`自动平仓或把历史Authority改写为非法。

### 4.4 Uninterrupted Authority Successor Compatibility

Signal、CapacityClaim、AdmissionDecision和Ticket永久保留其出生时冻结的
`selection_authority_id`，不得因为current Authority revision变化而改写。action-time validator接受：

```text
exact frozen authority == current authority
OR
frozen authority reaches current authority through one uninterrupted compatible successor chain
```

V0只允许以下successor edge：

```text
PRE_FENCE_CONTINUITY -> PRE_FENCE_CONTINUITY
PRE_FENCE_CONTINUITY -> NO_CHANGE
```

每一条edge还必须同时满足：

- same `selection_spec_id`；
- same Selection Period；
- same exact LONG/SHORT Universe pair；
- 两条Authority之间从未打开Strategy Entry Vacuum；
- Owner Strategy Control持续Enabled；
- Global Policy持续有效；
- successor grant证明eligible-close coverage连续。

以下任一事实立即打断compatibility：Vacuum、`VALID_EMPTY`、`OWNER_PAUSED_NOT_MATERIALIZED`、
`ACTIVE_NEW`、`FALLBACK_PREVIOUS`、Universe pair变化、Selection Period变化或Owner/Policy authority
中断。Selection source/compute failure默认只写Job/Attempt事实，不得仅为reason强制产生新的Authority
revision；确需revision时也必须满足上述窄successor合同。

## 5. Global Engineering Boundaries

### 5.1 Allowed production surface

- `src/trading_kernel/**`
- `migrations/trading_kernel/**`
- `scripts/trading_kernel/**`
- focused `tests/trading_kernel/**`
- `deploy/systemd/**`仅在证明需要修改现有四Worker托管方式时使用
- 本设计、计划与两份current roadmap的状态同步

### 5.2 Forbidden changes

- 不修改CPM、MPG、MI、BRF2或TradFi策略语义；
- 不恢复Crypto `SOR-001`生产Entry；
- 不增加风险、杠杆、并发、资本或Candidate Panel；
- 不引入AI/ML Selector、综合Score、Rank 8补位或Runtime调参；
- 不新增第二Ticket、Command、Lifecycle、Universe或发布系统；
- 不使用JSON/CSV/Markdown/cache作为runtime authority；
- 不增加dual write、compatibility adapter、old-schema reader或downgrade；
- 不修改`0001`至`0005`历史Migration或`migrations/trading_kernel/v4_schema.py`冻结baseline；
- 不允许网络I/O位于数据库transaction内；
- 不允许Selection Runner直接调用Materializer；
- 不允许Deployment等待当天Selection warming完成才算成功。

## 6. Execution And Verification Strategy

1. 每个Task严格执行**RED → GREEN → REFACTOR**；必须先记录预期失败；
2. shared Schema、`ports.py`、`pg_models.py`、`pg_unit_of_work.py`和Universe repository按本计划串行修改，
   禁止并行Task同时写；
3. 每个Task只运行Focused/Fast验证；完整Release tier仅对冻结exact candidate运行一次；
4. 每个Task完成后保存命令、通过数、失败数和未运行项，不用测试数量冒充覆盖质量；
5. Task之间通过typed model或committed PostgreSQL fact交接，禁止内存式隐藏进度；
6. 任一Task发现设计语义冲突时停止该Task并回到Plan复核，不在代码里发明新状态。

## 7. Dependency And Gate Summary

| Task | Owner | Capability | Depends on | Exit gate |
| --- | --- | --- | --- | --- |
| **DS-00** | Codex, sequential | Evidence、Golden和test baseline | Approved design | Exact artifact/digest and test map frozen |
| **DS-01** | Codex, sequential | Pure domain contracts | DS-00 | Four edge invariants pass in pure unit tests |
| **DS-02** | Codex, sequential | `0006` Schema and PostgreSQL repositories | DS-01 | Empty/forward migration and DB invariants pass |
| **DS-03** | Codex, sequential | Selection Runner and Snapshot production | DS-02 | Exact 24 decisions or whole-attempt failure |
| **DS-04** | Codex, sequential | Selection-Period continuity、disposition and Gap Audit | DS-02、DS-03 | Continuity/NO_CHANGE/DESIRED and VALID_EMPTY-intent fence are crash-safe |
| **DS-05** | Codex, sequential | Entry Vacuum drain、VALID_EMPTY finalization and retained-partial lifecycle | DS-02、DS-04 | No unfinished ENTRY crosses a resolved Vacuum |
| **DS-06** | Codex, sequential | Serial warming、staged pair、atomic activation/fallback | DS-04、DS-05 | No split LONG/SHORT authority; first Static fallback proven |
| **DS-07** | Codex, sequential | Observation/Admission/Ticket/dispatch enforcement | DS-04、DS-06 | Authority is revalidated at all four new-ENTRY boundaries |
| **DS-08** | Codex, sequential | Runtime hosting、recovery、Owner/release controls | DS-03–DS-07 | Independent leases recover; deploy never waits for warming |
| **DS-09** | Codex, sequential | Integrated certification and frozen candidate | DS-00–DS-08 | Golden/full-chain/release gates pass once |
| **DS-10** | Codex, sequential | Deployment and first activation runbooks | DS-09 | Reviewable evidence package only; no production authority |

## 8. Task Cards

以下规则适用于每一张Task Card：

- **Forbidden files**：除该卡`Allowed files`明确列出的路径外，不修改其他生产文件；roadmap/design
  仅允许同步状态，不得借机扩展语义；
- **Hard stops**：继承第9节全部Stop Conditions；该卡RED证据、Requirements和Done未全部满足时，
  不进入下一卡；
- **Owner**：每卡只有一个顺序执行Owner，不并行修改shared Schema、ports、models、UnitOfWork或
  Universe repository。

### DS-00 — Freeze Evidence And Test Portfolio

**Goal**

取得或可重复生成完整 **961×24 member-level Golden Artifact**，冻结输入、输出、程序和digest；同时
建立本能力的Focused/Fast/Release测试清单，先识别可复用fixture，避免测试只增不减。

**Allowed files**

- `docs/superpowers/plans/2026-08-23-sor-dynamic-instrument-selection-trading-v0-implementation-plan.md`
- `tests/trading_kernel/support/**`
- `tests/trading_kernel/fixtures/**`（仅当现有目录允许且数据不是runtime authority）
- bounded research artifact import/verification script under `scripts/trading_kernel/**`

**Requirements**

1. Artifact包含961 Sessions、24 members、qualification、reason、canonical values、rank、state和digest；
2. 冻结artifact SHA-256、Selection source digest、Detector/Registry/Exit Policy semantic identity；
3. artifact只用于测试，生产runtime不可读取；
4. 识别并删除/合并与新测试完全重复的旧fixture，不保留append-only测试资产；
5. 若artifact无法取得或重建：`DS-00 FAILED`，不得开始`DS-01`，也不得保留任何后续
   certification承诺。

**RED evidence**

- 新artifact verifier在artifact缺失、digest错误、cardinality不是961×24时失败；
- production import scan在`src/trading_kernel/**`引用artifact路径时失败。

**Done**

- exact artifact/digest可复现；
- test portfolio mapping记录Focused/Fast/Release层；
- zero production dependency on artifact。

#### DS-00 Execution Evidence — 2026-08-23

**状态：`DS-00 APPROVED`。** Decimal Golden已经被批准为DS-03/DS-09唯一Production Selection
parity baseline。Owner随后单独授权DS-01；该状态仍不授权DS-02、Migration执行、Tokyo部署、
Crypto SOR resume、Dynamic production activation或任何交易所写操作。

Artifact固定在test-only目录：

```text
tests/trading_kernel/fixtures/sor_dynamic_selection_v0/
├── manifest.json
├── member_decisions.csv.gz
└── selection_snapshots.csv.gz
```

| Artifact | Rows | File SHA-256 | Uncompressed content SHA-256 |
| --- | ---: | --- | --- |
| `member_decisions.csv.gz` | **23,064** | `e7aefa1727184c867eb9fe67901210ae943340743c6bf7bc4f4cf6f1f1530448` | `94fa341ea2a9f089a6ac5a4f936d58b05858b74cff61af872f34d0c06e3517a8` |
| `selection_snapshots.csv.gz` | **961** | `ebe22391c5b73f532a71bd1ff08a51d3f2851118c7dadbfb826d56638807972b` | `301b491958463473c2801c430e6b3a7ee8e5a40d38d6fa3dd0f0dd26b2daadfc` |
| `manifest.json` | 1 | `ad43069f81ee497fdf6344e2fb829c16cf4e526f3f79d3beb1a0c35deb3944fe` | N/A |

冻结身份：

| Identity | Digest / value | Ownership |
| --- | --- | --- |
| Artifact set | `sha256:5d8c701d2738daebc506921038b2afb5a8feeda4a25d9652866c9b41743d4e45` | DS-03/DS-09 Golden parity target |
| SelectionSpec | `sha256:a2c0d5d809a54b90564086f4eab230726a16fdb5524a1ce8f29f48ad659cfb10` | Frozen V0 rule identity |
| 24-cache source set | `sha256:05f1e3dcfc469aaf3022ca897b1efb3f5704cf85b9155a261a09170832e8d6da` | Test/research input only |
| Golden generator | `319d976e771f70a50663856bb1d86f25cfa5a7df8365ac06b14ad991b51d2119` | `scripts/trading_kernel/verify_sor_dynamic_selection_golden.py` |
| SOR Detector | `62841a063b1d0b9cc8d9f41d51befa6117953117c8c3adb38c371441539feba8` | Current tracked semantic identity |
| Strategy Registry | `db44ea2f39dbab3671d5bed8e63963248b86f1316fc29fbc6f10dded1c168049` | Current tracked semantic identity |
| Exit Policy | `25511f11e2b930d0572321b8989fe1cf63c87c941e615ca7b6b4f5266810348e` | Current tracked semantic identity |

Golden使用批准合同要求的 **`Decimal` precision 38 / `ROUND_HALF_EVEN`**。独立`REPORT.md`的
`Tail3=1,324`可由binary64 float精确复现；Decimal在7个相等OR/ATR cohort边界消除了float
rounding noise，冻结结果为`Tail3=1,323`、`TP1=2,989`、`Reclaim=7,732`。该差异不修改Feature、
Activity floor、Top N、Candidate Panel或Outcome，只固定已批准的Decimal语义；完整reconciliation
保存在`manifest.json.numeric_representation_resolution`。

| RED / verification case | Expected result | Direct result |
| --- | --- | --- |
| Missing manifest | Fail closed | `Golden manifest missing` |
| Corrupted Artifact digest | Fail closed | `Golden file digest mismatch` |
| Manifest cardinality `23,063` | Fail closed | `manifest row cardinality mismatch` |
| Production source references fixture | Fail closed | `production artifact dependency detected` |
| Second build from frozen inputs | Byte-identical | Three files and Artifact Set Digest identical |

| Tier | Frozen DS-00 portfolio | Execution rule |
| --- | --- | --- |
| Focused | verifier positive/negative cases、cardinality、digest、snapshot/member invariants | DS-00与DS-03日常RED/GREEN使用 |
| Fast | Focused verifier、production import scan、current-doc/Skill authority、Ruff、Mypy、diff check | 每张后续Task按受影响范围运行 |
| Release | frozen cache rebuild、byte determinism、961×24 SelectionCore parity | 仅对冻结exact candidate运行一次 |

Fixture审计没有发现现有Kernel fixture拥有member-level Dynamic Selection decision语义，因此本卡
没有可删除或合并的旧fixture；复用了已有24-symbol Binance 15m cache和Instrument Effect
`events.csv.gz`，只新增上述三个test-only Artifact。生产`src/trading_kernel/**`零引用。

最终GREEN命令与结果：

```bash
.venv/bin/python scripts/trading_kernel/verify_sor_dynamic_selection_golden.py \
  verify \
  --artifact-dir tests/trading_kernel/fixtures/sor_dynamic_selection_v0 \
  --cache-dir \
  /Users/jiangwei/research/sor-instrument-effect-v1/sor_instrument_effect_study/research_cache/binance_15m \
  --verify-inputs

.venv/bin/ruff check \
  scripts/trading_kernel/verify_sor_dynamic_selection_golden.py

.venv/bin/mypy \
  scripts/trading_kernel/verify_sor_dynamic_selection_golden.py

.venv/bin/python -m pytest -q \
  tests/trading_kernel/architecture/test_current_document_authority.py \
  tests/trading_kernel/architecture/test_project_skill_authority.py \
  tests/trading_kernel/architecture/test_test_support_boundaries.py

git diff --check
```

结果为Golden `verified`、Ruff/Mypy通过、Architecture **29 passed**、production import scan零命中、
`git diff --check`通过。完整Release tier尚未运行，也不应在DS-00重复运行。

### DS-01 — Pure Domain Contracts And State Invariants

**Goal**

建立不含SQLAlchemy、网络、文件或Worker依赖的Selection、Authority、Gap Audit和Vacuum domain模型，
先冻结状态、identity、时间和digest合同。

**Allowed files**

- new `src/trading_kernel/domain/instrument_selection.py`
- new `src/trading_kernel/domain/selection_authority.py`
- new `src/trading_kernel/domain/strategy_entry_vacuum.py`
- `src/trading_kernel/domain/strategy_universe.py`
- focused `tests/trading_kernel/unit/test_instrument_selection.py`
- focused `tests/trading_kernel/unit/test_selection_authority.py`
- focused `tests/trading_kernel/unit/test_strategy_entry_vacuum.py`

**Requirements**

1. frozen named Pydantic models，`extra="forbid"`，金融值使用`Decimal`；
2. exact `D 00:00` Session identity与`D 01:00` Selection Period boundary分离；
3. Authority outcomes只使用批准集合，首次Static fallback复用`FALLBACK_PREVIOUS`；
4. continuous proof与Gap Audit proof互斥且穷尽；
5. `first_eligible_close_time_ms`必须是canonical future close；
6. `VALID_EMPTY`明确forward-only；
7. StrategyUniverse增加`staged`合法转换，禁止staged发Signal或直接成为current Active；
8. Authority successor compatibility只允许4.4节的两类edge，且Vacuum、Owner/Policy中断、pair或
   Selection Period变化必须切断继承链。

**RED tests**

- `D 00:00`创建当期continuity被拒绝；
- first Static fallback缺Generation、Gap Audit或future close被拒绝；
- first Static fallback把mode切成Dynamic被拒绝；
- `VALID_EMPTY`试图重写已有Ticket/fill lineage被拒绝；
- LONG/SHORT任一单边activation plan被拒绝；
- `PRE_FENCE_CONTINUITY -> NO_CHANGE`同pair连续继承可接受birth Authority；
- reason-only continuity revision只要跨Vacuum、Owner/Policy中断或period变化即不兼容。

**Focused command**

```bash
pytest -q \
  tests/trading_kernel/unit/test_instrument_selection.py \
  tests/trading_kernel/unit/test_selection_authority.py \
  tests/trading_kernel/unit/test_strategy_entry_vacuum.py
```

**Done**

Pure domain完整表达批准设计，且没有基础设施import或新增业务状态。

#### DS-01 Execution Evidence — 2026-08-23

**状态：`DS-01 COMPLETE / FOCUSED_ACCEPTANCE_PASSED`。** 本卡完成时Active Execution Scope先收回为
`NONE`；Owner已于2026-08-24授权后续本地顺序实施，当前Scope因此推进为`DS-02`。本卡没有创建
Migration、Repository、Application、Worker或生产配置，也没有执行Tokyo、PostgreSQL、systemd
或交易所动作。

实现范围：

| Domain boundary | Implemented contract | Evidence |
| --- | --- | --- |
| Instrument Selection | Frozen `SelectionPeriod`、SOR V0 SelectionSpec、MemberDecision、Decimal precision 38 / `ROUND_HALF_EVEN`、exact 24 Candidate与LONG/SHORT EventSpecs、canonical digest | SelectionSpec digest精确等于DS-00 Golden；23,064条MemberDecision digest逐条一致 |
| Selection Authority | 批准Outcome集合、continuous/audited proof、time-bounded LONG/SHORT pair、首次Static `FALLBACK_PREVIOUS`、forward-only `VALID_EMPTY`、窄successor compatibility | D 00:00提前Authority、缺Generation/Gap Audit、Static mode漂移、pair/period/Vacuum/Owner/Policy中断均fail closed |
| Strategy Entry Vacuum | 只阻断new ENTRY，不阻断既有Ticket lifecycle，不重写lineage；显式drain/reconfigure/terminal transition | `OPEN -> DRAINING_ENTRY -> RECONFIGURING`合法；`VALID_EMPTY -> OPEN`非法；terminal state要求resolution |
| StrategyUniverse | 新增`staged`、`abandoned`与`manual/dynamic_selection/static_baseline` source semantics | Dynamic/Static必须`warming -> staged -> active`；manual保留`warming -> active`；只有`active`可发Signal |

RED命令与结果：

```bash
.venv/bin/python -m pytest -q \
  tests/trading_kernel/unit/test_instrument_selection.py \
  tests/trading_kernel/unit/test_selection_authority.py \
  tests/trading_kernel/unit/test_strategy_entry_vacuum.py
```

结果为**3个预期collection errors**：三个新Domain模块尚不存在，证明RED来自缺失能力而非脆弱
fixture或环境故障。

GREEN与Fast结果：

| Verification | Direct result |
| --- | ---: |
| Focused Domain tests（含现有StrategyUniverse regression） | **25 passed** |
| Fast Unit + Architecture portfolio | **946 passed** |
| Decimal Golden member digest comparison | **23,064 / 23,064 matched** |
| Full tracked Kernel Ruff | **All checks passed** |
| Full tracked Kernel Mypy | **163 source files，zero issues** |
| `git diff --check` | **passed** |

实际执行命令：

```bash
.venv/bin/python -m pytest -q \
  tests/trading_kernel/unit/test_instrument_selection.py \
  tests/trading_kernel/unit/test_selection_authority.py \
  tests/trading_kernel/unit/test_strategy_entry_vacuum.py \
  tests/trading_kernel/unit/test_strategy_universe.py

.venv/bin/python -m pytest \
  tests/trading_kernel/unit \
  tests/trading_kernel/architecture -q

.venv/bin/ruff check \
  src/trading_kernel scripts/trading_kernel tests/trading_kernel migrations/trading_kernel

.venv/bin/mypy src/trading_kernel scripts/trading_kernel

git diff --check
```

本卡未运行Integration/Full-chain/Release tier：DS-01只增加纯Domain合同，没有Schema、Repository、
Application或runtime链路变化；完整Release certification仍按计划留给冻结exact candidate的DS-09。

2026-08-24 Codex依照批准Production Design与本Task Card完成定向Reviewer审查，未发现阻塞进入
DS-02的Domain合同缺口；随后重新验证Focused **25 passed**、Golden **23,064 / 23,064**、
Ruff、Mypy与`git diff --check`。因此本卡状态冻结为 **`DS01_APPROVED`**。

### DS-02 — Forward Schema `0006` And PostgreSQL Ownership

**Goal**

以单一stopped-and-flat、forward-only Migration建立设计中的generic Selection facts、leases、
Authority、Vacuum、Gap Audit、suppression、Generation linkage和lineage字段。

**Allowed files**

- new `migrations/trading_kernel/versions/0006_sor_dynamic_selection_v0.py`
- `src/trading_kernel/infrastructure/pg_models.py`
- new `src/trading_kernel/infrastructure/pg_instrument_selection_repository.py`
- `src/trading_kernel/infrastructure/pg_universe_repository.py`
- `src/trading_kernel/infrastructure/pg_repositories.py`
- `src/trading_kernel/infrastructure/pg_signal_repository.py`
- `src/trading_kernel/infrastructure/pg_unit_of_work.py`
- `src/trading_kernel/application/ports.py`
- `src/trading_kernel/domain/signal.py`
- `src/trading_kernel/domain/capacity.py`
- `src/trading_kernel/domain/admission_decision.py`
- `src/trading_kernel/domain/ticket.py`
- focused schema/repository tests under `tests/trading_kernel/integration/**`

**Requirements**

1. exact revision `0005_tradfi_instrument_center -> 0006_sor_dynamic_selection_v0`；
2. stopped-and-flat source gates保留terminal lineage，不创建runtime facts；
3. Selection、Materialization、Observation leases是不同namespace；
4. Dynamic Desired members只来自Snapshot selected rows；不创建target-member复制表；
5. Universe创建时写sole `materialization_generation_id`；不创建第二linkage表或direct Snapshot FK；
6. rollback baseline只引用immutable source Universes；
7. Authority current pointer、Vacuum current、Gap Audit current采用exact key、optimistic version；
8. append-only facts拒绝UPDATE/DELETE；所有生产FK禁止cascade deletion；
9. Signal/CapacityClaim/AdmissionDecision/Ticket新增nullable `selection_authority_id`，repository
   mapping必须完整persist/read；Static既有lineage保持可读；
10. `downgrade()`明确拒绝。

**RED tests**

- 从empty和production-shaped `0005`升级前，测试因表/字段不存在失败；
- non-flat source拒绝Migration；
- duplicate Snapshot/Generation/Universe linkage被constraint拒绝；
- Dynamic Signal/CapacityClaim/AdmissionDecision/Ticket四段Authority lineage可逐段round-trip；
- first Static fallback shape与selection mode原子约束失败时whole transaction rollback；
- Migration后零Snapshot、Vacuum、Authority、Command副作用。

**Focused command**

```bash
pytest -q \
  tests/trading_kernel/integration/test_sor_dynamic_selection_migration.py \
  tests/trading_kernel/integration/test_instrument_selection_repository.py \
  tests/trading_kernel/integration/test_selection_authority_repository.py
```

**Done**

Disposable PostgreSQL证明empty/`0005` forward升级、preservation、constraints、query bounds和无副作用。

2026-08-24 Codex完成本卡RED/GREEN与定向Reviewer复核。Disposable PostgreSQL直接证明empty与
production-shaped `0005 -> 0006`、non-flat rollback、fix-forward downgrade拒绝、exact 24-member
SelectionSpec seed、immutable Static rollback pair、零Snapshot/Generation/Authority/Vacuum/Command
副作用、exact-two Generation target cardinality、append-only mutation拒绝、三lease namespace与
Authority current pointer。Signal、CapacityClaim、AdmissionDecision、Ticket的nullable birth
`selection_authority_id`已完成同值round-trip，Static `None`不改变既有digest。Focused/affected
验证为Migration **3 passed**、Schema rebuild **26 passed**、Domain/Repository **41 passed**、
Universe/Seed/Entry链 **60 passed**，Ruff、Mypy、`git diff --check`通过。因此本卡冻结为
**`DS02_APPROVED`**，active scope自动推进至 **DS-03**。

### DS-03 — Selection Runner And Immutable Snapshot

**Goal**

实现纯SelectionCore、Binance public Kline source和独立Selection Runner；Runner只提交Job、attempt、
Snapshot和exact 24 MemberDecisions，然后结束。

**Allowed files**

- `src/trading_kernel/domain/instrument_selection.py`
- new `src/trading_kernel/application/run_instrument_selection.py`
- `src/trading_kernel/application/market_ports.py`
- `src/trading_kernel/application/ports.py`
- `src/trading_kernel/infrastructure/binance_public_market_source.py`
- `src/trading_kernel/infrastructure/pg_instrument_selection_repository.py`
- new bounded script entry point under `scripts/trading_kernel/**`
- focused unit/integration tests

**Requirements**

1. exact fixed 24 Candidate identities；
2. `D 01:00`后读取每member exact 96 closed 15m bars，bounded concurrency默认6；
3. source-integrity先于qualification；任一member缺失使whole attempt=`SOURCE_FAILED`；
4. no Rank substitution；`ready_count=0..24`，`selected_count=min(7, ready_count)`：Ready `0`
   产生selected `0`，Ready `1..6`全部Selected，Ready `>=7`只取前`7`；
5. SelectionCore使用Decimal和canonical digest；
6. Network I/O在transaction外；
7. Runner不读取current Universe、Owner pause、Ticket或Position；
8. Runner不创建continuity、Generation、Vacuum、Authority或Signal。

**RED tests**

- one Candidate缺bar导致zero Snapshot/Rank；
- base volume误作quote volume导致Golden failure；
- future/open bar输入被拒绝；
- Selection Runner尝试调用Materializer的architecture test失败；
- duplicate exact job幂等，不同digest冲突。

**Done**

同一输入确定性产生exact Snapshot/24 decisions；failure只产生bounded attempt事实。

#### DS-03 Execution Evidence — 2026-08-24

**状态：`DS03_APPROVED`。** Active Execution Scope自动推进至 **DS-04**；生产权限仍为`NONE`。

本卡完成了唯一Selection Plane生产路径：

| Boundary | Implemented contract | Direct evidence |
| --- | --- | --- |
| Public source | Binance raw `fapiPublicGetKlines` exact 96 closed 15m bars；Quote Activity读取`quote_asset_volume`，拒绝float、缺失、重复、irregular和future/open bar | source/unit tests |
| SelectionCore | Decimal precision 38 / `ROUND_HALF_EVEN`；exact OR/ATR/Activity；stable rank；Ready `0..24`与Selected `min(7, ready)` | focused domain tests + full Golden parity |
| Runner | 默认bounded concurrency=`6`；claim transaction提交后才网络读取；Snapshot/Attempt使用独立短transaction提交 | transaction-boundary and concurrency tests |
| PostgreSQL | exact Job lease、append-only Attempt、Snapshot+24 Decision deferred-cardinality commit、same-digest idempotency、conflicting digest fail closed | disposable PostgreSQL integration |
| Isolation | Runner不import Materializer、Universe、Vacuum或Authority；runtime不读取Golden/cache | architecture tests |

DS-03 RED先证明缺失`SelectionKlineRequest`、SelectionCore、Runner和typed source导致collection失败；
随后GREEN完成。实施中还由Golden暴露并修正尚未部署的`0006`表示边界：Selection identity统一为
`sor-dynamic-selection-v0`，Selection几何列改为unbounded PostgreSQL `NUMERIC`，避免
`NUMERIC(38,18)`截断precision-38 canonical values。该修正没有改变Feature、Activity floor、Top N、
Candidate Panel或Outcome。

验证结果：

| Verification | Result |
| --- | ---: |
| Focused DS-03 unit/integration/architecture | **25 passed** |
| Production SelectionCore vs frozen raw cache + Golden | **961 Snapshot / 23,064 MemberDecision matched** |
| Fast portfolio（排除DS-08明确拥有的deployment classification文件） | **901 passed** |
| Ruff | **passed** |
| Mypy | **167 source files，zero issues** |
| `git diff --check` | **passed** |

完整Unit中的`test_deploy_tokyo_release.py`仍以旧`0004 -> 0005`compatible source冻结，当前产生
64个预期RED；它们不属于DS-03允许文件，按计划由 **DS-08 release classification**统一修复，未通过
删除/弱化测试绕开。完整Release tier仍只在DS-09 frozen exact candidate执行一次。

### DS-04 — Selection-Period Authority, Disposition And Gap Audit

**Goal**

实现独立Materialization Coordinator的前半段：`D 01:00`continuity、Snapshot disposition、
`VALID_EMPTY` intent fence、`NO_CHANGE/DESIRED`、Gap Audit和first eligible close发布边界。

**Allowed files**

- new `src/trading_kernel/application/coordinate_selection_materialization.py`
- `src/trading_kernel/domain/selection_authority.py`
- `src/trading_kernel/domain/strategy_entry_vacuum.py`
- `src/trading_kernel/application/ports.py`
- `src/trading_kernel/infrastructure/pg_instrument_selection_repository.py`
- bounded tests under unit/integration

**Requirements**

1. already-Dynamic period在`D 01:00`主动创建`PRE_FENCE_CONTINUITY`；不等待Snapshot；
2. `D 00:00`运行不得创建当期Authority；
3. Selection failure默认只记录Job/Attempt failure，不因reason强制产生Authority revision；确需
   continuity revision时必须构成4.4节的compatible successor；
4. ordinary`NO_CHANGE`继承continuous proof；late grant必须current-pair Gap Audit；
5. `selected_count=0`时创建/open带`VALID_EMPTY` intended outcome的Vacuum，原子阻断new-ENTRY
   authority并保持resolution pending；本卡不得假装ENTRY已drain或提交最终`VALID_EMPTY` Authority；
6. changed non-empty set只提交Generation `PENDING -> DESIRED`，不提前fence；
7. Gap Audit持久化positive suppression和checked-negative result digest；
8. transaction跨first eligible close必须rollback、增量audit并顺延；
9. Owner Pause始终高于continuity/disposition；
10. first pending Dynamic在Vacuum前继续Static authority且不创建伪predecessor。

**RED tests**

- 01:00–01:15 continuity连续；
- 01:15后late continuity/NO_CHANGE必须audit；
- `selected_count=0`只完成Vacuum fence/disposition，不在未drain时提交`VALID_EMPTY` Authority；
- Vacuum commit后旧Authority即使仍是current pointer也不能授权new ENTRY；
- audit COMPLETE缺scope/result digest不能grant；
- Selector停止后Materializer仍可从DB完成Disposition。

**Done**

所有pre-fence outcome和`VALID_EMPTY` intent fence可仅从PostgreSQL恢复，且不存在未授权未审计
eligible-close gap；最终drain与`VALID_EMPTY` Authority commit明确留给DS-05。

#### DS-04 Execution Evidence — 2026-08-24

**状态：`DS04_COMPLETE / FOCUSED_AND_FAST_ACCEPTANCE_PASSED`。** Active Execution Scope自动推进至
**DS-05**；`implementation_authority=CODE_AND_TEST_ONLY`，`production_authority=NONE`。

本卡完成Materialization Coordinator的pre-fence半链路，Selector提交Snapshot后即可退出；后续
Disposition、continuity、Generation handoff、Vacuum intent和Gap Audit只从PostgreSQL durable facts
恢复：

| Boundary | Implemented contract | Direct evidence |
| --- | --- | --- |
| Selection Period | `D 00:00`不创建Authority；already-Dynamic在`D 01:00`建立exact previous pair `PRE_FENCE_CONTINUITY`；未来pending mode不得提前生效 | unit + PostgreSQL integration |
| Snapshot disposition | Owner Pause优先；same pair=`NO_CHANGE`；changed pair=`PENDING -> DESIRED`；previous pair漂移时Generation=`ABANDONED`；expired Snapshot fail closed | coordinator integration |
| First activation | `static_baseline -> pending dynamic_selection`在Snapshot前保持Static且不伪造Selection predecessor；same-pair terminal outcome才激活pending mode | domain + integration |
| VALID_EMPTY intent | zero-member Snapshot只打开generation-free Vacuum并原子阻断new ENTRY；不提前提交`VALID_EMPTY` Authority、不改写既有Ticket | vacuum/authority unit + integration |
| Gap Audit | 网络读取在transaction外；提交前重验Owner/Selection control、current Authority、Universe projection和Vacuum；positive suppression与checked-negative共同进入digest | domain + PostgreSQL integration |
| Eligible-close race | 跨过候选close时不提交proof/Authority；同一PENDING Audit增量延伸到下一canonical close，不遗留第二套current Audit | fault integration |
| Failure evidence | missing scope result与Detector semantic drift持久化`FAILED`；runtime projection drift保持PENDING且不grant | fault integration |

RED阶段直接暴露并关闭两个实现缺陷：Audit网络读取期间Universe projection漂移仍可能错误grant；
`0006`原scope唯一约束会阻止第二个Selection Period获得新的immutable `entry_vacuum_id`。由于`0006`
尚未部署，Schema已改为保留terminal历史行、仅对open/fail-closed Vacuum建立partial unique current-fence
约束；Repository current selector只返回未解析的negative fence。该修正没有执行Migration，也没有修改
已部署Schema。

验证结果：

| Verification | Result |
| --- | ---: |
| DS-04 focused unit/integration/migration | **50 passed** |
| Fast Unit + Architecture（继续排除DS-08拥有的`test_deploy_tokyo_release.py`） | **902 passed** |
| Ruff | **passed** |
| Mypy | **168 source files，zero issues** |
| `git diff --check` | **passed** |

完整Release tier仍只在DS-09 frozen exact candidate执行。本卡没有运行生产Migration、Tokyo部署、
Dynamic activation、Crypto SOR resume或exchange mutation。

### DS-05 — Strategy Entry Vacuum, Durable Cancel And Retained Partial

**Goal**

把Vacuum落实到Admission、Ticket、ENTRY dispatch与Lifecycle，关闭unfinished ENTRY和部分成交竞态，
同时保持已有Position生命周期不受Selection变更影响。

**Allowed files**

- new `src/trading_kernel/application/drain_strategy_entry_vacuum.py`
- `src/trading_kernel/application/coordinate_selection_materialization.py`
- `src/trading_kernel/application/issue_ready_signal.py`
- `src/trading_kernel/application/issue_ticket.py`
- `src/trading_kernel/application/revalidate_entry_dispatch.py`
- `src/trading_kernel/application/dispatch_exchange_command.py`
- `src/trading_kernel/application/reconcile_ticket.py`
- `src/trading_kernel/application/recover_unknown_command.py`
- `src/trading_kernel/domain/commands.py`
- `src/trading_kernel/domain/events.py`
- `src/trading_kernel/domain/aggregate.py`
- `src/trading_kernel/domain/reducer.py`
- `src/trading_kernel/domain/exit_policy.py`
- `src/trading_kernel/application/maintain_ticket_lifecycle.py`
- `src/trading_kernel/domain/selection_authority.py`
- `src/trading_kernel/domain/strategy_entry_vacuum.py`
- `src/trading_kernel/application/ports.py`
- `src/trading_kernel/infrastructure/pg_instrument_selection_repository.py`
- focused unit/integration/full-chain tests

**Requirements**

1. Signal无Ticket、prepared、claimed、open-zero-fill、unknown、partial、full fill逐态处理；
2. exchange cancel先持久化durable Command，再在transaction外dispatch；
3. unknown outcome阻塞Vacuum resolution且不blind resend；
4. Vacuum partial只有actual quantity可形成step-aligned正TP1+正Runner才保留；
5. 其他partial继续controlled flatten，不新增runner-only；
6. filled/protected Position继续正式Lifecycle；
7. Vacuum只有在命令、order、unknown和保护全部闭合后写`ENTRY_DRAINED`；
8. intended outcome=`VALID_EMPTY`时，只有`ENTRY_DRAINED`后才能在同一transaction提交
   `SelectionSessionAuthority(VALID_EMPTY)`并把Vacuum置为terminal；
9. `VACUUM_PARTIAL_RETAINED`保留原Ticket/Reservation的完整计划风险占用和Netting Domain
   ownership；不得按reduced actual quantity释放capacity、降低active Ticket count、发第二Ticket或add-on。

**RED tests**

- dispatch preflight在Vacuum打开后零exchange mutation；
- zero-fill cancel unknown阻塞；
- partial实际数量不足双腿时controlled flatten；
- retained fill保护失败时controlled flatten；
- `VALID_EMPTY`不得平仓protected Position；
- `VALID_EMPTY`在unfinished ENTRY未drain时不能commit最终Authority；drain完成后Authority与terminal
  Vacuum原子commit；
- `VALID_EMPTY`前合法Ticket/fill保持原lineage，commit后new Signal enforcement留给DS-07；
- `VACUUM_PARTIAL_RETAINED`在Episode terminal前不释放original planned reservation、Netting Domain
  或capacity，也不能基于reduced actual quantity产生第二Ticket/add-on；
- crash在cancel前后、quantity freeze前后均可恢复。

**Done**

没有unfinished ENTRY能跨过resolved Vacuum；`VALID_EMPTY`只在drain完成后成为current Authority；
retained partial不释放原计划capacity，且既有Ticket只按冻结Lifecycle推进。

#### DS-05 Execution Evidence — 2026-08-24

**状态：`DS05_COMPLETE / FOCUSED_AND_FAST_ACCEPTANCE_PASSED`。** Active Execution Scope自动推进至
**DS-06**；`implementation_authority=CODE_AND_TEST_ONLY`，`production_authority=NONE`。

本卡把Strategy Entry Vacuum接入Admission、Ticket issuance、ENTRY dispatch最终preflight、durable
cancel、unknown recovery与正式Lifecycle：

| Boundary | Implemented contract | Direct evidence |
| --- | --- | --- |
| Admission / Ticket | open Vacuum在Admission与Ticket transaction内重复fail closed，不产生Claim、Ticket、Reservation、Netting Domain或Command | PostgreSQL integration |
| Prepared / claimed ENTRY | prepared或claimed ENTRY被精确`SUPERSEDED`，释放预算、ENTRY lane与Netting Domain；行情网络读取期间新开的Vacuum仍在最终DB preflight拦截，zero venue mutation | integration + fault race |
| Open zero-fill | 先提交带Vacuum lineage的durable `CANCEL_ORDER`，transaction外dispatch；Cancel accepted后仍等待PositionSnapshot确认order absent才冻结final quantity | reducer + PostgreSQL integration |
| Unknown cancel | `OUTCOME_UNKNOWN`阻塞drain且不blind resend；venue truth仍open时原Command终结为reconciled-absent、Aggregate进入retryable rejection并创建下一generation durable Cancel | integration recovery |
| Partial fill | 只有step-aligned、正TP1+正Runner、`NORMAL` post-fill risk的actual quantity可进入`VACUUM_PARTIAL_RETAINED`；否则Incident + controlled flatten | unit + integration |
| Capacity retention | retained partial保持原Ticket、完整planned Reservation、active Ticket count与Netting Domain；Initial Stop/Stress完成前ENTRY lane不释放 | PostgreSQL integration |
| Protection failure | retained partial Initial Stop rejection创建`vacuum_partial_initial_stop_rejected` Incident与actual-quantity controlled flatten，Vacuum持续阻塞至正式flat closure | integration |
| Drain finalization | Generation Vacuum在同一transaction推进`DRAINING_ENTRY -> MATERIALIZING`与`DRAINING_ENTRY -> RECONFIGURING`；`VALID_EMPTY`只有exact intent、zero-member Snapshot、Owner enabled且无blocker时原子提交terminal Vacuum、current Authority和pending mode activation | PostgreSQL integration |
| Non-retroactivity | protected Ticket不属于Vacuum drain blocker；`VALID_EMPTY`不改写Position、Reservation、Netting Domain、Aggregate version或既有Lifecycle | PostgreSQL integration |
| Read projection | 新增Aggregate/Event状态全部映射到Owner Console Entry causality，保持fail-fast完整性 | unit |

RED阶段直接暴露并关闭两个状态机缺陷：generation-free Vacuum缺少`NO_SELECTION_READY_MEMBERS`
intent校验；Generation Vacuum已写`OPEN/DRAINING_ENTRY`两条事件但projection version仍为1，导致
`ENTRY_DRAINED`事件sequence冲突。实现现以projection version 2承接前两条事件，并拒绝任何错误
intent被提交为`VALID_EMPTY`。

验证结果：

| Verification | Result |
| --- | ---: |
| DS-05 focused unit/integration/migration/architecture | **228 passed** |
| Fast Unit + Architecture（继续排除DS-08拥有的`test_deploy_tokyo_release.py`） | **916 passed** |
| Ruff | **passed** |
| Mypy | **169 source files，zero issues** |
| `git diff --check` | **passed** |

本卡没有运行生产Migration、Tokyo部署、Dynamic activation、Crypto SOR resume或exchange mutation。

### DS-06 — Serial Warming, Atomic Pair Activation And Fallback

**Goal**

复用现有global warming queue完成LONG/SHORT串行warming到`staged`，并以一个transaction原子激活
pair或按exact gates fallback previous。

**Allowed files**

- `src/trading_kernel/domain/strategy_universe.py`
- `src/trading_kernel/application/install_strategy_universe.py`
- `src/trading_kernel/application/advance_strategy_universe.py`
- `src/trading_kernel/application/certify_universe_instrument.py`
- `src/trading_kernel/application/abandon_strategy_universe.py`
- `src/trading_kernel/application/coordinate_selection_materialization.py`
- `src/trading_kernel/infrastructure/pg_universe_repository.py`
- `src/trading_kernel/infrastructure/pg_instrument_selection_repository.py`
- focused unit/integration/fault tests

**Requirements**

1. LONG warming成功后进入`staged`并释放global slot；SHORT随后warming；
2. staged无Signal authority；
3. final transaction同时切两个pointers、activate targets、retire previous、commitAuthority并resolve Vacuum；
4. 任一失败不产生LONG新/SHORT旧split；
5. fallback要求Owner Enabled、previous valid、ENTRY_DRAINED、exact COMPLETE union audit、no supersession；
6. first Static activation post-fence failure复用`FALLBACK_PREVIOUS + STATIC_BASELINE`，mode保持Static，
   并在同一transaction清空pending mode/effective-session/authorization字段；
7. transaction跨first eligible close时rollback并扩展audit；
8. newest valid Snapshot可SUPERSEDE未Active generation；
9. staged/warming target abandonment必须经正式`abandon_strategy_universe` application boundary，
   将其扩展为合法`warming/staged -> abandoned`；Coordinator不得直接写repository lifecycle state。

**RED tests**

- staged member不能Signal；
- duplicate target Universe被unique key拒绝；
- LONG成功/SHORT失败不切pointer；
- LONG staged/SHORT failed时两个target均经正式abandonment入口终止，current pair保持不变；
- first Static fallback只resolve Vacuum但无Authority时测试失败；
- first Static fallback写Dynamic mode时测试失败；
- crash before/after fallback commit幂等恢复。

**Done**

Active pair、Authority和Vacuum终态始终原子一致，首次Static恢复也受Gap Audit保护。

#### DS-06 Execution Evidence — 2026-08-24

**状态：`DS06_COMPLETE / FOCUSED_AND_FAST_ACCEPTANCE_PASSED`。** Active Execution Scope自动推进至
**DS-07**；`implementation_authority=CODE_AND_TEST_ONLY`，`production_authority=NONE`。

本卡复用唯一global warming queue完成LONG→SHORT串行materialization，并把两侧staged、最终
Authority和Vacuum终态收敛为一个原子状态机：

| Boundary | Implemented contract | Direct evidence |
| --- | --- | --- |
| Serial warming | LONG `warming -> staged`后释放global slot，SHORT随后warming；staged scope关闭Observation/ENTRY authority | PostgreSQL integration + Migration constraint |
| Atomic activation | 同一transaction retire previous pair、activate targets、切两个current pointers、提交`ACTIVE_NEW`、终结Generation和Vacuum | PostgreSQL integration + 8-point fault injection |
| Exact fallback | 1800秒timeout或terminal certification blocker先正式abandon targets，再完成union Gap Audit并恢复exact previous pair；具体失败原因永久写入Generation | Dynamic/first-Static integration |
| First Static failure | `FALLBACK_PREVIOUS + STATIC_BASELINE`保留Static mode并原子清空pending mode/effective session/authorization | PostgreSQL integration |
| Supersession | 新合法Snapshot使旧Generation=`SUPERSEDED`、旧targets abandoned；Vacuum直接重绑定新Generation，或对最新零成员Snapshot原子终结为`VALID_EMPTY` | PostgreSQL integration + commit-fault rollback |
| Pause precedence | RECONFIGURING阶段Owner Pause终结targets/Generation、Vacuum=`OWNER_PAUSED`，且zero fallback Authority；DRAINING_ENTRY阶段的继续drain由DS-08 runtime card统一托管 | PostgreSQL integration + scoped plan boundary |
| Recovery hygiene | supersession/Pause原子终结旧PENDING Gap Audit；`ACTIVE_NEW/NO_CHANGE/FALLBACK_PREVIOUS/VALID_EMPTY`由Coordinator幂等读取，不重复创建Authority或Audit | crash/retry integration |
| Architecture | Materialization Coordinator纳入Universe authority扫描，只放行精确相邻词`FALLBACK_PREVIOUS`，不放宽legacy/schema/runtime compatibility禁令 | Architecture audit |

验证结果：

| Verification | Result |
| --- | ---: |
| DS-06 focused unit/integration/migration/architecture | **146 passed** |
| Fast Unit + Architecture（继续排除DS-08拥有的`test_deploy_tokyo_release.py`） | **916 passed** |
| Ruff | **passed** |
| Mypy | **169 source files，zero issues** |
| `git diff --check` | **passed** |

本卡没有运行生产Migration、Tokyo部署、Dynamic activation、Crypto SOR resume或exchange mutation。

### DS-07 — Observation, Signal, Ticket And Dispatch Authority Enforcement

**Goal**

在四个new-ENTRY边界重复验证exact Universe、Selection Authority、Vacuum、first eligible close和
suppression，并把同一个birth `selection_authority_id`冻结到
Signal/CapacityClaim/AdmissionDecision/Ticket lineage。

**Allowed files**

- `src/trading_kernel/application/observe_strategy_scope.py`
- `src/trading_kernel/application/produce_strategy_signal.py`
- `src/trading_kernel/application/ingest_signal.py`
- `src/trading_kernel/application/issue_ready_signal.py`
- `src/trading_kernel/application/issue_ticket.py`
- `src/trading_kernel/application/build_capacity_claim.py`
- `src/trading_kernel/application/revalidate_entry_dispatch.py`
- `src/trading_kernel/infrastructure/pg_signal_repository.py`
- `src/trading_kernel/infrastructure/pg_repositories.py`
- `src/trading_kernel/domain/signal.py`
- `src/trading_kernel/domain/capacity.py`
- `src/trading_kernel/domain/admission_decision.py`
- `src/trading_kernel/domain/ticket.py`
- focused unit/integration/full-chain tests

**Requirements**

1. Gate位于Observation、ingestion、Ticket issuance、dispatch preflight；
2. Dynamic outcomes只允许Authority exact pair；Candidate Panel/Decision本身无权限；
3. first-trigger suppression使later second cross不生成Signal；
4. first Static fallback由Static path消费transition Authority，但mode保持Static；
5. `VALID_EMPTY`commit后无new Signal/ENTRY；此前protected lifecycle不受影响；
6. existing Signal在Vacuum后得到terminal blocker，不生成第二ENTRY；
7. Owner Strategy Control和Global Policy继续高于Selection；
8. queries使用exact key或bounded actionable selector；
9. action-time validation接受exact current Authority或4.4节的uninterrupted compatible successor
   chain；不得仅因current Authority ID revision而误杀合法in-flight lineage；
10. `build_capacity_claim()`、`freeze_capacity_claim()`、`freeze_admission_decision()`和
    `issue_ticket()`必须逐段传播同一个birth `selection_authority_id`，不得重写为successor ID。

**RED tests**

- incompatible stale Authority、wrong pair、wrong generation、open Vacuum、close过早、suppression
  匹配分别fail closed；
- `PRE_FENCE_CONTINUITY -> PRE_FENCE_CONTINUITY -> NO_CHANGE`同period/same pair/no Vacuum链允许
  birth Authority继续到action-time；任一break condition立即fail closed；
- first Static fallback second cross被suppression阻断；
- `Signal.selection_authority_id == CapacityClaim.selection_authority_id ==
  AdmissionDecision.selection_authority_id == Ticket.selection_authority_id`；任一步不同fail closed；
- Static非transition Ticket路径保持原语义，不引入runtime adapter；
- lifecycle Commands不读取current Selection membership。

**Done**

任一new ENTRY无法绕过正式Authority链，已有exposure仍由Ticket冻结事实管理。

#### DS-07 Execution Evidence — 2026-08-24

**Status：COMPLETE**。四个new-ENTRY边界现在共用同一个bounded Selection Authority evaluator：

- Observation在读取网络行情前验证current pair、Authority period、Vacuum、first eligible close和
  trigger suppression，并冻结birth `selection_authority_id`；
- Signal ingestion接受exact current Authority或同period、same pair、无Vacuum/Owner/Policy中断的
  `PRE_FENCE_CONTINUITY -> PRE_FENCE_CONTINUITY -> NO_CHANGE` successor chain；
- Admission在Signal出生后出现Vacuum时形成terminal `AdmissionDecision(REJECTED)`，不创建Claim、
  Ticket或Command；
- Ticket issuance在同一transaction锁定Selection Control与current Authority pointer，并校验
  Signal/Claim/Ticket birth lineage；
- ENTRY dispatch在venue mutation前重新读取action-time facts；Selection drift或Vacuum导致zero venue
  mutation，Initial Stop/TP1/Runner/Exit等已有Ticket lifecycle不读取current Selection membership。

本卡还通过回归RED关闭两个既有资产缺口：旧Universe eligibility fixture仍冻结`0005`Schema identity；
以及`0006`为新增Candidate写入退休的`perpetual / crypto_asset`Product Profile。前者已对齐current
Schema，后者已改为current `PERPETUAL / CRYPTO`合同并冻结完整canonical Product Profile digest；
Migration测试逐个验证24个Candidate Profile可被正式Domain模型读取。该修复不改变Candidate、Alpha、
Top-N、风险或Universe成员语义。

Task Card外的必要依赖闭合如下，均未扩展业务范围：

| File | Necessity |
| --- | --- |
| `src/trading_kernel/application/ports.py` | 正式暴露bounded Authority chain、interruption、suppression、Generation pair和current-pointer lock接口 |
| `src/trading_kernel/application/dispatch_exchange_command.py` | 真正action-time ENTRY facts assembly与zero-mutation拒绝边界位于该调用端 |
| `src/trading_kernel/infrastructure/pg_instrument_selection_repository.py` | Ticket transaction必须对current Authority pointer执行`FOR UPDATE` |
| `src/trading_kernel/application/issue_ready_signal.py` | Vacuum后existing Signal的terminal AdmissionDecision只能在正式Admission边界形成 |
| `migrations/trading_kernel/versions/0006_sor_dynamic_selection_v0.py` | Full-chain暴露的Candidate Product Profile seed与current Product合同冲突必须在未部署Revision内修正 |

| Verification | Result |
| --- | ---: |
| Core Authority focused | **82 passed** |
| Affected Observation/Signal/Admission/Ticket/Dispatch/Vacuum/Lifecycle integration | **169 passed** |
| Fast Unit + Architecture（继续排除DS-08拥有的`test_deploy_tokyo_release.py`） | **932 passed** |
| Migration + affected full-chain | **30 passed** |
| Ticket type-fix regression | **29 passed** |
| Ruff | **passed** |
| Mypy | **169 source files，zero issues** |
| `git diff --check` | **passed** |

本卡没有执行生产Migration、Tokyo部署、Dynamic activation、Crypto SOR resume或exchange mutation。
Active Execution Scope自动推进至**DS-08**；`implementation_authority=CODE_AND_TEST_ONLY`，
`production_authority=NONE`。

### DS-08 — Runtime Hosting, Recovery, Owner Control And Release Classification

**Goal**

把Selection/Materialization独立tick和lease托管到现有persistent runtime，提供bounded readonly状态、
Owner dynamic/static/disabled控制以及thin release compatibility projection。

**Allowed files**

- `src/trading_kernel/interfaces/observation_worker.py`
- `src/trading_kernel/interfaces/worker_process.py`
- new bounded interface modules only if independent entry points cannot remain readable otherwise
- `src/trading_kernel/infrastructure/production_runtime.py`
- `src/trading_kernel/application/runtime.py`
- `src/trading_kernel/application/owner_control.py`
- `src/trading_kernel/infrastructure/pg_owner_control.py`
- `scripts/trading_kernel/certify_release_candidate.py`
- `scripts/trading_kernel/deploy_tokyo_release.py`
- `scripts/trading_kernel/deployment_control.py`
- `scripts/trading_kernel/certify_readonly.py`
- focused runtime/deployment tests

**Requirements**

1. Selection、Materialization、Observation独立entry point与lease identity；
2. 可共用Observation OS process，但禁止同一call stack直接调用；
3. crash从DB exact state恢复；
4. readonly显示Job/Snapshot/Generation/Vacuum/Audit/Authority/first eligible close；
5. Owner Pause阻塞materialization和fallback，继续drain；
6. `COMPATIBLE_RESTART`直接恢复persisted Active pair，zero warming；
7. `REQUIRES_RUNTIME_REMATERIALIZATION`保持fenced并后台推进；
8. Deployment completion不等待pending Generation；
9. release compatibility只引用existing certification manifest，不建立第二classifier。

**RED tests**

- Selection process停止时Materializer继续；
- `COMPATIBLE_RESTART`不创建new Generation/warming；
- `REQUIRES_RUNTIME_REMATERIALIZATION`的deploy completion不等待warming，但runtime可以创建或恢复
  background Generation；
- pending warming不阻塞DEPLOY COMPLETE；
- incompatible manifest无法伪装compatible；
- Owner Pause期间fallback永远被拒绝。

**Done**

四Worker模型保持不变，业务warming与软件部署关键路径彻底分离。

### DS-09 — Golden, Full-Chain And Release Certification

**Goal**

冻结一个exact candidate并只对它运行完整认证，证明研究语义、runtime correctness、Migration、
exchange-write边界和部署恢复全部闭合。

**Required evidence**

| Tier | Required proof |
| --- | --- |
| Golden | 961×24 exact identity/value/rank/state/digest parity and deterministic rerun |
| Migration | Empty and production-shaped `0005 -> 0006`, preservation, downgrade rejection, zero side effects |
| Full chain | Snapshot → continuity/disposition → Vacuum/drain → warming/staged → activation/fallback → Signal → Ticket → protected lifecycle |
| Fault | source failure、authority revision compatibility/break、lease expiry、close race、cancel unknown、partial fill capacity retention、split prevention、first Static fallback、crash recovery |
| Architecture | no parallel chain、file authority、duplicate linkage、timer worker、runtime compatibility or retired semantics |
| Static analysis | Ruff、repository Mypy、document references and `git diff --check` |

**Release commands**

```bash
pytest -q tests/trading_kernel
ruff check src/trading_kernel scripts/trading_kernel tests/trading_kernel
mypy src/trading_kernel scripts/trading_kernel
git diff --check
```

实际release certification还必须使用仓库现有exact-candidate certification入口并保存其manifest；
若任一修复改变candidate，旧manifest立即失效且完整Release tier只对新candidate重跑一次。

**Done**

- 所有批准设计requirements有直接测试证据；
- zero skipped safety gate；
- test portfolio删除/合并重复fixture；
- exact candidate可进入独立部署复核，但尚无生产授权。

### DS-10 — Deployment And First Dynamic Activation Evidence Package

**Goal**

准备而不执行stopped-and-flat `0006`部署和首次Dynamic activation runbook，使Owner能基于明确证据
分别授权软件发布与真实资格切换。

**Requirements**

1. 部署前刷新current PostgreSQL、systemd、release marker和Binance readonly facts；
2. `0006`要求exact flat、Entry fenced、old writers stopped、preservation digest通过；
3. 首次部署只安装capability和Static baseline/control，`dynamic_selection`不自动启用；
4. postdeploy验证Schema/commit、四Worker、zero restart drift、Static pair、zero unexpected
   Snapshot/Vacuum/Authority/Command；
5. 首次Dynamic activation另需24 Candidate operational audit、Owner control authorization和
   next exact decision boundary；
6. first activation success、pre-fence failure、post-fence Static fallback分别有readonly验收步骤；
7. rollback是fix-forward Static materialization，不downgrade Schema、不恢复retired runtime；
8. 不包含Crypto resume或真实交易写入授权。

**Done**

形成可复核runbook、release manifest要求、postflight查询和唯一下一动作；生产状态保持不变。

## 9. Stop Conditions

任一条件出现时停止当前Task，不进入下一Task：

1. Golden Artifact缺失、不可复现或与批准V0语义不一致；
2. 必须新增设计外Authority outcome、第二current pointer或第二release classifier才能实现；
3. 任何网络I/O需要在数据库transaction内才能维持流程；
4. first Static fallback无法在mode保持Static时消费Gap Audit/suppression；
5. `VALID_EMPTY`只能通过改写已有Ticket/Position才能实现；
6. LONG/SHORT不能保持最终原子一致；
7. partial fill保留无法形成合法正TP1+Runner双腿；
8. Schema需要dual write、old reader、downgrade或active-position handover；
9. 当前tracked identity与冻结设计或Golden source identity漂移；
10. 任何测试通过依赖削弱现有Ticket、Command、Lifecycle、Policy或Netting invariant。

## 10. Final Done Contract

P3-X.3实现阶段只有同时满足以下条件才算完成：

```text
Frozen Selection V0 == production SelectionCore
AND Selection Plane ends at committed Snapshot/failed Job
AND Materializer recovers independently from PostgreSQL
AND D 01:00 owns Authority-period rollover
AND in-flight lineage survives only an uninterrupted compatible Authority successor chain
AND every authority gap is audited before grant
AND VALID_EMPTY is forward-only
AND first Static fallback is suppression-safe while mode stays Static
AND no unfinished ENTRY crosses resolved Vacuum
AND LONG/SHORT pair activates atomically
AND Signal/CapacityClaim/AdmissionDecision/Ticket freeze one birth Authority identity
AND all new ENTRY boundaries revalidate exact or compatible uninterrupted Authority
AND compatible deploy performs zero warming
AND complete exact-candidate certification passes
```

即使上述全部通过，Tokyo部署和首次Dynamic activation仍需各自独立Owner授权。
