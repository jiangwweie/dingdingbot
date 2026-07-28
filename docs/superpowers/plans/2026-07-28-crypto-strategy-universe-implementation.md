# Crypto Strategy Universe General Capability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:test-driven-development` for every task and
> `superpowers:verification-before-completion` before any completion claim.
> This plan is **OWNER_REVIEW_REQUIRED** and must not be executed before explicit
> Owner confirmation.

**Goal:** Make each existing crypto Strategy Event use an independently
versioned, unordered, PostgreSQL-authoritative candidate universe that can be
installed once and then automatically certified, warmed, and atomically
activated without changing detector or order-chain code.

**Architecture:** Strategy Registry remains static code authority for signal and
exit semantics; StrategyUniverse becomes the only candidate-membership
authority; the existing Trading Kernel remains the only path from Signal to
Review. Reconciliation performs bounded authenticated read-only instrument
certification, Observation performs market-data warming, and PostgreSQL performs
one atomic active-pointer switch. No fifth worker, dynamic plugin loader,
compatibility reader, file authority, or exchange-setting command is added.

**Tech Stack:** Python 3.11+, frozen Pydantic v2 models,
`decimal.Decimal`, SQLAlchemy 2, PostgreSQL 16/Alembic, pytest,
pytest-asyncio, Ruff, Mypy, CCXT-compatible Binance USD-M adapters, four
persistent systemd workers.

## 执行状态

| 工作 | 当前状态 | 权限边界 |
| --- | --- | --- |
| 详细设计 | 待 Owner 审查 | 仅文档 |
| 测试用例规格 | 待 Owner 审查 | 仅文档 |
| 自动化测试代码 | 未开始 | Owner 确认后先写 RED |
| 生产代码 | 未开始 | 对应 RED 失败后才能写 |
| 最终标的清单 | 未固定 | 生产播种前单独确认 |
| Tokyo 迁移/部署 | 未授权 | 本计划不执行 |

## 设计权威

- 设计：
  `docs/superpowers/specs/2026-07-28-crypto-strategy-universe-design.md`
- 测试用例：
  `docs/superpowers/specs/2026-07-28-crypto-strategy-universe-test-cases.md`
- 当前运行权威：`docs/current/*`、当前代码、PostgreSQL 和交易所只读事实。

如实现细节与设计冲突，停止编码并回到 Owner 确认，不以局部测试通过覆盖设计。

## 全局工程约束

1. **测试优先**：每个生产行为必须先有针对缺失行为的 RED，再实现 GREEN。
2. **单一权威**：删除 Registry candidate list 和
   `brc_strategy_candidate_scopes`，不保留双读、双写或 fallback。
3. **单一执行链**：不得从 Universe 配置、认证或预热直接创建 Ticket 或命令。
4. **纯领域**：domain 不依赖 SQLAlchemy、Venue client、文件、subprocess、
   日志、框架或系统时钟。
5. **明确类型**：核心边界使用 frozen named Pydantic model，禁止无类型 dict
   穿过 domain/application 边界。
6. **无序集合**：成员排序仅用于 canonical digest，不进入 Entry rank。
7. **有界查询**：运行 cadence 查询只读取 current/warming 和最多 10 个成员，
   不扫描完整历史。
8. **事务边界**：所有网络 I/O 在 PostgreSQL 事务外；激活是 DB-only 原子
   事务。
9. **人工设置**：不新增 leverage、margin 或 position mode 交易所写命令。
10. **无旧包袱**：新字段在 flat-only migration 后为非空，不添加 legacy
    decoder 或 nullable compatibility。
11. **不接美股**：代码、seed、runtime profile 和测试默认值都不得启用
    US-equity instrument。
12. **不做生产播种**：测试 fixture 可以使用 8 个示例 symbol，但不得把它们
    声明为最终生产池。
13. **P1 前置**：先合并并验收 Settlement fairness、exact Binance order
    attribution、BNB fee valuation 和 closure-only handover；Universe 不
    复制或绕过这些能力。
14. **发布隔离**：P1 保持 schema `0001` 独立发布并闭合 pending Ticket，
    Universe `0002` 只能在最终 flat 后另行发布。

## 文件结构

| 文件 | 操作 | 单一职责 |
| --- | --- | --- |
| `src/trading_kernel/domain/strategy_universe.py` | 新增 | 无序成员、digest、生命周期不变量 |
| `src/trading_kernel/domain/instrument_identity.py` | 新增 | canonical id 与 CCXT symbol 转换 |
| `src/trading_kernel/domain/instrument_certification.py` | 新增 | 只读事实的纯认证分类 |
| `src/trading_kernel/application/install_strategy_universe.py` | 新增 | 幂等安装配置 |
| `src/trading_kernel/application/advance_strategy_universe.py` | 新增 | DB-only readiness/activation 协调 |
| `src/trading_kernel/application/project_comparative_universe.py` | 新增 | MPG/MI O(N) 共享投影 |
| `src/trading_kernel/infrastructure/pg_universe_repository.py` | 新增 | Universe/current/certification persistence |
| `scripts/trading_kernel/configure_strategy_universe.py` | 新增 | 唯一配置提交 CLI |
| `migrations/trading_kernel/versions/0002_crypto_strategy_universe.py` | 新增 | flat-only 前向 schema |
| `src/trading_kernel/domain/strategy_registry.py` | 修改 | 删除候选成员职责 |
| `src/trading_kernel/domain/arbitration.py` | 修改 | 删除 candidate scope priority |
| `src/trading_kernel/application/observe_strategy_scope.py` | 修改 | Warming 与 Active 明确分流 |
| `src/trading_kernel/application/ports.py` | 修改 | 增加最小 typed ports |
| `src/trading_kernel/infrastructure/pg_models.py` | 修改 | 新 schema 声明 |
| `src/trading_kernel/infrastructure/pg_signal_repository.py` | 修改 | 当前 Universe eligibility join |
| `src/trading_kernel/infrastructure/production_runtime.py` | 修改 | 删除固定 map/count |
| `src/trading_kernel/infrastructure/strategy_registry_seed.py` | 修改 | 只播种策略语义 |
| `src/trading_kernel/infrastructure/runtime_authority_seed.py` | 修改 | Policy 绑定 Event，不展开成员 |
| `src/trading_kernel/infrastructure/venue_adapter.py` | 修改 | 使用严格 InstrumentCodec |
| Observation/Reconciliation worker 入口 | 修改 | 每 cadence 最多推进一个有界维护工作 |

## Task 0：完成 P1 闭环前置门

**Required design and plan:**

- `docs/superpowers/specs/2026-07-28-reconciliation-settlement-review-attribution-repair-design.md`
- `docs/superpowers/plans/2026-07-28-reconciliation-settlement-review-attribution-repair.md`
- `docs/superpowers/specs/2026-07-28-reconciliation-settlement-review-attribution-repair-test-cases.md`

- [ ] P1 实现已通过 Owner 确认后按 RED/GREEN 完成。
- [ ] 多 Ticket Settlement/Review fairness、regular/algo actualOrderId
  attribution、USDT/BNB fee 和 STOP_MARKET/GTX 测试全部通过。
- [ ] P1 未改变 Alembic head，未夹带 Universe schema。
- [ ] BTC-like pending Ticket 已经正常 `BudgetSettled -> ReviewRecorded ->
  terminal`，未使用 DML。
- [ ] 所有生产 Ticket、position、order、Incident、Settlement 和 Review
  已完成 flat certification。
- [ ] 只有上述证据全部存在后，才开始本计划 Task 1。

**Stop gate:** 任一 pending closure、incomplete Review 或 exchange residue
存在时，不创建 Universe migration，不执行生产播种。

## Task 1：建立无序 Universe 与 InstrumentCodec 领域边界

**Files:**

- Create: `src/trading_kernel/domain/strategy_universe.py`
- Create: `src/trading_kernel/domain/instrument_identity.py`
- Create: `tests/trading_kernel/unit/test_strategy_universe.py`
- Create: `tests/trading_kernel/unit/test_instrument_identity.py`

**Interfaces:**

```python
def build_strategy_universe(
    *,
    universe_version_id: str,
    strategy_group_id: str,
    event_spec_id: str,
    universe_version: int,
    exchange_instrument_ids: Sequence[str],
    installed_at_ms: int,
) -> StrategyUniverseVersion: ...


def parse_binance_usdm_instrument_id(
    exchange_instrument_id: str,
) -> BinanceUsdmInstrumentIdentity: ...


def to_ccxt_symbol(identity: BinanceUsdmInstrumentIdentity) -> str: ...
```

- [ ] 写 `UNI-DOM-001` 至 `UNI-DOM-012` 和 `ID-001` 至 `ID-008`。
- [ ] 运行两个 unit 文件并记录 RED：模块不存在。
- [ ] 实现 frozen models、1..10 校验、去重、canonical sort、digest 和严格
  codec。
- [ ] 验证输入顺序不改变 digest，非法 Venue/Product/quote 被拒绝。
- [ ] 运行 Ruff 和 Mypy focused checks。

**Commit:** `feat(kernel): define unordered crypto strategy universes`

## Task 2：建立纯 instrument certification 决策

**Files:**

- Create: `src/trading_kernel/domain/instrument_certification.py`
- Create: `tests/trading_kernel/unit/test_instrument_certification.py`

**Interfaces:**

```python
class InstrumentCertificationFacts(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    runtime_profile_id: str
    exchange_instrument_id: str
    product_status: str
    tick_size: Decimal | None
    step_size: Decimal | None
    min_qty: Decimal | None
    min_notional: Decimal | None
    position_mode: str | None
    margin_mode: str | None
    configured_leverage: int | None
    unowned_position_qty: Decimal
    unowned_open_order_count: int
    observed_at_ms: int


def classify_instrument_certification(
    facts: InstrumentCertificationFacts,
    *,
    required_leverage: int,
    required_margin_mode: Literal["cross"],
    valid_for_ms: int,
) -> InstrumentCertification: ...
```

- [ ] 写规则完整、5x/Cross、独立双向、未知产品、unowned exposure、暂时不可用
  的 RED。
- [ ] 实现稳定 `blocker_code`；不得包含日志字符串推断。
- [ ] 验证 BRC-owned active Ticket 不构成认证阻塞，Netting Domain 仍由 Entry
  单独阻塞。
- [ ] 验证函数不读取时钟、不访问数据库、不调用 Venue。

**Commit:** `feat(kernel): classify readonly instrument eligibility`

## Task 3：前向迁移 PostgreSQL 权威模型

**Files:**

- Create:
  `migrations/trading_kernel/versions/0002_crypto_strategy_universe.py`
- Modify: `src/trading_kernel/infrastructure/pg_models.py`
- Modify: `tests/trading_kernel/integration/test_schema_baseline.py`
- Modify:
  `tests/trading_kernel/integration/test_schema_migration_postgres.py`
- Create:
  `tests/trading_kernel/integration/test_strategy_universe_schema.py`

**Schema changes:**

```text
add brc_strategy_universe_versions
add brc_strategy_universe_members
add brc_strategy_universe_current
add brc_instrument_certification_current
add brc_comparative_projection_current

drop brc_strategy_candidate_scopes

allow brc_instruments pending_certification -> active

replace runtime scope enabled
with observation_enabled + entry_enabled + universe/warm fields

add non-null universe_version_id + universe_semantic_digest
to Signal, Claim, Ticket
```

- [ ] 先写 clean-upgrade、约束、部分唯一索引、FK、非空 lineage RED。
- [ ] 运行 disposable PostgreSQL migration 并确认 RED。
- [ ] 实现 `0001 -> 0002` 前向迁移；不重写生产历史、不增加 downgrade 运行
  兼容。
- [ ] 用 SQLAlchemy metadata 与真实 PostgreSQL information schema 双重断言。
- [ ] 验证超过 10 成员、重复成员、两个 warming 版本、两个 active pointer
  均被数据库约束拒绝。
- [ ] 验证迁移只能在 runtime/trade tables flat 时执行；非平状态 fail closed。

**Commit:** `feat(kernel): add crypto universe authority schema`

## Task 4：从 Registry 和 Owner Policy 删除成员权威

**Files:**

- Modify: `src/trading_kernel/domain/strategy_registry.py`
- Modify: `src/trading_kernel/domain/detector.py`
- Modify: `src/trading_kernel/infrastructure/strategy_registry_seed.py`
- Modify: `src/trading_kernel/infrastructure/runtime_authority_seed.py`
- Modify: `tests/trading_kernel/unit/test_strategy_registry.py`
- Modify:
  `tests/trading_kernel/unit/detectors/test_registered_detectors.py`
- Modify:
  `tests/trading_kernel/integration/test_strategy_registry_seed.py`
- Modify:
  `tests/trading_kernel/integration/test_runtime_authority_seed.py`

**Required contract:**

```python
class RegisteredStrategyContract(BaseModel):
    strategy_group_id: str
    strategy_version_id: str
    event_spec_id: str
    supported_sides: tuple[PositionSide, ...]
    required_facts: tuple[RequiredFactSpec, ...]
    protection_semantics: ProtectionSemantics
    status: StrategyStatus
```

- [ ] 写 Registry semantic hash 不受 Universe 影响的 RED。
- [ ] 写 Owner Policy 只绑定稳定 `allowed_event_spec_ids` 的 RED。
- [ ] 删除 `InstrumentPriority`、`candidate_instruments` 和所有 seed 展开。
- [ ] 删除 Policy `runtime_scope_ids` 成员清单语义。
- [ ] 保持 detector、Facts、方向、保护和退出 semantic hash 不变。
- [ ] 证明修改 Universe 不需要 StrategyVersion 或 OwnerPolicyVersion 升级。

**Commit:** `refactor(kernel): separate strategy semantics from universe membership`

## Task 5：实现幂等安装与 PostgreSQL Repository

**Files:**

- Create: `src/trading_kernel/application/install_strategy_universe.py`
- Create:
  `src/trading_kernel/infrastructure/pg_universe_repository.py`
- Modify: `src/trading_kernel/application/ports.py`
- Modify: `src/trading_kernel/infrastructure/pg_unit_of_work.py`
- Create:
  `tests/trading_kernel/integration/test_strategy_universe_repository.py`
- Create:
  `tests/trading_kernel/integration/test_install_strategy_universe.py`

**Minimal port:**

```python
class StrategyUniverseRepository(Protocol):
    async def install(
        self,
        request: UniverseInstallRequest,
    ) -> UniverseInstallResult: ...

    async def get_current(
        self,
        event_spec_id: str,
    ) -> UniverseCurrent | None: ...

    async def get_members(
        self,
        universe_version_id: str,
    ) -> tuple[str, ...]: ...

    async def claim_next_certification_target(
        self,
        *,
        now_ms: int,
        lease_until_ms: int,
    ) -> CertificationTarget | None: ...

    async def try_activate(
        self,
        *,
        universe_version_id: str,
        now_ms: int,
    ) -> ActivationResult: ...
```

- [ ] 写同集合 current/warming 幂等、retired 后可重新创建、并发冲突 RED。
- [ ] 写一事务插入 version/members/scopes 或零行的 RED。
- [ ] 写新 canonical id 插入 pending instrument、既有 identity 冲突整事务
  拒绝的 RED。
- [ ] 实现 bounded exact queries；repository 不进行认证业务判断。
- [ ] 验证所有列表输出 canonical sorted，但不产生 rank 字段。
- [ ] 对 repository 文件做可读性审查；超过稳定职责时按 version/current 与
  certification projection 拆分，不按表机械造多层 wrapper。

**Commit:** `feat(kernel): install versioned strategy universes`

## Task 6：移除固定 Adapter 标的映射

**Files:**

- Modify: `src/trading_kernel/infrastructure/production_runtime.py`
- Modify: `src/trading_kernel/infrastructure/venue_adapter.py`
- Modify:
  `src/trading_kernel/infrastructure/binance_public_market_source.py`
- Modify: `tests/trading_kernel/unit/test_production_runtime.py`
- Modify: `tests/trading_kernel/unit/test_venue_adapter.py`
- Create:
  `tests/trading_kernel/integration/test_dynamic_instrument_routing.py`

- [ ] 先写一个 Registry 未出现但 canonical id 合法的 fixture 合约 RED。
- [ ] 删除 `_EXPECTED_UNIQUE_INSTRUMENTS` 和 Registry-derived fixed map。
- [ ] Venue 与 market-data adapter 使用 Task 1 的 Codec 即时纯转换。
- [ ] 认证仍是交易资格门；Codec 成功不等于可交易。
- [ ] 验证已从 Active Universe 移除的 Ticket instrument 仍能进行保护、退出
  和只读 reconciliation。
- [ ] 验证非法/未认证 instrument 无 Venue 写调用。

**Commit:** `refactor(kernel): resolve certified instruments without static maps`

## Task 7：接入只读认证与 PostgreSQL Monitor

**Files:**

- Modify: `src/trading_kernel/application/ports.py`
- Create: `src/trading_kernel/application/certify_universe_instrument.py`
- Modify: `src/trading_kernel/interfaces/reconciliation_worker.py`
- Modify: `scripts/trading_kernel/run_reconciliation_worker_once.py`
- Modify: `src/trading_kernel/infrastructure/pg_universe_repository.py`
- Modify: `src/trading_kernel/application/project_owner_state.py`
- Modify: `src/trading_kernel/infrastructure/pg_repositories.py`
- Create:
  `tests/trading_kernel/unit/test_certify_universe_instrument.py`
- Create:
  `tests/trading_kernel/integration/test_universe_certification_worker.py`
- Create:
  `tests/trading_kernel/integration/test_universe_monitor.py`

**Execution order:**

```text
reconciliation safety work
-> claim at most one due certification target
-> close transaction
-> authenticated readonly venue snapshot
-> pure classification
-> short transaction persist certification/monitor
-> DB-only try_activate
```

- [ ] 先写“网络 I/O 不在事务内”的 executable RED。
- [ ] 写 Ticket reconciliation 永远优先于 certification 的 RED。
- [ ] 写 eligible、owner action、transient、resolved Monitor 全矩阵 RED。
- [ ] 实现最多一个 target/cadence、租约恢复、next-check backoff。
- [ ] 验证没有 `SET_LEVERAGE`、margin mutation 或 position mode mutation。
- [ ] 验证相同 blocker 不产生无界 Monitor event。

**Commit:** `feat(kernel): certify universe instruments through readonly reconciliation`

## Task 8：实现 Warming Scope，硬隔离 Signal

**Files:**

- Modify: `src/trading_kernel/application/observe_strategy_scope.py`
- Modify: `src/trading_kernel/interfaces/observation_worker.py`
- Modify: `scripts/trading_kernel/run_observation_worker_once.py`
- Modify: `src/trading_kernel/application/ports.py`
- Modify: `src/trading_kernel/infrastructure/pg_signal_repository.py`
- Create:
  `tests/trading_kernel/unit/test_observe_strategy_scope.py`
- Create:
  `tests/trading_kernel/integration/test_universe_warming.py`

- [ ] 写 Warming 获取完整 Facts 但 signal repository 调用次数为零的 RED。
- [ ] 写 incomplete/stale/malformed Facts 不 ready 的 RED。
- [ ] 写 crash lease expiry 后可恢复且不重复 signal 的 RED。
- [ ] 实现 typed `WarmReadiness` 和 digest。
- [ ] Active Scope 保持现有 signal ingestion 语义；Warming 不复制 detector。
- [ ] 激活后不追发预热期间的历史 trigger。

**Commit:** `feat(kernel): warm universe scopes without signal emission`

## Task 9：把 MPG/MI 比较输入从 O(N²) 降到 O(N)

**Files:**

- Create:
  `src/trading_kernel/application/project_comparative_universe.py`
- Modify: `src/trading_kernel/application/observe_strategy_scope.py`
- Modify: `src/trading_kernel/infrastructure/pg_universe_repository.py`
- Create:
  `tests/trading_kernel/unit/test_project_comparative_universe.py`
- Create:
  `tests/trading_kernel/integration/test_comparative_universe_projection.py`
- Create:
  `tests/trading_kernel/integration/test_universe_market_call_bounds.py`

**Projection key:**

```text
event_spec_id
+ universe_version_id
+ closed_bar_time_ms
+ canonical member set digest
```

- [ ] 写 8 成员 MPG/MI fixture，并在 RED 中证明当前路径重复拉取。
- [ ] 一次构造完整 typed `ComparativeStrengthSnapshot`，原子写 current
  projection。
- [ ] 所有 candidate scopes 读取同一 exact projection。
- [ ] 缺一个成员、closed time 不一致、digest 不一致时 fail closed。
- [ ] 用 counting fake 断言每成员每闭合周期最多一次 market read。
- [ ] 不增加第二 detector 或第二 Signal producer。

**Commit:** `perf(kernel): share comparative universe projections`

## Task 10：实现原子激活和失败恢复

**Files:**

- Create: `src/trading_kernel/application/advance_strategy_universe.py`
- Modify: `src/trading_kernel/infrastructure/pg_universe_repository.py`
- Create:
  `tests/trading_kernel/unit/test_advance_strategy_universe.py`
- Create:
  `tests/trading_kernel/integration/test_strategy_universe_activation.py`
- Create:
  `tests/trading_kernel/integration/test_strategy_universe_activation_faults.py`

- [ ] 写未认证、未预热、readiness 过期、projection 不完整的 RED。
- [ ] 写 activation 任一步注入异常都保持旧 Universe 完整 active 的 RED。
- [ ] 写两个 worker 同时 `try_activate` 只产生一个 generation 的 RED。
- [ ] 实现 single transaction lock/CAS/pointer/scope/state 切换。
- [ ] 激活事务内断言零 network call、零 signal、零 Ticket mutation。
- [ ] 重跑后返回 already-active，不产生第二次激活。

**Commit:** `feat(kernel): atomically activate warmed strategy universes`

## Task 11：收紧 Signal、Entry、Ticket 的 Universe 因果链

**Files:**

- Modify: `src/trading_kernel/domain/signal.py`
- Modify: `src/trading_kernel/domain/capacity.py`
- Modify: `src/trading_kernel/domain/ticket.py`
- Modify: `src/trading_kernel/application/ingest_signal.py`
- Modify: `src/trading_kernel/application/produce_strategy_signal.py`
- Modify: `src/trading_kernel/infrastructure/pg_signal_repository.py`
- Modify: `src/trading_kernel/application/issue_ticket.py`
- Modify: `src/trading_kernel/application/revalidate_entry_dispatch.py`
- Modify: `src/trading_kernel/domain/arbitration.py`
- Modify: `src/trading_kernel/infrastructure/pg_repositories.py`
- Modify: `src/trading_kernel/infrastructure/pg_unit_of_work.py`
- Modify: `tests/trading_kernel/unit/test_arbitration.py`
- Create:
  `tests/trading_kernel/integration/test_universe_signal_eligibility.py`
- Modify: `tests/trading_kernel/integration/test_issue_ticket.py`
- Modify: `tests/trading_kernel/unit/test_entry_dispatch_preflight.py`
- Modify: `tests/trading_kernel/integration/test_command_dispatch.py`

**New frozen lineage:**

```python
universe_version_id: str
universe_semantic_digest: str
```

- [ ] 写 Signal 只能由 exact Active Scope 创建的 RED。
- [ ] 写切换后旧 Signal 无 Claim/Ticket 的 RED。
- [ ] 写 Ticket issue 前切换与 command dispatch 前切换两个 race RED。
- [ ] 删除 `candidate_scope_priority` 字段、SQL order 和所有测试 fixture。
- [ ] Arbitration 稳定排序只保留 Owner Policy priority、Signal
  occurrence/observation time 和 signal id tie-break。
- [ ] Claim/Ticket 冻结并校验与 Signal 相同的 Universe identity。
- [ ] 订单、成交、Settlement、Review 通过 Ticket 保持可追溯。

**Commit:** `feat(kernel): freeze universe identity through ticket admission`

## Task 12：提供单次配置提交和只读状态查询

**Files:**

- Create: `scripts/trading_kernel/configure_strategy_universe.py`
- Create: `scripts/trading_kernel/read_strategy_universe_status.py`
- Create:
  `tests/trading_kernel/unit/test_configure_strategy_universe_script.py`
- Create:
  `tests/trading_kernel/integration/test_strategy_universe_scripts.py`

**CLI contract:**

```text
configure_strategy_universe.py
  --runtime-profile-id BRC-...
  --event-spec-id SOR-LONG
  --instrument BTCUSDT
  --instrument BNBUSDT
  ...

read_strategy_universe_status.py
  --runtime-profile-id BRC-...
  [--event-spec-id SOR-LONG]
```

- [ ] 写未知 Event、重复 symbol、0/11 成员、非法 quote 的 RED。
- [ ] 使用应用 use case，不在 script 中直接拼 SQL。
- [ ] 输出固定结构的 terminal text；不得写 JSON/Markdown 文件。
- [ ] 配置成功后明确返回 version id、digest 和 warming 状态。
- [ ] 只读状态显示成员认证、预热、Monitor blocker 和 current generation。
- [ ] 不显示 credential、账户敏感值或完整 Venue payload。

**Commit:** `feat(kernel): configure and inspect strategy universes`

## Task 13：全链、故障、架构和性能验收

**Files:**

- Create:
  `tests/trading_kernel/full_chain/test_crypto_universe_replacement.py`
- Create:
  `tests/trading_kernel/full_chain/test_crypto_universe_failure_recovery.py`
- Create:
  `tests/trading_kernel/architecture/test_strategy_universe_architecture.py`
- Create:
  `tests/trading_kernel/integration/test_strategy_universe_query_bounds.py`
- Modify:
  `tests/trading_kernel/architecture/test_current_document_authority.py`
- Modify:
  `scripts/trading_kernel/certify_readonly.py`

- [ ] 跑配套测试规格中 `CHN-*`、`FLT-*`、`ARC-*`、`PERF-*` 全部 RED。
- [ ] 使用真实 PostgreSQL 和 fake Venue 完成配置到 Ticket 的正式生产路径，
  fixture 不可直写中间表绕过 producer。
- [ ] 对激活事务、Entry race、Worker crash、网络 timeout、Monitor 恢复做故障
  注入。
- [ ] 使用 query counting 与 `EXPLAIN` 证明最大 10/70 行边界。
- [ ] 证明四 Worker、零文件输出、零新增 exchange mutation kind。
- [ ] 执行完整 suite、Ruff、Mypy、migration、static architecture checks。

**Commit:** `test(kernel): certify crypto universe replacement full chain`

## Task 14：更新当前合同，但停止在部署前

**Files:**

- Modify:
  `docs/current/strategy-group-handoffs/STRATEGYGROUP_REGISTRY_CONTRACT.md`
- Modify: `docs/current/STRATEGY_ENGINEERING_INTAKE_CONTRACT.md`
- Modify: `docs/current/PROJECT_INFORMATION_ARCHITECTURE.md`
- Modify: `docs/current/P0_TRADING_KERNEL_REBUILD_DESIGN.md`
- Modify: `docs/current/P0_TRADING_KERNEL_REBUILD_IMPLEMENTATION_PLAN.md`
- Modify: `docs/current/TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md`
- Modify: `docs/current/MAIN_CONTROL_ROADMAP.md`

- [ ] 只有代码和全套验证完成后，才把已实现边界写入 `docs/current/*`。
- [ ] Registry 合同删除 `candidate_instruments`，改为引用 Universe current。
- [ ] 部署合同保留四 Worker、flat-release、5x/Cross 和 Entry-last。
- [ ] Roadmap 只记录当时实际 commit、schema、测试和待部署状态。
- [ ] 运行文档 authority 测试和全仓引用搜索，删除过时候选优先级说明。
- [ ] 提交本地实现后停止；不得迁移 Tokyo、不得生产播种、不得启用 Entry。

**Commit:** `docs(kernel): adopt strategy universe authority`

## Task 15：生产播种和部署是独立 Owner 门

本任务 **不随 Task 1-14 自动执行**，也不在当前文档阶段确定清单。

开始条件：

```text
Owner 明确固定每个 Event 的最终成员
and P1 fairness/order attribution 已独立发布并验收
and BTC pending closure 已正常 terminal
and 所有 Ticket/position/order/Settlement/Review 完整 flat
and 本地实现和验收已由 Owner 确认
and Tokyo action-time facts 已刷新
```

生产动作只能使用正式 CLI 和现行部署脚本。不得手工导入 SQL、恢复研究文件、
编辑服务器源码或自动修改交易所设置。

## 必须保持 RED 的实施顺序

1. 领域不变量和 digest；
2. schema 和 repository；
3. Registry/Policy 解耦；
4. dynamic codec；
5. 认证与 Monitor；
6. Warming 无 Signal；
7. Comparative O(N)；
8. 原子激活；
9. Signal/Ticket 因果与 race；
10. CLI；
11. 全链、故障、性能和架构。

任何一项在没有对应 RED 证据时，不允许先提交生产实现。

## 最终本地验证命令

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
git status --short
```

PostgreSQL migration、query plan 和 disposable full-chain 命令以仓库当时的
正式 test harness 为准；不得用 SQLite 或 mock 单点成功替代 PostgreSQL 集成
证据。

## 完成条件

Task 1-14 只有在以下条件全部为真时才可标记本地完成：

- 每个新增行为都有先 RED 后 GREEN 的记录；
- 全量测试、Ruff、Mypy、migration 和 architecture gate 全部通过；
- Registry、Universe、Owner Policy、Runtime Scope 没有重复成员权威；
- 新标的无需修改 detector、Registry 或 Adapter map；
- Universe 顺序不影响 Entry；
- Warming 不产生 Signal；
- 认证不产生交易所写；
- 激活失败时旧池完整可用；
- Signal、Claim、Ticket、命令、订单、成交、持仓、Settlement、Review 可沿
  Ticket 完整追溯；
- Comparative market reads 为 O(N)；
- 四 Worker、资源边界和零运行时文件合同保持不变；
- 最终生产清单、Tokyo 迁移、生产播种和 Entry 启用仍处于独立 Owner 门之后。
