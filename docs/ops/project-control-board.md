# Project Control Board

Last updated: 2026-05-09

## 1. Current Phase

`Observation + Research Methodology Reset`: the project is observation-ready for docs-only / shadow-no-order BTC+ETH Phase 1 review, but observation-ready is not live-ready, docs-only is not runtime, shadow/no-order is not paper/testnet/live, and a research object is not a runtime or small-live candidate.

Current binding interpretation:

- Live-safe / Mac mini observation may continue as observation and health context.
- `Strategy Research Re-entry v1` is the active strategy exploration / intake lane.
- BTC+ETH Phase 1 is a docs-only / shadow-no-order research object.
- SRR-002 is the governing docs-only methodology baseline.
- No current module satisfies SRR-002 standards.
- No current runtime candidate exists.
- No current small-live candidate exists.
- Strategy research results must not mutate runtime/profile/risk/parameters.

## 2. Current Mainline And Exploration Lane

| Mainline | Current status | Evidence | Not to be misread as |
|---|---|---|---|
| Strategy Research Re-entry v1 | Active strategy exploration / intake lane; strategy families, edge hypotheses, failure hypotheses, research briefs, candidate ranking, and Owner-review question framing only | Owner-approved window split; this control board; `docs/ops/project-roadmap-v2.md` as roadmap authority | backtest authorization; experiment authorization; adapter run; runtime activation; implementation task; Claude task card |
| 4h Direction A BTC+ETH Phase 1 observation design | Current docs-only / shadow-no-order observation design object; observation-ready research object; not runtime; not small-live | `docs/ops/project-roadmap-v2.md`; `docs/ops/live-safe-v1-task-board.md`; `docs/ops/observation-research-reset-reconciliation-snapshot-2026-05-09.md`; `docs/ops/direction-a-btc-eth-phase1-owner-review-2026-05-09.md`; `docs/ops/direction-a-btc-eth-phase1-observation-design-consolidation.md` | runtime candidate; small-live candidate; paper/testnet/live; parameter optimization; portfolio/router; SOL Phase 2 |

## 2.1 Strategy Research Re-entry v1 Window

`Strategy Research Re-entry v1` is an active strategy exploration / intake lane.

It may discuss:

- strategy families;
- edge hypotheses;
- failure hypotheses;
- research briefs;
- candidate ranking;
- question framing for Owner review.

It does not authorize:

- new backtests;
- new experiments;
- adapter runs;
- strategy runtime activation;
- paper/testnet/live;
- small-live;
- strategy/risk/profile/parameter changes;
- Claude task cards.

Total Control v2 remains the authority for roadmap, Owner decision queue, Codex/Claude gating, and whether any research brief may upgrade to Codex read-only inspect.

## 3. Current Non-Goals

- no BTC+ETH Phase 1 paper / testnet / live execution
- no strategy runtime activation
- no new runtime behavior
- no small-live
- no strategy rule changes
- no risk profile changes
- no parameter changes
- no portfolio engine
- no strategy router
- no multi-strategy combination
- no SOL Phase 2
- no CPM rescue / CPM reopening
- no short-side work
- no new backtest
- no new experiment
- no new adapter run
- read-only review of existing artifacts only
- no Claude task card for implementation

These non-goals apply to BTC+ETH Phase 1 / the strategy-research object. They do not prohibit ongoing Mac mini / Live-safe observation.

## 4. Owner Decision Queue

### 4.1 Current Metric / Reporting Decisions

| Decision | Why Owner decision is needed | Current evidence | Consequence if unresolved | Urgency |
|---|---|---|---|---|
| A1/A3 trade count mismatch | Shadow/no-order reporting needs a single metric definition before a stable template is finalized. | Phase 1 doc = 490; frontier JSON = 373. | Observation reports may mix accepted-trade count and scenario-accounting count. | Medium |
| A1/A3 time-in-market mismatch | Exposure reporting needs a clear definition: asset-level, portfolio-active, or aggregate exposure. | Phase 1 doc approx 38%; frontier JSON = 52.26%. | Time-in-market / exposure readings remain ambiguous. | Medium |
| BTC+ETH portfolio MaxDD baseline | Owner must decide whether exact combined portfolio MaxDD is required for no-order observation. | Standalone asset docs cannot exactly compute BTC+ETH portfolio MaxDD timing. | Shadow/no-order can proceed with caveat, but exact baseline drawdown remains missing. | Low-Medium |
| Whether MTM drawdown is required for shadow/no-order reporting | MTM drawdown adds observation burden but captures open-risk stress that closed-trade metrics miss. | Owner brief records MTM drawdown inclusion as pending. | Reporting may cover only realized/virtual drawdown and miss intra-position stress. | Medium |

### 4.2 Project Governance Decisions

| Decision | Why Owner decision is needed | Current evidence | Consequence if unresolved | Urgency |
|---|---|---|---|---|
| Whether SRR-002 is accepted as methodology baseline | Future research gates need one stable standard to prevent evidence drift. | SRR-002, task board, reconciliation snapshot, and Owner brief all mark SRR-002 as docs-only methodology baseline. | Future analysis may keep reopening old fragile evidence as promotion material. | High |
| Whether current 3 visible untracked Owner-facing docs should be committed | They form the current Owner-review package and are not yet tracked. | Current visible docs: BTC+ETH consolidation, reconciliation snapshot, Owner decision brief. | Current control state remains local-only and easier to lose or duplicate. | Medium |
| Whether the historical 21-doc batch is still relevant or superseded / not visible in this worktree | The requested 21-doc batch is not present in this worktree; Owner must provide inventory or accept current local state. | Reconciliation snapshot records 3 visible untracked docs; 21-doc batch not visible. | No reliable grouping or archival action can be taken for the missing batch. | Medium |

## 5. Current Risk Queue

| Risk | Area | Current impact | Blocks current phase? | Handling |
|---|---|---|---|---|
| No validated pre-observable applicability boundary | Methodology / evidence | Blocks runtime / small-live interpretation; does not block docs-only / shadow-no-order observation. | No for current phase; yes for runtime/small-live. | Keep SRR-002 caveat explicit in all Direction A observation reporting. |
| Top-winner dependence | Evidence fragility | BTC+ETH unshaped top-3/top-5 removal is negative; positive evidence depends on sparse trend episodes. | No. | Must remain disclosed in observation reporting. |
| 2022 / 2025 vulnerability | Year / regime fragility | 2022 and 2025 are negative for BTC+ETH; these are key vulnerability years for observation review. | No. | Track year-specific vulnerability and avoid judging observation only by favorable windows. |
| A1/A3 metric mismatch | Artifact consistency | Trade count and time-in-market conflict across docs/artifacts. | Partially: blocks final metric template, not docs-only control stage. | Owner decides whether to reconcile before finalizing reporting. |
| Historical small-live wording in older docs | Documentation semantics | Older wording can be misread as activation permission. | No. | Current roadmap/task-board/ADR/snapshot override historical small-live wording. |
| 21-doc batch not visible in current worktree | Document inventory | Cannot group, archive, stage, or supersede unseen docs. | No for current 3-doc package. | Treat as unresolved until Owner provides inventory or declares it superseded. |

## 6. Observation Queue

| Observation item | Current state | Evidence location | Next check | Escalation condition |
|---|---|---|---|---|
| Mac mini environment state | Observation may continue; no BTC+ETH Phase 1 execution implied. | Reconciliation snapshot; live-safe findings. | Confirm data available / delayed / paused / anomaly status. | Missing/stale data, repeated local process anomaly, or unclear source state. |
| BTC/ETH 4h signal state | Shadow/no-order only; no signal may become an order. | BTC+ETH consolidation; Owner brief. | Record no signal / candidate / invalidated / skipped. | Any pressure to treat a candidate signal as paper/testnet/live instruction. |
| Skipped-signal reason | Required observation field. | Reconciliation snapshot log template. | Record missing data, stale bar, duplicate bar, manual pause, rule mismatch, other. | Repeated unexplained skip reason or rule ambiguity. |
| Virtual exposure | Observation metric only, not sizing or order logic. | BTC+ETH consolidation. | Track virtual open/flat, virtual initial risk, virtual aggregate risk. | Virtual exposure exceeds agreed shadow thresholds or definitions are unclear. |
| Fragility markers | Must remain visible. | BTC+ETH consolidation; SRR-001/002. | Track top-winner dependence, shared episode dependence, consecutive loser count. | Reporting hides or downplays top-winner / top-3 / top-5 fragility. |
| Year-specific vulnerability | 2022/2025 are documented vulnerable years. | BTC+ETH consolidation. | Track 2022-style bear/chop and 2025-style cost/chop analogues. | Observation resembles known vulnerable states without clear annotation. |
| Live-safe read-only health context | Background health context only; not execution control for BTC+ETH Phase 1. | ADR-0005, ADR-0006, ADR-0007; task board. | Continue reading existing read-only / report-only health artifacts. | Any attempt to convert observation artifact into automatic block/recovery/execution control without a separate approved task. |

Live-safe artifacts are background health context and do not become execution control for BTC+ETH Phase 1.

## 7. Codex-owned Areas

- phase naming and SSOT maintenance
- Owner decision framing
- SRR-002 methodology boundary interpretation
- ADR / roadmap / task-board consistency judgment
- whether any item is allowed to become a Claude task card
- core execution / risk / reconciliation decisions
- merge readiness / review decisions
- preventing docs from being misread as runtime or small-live permission

## 8. Claude-safe Areas

Claude may only act under a Codex task card.

Allowed examples:

- local docs cleanup
- allowed-file formatting fixes
- read-only artifact inventory
- small table formatting
- bounded report formatter
- targeted tests for already-decided implementation

No Claude implementation task card is created by this document.

## 9. Current Forbidden Actions

- running backtest / experiment / adapter
- starting runtime for BTC+ETH Phase 1
- paper / testnet / live execution for BTC+ETH Phase 1
- small-live
- modifying runtime profile
- modifying strategy parameters
- modifying risk profile
- introducing SOL Phase 2
- CPM rescue / CPM reopening
- short-side work
- portfolio / router / multi-strategy implementation
- funding / OI / data capability implementation
- allowing Claude to define scope or implement independently

## 10. Owner Summary

Owner 现在不是“没事做”，而是进入项目控制模式。当前主线已经收束为 `Observation + Research Methodology Reset`：4h Direction A BTC+ETH Phase 1 只是 docs-only / shadow-no-order observation design，不是 runtime candidate，也不是 small-live candidate。SRR-002 是当前研究方法基线，它明确要求未来研究必须解决 pre-observable applicability boundary、top-winner fragility、year concentration、MTM drawdown 等问题；当前没有任何模块满足 SRR-002，因此不能把观察结论解释为执行许可。

当前 Owner 的重点不是继续催生新策略，而是管理边界、口径和证据一致性。A1/A3 trade count 存在 490 vs 373 的冲突，time-in-market 存在约 38% vs 52.26% 的冲突，BTC+ETH portfolio MaxDD baseline 尚未精确建立，MTM drawdown 是否纳入 shadow/no-order reporting 也需要 Owner 决定。同时，3 个当前可见的 untracked Owner-facing docs 是否提交、历史 21-doc batch 是否仍有效，也需要 Owner 明确。所有这些工作都只是在完善控制板和观察报告口径；它不授权 BTC+ETH Phase 1 paper/testnet/live，不授权 strategy runtime activation，不授权 small-live，不授权 portfolio/router/SOL/CPM/short-side，也不授权参数、风险或 runtime profile 变更。
