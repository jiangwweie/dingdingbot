# Project Roadmap v2

Last updated: 2026-05-09

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

The current stage is neither a multi-strategy phase, a multi-asset expansion
phase, nor a live/small-live activation phase.

The current stage is:

`Observation + Research Methodology Reset`

The only current mainline strategy-research object is:

`Direction A BTC+ETH Phase 1 observation design`

BTC+ETH Phase 1 is docs-only and observation-methodology focused. It does not
authorize strategy runtime, paper/testnet/live trading, small-live execution,
portfolio/router work, SOL Phase 2, CPM reopening, short-side work, parameter
optimization, or runtime/profile/risk changes.

The active tracks are:

1. `Live-safe Foundation` - preserved as a system safety foundation, but no
   live/small-live execution is authorized by the current research stage.
2. `BTC+ETH Phase 1 Observation + Research Methodology Reset` - docs-only
   consolidation, artifact reconciliation, SRR-002 discipline, and Owner review
   readiness.

All other capabilities belong to the future capability pool unless the Owner
explicitly promotes them through a separate decision. Other directions should
stay in backlog, archive, or future-research-pool form by default.

### Strategy Candidate Gate Status

As of 2026-05-06, the Live-safe Foundation track may continue as system
foundation work, but the current priority strategy module, CPM-1, has not passed
the OOS gate. CPM-1 remains frozen and paused, is not a small-live or canary-live
candidate, and its promotion path is stopped. The project therefore has no
deployable small-live strategy candidate at this point.

This status does not change runtime profiles, strategy parameters, risk rules,
live enablement, or live-safe control logic. Research and classification
evidence must continue to be handled through explicit Owner decisions.

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

## Active Track 2: Baseline Strategy Module Stabilization

### Goal

The current ETH Pinbar line is no longer treated as the system-wide strategy. It should be stabilized as:

`Crypto Pullback Module v1`

This is the current and only priority strategy module, used to validate the full loop from research to backtest to execution to monitoring to review.

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
