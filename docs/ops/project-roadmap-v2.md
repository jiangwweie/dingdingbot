# Project Roadmap v2

Last updated: 2026-05-26

## Document Role

This document defines the long-term direction, current-stage boundaries, capability selection principles, and AI-agent collaboration constraints for the project.

It is not a task breakdown, sprint plan, implementation spec, or promise of strategy returns.

Detailed tasks, branches, tests, and code changes must be created under the constraints of this document.

## Vision

The project aims to build an AI-agent assisted low-frequency derivatives trading system.

The long-term direction is:

- Full-auto.
- Low-frequency.
- Multi-direction.
- Extensible.

The current stage does not aim to build a complete multi-strategy platform, multi-asset engine, data lake, or portfolio engine in advance.

System priorities are:

- Execution safety.
- Account-level risk control.
- Research and runtime isolation.
- Explainable decisions.
- Traceable behavior.
- Clear module boundaries.
- On-demand extensibility.

Return, drawdown, and annualized performance numbers are evaluation outputs, not hard-coded system constraints.

## Why This Revision Exists

The older roadmap used a linear phase narrative:

`Live-safe -> Regime -> Data -> Multi-strategy -> Multi-asset -> Portfolio`

That direction was broadly reasonable, but it can be misread by AI agents as a sequence of large current-build obligations.

This revision changes the framing to:

- Thin core.
- Current active tracks.
- On-demand capability pool.
- Full lifecycle traceability.

The key reasons are:

- Complexity should be driven by actual strategy scope.
- Infrastructure should not be built ahead of validated need.
- AI-agent development is fast, so the roadmap must actively constrain scope drift.
- The highest current value is live-safe hardening and traceability.

## Current Stage

The current stage is neither a multi-strategy phase, a multi-asset runtime
expansion phase, nor a live/small-live activation phase.

The current stage is:

`RBC Reset / Opportunity Structure Discovery v0`

2026-05-25 Owner-facing mainline update:

The business direction is now fixed as `Personal Leveraged Campaign Business
Chain v0`, documented in
`docs/ops/personal-leveraged-campaign-mainline-v0.md` and accepted by
`docs/adr/0008-personal-leveraged-campaign-business-chain.md`.

The mainline is no longer "make better research tables" as an end state. The
target chain is:

`Data Ingestion -> Market State / Feature Builder -> Strategy Detector -> Mode Router -> Playbook Governance -> Human Arm Gate -> Strategy Contract -> Trade Intent -> Risk-Aware Order Builder -> Execution + Order Lifecycle -> Position / Campaign / Profit Protection Control`

This reframes the current work from pure opportunity review toward a future
`Playbook Governance -> Human Arm Gate -> Strategy Contract -> Risk-Aware Order Builder -> Campaign Profit Protection Control`
loop.

2026-05-25 Owner-facing amendment:

The project direction is now formally reframed by ADR-0012 as
`Bounded Risk Campaign System`.

The active product model is no longer "prove a stable strategy first, then
build a strategy execution platform." It is:

`isolated risk capital -> Owner-selected Playbook -> bounded campaign attempts -> hard risk envelope -> profit protection / loss lock -> evidence packet -> outcome review`

This allows bounded testnet or future risk-capital experimentation without
pretending that a runtime-eligible strategy exists. The system's job is to
prevent risk spillover, playbook-switch loss-counter reset, post-loss risk
escalation, uncontrolled profit giveback, and programmatic withdrawal.

Playbook Governance is now a BRC sub-capability. Strategy Contract/runtime
execution work remains a future branch until a governed playbook and promoted
strategy justify it.

2026-05-25 Playbook Governance amendment:

The PLC roadmap review accepted ADR-0011 and
`docs/ops/playbook-governance-r0-plan.md`. The immediate next phase is
`Playbook Governance R0`, not further Strategy Contract/runtime
implementation. The reason is evidence-state driven: the project currently has
no runtime-eligible strategy candidate, so the highest-value next capability is
governing human playbook switching, cooldowns, decision logs, and CPV0_2
continuity before any new execution-oriented branch.

2026-05-25 Owner boundary clarification:

- real live trading remains prohibited unless separately and explicitly
  authorized by the Owner;
- all non-real-live development and research work, including runtime, paper,
  testnet, tiny-live-style rehearsal, read-only exchange sync, and other
  exchange-connected tests, may be executed after reasonable scoped
  verification and explicit Owner authorization for the specific action;
- this does not authorize automatic strategy promotion, real-funds deployment,
  live order placement, live transfer, withdrawal, or LLM/agent autonomous
  buy/sell/short/size/leverage decisions.

See `docs/adr/0009-non-real-live-execution-authorization-boundary.md`.

2026-05-26 BRC-R4 operator-console update:

The current engineering stage is `BRC-R4 API Surface Cleanup + Local Operator
Console`. The system now has a local Owner-facing BRC control surface with
username/password/Google-Authenticator login, BRC-first API mounting, operator
plan/confirmation flow, LLM workflow visibility, review decision input, ledger
views, runtime safety summary, and human-readable chain explanations.

This is still local operation governance, not production deployment. User
tables/RBAC, Feishu cards, cloud hardening, CSRF/nonce/idempotency,
secret-manager integration, strategy pool construction, withdrawal interfaces,
automatic strategy execution, and real live remain future or unauthorized
tracks.

2026-05-26 BRC-R4.1 delivery-console amendment:

The current product stage is now `BRC-R4.1 Delivery Owner Guide`. The console
is no longer treated as a collection of engineering status pages. It must
answer, in Owner language, the four operating questions on every primary path:

- where am I now;
- what can I do;
- why can/cannot I do it;
- what is the next click or confirmation, and whether it can affect a real
  account.

`/api/brc/readiness` is the readonly product-state translation layer for the
local console. It does not replace risk facts, does not mutate campaign or
runtime state, and does not authorize orders. It only translates existing BRC
and runtime conditions into Guide/action-card decisions. `/guide` is the
default Owner entry. Review must auto-bind the latest campaign when available;
Owner should not be asked to hand-type Campaign ID as the normal path.

This amendment still does not start Feishu approval, cloud deployment,
strategy-pool construction, real live, withdrawal/transfer, automatic strategy
execution, automatic sizing, or any broader testnet authority.

2026-05-26 local acceptance amendment:

For local Owner acceptance only, the development environment defaults to the
fixed BRC testnet rehearsal posture:

- `EXCHANGE_TESTNET=true`;
- `RUNTIME_PROFILE=brc_btc_eth_testnet_runtime`;
- `RUNTIME_CONTROL_API_ENABLED=true`;
- `RUNTIME_TEST_SIGNAL_INJECTION_ENABLED=true`.

This is a local testing convenience so the Owner can validate the full
testnet chain without repeatedly editing env flags. It is not the production
security model. Before Feishu integration, cloud deployment, public/internal
Web mutation controls, strategy-pool execution, or real-live review, these
permissions must be re-gated by the relevant deployment/security tasks.

2026-05-25 PLC execution-stage update:

- PLC Phase 0 local sandbox, Phase 1 read-only runtime adapter, Phase 2 paper
  observation packet, Phase 3 bounded testnet rehearsal, and Phase 4
  non-real-live runtime hardening/smoke are complete for review.
- Phase 5A small-scale rehearsal readiness has started under
  `docs/ops/plc-phase5-small-scale-rehearsal-design.md`: account-scope risk,
  campaign runtime-event state transitions, and Strategy Contract promotion
  gating are now the current non-real-live hardening focus.
- Phase 5A bounded Binance testnet smoke passed after those first gates.
- Repeated or longer testnet rehearsal, multi-symbol runtime, and real live
  remain separate gates. Real live remains unauthorized.
- Phase 5B repeated testnet rehearsal is now opened by Owner authorization.
  It remains ETH-only and testnet-only. The first multi-symbol prerequisite is
  symbol-isolation hardening/audit; multi-symbol runtime itself remains blocked.
- Phase 5B repeated Binance testnet rehearsal passed across two fresh runtime
  processes. The result supports continued ETH-only non-real-live hardening;
  it does not promote multi-symbol runtime or real live.
- Phase 5C local BTC/ETH synthetic fixture passed for reconciliation and
  runtime read-model symbol filtering. Multi-symbol runtime still requires a
  separate Owner-authorized exchange-connected rehearsal and profile/config
  review.
- Phase 5D BTC/ETH exchange-connected read-only rehearsal passed after bounded
  BTC testnet orphan conditional cleanup. Multi-symbol runtime remains blocked
  pending separate profile/config and execution-runtime authorization.
- Phase 5E design has started as an Owner-review package only. The proposed
  path is one new readonly BTC/ETH testnet runtime profile, minimal
  multi-symbol market-scope config support, and one runtime process with
  sequential ETH then BTC controlled exposure under explicit exposure/order
  caps, stop conditions, and rollback. No implementation or testnet runtime
  execution is authorized by the design document.
- Phase 5E was then Owner-authorized for bounded testnet. One runtime process
  started with BTC/ETH market scope and order-watch. ETH controlled
  entry/close passed and ended flat. BTC controlled entry was blocked before
  order placement because fixed `0.001 BTC` notional was below min_notional;
  the cap was not raised. Final direct Binance testnet and PG state were
  flat/no-open-orders. Real live remains unauthorized.
- Phase 5E follow-up added read-only feasibility preflight for fixed ETH/BTC
  controlled specs so min_notional/cap blockers are visible before arming a
  testnet entry window. BTC blocker handling now reports the next viable
  exchange-step amount, estimated notional, and cap shortfall as Owner decision
  evidence; it still does not raise caps or resize BTC orders automatically.
- Owner then approved Binance testnet operations without the prior
  minimum-capital limitation. Phase 5E BTC controlled amount/cap are updated
  for a testnet-only retry: `0.002 BTC`, max notional `250 USDT`, sequential
  one-symbol exposure, real live still unauthorized.
- Phase 5E BTC testnet retry passed: feasibility was `OK`, controlled BTC
  entry `0.002 BTC` completed, runtime-managed close filled, three protection
  orders were terminalized/canceled, final direct Binance testnet and PG state
  were flat/no-open-orders, controls were restored, and runtime stopped.
- Phase 5E follow-up added a read-only inventory endpoint for standardized
  BTC/ETH preflight and final flatness evidence across exchange and PG state.
- Phase 5E+ long-term capability planning is now captured in
  `docs/ops/plc-long-term-capability-roadmap-v1.md`. The next recommended
  direction is local campaign risk state-machine completion before more
  exchange-connected rehearsal: state before action, account before symbol,
  Strategy Contract freeze before runtime, sequential before simultaneous, and
  evidence before promotion.
- PLC-STATE-001 completed the first local campaign state-machine core for
  review: transition rules are now table-driven, runtime/Owner triggers are
  explicit, transition records are replayable and audit-ready, and `entry_filled`
  cannot arm a campaign from `observe`. No additional testnet action was needed
  for this local proof.
- PLC-STATE-002/003/004 completed the next local campaign state-machine layer:
  durable transition ledger, PG replay proof, runtime event wiring from existing
  order lifecycle callbacks, and a read-only replay evidence packet for future
  bounded testnet rehearsals. This strengthens auditability without changing
  runtime profile defaults or authorizing real live.
- Playbook Governance R0 is now accepted with amendments as the next
  docs-governance phase. The execution branch of PLC remains preserved as
  safety evidence but reserved/deferred. Tracks B-E runtime implementation,
  Phase 5H-8 runtime-oriented work, Strategy Contract v2 implementation, and
  further paper/testnet runtime remain deferred until a governed playbook and a
  separately promoted strategy justify them.
- BRC-R0/R1 is implemented and Binance testnet smoke passed as the new mainline
  acceptance slice. It adds the BRC domain model, PG persistence, readonly
  inactive `brc_btc_eth_testnet_runtime` profile seed, and internal test
  endpoints for ETH -> mock profit -> BTC -> mock loss. Mock PnL is BRC
  business-state evidence only and does not mutate exchange fills, balances,
  withdrawals, or daily risk accounting. Final outcome was
  `ended_testnet_rehearsal_complete_loss_locked`; evidence inventory was flat.
  Real live and program withdrawal remain unauthorized.
- BRC-R2-001 is the next active BRC capability slice. It focuses on low-friction
  campaign operation review: latest campaign review packet, next-campaign
  eligibility gate, a local read-only operator helper, and narrow
  text-to-read-action draft. This does not expand order authority, strategy
  authority, withdrawal/transfer authority, real-live authority, or
  natural-language auto-execution.
- BRC-R2-002 extends that operator layer with an Owner-confirmed read-only
  runner: Owner text is converted to a draft, then a read-only plan, then a
  confirmed read-only run. The confirmation phrase is scoped to read-only BRC
  review actions and does not authorize testnet orders, real live,
  withdrawals/transfers, automatic sizing, or strategy execution.
- BRC-R2-003 makes the operator action ledger database-backed:
  `/operator/plan` persists an action row, canonical run uses `action_id`, and
  confirmation failures/unknown text are retained as blocked ledger rows. This
  keeps the operation-governance layer auditable without expanding execution
  authority.
- BRC-R2-004 completes the first operation-governance loop by persisting Owner
  review decisions after operator runs. These decisions record review posture
  and the next recommended task only; they cannot create campaigns, trigger
  runtime/order actions, authorize real live, authorize withdrawal, or
  authorize strategy execution.
- BRC-R3 adds a LangGraph-shaped LLM operator gateway for the BRC operation
  governance layer. The LLM may classify Owner text into a small typed action
  enum and the workflow may pause/resume around Owner confirmation, but BRC PG
  tables remain the audit fact source. Read-only actions still require
  `CONFIRM_READ_ONLY_BRC`; the fixed controlled testnet rehearsal requires
  `CONFIRM_BRC_TESTNET_REHEARSAL`. This does not authorize live/mainnet,
  withdrawal/transfer, strategy execution, automatic sizing/leverage/side
  selection, or broader multi-symbol runtime expansion.
- The external BRC audit immediate safety-gate fixes are complete for review
  in commit `bc7e2ad`. Remaining audit/deployment items are recorded in
  `docs/ops/brc-pre-deploy-audit-backlog.md` and are deferred to the correct
  future gates: Feishu callbacks, cloud deployment, Web mutation controls, and
  strategy-pool construction. The next recommended capability is local
  operation friction reduction through `BRC-R4-001 Local Operator Console`,
  not broader trading authority.

The active research SSOT is:

- `docs/ops/opportunity-research-governance-v0.md`
- `docs/ops/opportunity-research-control-board.md`
- `docs/ops/opportunity-hypothesis-register.md`

The current research model is an open opportunity-structure research funnel.
It may compare opportunity mechanisms, edge hypotheses, failure hypotheses,
capital-shape ideas, manual-event workflows, observe-only indicators, and
no-long/risk-off contexts before deciding whether anything deserves deeper
study.

This stage does not pre-assume small-capital heavy swing, 1h entry, Campaign,
OKX MCP, Direction A, HTF/LTF trend baseline, Owner-Gated execution, or
StrategySignalV2 as the answer.

Direction A / BTC+ETH Phase 1 is downgraded from current mainline to evidence
archive / benchmark / cautionary case. It may inform future comparisons, but it
does not define the current research priority.

Live-safe Foundation is preserved as a runtime safety foundation. It no longer
defines research priority. Runtime and research remain isolated.

The active tracks are:

1. `Opportunity Structure Discovery v0` - open research funnel, hypothesis
   register, minimal falsification plans, labels, and capital-shape
   classification.
2. `Bounded Risk Campaign Mainline` - isolated risk bucket, Owner-selected
   playbook, bounded attempts, hard risk envelope, playbook switch evidence,
   profit-protect/loss-lock state, and outcome packet. Strategy Contract and
   automated execution are future branches, not prerequisites for BRC
   governance. Withdrawal is Owner-external and not a system object.
3. `Runtime Safety Foundation` - Live-safe, OwnerGate, StrategySignalV2,
   permission state, and execution-chain safety remain runtime-only boundary
   material unless separately promoted.
4. `Evidence Archive` - Direction A, CPM-1, HTF/LTF, SRR-002, HTP, short-side
   OHLCV, and other prior research remain available as archived evidence,
   benchmarks, or failure/cautionary material.

All other capabilities belong to the future capability pool unless Codex
promotes them locally inside the research freedom zone or Owner explicitly
promotes them toward real-account use. Local research/design/code experiments
must be labeled, tested where applicable, and disconnected from real trading by
default.

### Strategy Candidate Gate Status

As of 2026-05-25, the Live-safe Foundation track may continue as system
foundation work, but the current priority strategy module, CPM-1, has not passed
the OOS gate. CPM-1 remains frozen and paused, is not a small-live or canary-live
candidate, and its promotion path is stopped. The project therefore has no
deployable small-live strategy candidate at this point.

`SQ02_DOWNSIDE_CONT_V0` may be used as the first strategy-contract skeleton
candidate for the Personal Leveraged Campaign mainline. It is currently a
design/local-sandbox candidate only. Any move toward scanner, alert, watchlist,
runtime, paper, testnet, tiny-live, account connectivity, leverage, sizing, or
order-path use requires a separate promotion request, scoped verification, and
explicit Owner authorization.

This status does not by itself change runtime profiles, strategy parameters,
risk rules, live enablement, or live-safe control logic. Research and
classification evidence must continue to use explicit labels and promotion
gates. Owner confirmation is required before any runtime, paper, testnet,
tiny-live, exchange-connected, account-action, push, deployment, or direct
research-to-order step; real live trading remains separately prohibited unless
explicitly authorized.

## Core Design Principles

### Thin Core

The core should keep only the capabilities that are required now:

- Order-state synchronization.
- Protection-order management.
- Account-level risk control.
- Circuit breaker and kill switch.
- Reconciliation.
- Structured logs.
- Configuration isolation.
- Research and runtime isolation.
- Decision traceability.

The core should not pre-build full multi-strategy, multi-asset, or portfolio behavior.

### Strategy Need Drives Complexity

Infrastructure is justified by a concrete strategy or risk need, not by imagined future scope.

Examples:

| Capability | Trigger |
| --- | --- |
| Funding data | A strategy needs crowding, carry, or toxic-state judgment |
| Open interest data | A strategy needs leverage buildup, deleveraging, or trend-quality judgment |
| Spread data | Asset expansion or execution gating requires it |
| Regime layer | Multiple strategy modules need shared state routing |
| Strategy router | Strategy outputs can conflict |
| Portfolio engine | Multiple strategies or assets share one risk budget |
| TradFi data adapters | Gold or equity-index style derivatives are actually being introduced |

Do not build the full capability before a real strategy or risk need exists.

### Separate Required From Optional

All project capabilities should be treated as one of:

- Required now.
- Optional later.
- Not worth doing now.

Required now supports live-safe and current strategy-module stabilization.

Optional later is promoted only by actual strategy or risk demand.

Not worth doing now includes:

- Full order-book simulation.
- Tick-level replay.
- Complex ML regime systems.
- Full data lake work.
- Full portfolio optimizer work.

### Research And Runtime Isolation

Research may produce:

- Reports.
- Candidates.
- Diagnostics.
- Suggestions.
- Hypotheses.

Research must not directly produce:

- Runtime profile changes.
- Strategy promotion.
- Risk-parameter overrides.
- Automatic live enablement.

This isolation remains a permanent safety rule.

### Full Lifecycle Explainability

The system must not only record what happened, but also explain:

- Why it happened.
- On what basis it happened.
- Which version produced it.
- How to reproduce it.
- How to roll it back.

Traceability should cover:

- Research results.
- Architecture decisions.
- Code changes.
- Configuration versions.
- Signal decisions.
- Risk decisions.
- Execution events.
- Trade outcomes.

## Active Track 1: Live-safe Foundation

### Goal

The goal is not higher returns. The goal is a system that, when fully automated:

- Does not run uncontrolled.
- Does not trade unprotected.
- Does not fail silently.
- Does not amplify errors.
- Can pause.
- Can recover.
- Can be audited.
- Can be replayed and reviewed.

### Design Rules

1. Exchange-native protection orders should back any live position.
2. The exchange is the source of truth.
3. When system state is uncertain, default to blocking new entries.
4. Account-level risk is above strategy signals.
5. Circuit breakers cover execution, risk, protection health, data health, and connectivity health.
6. Reconciliation must run continuously, not only at startup.
7. All key decisions must be structured and traceable.

### Current Focus

Current live-safe focus areas are:

- Trusted order state.
- Trusted protection-order state.
- Effective account-level runtime risk limits.
- Stronger circuit-break behavior.
- Continuous reconciliation.
- Replayable logs and event trails.

## Historical Track: Baseline Strategy Module Stabilization

2026-05-22 note: This section is historical context from the pre-reset baseline
strategy phase. It is superseded for current work by `RBC Reset / Opportunity
Structure Discovery v0`. CPM-1 is paused and is not the current mainline,
runtime candidate, or small-live candidate. CPM-1 or Baseline Strategy Module
Stabilization may be reconsidered only through the opportunity research funnel.
Any path toward real secrets, real trading permissions, real account actions,
push, real-account deployment, or direct research-to-real-order wiring remains
behind the Owner confirmation gate.

### Goal

The current ETH Pinbar line is no longer treated as the system-wide strategy. It should be stabilized as:

`Crypto Pullback Module v1`

Historical context: this was previously treated as the priority strategy module
for validating the full loop from research to backtest to execution to
monitoring to review. It is now paused for current work and must not be read as
the current mainline or as authorization for CPM-1 runtime, small-live,
backtests, experiments, adapter runs, strategy/risk/profile/parameter changes,
or implementation.

### Module Position

This module is:

- Higher-timeframe directional bias.
- Lower-timeframe pullback entry.
- Pattern confirmation.
- Partial take-profit structure.

Current intended scope:

| Dimension | Position |
| --- | --- |
| Strategy family | Pullback |
| Asset | `ETH/USDT:USDT` |
| Timeframe | `1h` |
| Direction | `LONG-only` |
| Market assumption | Trend intact, pullback ending |
| Profit source | Continuation after pullback |
| Failure source | Pullback turns into reversal, overheating, high volatility, fake rebound |
| Portfolio role | Crypto trend pullback module |

### What This Stage Is Not

This is not a stage for broad parameter tweaking or saving every bad regime by force.

The focus is to clarify:

- What the module earns from.
- What the module loses to.
- Its valid market boundaries.
- Its invalid market boundaries.
- How it may later be routed or constrained.

Do not treat 2023-style failure as a parameter problem by default. Treat it first as a regime-mismatch signal.

## Decision Traceability Foundation

Decision traceability is a cross-cutting foundation for the entire system lifecycle.

It includes:

- Research traceability.
- Design traceability.
- Code-change traceability.
- Runtime-config traceability.
- Signal-decision traceability.
- Risk and execution traceability.
- Post-trade attribution traceability.

### Minimum Current Standard

The current phase must guarantee:

- ADRs for important design decisions.
- Runtime config version, hash, and source.
- Research metadata for engine, cost, data, and commit.
- Signal trigger or filter reasons.
- Risk allow or deny reasons.
- Execution event chains.
- Trade outcomes traceable back to signal and config context.

Do not build a giant audit platform now. Build only the minimum traceability needed to explain critical decisions and replay critical trades.

## Backtest And Research Boundary

The current backtest engine should be treated as the official bar-research engine.

It is for:

- Strategy-module research.
- Parameter comparison.
- Filter validation.
- Pattern-strategy evaluation.

It is not a full trading simulator.

Do not pursue now:

- Full order-book simulation.
- Tick-level matching.
- Maker queue modeling.
- Complex exchange-anomaly simulation.
- High-frequency execution-alpha simulation.

Backtest outputs should always include metadata such as:

- `engine_name`
- `engine_version`
- `matching_model`
- `account_model`
- `cost_model`
- `risk_model`
- `data_window`
- `same_bar_policy`
- `funding_model`
- `proxy_or_official`

## Frontend Role

The frontend is not a trading control desk. It is:

- Owner console.
- Live-safe observability surface.
- Research traceability viewer.

Current frontend principles:

- Read-only.
- Low-operation.
- High-explanation.
- High-state visibility.
- High-traceability.

Do not add now:

- Runtime profile editing.
- Hot strategy parameter changes.
- One-click promotion of research candidates.
- Manual order entry.
- Live-strategy switching.
- Risk bypass actions.

## Future Capability Pool

The following are not current must-build items. They are capability candidates for later.

### Regime Capability

Use when multiple strategy modules need shared market-state interpretation.

### Data Capability

Use when strategy or risk logic explicitly needs:

- Mark price.
- Funding rate.
- Open interest.
- Bid/ask spread.

Do not build full data-lake scope now.

### Strategy Module Capability

Add new modules only when they have:

- Clear role.
- Clear valid regime.
- Clear failure regime.
- Clear data needs.
- Clear risk-exposure explanation.

### Multi-asset Capability

Do not promote to active scope until strategy, execution, data, and risk assumptions all support the asset class.

### Portfolio Capability

Do not pre-build a full portfolio engine before multiple strategies or assets truly share one risk budget.

### Replay And Validation Capability

Build later when enough live or shadow events exist to make replay genuinely useful.

## AI-Agent Governance

### Role Model

| Role | Responsibility |
| --- | --- |
| Owner | Direction, tradeoffs, final decisions |
| Codex | Architecture, core implementation, key-path ownership |
| Claude Code | Bounded implementation, tests, docs, non-core work |
| External review | Strategy, methodology, and risk-boundary review |

### Agent Rules

All agents must follow:

- Do not expand scope freely.
- Do not turn future directions into current implementation.
- Do not modify runtime profiles directly.
- Do not break research and runtime isolation.
- Do not change core paths without clear explanation.
- Core changes must include risk impact and rollback notes.

Codex decides whether a capability belongs to the current active tracks or to the future capability pool. Claude does not own that judgment.

### Documentation First

Important direction and core changes should have:

- Planning context.
- ADRs when needed.
- Task boundaries.
- Allowed files.
- Forbidden files.
- Test requirements.
- Rollback path.

## Explicit Not-Now List

The current stage does not include:

- Multi-asset rollout.
- Parallel multi-strategy runtime.
- Full regime layer.
- Full data feature store.
- Full portfolio engine.
- Full trading simulator.
- Tick or order-book replay.
- Complex ML trading systems.
- Frontend runtime-control features.
- One-click candidate promotion.
- Return optimization as the primary track.

## One-Line Summary

The project should move from rapid feature stacking into thin-core governance:

Prioritize live-safe, decision traceability, and stabilization of the current strategy module. Add regime, data, multi-strategy, multi-asset, and portfolio capabilities only when a concrete strategy or risk need justifies them.

Shorter version:

Build the core thin and stable first, then let strategy needs drive modular expansion.
