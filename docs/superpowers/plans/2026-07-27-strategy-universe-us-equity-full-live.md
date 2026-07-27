# Strategy Universe 与美股合约完整接入 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在唯一 Trading Kernel 链内完成独立加密标的池、版本化无感切换、`RSRVCB-001` 美股合约全时段实盘能力、共享资金准入、完整退出、前向 DML、集成验收与提交，并在部署前硬停止。

**Architecture:** 用静态 `StrategyPluginRegistry` 承载代码语义，用 PostgreSQL `StrategyUniverseVersion` 承载候选成员，用共享 Universe Projection 驱动 RSR top-2，再经 VCB armed 与闭合 15m Trigger 产生标准 `StrategySignal`。产品、Session、企业事件和流动性在行动时形成不可变准入快照；所有 Signal 继续进入现有 Authority、Capacity、Ticket、Exchange Command、Lifecycle、Reconciliation、Settlement、Review 单链。

**Tech Stack:** Python 3.14、Pydantic frozen models、`decimal.Decimal`、SQLAlchemy 2 async、asyncpg、Alembic、PostgreSQL、pytest、Ruff、Mypy、ccxt/Binance USDⓈ-M adapters。

**执行状态：** `IMPLEMENTED_AND_LOCALLY_ACCEPTED / DEPLOYMENT_BLOCKED`

**跟踪权威：** 本文件保留批准时的测试优先执行配方与原始 checkbox，不把事后结果伪装成逐步 RED 证据；实际完成状态、精确命令和 fresh 结果由 `docs/superpowers/specs/2026-07-27-strategy-universe-us-equity-acceptance-matrix.md` 记录。

## Global Constraints

1. **Owner 决策优先：** 完整实盘能力；每个策略独立标的池；移除 AVAX；相关性完全不实现；固定 5x；加密与美股共享 Capacity。
2. **开发顺序：** 每项生产行为必须先写 RED 测试、确认按预期失败、再写最小实现、最后重构与集成。
3. **单链：** 不新增美股执行链、策略私有 Ticket、文件权威、兼容 reader 或 dual write。
4. **数据库：** 新 schema 为 `0002_strategy_universe_us_equity`，从 `0001_initial` 前向升级。
5. **完整测试：** 单元测试不是验收；必须完成 PostgreSQL 集成、full-chain mock、故障恢复、全回归和静态检查。
6. **生产安全：** 本计划只允许本地代码、测试数据库和 mock exchange；禁止部署、systemd 变更、生产 DML 和真实交易所写入。
7. **相关性隔离：** 除设计文档未来附录外，代码、schema、测试、reason code 与配置均不得出现相关性准入。
8. **文档权威：** 实施计划与设计留在 `docs/superpowers/**`；只有完成验收并准备部署时才更新 `docs/current/**` 的长期契约，`MAIN_CONTROL_ROADMAP.md` 仅在真实生产状态变化后更新。

---

## Task 1: 锁定设计、测试矩阵与旧假设扫描

**Files:**

- Modify: `docs/superpowers/specs/2026-07-27-us-equity-perpetual-rsr-vcb-15m-design.md`
- Create: `docs/superpowers/plans/2026-07-27-strategy-universe-us-equity-full-live.md`
- Create: `docs/superpowers/specs/2026-07-27-strategy-universe-us-equity-acceptance-matrix.md`
- Test: `tests/trading_kernel/architecture/test_current_document_authority.py`

- [ ] **Step 1: 创建需求—代码—测试验收矩阵**

矩阵至少覆盖：

```text
36 crypto scopes / AVAX absent
13 US candidates + 2 references
Universe warm/activate/retire
RSR projection / VCB armed / 15m first trigger
five session classes
product/liquidity/corporate-event admission
shared 3 tickets / 9% stop risk / 90% margin / fixed 5x
breakout failure / 24h / 72h exits
forward migration / DML
full-chain / restart / duplicate / unknown outcome
deployment hard stop
```

- [ ] **Step 2: 扫描并分类固定旧假设**

Run:

```bash
rg -n "0001_initial|22 scopes|== 22|AVAX|candidate_instruments|venue_symbols" \
  src tests scripts migrations docs/current \
  --glob '!**/__pycache__/**'
```

将结果分为：

1. 必须修改的 runtime/schema/seed；
2. 必须重写的 retired-semantics tests；
3. 只描述当前生产事实、部署前不得修改的 `docs/current/MAIN_CONTROL_ROADMAP.md`；
4. 历史材料，不做 runtime authority。

- [ ] **Step 3: 验证文档没有残留冲突**

Run:

```bash
rg -n "OBSERVE_ONLY|相关性准入|cluster|只能持有一个|fixed 22|TBD|TODO|implement later" \
  docs/superpowers/specs/2026-07-27-us-equity-perpetual-rsr-vcb-15m-design.md \
  docs/superpowers/plans/2026-07-27-strategy-universe-us-equity-full-live.md
python3 -m pytest tests/trading_kernel/architecture/test_current_document_authority.py -q
git diff --check
```

Expected: 只允许“非目标/未来附录”说明相关性；没有 observe-only 产品阶段、未决占位或格式错误。

- [ ] **Step 4: 提交文档基线**

```bash
git add docs/superpowers/specs/2026-07-27-us-equity-perpetual-rsr-vcb-15m-design.md \
  docs/superpowers/plans/2026-07-27-strategy-universe-us-equity-full-live.md \
  docs/superpowers/specs/2026-07-27-strategy-universe-us-equity-acceptance-matrix.md
git commit -m "docs: define strategy universe and us equity full-live design"
```

---

## Task 2: 领域身份、Strategy Plugin 与独立标的池

**Files:**

- Create: `src/trading_kernel/domain/strategy_plugin.py`
- Create: `src/trading_kernel/domain/strategy_universe.py`
- Modify: `src/trading_kernel/domain/strategy_registry.py`
- Modify: `src/trading_kernel/domain/detector.py`
- Modify: `src/trading_kernel/domain/identities.py`
- Test: `tests/trading_kernel/unit/test_strategy_plugin.py`
- Test: `tests/trading_kernel/unit/test_strategy_universe.py`
- Modify: `tests/trading_kernel/unit/test_strategy_registry.py`
- Modify: `tests/trading_kernel/unit/detectors/test_registered_detectors.py`

- [ ] **Step 1: RED — 写身份分离与精确池测试**

测试断言：

1. Event semantic hash 不再包含 Universe 成员；
2. `UniverseVersion` digest 对成员、角色、顺序确定；
3. 当前六个插件与 RSRVCB 插件均可按 Event ID 获取；
4. 未注册 Event fail-closed；
5. 六个加密 Event 精确得到已批准的 6 成员池；
6. 全部当前池不包含 `AVAXUSDT`；
7. 美股候选 13 个、reference 2 个。

Run:

```bash
python3 -m pytest \
  tests/trading_kernel/unit/test_strategy_plugin.py \
  tests/trading_kernel/unit/test_strategy_universe.py \
  tests/trading_kernel/unit/test_strategy_registry.py -q
```

Expected: 因新类型和新成员未实现而失败，不允许 ImportError 之外掩盖业务断言。

- [ ] **Step 2: GREEN — 实现纯领域模型**

核心接口：

```python
class UniverseMemberRole(StrEnum):
    CANDIDATE = "candidate"
    REFERENCE = "reference"


class UniverseLifecycle(StrEnum):
    DRAFT = "draft"
    INSTALLED = "installed"
    WARMING = "warming"
    ACTIVE = "active"
    RETIRING = "retiring"
    RETIRED = "retired"


class StrategyDetector(Protocol):
    def detect(self, snapshot: MarketSnapshot) -> StrategySignal | None: ...


@dataclass(frozen=True)
class StrategyPlugin:
    event_id: str
    detector: StrategyDetector
    market_plan_factory: MarketPlanFactory
    exit_policy_factory: ExitPolicyFactory
    universe_kind: UniverseKind
```

`RegisteredStrategyContract` 保留语义、facts、timeframes 与版本，不再拥有运行时候选集合。临时测试 fixture 必须显式提供 Universe，不加入 fallback。

- [ ] **Step 3: GREEN — 注册七个插件并移除 if-chain**

把 `detector_for` 改为 registry lookup；现有 detector 对相同 fixture 保持行为等价。

- [ ] **Step 4: 验证**

```bash
python3 -m pytest tests/trading_kernel/unit/test_strategy_plugin.py \
  tests/trading_kernel/unit/test_strategy_universe.py \
  tests/trading_kernel/unit/test_strategy_registry.py \
  tests/trading_kernel/unit/detectors -q
python3 -m ruff check src/trading_kernel/domain tests/trading_kernel/unit
```

- [ ] **Step 5: 提交**

```bash
git add src/trading_kernel/domain tests/trading_kernel/unit
git commit -m "feat: separate strategy semantics from versioned universes"
```

---

## Task 3: `0002` schema、repository 与 Universe 原子状态机

**Files:**

- Create: `migrations/trading_kernel/versions/0002_strategy_universe_us_equity.py`
- Modify: `src/trading_kernel/infrastructure/pg_models.py`
- Create: `src/trading_kernel/infrastructure/pg_universe_repository.py`
- Modify: `src/trading_kernel/infrastructure/pg_unit_of_work.py`
- Create: `src/trading_kernel/application/install_strategy_universe.py`
- Create: `src/trading_kernel/application/activate_strategy_universe.py`
- Test: `tests/trading_kernel/integration/test_schema_migration_postgres.py`
- Create: `tests/trading_kernel/integration/test_strategy_universe_activation.py`
- Create: `tests/trading_kernel/integration/test_strategy_universe_activation.py`
- Modify: `tests/trading_kernel/integration/test_schema_baseline.py`

- [ ] **Step 1: RED — 真实 PostgreSQL migration 测试**

覆盖：

1. `0001 -> 0002` upgrade；
2. `0002 -> 0001 -> 0002` downgrade/upgrade；
3. 新表、列、外键、唯一约束、check constraints；
4. Alembic head 精确为 `0002_strategy_universe_us_equity`；
5. 已有 33 表及历史数据不丢失。

Run:

```bash
python3 -m pytest \
  tests/trading_kernel/integration/test_schema_migration_postgres.py \
  tests/trading_kernel/integration/test_schema_baseline.py -q
```

- [ ] **Step 2: GREEN — 建立 schema 与模型**

按设计文档第 9 节建立 version/member/current/activation/projection/armed/product/calendar/corporate-event/policy 表，以及 scope/signal/claim 扩展列。migration 必须有完整 downgrade，不执行 seed 或网络调用。

- [ ] **Step 3: RED — Repository/状态机事务测试**

覆盖：

1. immutable version 不能修改成员；
2. digest 或业务版本冲突显式报错；
3. warming scope 只能 Observation、不能 Entry；
4. warm readiness 不完整时激活失败；
5. 激活同一事务切换 current、scope state 与审计；
6. 两个并发激活只有一个成功；
7. 重放同一激活幂等；
8. 旧 Ticket 引用保持有效。

- [ ] **Step 4: GREEN — 实现 repository 与 use cases**

网络 I/O 必须在调用激活事务前完成；激活只接受已持久化 readiness facts。

- [ ] **Step 5: 验证**

```bash
python3 -m pytest \
  tests/trading_kernel/integration/test_schema_migration_postgres.py \
  tests/trading_kernel/integration/test_strategy_universe_activation.py -q
python3 -m ruff check migrations/trading_kernel src/trading_kernel/infrastructure \
  src/trading_kernel/application
```

- [ ] **Step 6: 提交**

```bash
git add migrations/trading_kernel src/trading_kernel/infrastructure \
  src/trading_kernel/application tests/trading_kernel/integration
git commit -m "feat: add atomic strategy universe persistence"
```

---

## Task 4: 确定性 seed、36 个加密 scope 与 13+2 美股 Universe

**Files:**

- Modify: `src/trading_kernel/infrastructure/strategy_registry_seed.py`
- Modify: `src/trading_kernel/infrastructure/runtime_authority_seed.py`
- Create: `src/trading_kernel/infrastructure/strategy_universe_seed.py`
- Modify: `src/trading_kernel/infrastructure/production_runtime.py`
- Modify: `scripts/trading_kernel/seed_strategy_registry.py`
- Modify: `scripts/trading_kernel/seed_runtime_authority.py`
- Create: `scripts/trading_kernel/seed_strategy_universes.py`
- Modify: `tests/trading_kernel/integration/test_strategy_registry_seed.py`
- Modify: `tests/trading_kernel/integration/test_runtime_authority_seed.py`
- Create: `tests/trading_kernel/integration/test_strategy_universe_seed.py`
- Modify: `tests/trading_kernel/unit/test_production_runtime.py`

- [ ] **Step 1: RED — 精确 seed 与幂等测试**

断言：

```text
crypto active scopes = 36
US candidate warming scopes = 13
US reference runtime scopes = 0
AVAX scopes = 0
all product instruments have explicit asset_class
second seed inserts 0 and changes 0
conflicting seed fails atomically
schema revision = 0002_strategy_universe_us_equity
```

- [ ] **Step 2: GREEN — 新 seed**

将候选成员从 Strategy Registry seed 移到 Universe seed。Runtime authority 不再硬编码 `22`，而是验证当前 Universe 派生的精确 scope 集合与 digest。

- [ ] **Step 3: GREEN — 更新 runtime mapping**

生产 runtime 按 current Universe 和 product profile 构造 observation mapping；禁止以 Registry 静态 tuple 作为 current membership。

- [ ] **Step 4: 验证**

```bash
python3 -m pytest \
  tests/trading_kernel/integration/test_strategy_registry_seed.py \
  tests/trading_kernel/integration/test_runtime_authority_seed.py \
  tests/trading_kernel/integration/test_strategy_universe_seed.py \
  tests/trading_kernel/unit/test_production_runtime.py -q
```

- [ ] **Step 5: 提交**

```bash
git add src/trading_kernel/infrastructure scripts/trading_kernel \
  tests/trading_kernel/integration tests/trading_kernel/unit/test_production_runtime.py
git commit -m "feat: seed independent crypto and us equity universes"
```

---

## Task 5: 分页闭合 K 线与市场数据契约

**Files:**

- Modify: `src/trading_kernel/domain/market.py`
- Modify: `src/trading_kernel/application/market_ports.py`
- Modify: `src/trading_kernel/infrastructure/binance_public_market_source.py`
- Create: `src/trading_kernel/application/load_closed_candle_window.py`
- Modify: `tests/trading_kernel/unit/test_binance_public_market_source.py`
- Create: `tests/trading_kernel/unit/test_closed_candle_window.py`
- Create: `tests/trading_kernel/integration/test_market_window_pagination.py`

- [ ] **Step 1: RED — 分页、闭合与完整性矩阵**

覆盖：

1. 744 根 1h 需要多页；
2. page boundary 重叠自动按 identity 去重；
3. close time 乱序、重复、缺口、未闭合尾 K 分别失败；
4. 不足窗口返回 typed unavailable，不返回部分可交易 snapshot；
5. retry 后相同 digest；
6. 15m/1h/4h 不混用。

- [ ] **Step 2: GREEN — port 与 adapter**

实现 `ClosedCandlePageRequest/Page` 和 bounded window loader。Adapter 只负责分页 I/O 与 payload parse；application 验证完整窗口；domain 不知道 Binance limit。

- [ ] **Step 3: 集成验证**

使用录制形状的 mock Binance payload，不访问公网：

```bash
python3 -m pytest \
  tests/trading_kernel/unit/test_binance_public_market_source.py \
  tests/trading_kernel/unit/test_closed_candle_window.py \
  tests/trading_kernel/integration/test_market_window_pagination.py -q
```

- [ ] **Step 4: 提交**

```bash
git add src/trading_kernel/domain/market.py src/trading_kernel/application \
  src/trading_kernel/infrastructure/binance_public_market_source.py \
  tests/trading_kernel
git commit -m "feat: load deterministic paged closed-candle windows"
```

---

## Task 6: RSR Projection、VCB Armed 与完整 15m Trigger

**Files:**

- Create: `src/trading_kernel/domain/detectors/rsr_vcb.py`
- Create: `src/trading_kernel/domain/universe_projection.py`
- Create: `src/trading_kernel/application/project_strategy_universe.py`
- Create: `src/trading_kernel/application/observe_ranked_strategy_scope.py`
- Modify: `src/trading_kernel/application/observe_strategy_scope.py`
- Modify: `src/trading_kernel/application/produce_strategy_signal.py`
- Modify: `src/trading_kernel/domain/signal.py`
- Modify: `src/trading_kernel/infrastructure/pg_signal_repository.py`
- Test: `tests/trading_kernel/unit/detectors/test_rsr_vcb.py`
- Test: `tests/trading_kernel/unit/test_universe_projection.py`
- Create: `tests/trading_kernel/integration/test_rsr_vcb_observation.py`
- Modify: `tests/trading_kernel/integration/test_live_replay_detector_parity.py`

- [ ] **Step 1: RED — 公式与反前视测试**

至少覆盖：

1. 24h/72h relative strength；
2. QQQ/SPY 参考平均；
3. EMA20/EMA50 trend；
4. quote volume ratio；
5. 确定性 top-2 与 instrument tie-break；
6. BB20 sample std；
7. shifted 240-window 35% quantile 不含当前值；
8. compression `<= 0.90` 边界；
9. prior 72h high 不含当前 K；
10. first closed-15m cross、bullish、volume `>= 1.80`；
11. armed 之后才可触发；
12. 24h cooldown 与重放幂等；
13. snapshot digest 或 Universe mismatch fail-closed；
14. live/replay parity。

- [ ] **Step 2: GREEN — 纯领域公式**

所有统计运算使用 Decimal；quantile 和 sample std 必须在领域层有确定性实现，不引入 pandas/numpy 为生产依赖。

- [ ] **Step 3: RED — Projection/armed 持久化集成**

覆盖 lease、同输入幂等、失败运行审计、top-2 驱动 scope、rank 退出失效、Universe 切换失效、触发 lineage 持久化。

- [ ] **Step 4: GREEN — Application/repository wiring**

RSR 每个 1h close 只执行一次；15m 深度观察只作用于 top-2。Signal 冻结 projection、armed、Universe、session/product lineage。

- [ ] **Step 5: 验证**

```bash
python3 -m pytest \
  tests/trading_kernel/unit/detectors/test_rsr_vcb.py \
  tests/trading_kernel/unit/test_universe_projection.py \
  tests/trading_kernel/integration/test_rsr_vcb_observation.py \
  tests/trading_kernel/integration/test_live_replay_detector_parity.py -q
```

- [ ] **Step 6: 提交**

```bash
git add src/trading_kernel tests/trading_kernel
git commit -m "feat: implement rsr vcb ranked 15m signals"
```

---

## Task 7: 产品、Session、日历与企业事件准入

**Files:**

- Create: `src/trading_kernel/domain/product_admission.py`
- Create: `src/trading_kernel/domain/us_equity_session.py`
- Create: `src/trading_kernel/domain/corporate_events.py`
- Create: `src/trading_kernel/application/build_product_admission_snapshot.py`
- Modify: `src/trading_kernel/domain/entry_admission_snapshot.py`
- Modify: `src/trading_kernel/infrastructure/venue_adapter.py`
- Create: `src/trading_kernel/infrastructure/us_market_calendar_seed.py`
- Create: `src/trading_kernel/infrastructure/pg_product_admission_repository.py`
- Create: `scripts/trading_kernel/seed_us_market_calendar.py`
- Create: `scripts/trading_kernel/import_corporate_events.py`
- Test: `tests/trading_kernel/unit/test_product_admission.py`
- Test: `tests/trading_kernel/unit/test_us_equity_session.py`
- Test: `tests/trading_kernel/unit/test_corporate_events.py`
- Modify: `tests/trading_kernel/unit/test_entry_admission_snapshot.py`
- Modify: `tests/trading_kernel/unit/test_venue_adapter.py`
- Create: `tests/trading_kernel/integration/test_product_admission_snapshot.py`
- Create: `tests/trading_kernel/integration/test_us_market_calendar_seed.py`

- [ ] **Step 1: RED — Session/DST/提前收市矩阵**

覆盖 2026–2028：

1. regular 边界；
2. premarket/afterhours/overnight；
3. 周末/节假日；
4. 提前收市；
5. DST 春秋切换；
6. horizon 外或日历冲突为 UNKNOWN；
7. multiplier 精确为 1/0.5/0.5/0.25/0.25/0。

- [ ] **Step 2: GREEN — 纯 Session classifier 与确定性官方日历 seed**

日历 seed 带官方 source、timezone、horizon 与 digest；不得在 runtime cadence 访问网页。

- [ ] **Step 3: RED — 产品、流动性与企业事件矩阵**

覆盖：

1. contract/underlying/margin/status 精确匹配；
2. fixed configured leverage=5；
3. 各 Session spread/basis 阈值；
4. top-5 depth ratio；
5. funding/product facts freshness；
6. earnings -4h、date-only whole-day、+2 closed 15m；
7. split/adjustment freeze、reprofile、rewarm；
8. coverage 缺失/过期/冲突 fail-closed。

- [ ] **Step 4: GREEN — 行动时 snapshot**

Venue adapter 获取事实但不做政策判断；domain 构建并验证 frozen snapshot；repository 保存 version/digest 与 coverage。

- [ ] **Step 5: 集成验证**

使用 mock exchangeInfo、book、mark/index、funding 和 corporate-event provider，但使用真实 PostgreSQL repository：

```bash
python3 -m pytest \
  tests/trading_kernel/unit/test_product_admission.py \
  tests/trading_kernel/unit/test_us_equity_session.py \
  tests/trading_kernel/unit/test_corporate_events.py \
  tests/trading_kernel/integration/test_product_admission_snapshot.py \
  tests/trading_kernel/integration/test_us_market_calendar_seed.py -q
```

- [ ] **Step 6: 提交**

```bash
git add src/trading_kernel scripts/trading_kernel tests/trading_kernel
git commit -m "feat: add us equity product and session admission"
```

---

## Task 8: 共享 stop-risk、5x sizing 与行动时 Capacity

**Files:**

- Modify: `src/trading_kernel/domain/capacity.py`
- Modify: `src/trading_kernel/domain/capacity_sizing.py`
- Modify: `src/trading_kernel/application/build_capacity_claim.py`
- Modify: `src/trading_kernel/application/revalidate_entry_dispatch.py`
- Modify: `src/trading_kernel/infrastructure/runtime_authority_seed.py`
- Modify: `tests/trading_kernel/unit/test_capacity.py`
- Modify: `tests/trading_kernel/unit/test_capacity_sizing.py`
- Modify: `tests/trading_kernel/integration/test_capacity_claim_to_ticket.py`
- Create: `tests/trading_kernel/unit/test_cross_asset_capacity.py`
- Modify: `tests/trading_kernel/unit/test_entry_dispatch_preflight.py`

- [ ] **Step 1: RED — 全局共享风险矩阵**

覆盖：

1. crypto + equity 共用 3 Ticket；
2. `gross_risk_at_stop + new <= 9% equity`；
3. regular 3%、pre/after 1.5%、overnight/weekend 0.75%；
4. 5x 下 90% initial margin；
5. Session transition 不重缩既有 Ticket；
6. action-time Session 变化重新 sizing；
7. product snapshot 缺失或 stale 拒绝；
8. quantity 量化后不超过 stop-risk；
9. 不能靠提高 leverage 或放宽 stop 通过；
10. dispatch preflight 再验证 identity/digest 和 account drift。

- [ ] **Step 2: GREEN — 显式组合止损上限**

RuntimePolicy 增加 `max_portfolio_stop_risk_fraction=Decimal("0.09")`；`CapacityUsage.gross_risk_at_stop` 成为硬约束，不创建相关性分支。

- [ ] **Step 3: GREEN — ProductAdmission/Session wiring**

只对 `asset_class=us_equity` 应用 session multiplier；加密为 1。Claim 冻结 before/after、session 与 product digest。

- [ ] **Step 4: 集成验证**

```bash
python3 -m pytest \
  tests/trading_kernel/unit/test_capacity.py \
  tests/trading_kernel/unit/test_capacity_sizing.py \
  tests/trading_kernel/integration/test_capacity_claim_to_ticket.py \
  tests/trading_kernel/unit/test_cross_asset_capacity.py \
  tests/trading_kernel/unit/test_entry_dispatch_preflight.py -q
```

- [ ] **Step 5: 提交**

```bash
git add src/trading_kernel tests/trading_kernel
git commit -m "feat: enforce shared cross-asset stop-risk capacity"
```

---

## Task 9: Ticket lineage、通用退出规则与 Lifecycle

**Files:**

- Modify: `src/trading_kernel/domain/ticket.py`
- Modify: `src/trading_kernel/domain/exit_policy.py`
- Modify: `src/trading_kernel/application/issue_ticket.py`
- Modify: `src/trading_kernel/application/maintain_ticket_lifecycle.py`
- Modify: `src/trading_kernel/infrastructure/pg_repositories.py`
- Modify: `tests/trading_kernel/unit/test_ticket.py`
- Modify: `tests/trading_kernel/unit/test_exit_policy.py`
- Modify: `tests/trading_kernel/integration/test_issue_ticket.py`
- Modify: `tests/trading_kernel/integration/test_ticket_lifecycle_maintenance.py`
- Modify: `tests/trading_kernel/full_chain/test_registered_strategy_exit_matrix.py`

- [ ] **Step 1: RED — Ticket 冻结测试**

断言 Ticket 可追溯到 Universe/projection/armed/product/session/exit policy；后续 current pointer 变化不改变冻结字段。

- [ ] **Step 2: RED — 退出状态矩阵**

覆盖：

1. TP1 前 closed 15m below boundary 全退；
2. 未闭合 candle 不触发；
3. TP1 后 breakout failure 不覆盖 runner policy；
4. 1R TP1 50%、BE、structural runner；
5. 24h pre-TP1 time stop；
6. 72h max holding；
7. protective stop 优先；
8. 重复 lifecycle cadence 不重复 command；
9. 部分 fill 与 unknown outcome 继续现有恢复语义。

- [ ] **Step 3: GREEN — 通用规则**

实现 `BreakoutFailureRule` 与 `PhaseTimeStopRule` 并加入 frozen policy payload。Worker 只解释规则，不判断 Event ID。

- [ ] **Step 4: 集成验证**

```bash
python3 -m pytest \
  tests/trading_kernel/unit/test_ticket.py \
  tests/trading_kernel/unit/test_exit_policy.py \
  tests/trading_kernel/integration/test_issue_ticket.py \
  tests/trading_kernel/integration/test_ticket_lifecycle_maintenance.py \
  tests/trading_kernel/full_chain/test_registered_strategy_exit_matrix.py -q
```

- [ ] **Step 5: 提交**

```bash
git add src/trading_kernel tests/trading_kernel
git commit -m "feat: freeze us strategy lineage and phased exits"
```

---

## Task 10: Worker/runtime 装配与无感 Universe 切换

**Files:**

- Modify: `src/trading_kernel/interfaces/observation_worker.py`
- Modify: `src/trading_kernel/interfaces/entry_worker.py`
- Modify: `src/trading_kernel/interfaces/worker_process.py`
- Modify: `src/trading_kernel/application/select_entry_candidate.py`
- Modify: `src/trading_kernel/application/runtime.py`
- Modify: `src/trading_kernel/infrastructure/production_runtime.py`
- Modify: `scripts/trading_kernel/run_observation_worker_once.py`
- Modify: `tests/trading_kernel/integration/test_global_runtime_workers.py`
- Modify: `tests/trading_kernel/integration/test_runtime_fact_workers.py`
- Create: `tests/trading_kernel/integration/test_universe_hot_swap_workers.py`
- Modify: `tests/trading_kernel/full_chain/test_six_event_system_certification.py`

- [ ] **Step 1: RED — worker 行为测试**

覆盖：

1. warming scope 可被 Observation 认领但不被 Entry 选择；
2. active scope 可完整进入；
3. projection job 与 scope job 公平认领；
4. worker crash/lease expiry 可重领；
5. 原子激活后无需重启 worker 即看到新 current Universe；
6. retiring scope 不能产生新 Ticket；
7. retiring scope 的既有 Ticket 继续 Lifecycle/Reconciliation；
8. 49 个候选 scope 不造成静态 mapping 缺失；
9. no-signal cadence 零文件输出。

- [ ] **Step 2: GREEN — runtime repository 驱动**

Observation/Entry 每次认领通过 bounded current query 获得 scope；缓存只允许以 version/digest 为键并在 pointer 变化时失效。

- [ ] **Step 3: 回归六个原 Event**

更新已退役的 AVAX fixture，但保持六个 Event 公式、Signal、Ticket 与 exit 语义不弱化。

- [ ] **Step 4: 验证**

```bash
python3 -m pytest \
  tests/trading_kernel/integration/test_global_runtime_workers.py \
  tests/trading_kernel/integration/test_runtime_fact_workers.py \
  tests/trading_kernel/integration/test_universe_hot_swap_workers.py \
  tests/trading_kernel/full_chain/test_six_event_system_certification.py -q
```

- [ ] **Step 5: 提交**

```bash
git add src/trading_kernel/interfaces src/trading_kernel/application \
  src/trading_kernel/infrastructure/production_runtime.py \
  scripts/trading_kernel tests/trading_kernel
git commit -m "feat: run versioned universes through persistent workers"
```

---

## Task 11: 前向 DML、schema/runtime 工具与部署硬门

**Files:**

- Create: `scripts/trading_kernel/cutover_strategy_universes.py`
- Create: `src/trading_kernel/infrastructure/strategy_universe_cutover.py`
- Modify: `scripts/trading_kernel/verify_schema.py`
- Modify: `scripts/trading_kernel/certify_readonly.py`
- Modify: `scripts/trading_kernel/deploy_tokyo_release.py`
- Modify: `scripts/trading_kernel/verify_flat_cutover.py`
- Modify: `scripts/trading_kernel/cutover_tokyo.py`
- Modify: `scripts/trading_kernel/reset_flat_runtime.sql`
- Create: `tests/trading_kernel/integration/test_strategy_universe_cutover_dml.py`
- Modify: `tests/trading_kernel/unit/test_deploy_tokyo_release.py`
- Modify: `tests/trading_kernel/integration/test_cutover_state_machine.py`
- Modify: `tests/trading_kernel/integration/test_production_cutover_adapter.py`
- Modify: `tests/trading_kernel/architecture/test_flat_runtime_reset_sql.py`

- [ ] **Step 1: RED — DML 前置与不变量测试**

用 disposable PostgreSQL 覆盖：

1. ENTRY 未 fenced 拒绝；
2. 服务/flat/order/schema facts 不满足拒绝；
3. 精确 Ticket ID terminalization；
4. 保留 append-only Signal/Ticket/Command/Reconciliation/Settlement/Review；
5. release reservation/domain/lane；
6. current projection 清理；
7. 新 Universe/scope/current pointer 安装；
8. 单事务故障完整回滚；
9. 重放同一 cutover ID 幂等；
10. 不存在 symbol-based wildcard 清理。

- [ ] **Step 2: GREEN — typed cutover adapter**

脚本只组装已验证 facts 和调用 repository；不包含交易所写入。默认 `--dry-run`，真实 apply 需要显式 `--apply`、cutover ID、target commit/schema/profile。

- [ ] **Step 3: 更新工具到新 schema**

所有认证、部署与 cutover 工具默认/期望 revision 更新到 `0002_strategy_universe_us_equity`；runtime scope 计数从静态 22 改为按 current Universe 验证。

- [ ] **Step 4: 部署硬停止测试**

部署程序必须在缺少 Owner-provided authorization artifact/flag 时停止在 mutation 之前；本分支测试只验证该停止，不创建授权。

- [ ] **Step 5: 验证**

```bash
python3 -m pytest \
  tests/trading_kernel/integration/test_strategy_universe_cutover_dml.py \
  tests/trading_kernel/integration/test_cutover_state_machine.py \
  tests/trading_kernel/integration/test_production_cutover_adapter.py \
  tests/trading_kernel/unit/test_deploy_tokyo_release.py \
  tests/trading_kernel/architecture/test_flat_runtime_reset_sql.py -q
```

- [ ] **Step 6: 提交**

```bash
git add scripts/trading_kernel src/trading_kernel/infrastructure tests/trading_kernel
git commit -m "feat: add guarded forward strategy-universe cutover"
```

---

## Task 12: Full-chain mock 与故障恢复验收

**Files:**

- Create: `tests/trading_kernel/full_chain/test_us_equity_strategy_certification.py`
- Create: `tests/trading_kernel/full_chain/test_cross_asset_strategy_certification.py`
- Create: `tests/trading_kernel/full_chain/test_universe_replacement_certification.py`
- Modify: `tests/trading_kernel/full_chain/test_fault_matrix.py`
- Modify: `tests/trading_kernel/full_chain/test_multi_position_certification.py`
- Create: `tests/trading_kernel/fixtures/us_equity_market.py`
- Create: `tests/trading_kernel/fixtures/mock_exchange.py`

- [ ] **Step 1: RED — full-chain happy path**

在真实 PostgreSQL、真实 repositories/use cases/workers、mock Binance 边界下执行：

```text
seed -> warm -> activate
-> 4h regime -> 1h RSR projection
-> VCB armed -> closed-15m trigger
-> Signal -> readiness -> authority
-> ProductAdmission -> CapacityClaim
-> Ticket -> ENTRY command -> mock fill
-> Initial Stop -> TP1 -> BE -> runner exit
-> Reconciliation -> Settlement -> Review
```

断言每个 identity、digest、状态转换、command generation 与审计记录唯一。

- [ ] **Step 2: RED — Session 与跨资产共享链**

同一套 full-chain 参数化五个 Session；并在 crypto + US candidate 并发下验证全局 Ticket、9% stop-risk、90% margin、ENTRY lane 与多 Netting Domain。

- [ ] **Step 3: RED — 无感替换**

旧 Ticket 活跃时安装/预热新 Universe，激活后：

1. 旧成员不能新 ENTRY；
2. 旧 Ticket 完成保护/退出/结算；
3. 新成员可产生新 Ticket；
4. Signal/Ticket lineage 不串版本。

- [ ] **Step 4: RED — fault/recovery**

覆盖：

1. projection lease 中断；
2. activation 并发；
3. duplicate closed candle；
4. Signal 重放；
5. Ticket issue 重试；
6. ENTRY outcome unknown；
7. partial fill；
8. worker restart；
9. product/session facts 在 Signal 后漂移；
10. corporate-event coverage 过期；
11. schema/commit identity mismatch Runtime Fence。

- [ ] **Step 5: GREEN — 只修真实链路缺口**

不得为通过 full-chain 测试增加测试专用生产分支、repository fake 或绕过真实状态机。

- [ ] **Step 6: 运行完整 full-chain**

```bash
python3 -m pytest tests/trading_kernel/full_chain -q
```

- [ ] **Step 7: 提交**

```bash
git add src/trading_kernel tests/trading_kernel/full_chain \
  tests/trading_kernel/fixtures
git commit -m "test: certify full cross-asset strategy lifecycle"
```

---

## Task 13: 架构、性能、全回归与最终验收

**Files:**

- Create: `tests/trading_kernel/architecture/test_strategy_universe_boundaries.py`
- Create: `tests/trading_kernel/architecture/test_no_correlation_runtime.py`
- Create: `tests/trading_kernel/integration/test_strategy_universe_query_bounds.py`
- Modify: `docs/superpowers/specs/2026-07-27-strategy-universe-us-equity-acceptance-matrix.md`
- Modify only if long-lived contract changed and code/tests already prove it:
  - `docs/current/P0_TRADING_KERNEL_REBUILD_DESIGN.md`
  - `docs/current/P0_TRADING_KERNEL_REBUILD_IMPLEMENTATION_PLAN.md`
  - `docs/current/strategy-group-handoffs/STRATEGYGROUP_REGISTRY_CONTRACT.md`
  - `docs/current/TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md`

- [ ] **Step 1: RED/GREEN — 架构守卫**

自动检查：

1. domain 无 SQLAlchemy、ccxt、文件、subprocess、web imports；
2. 只有一个 Ticket/Exchange Command 生产链；
3. runtime 不读 Markdown/JSON/output；
4. StrategyPlugin 不能从 DB 动态加载 Python；
5. 没有 old schema fallback/dual write；
6. 没有 correlation/cluster runtime model、policy 或 reason code；
7. no-signal cadence 不写文件。

- [ ] **Step 2: RED/GREEN — 查询与资源边界**

断言：

1. current Universe/scope 用 bounded indexed query；
2. projection 不 full-history scan；
3. 一个 1h close 每个 Universe 一次 projection；
4. 15m 深度拉取最多 top-2；
5. worker cadence 无 N×全 Universe 重拉；
6. 东京 worker 资源限制内无新增常驻进程。

- [ ] **Step 3: 完整 PostgreSQL 与 Trading Kernel 回归**

Fresh evidence：

```bash
python3 -m pytest tests/trading_kernel -q
```

Expected: 所有 unit、integration、full-chain、architecture 通过；不能用 `-k`、skip 或 xfail 隐藏失败。

- [ ] **Step 4: 静态检查**

```bash
python3 -m ruff check src tests scripts migrations
python3 -m mypy src/trading_kernel scripts/trading_kernel
python3 scripts/audit_production_runtime_file_io.py
git diff --check
```

- [ ] **Step 5: disposable PostgreSQL 接受性重建**

```bash
python3 scripts/trading_kernel/bootstrap_schema.py --database-url "$TEST_DATABASE_URL"
python3 scripts/trading_kernel/verify_schema.py --database-url "$TEST_DATABASE_URL"
python3 scripts/trading_kernel/seed_strategy_registry.py --database-url "$TEST_DATABASE_URL"
python3 scripts/trading_kernel/seed_strategy_universes.py --database-url "$TEST_DATABASE_URL"
python3 scripts/trading_kernel/seed_runtime_authority.py --database-url "$TEST_DATABASE_URL"
python3 scripts/trading_kernel/seed_us_market_calendar.py --database-url "$TEST_DATABASE_URL"
python3 scripts/trading_kernel/certify_readonly.py --database-url "$TEST_DATABASE_URL"
```

使用任务专用 disposable database；不得指向 Tokyo production。

- [ ] **Step 6: 完成验收矩阵**

每一项填写：

```text
requirement
design section
production files
test files
exact command
fresh result
remaining deployment-time gate
```

不允许“单元测试已过”等泛化证据。

- [ ] **Step 7: current docs 一致性检查**

只更新长期结构契约；`MAIN_CONTROL_ROADMAP.md` 继续记录实际生产仍是旧 commit/schema，直到真实部署完成。

- [ ] **Step 8: 最终 review**

```bash
git status --short
git diff --stat HEAD
git log --oneline --decorate -12
```

复核无凭证、生产输出、数据库 dump、`.env`、cache、`__pycache__` 或无关用户文件。

- [ ] **Step 9: 最终提交**

```bash
git add src tests scripts migrations docs
git commit -m "feat: complete versioned cross-asset strategy groups"
```

如无剩余变更，保留 clean worktree。

---

## Task 14: 部署前硬停止与 Owner 交付

- [ ] **Step 1: 明确未执行事项**

确认本任务没有：

```text
Tokyo SSH mutation
production PostgreSQL migration/DML
systemd stop/start/restart
exchange order/cancel/leverage/margin write
release symlink switch
```

- [ ] **Step 2: 交付证据**

交付：

1. worktree 与 branch；
2. commit 列表与最终 HEAD；
3. 设计文档、执行计划、验收矩阵；
4. 全回归、full-chain、PostgreSQL、Ruff、Mypy、architecture 结果；
5. schema 与 DML dry-run 结果；
6. 部署时必须重新取得的 current code、PostgreSQL、systemd、exchange-flat facts；
7. 明确状态 `WAITING_FOR_OWNER_DEPLOYMENT_CONFIRMATION`。

- [ ] **Step 3: 停止**

不得把“Standing Authorization”解释为本任务的部署确认。代码提交与验收完成后停止，不运行任何部署或生产变更命令。
