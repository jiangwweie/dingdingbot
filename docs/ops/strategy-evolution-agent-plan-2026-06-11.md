# Strategy Evolution Agent Plan

Status: AGENT_PLANNING
Date: 2026-06-11
Audience: Codex / Claude / future AI agents
Authority: Owner strategy-evolution discussion 2026-06-11

## Document Role

This document captures the Owner-aligned strategy and research evolution plan
for BRC after the runtime-governance base converges.

It is an agent-facing planning document. It is not canon, not an ADR, not a
live-trading authorization, not a strategy-performance promise, and not proof
that any strategy is runtime-eligible.

When this document conflicts with Owner explicit decisions, tracked code, or
`docs/canon/*`, those sources win.

## Owner Profile and Operating Intent

The Owner is a bank technology programmer, not a professional quantitative
researcher. BRC should not be evolved as an institutional asset-management or
portfolio-optimization platform.

The target posture is:

```text
personal small-capital right-tail trial system
+ bounded StrategyRuntimeInstance
+ Owner-controlled capital and manual account oversight
+ loss-of-control prevention first
+ auditable strategy semantics
+ small-funds live learning loop after explicit authorization
```

Research and backtesting may be lighter than institutional quant standards.
Execution governance must remain strict.

Important Owner corrections:

- Do not over-focus on withdrawal automation. Owner will inspect the account
  directly. The system only needs enough capital-base evidence to avoid
  polluting strategy PnL and review.
- The current strategy layer should not be locked into pure price action just
  because the first semantics are price-action heavy.
- Avoid hard-coding strategy preferences that should be versioned parameters.
- Binance futures historical K-lines can be downloaded as needed; symbol
  availability is not the core architecture problem.

## Current Code-Fact Starting Point

Use current code verification before acting. At the time this plan was written:

- Runtime-governance base is materially stronger than the strategy layer.
- `src/domain/strategy_semantics.py` already defines
  `StrategyImplementationBinding`, `RequiredFacts`,
  `StrategyEvaluationContext`, `EntryPolicy`, `ProtectionPolicy`, and
  `ExitPolicy`.
- Initial strategy semantics exist for CPM / BRF / BTPC / LSR / RBR / VCB /
  RMR / FCO, but they are reference or candidate semantics, not proven-alpha
  production strategies.
- `ParameterSetVersion` is still a key missing concept.
- Historical replay / campaign replay exists in fragments, but a unified
  `Historical Semantic Replay` path from historical K-lines into strategy
  facts, signal rows, path rows, and agent-reviewable reports is not yet the
  mainline.
- LLM advisory exists as a branch capability in the LLM advisory plane work:
  typed events, context packets, advisory ledger, Feishu push-only cards,
  safety checks, and eval harness. Agents must re-check whether it is merged
  into the active integration branch before treating it as current capability.

Do not describe branch-local or untracked files as integrated capabilities.

## Strategy Direction

Preferred strategy shape for the Owner:

- low-frequency and explainable;
- low-parameter;
- compatible with manual understanding and review;
- mostly 1h entry/observation, extendable to 4h and 1d;
- compatible with swing holding periods of days to weeks;
- right-tail opportunities are important, but range/mean-reversion and
  breakout-style families may also exist when their semantics and facts are
  explicit.

Avoid near-term focus on:

- high-frequency trading;
- order-book microstructure as a required first capability;
- black-box ML;
- large multi-factor optimization;
- institutional portfolio optimization;
- broad multi-asset runtime expansion before strategy/review semantics mature.

## Timeframe Policy

Owner preference:

```text
main: 1h
later extension: 4h, 1d
manual holding style: often days, sometimes weeks
```

Recommended semantics:

- 1h is the primary trigger and observation timeframe.
- 4h provides structure confirmation or conflict evidence.
- 1d provides regime / macro background and risk context.

Do not hard-code "4h unsupported means block" globally. Make the behavior
strategy-specific:

- Trend / breakout / right-tail strategies may require 4h or 1d support for
  `NORMAL_ATTEMPT`.
- Mean-reversion / repair-style strategies may trade against background only
  with explicit reversal structure, smaller risk profile, tighter protection,
  and shorter time stop.
- When uncertain but potentially useful, classify as `MICRO_ATTEMPT` or
  `OBSERVE_ONLY` rather than forcing a binary allow/block.

## Attempt Classification Vocabulary

Strategy and replay layers may recommend these review classifications:

```text
BLOCK
OBSERVE_ONLY
MICRO_ATTEMPT
NORMAL_ATTEMPT
```

These are evidence classifications, not execution authority.

Meaning:

- `BLOCK`: missing/stale facts, explicit semantic conflict, protection not
  representable, or known unsafe condition.
- `OBSERVE_ONLY`: record the would-have signal and path, no order.
- `MICRO_ATTEMPT`: very small bounded attempt when the idea is uncertain but
  valuable enough to learn from.
- `NORMAL_ATTEMPT`: candidate deserves the normal bounded runtime profile after
  required facts, replay evidence, runtime boundary, and FinalGate pass.

Do not encode fixed capital percentages in this vocabulary unless the Owner
later approves a concrete runtime profile or parameter set.

## Exit and Runner Direction

The Owner cares about not exiting too early. For right-tail / trend strategies,
first-class exit semantics should support:

```text
hard stop
TP1 partial realization
runner
trailing or structure-invalidation exit
time stop for failed follow-through
```

Do not hard-code a universal TP1, runner split, or time stop.

Defaults may be used as starting parameters only through a versioned
`ParameterSetVersion`, for example:

- TP1 range candidates;
- runner split candidates;
- trailing / structure invalidation settings;
- time-stop windows by strategy type.

Range / mean-reversion strategies may use fixed RR, range targets, and stricter
time stops. They do not need mandatory runners unless the strategy semantics
justify one.

## Evidence Philosophy

For this project, backtesting is not a pass/fail profit certificate.

Use this hierarchy:

```text
Historical Semantic Replay = main screening evidence
Shadow Observation = current environment sanity check
Micro Attempt = execution, risk, and review validation
Runtime Review = promote / revise / park decision support
```

Historical evidence should answer:

- How often does the signal trigger?
- Is it concentrated in one market regime?
- Does 4h/1d context change behavior?
- What are MFE, MAE, TP1 hit, runner path, time-to-invalid, and time-to-follow
  through?
- Does the entry frequently fail quickly?
- Does the exit policy cap right-tail winners?
- Which cases should be `NORMAL_ATTEMPT`, `MICRO_ATTEMPT`, `OBSERVE_ONLY`, or
  `BLOCK`?

It should not claim:

- future profitability is proven;
- a strategy is safe to trade real funds;
- a parameter set is optimal;
- Owner authorization is no longer required.

## Target Replay Architecture

First build a pluggable semantic replay framework, then connect one simple
strategy sample.

Target chain:

```text
Historical Kline files
-> ReplayDatasetManifest
-> CandleQuality / closed-candle validation
-> MultiTimeframeFactBuilder
-> StrategyEvaluationContext
-> StrategyImplementation.evaluate()
-> ReplaySignalRow
-> PathAnalyzer
-> ReplayPathRow
-> StrategyReplayReport
-> optional LLMContextPacket
-> optional LLM AdvisoryRecommendation
```

The replay path should reuse the same strategy-semantics concepts as runtime:

```text
StrategyImplementation
RequiredFacts
EntryPolicy
ProtectionPolicy
ExitPolicy
ReviewMetrics
```

Avoid creating a separate "research strategy" implementation that diverges
from runtime semantics.

## First-Class Artifacts to Add

Recommended future artifacts:

1. `ReplayDatasetManifest`
   - symbol;
   - timeframe;
   - source;
   - start/end;
   - row count;
   - missing candles;
   - duplicate candles;
   - closed-only status;
   - download/import time;
   - checksum or file hash.

2. `CandleQuality`
   - closed candle status;
   - gap/continuity checks;
   - stale/partial-candle behavior;
   - multi-timeframe alignment evidence.

3. `ParameterSetVersion`
   - strategy family/version;
   - parameter version ID;
   - effective parameter values;
   - status: draft / frozen / replayed / parked;
   - source and Owner/Codex notes.

4. `StrategyReplaySpec`
   - dataset selection;
   - strategy binding;
   - parameter set;
   - timeframe policy;
   - path-analysis windows;
   - output destinations.

5. `ReplayRun`
   - run ID;
   - spec ID;
   - code version;
   - dataset manifest IDs;
   - parameter set ID;
   - created_at;
   - no-order / no-execution boundary flags.

6. `ReplaySignalRow`
   - timestamp;
   - symbol;
   - timeframe;
   - strategy IDs;
   - required-fact check result;
   - context classification;
   - signal decision;
   - recommended attempt class.

7. `ReplayPathRow`
   - MFE / MAE;
   - R multiple path;
   - TP1 hit;
   - runner path;
   - time to invalidation;
   - time stop result;
   - max giveback;
   - exit-policy comparison fields.

8. `StrategyReplayReport`
   - Markdown for Owner/Codex review;
   - JSON for audit and reproducibility;
   - CSV or Parquet for analysis.

Trading Console visualization should be later than Markdown/JSON/CSV outputs.

## Hard-Coding Boundary

Code may hard-code safety and semantic boundaries:

- missing required facts fail closed;
- stale facts cannot become allow signals;
- K-lines must be closed when used as closed-candle evidence;
- replay cannot create orders or `ExecutionIntent`;
- LLM cannot create trading authority;
- `ProtectionPolicy` and `ExitPolicy` stay separate;
- risk calculations use `Decimal` where financial amounts are involved;
- `BLOCK / OBSERVE_ONLY / MICRO_ATTEMPT / NORMAL_ATTEMPT` are typed states.

Code should not hard-code strategy preferences:

- fixed TP1 such as 1.5R;
- fixed runner split such as 50/50;
- fixed 7/14-day time stop;
- global 4h/1d allow/block rule;
- symbol-specific rules;
- parameter sweeps disguised as constants.

Those belong in `ParameterSetVersion` and replay reports.

## LLM Role

LLM may be used as:

```text
Review Copilot
Audit Digest Generator
Blocker Explainer
Replay Report Summarizer
Closed-Trade Review Assistant
Registered Strategy Family Recommender
```

LLM must not be used as:

```text
Strategy Brain
market/account/exchange fact source
buy/sell/short/size/leverage decision maker
OrderCandidate creator
ExecutionIntent creator
FinalGate bypass
withdrawal / transfer actor
```

Recommended LLM input sources:

- `StrategyReplayReport`;
- `RuntimeSemanticReviewPacket`;
- `RightTailReviewSummary`;
- FinalGate blocker packets;
- protection anomaly packets;
- reconciliation mismatch packets;
- closed-trade review packets.

Recommended LLM outputs:

- summary;
- missing-fact explanation;
- risk notes;
- review notes;
- registered strategy-family suggestions;
- research idea notes.

Every LLM recommendation should reference concrete IDs when available:

```text
replay_run_id
strategy_family_id
strategy_family_version_id
parameter_set_version_id
runtime_instance_id
order_candidate_id
review_packet_id
```

## Promotion / Revise / Park Loop

Do not promote strategies mechanically.

Useful future gate:

```text
MicroAttemptPromotionGate
```

Suggested inputs:

- at least a small number of micro attempts, often around 3, but not as an
  automatic rule;
- no runtime boundary breach;
- no data-quality failure;
- no protection failure;
- no duplicate-submit or idempotency issue;
- clear replay/review evidence;
- Owner/Codex review conclusion.

Bounded strategy losses are not system failures. A normal bounded loss may
allow the runtime to continue. Data, protection, execution, reconciliation, or
submit-safety failures should pause and require review.

## Phased Plan

### P0: Strategy Quality Loop v1

Goal: make strategies auditable and replayable before adding more strategy
families.

Build:

- `ParameterSetVersion` model and file/DB strategy that does not pollute domain
  logic with I/O;
- `ReplayDatasetManifest` and `CandleQuality`;
- 1h-first `MultiTimeframeFactBuilder` with optional 4h/1d context;
- non-executing `Historical Semantic Replay` mainline;
- one simple strategy sample connected end-to-end;
- Markdown / JSON / CSV report outputs;
- basic report-to-LLM context packet.

Done when agents can answer:

- why a signal fired;
- which facts were required and present;
- whether the candle/context was valid;
- what happened after entry in MFE/MAE/R terms;
- whether the case is `BLOCK`, `OBSERVE_ONLY`, `MICRO_ATTEMPT`, or
  `NORMAL_ATTEMPT`;
- which parameter set produced the report.

### P1: Entry and Exit Evidence Depth

Goal: improve bad-trade filtering and runner/exit behavior without chasing
profit optimization.

Build:

- richer `PathAnalyzer` for TP1, runner, trailing, time stop, and structure
  invalidation;
- context split by 1h/4h/1d support or conflict;
- entry-quality summaries;
- exit-path summaries;
- shadow-observation comparison against historical replay;
- LLM audit/review summaries for replay and closed trades.

### P2: Strategy Family Expansion

Goal: add more strategy families only after the replay/review loop can judge
them.

Candidate families:

- CPM / BRF refinement;
- VCB breakout / volatility compression;
- LSR / RBR range or liquidity sweep reversion;
- BTPC short continuation;
- FCO funding/open-interest/crowding only after fact coverage is wired.

Each added strategy must provide:

- `StrategyImplementation`;
- `RequiredFacts`;
- parameter set;
- protection policy;
- exit policy;
- review metrics;
- replay report;
- explicit missing/stale behavior.

### P3: Console and Operator Experience

Goal: expose stable evidence to the Owner after report shape stabilizes.

Build:

- strategy replay run list;
- report detail view;
- parameter-set version view;
- promote / revise / park decision surface;
- LLM advisory inbox linkage;
- comparison between historical replay, shadow observation, micro attempts, and
  runtime review.

Do not build this before the report schema stabilizes.

## Agent Instructions

When future agents work on strategy evolution:

1. Read `docs/canon/*` first.
2. Re-check current code and branch before describing capability status.
3. Treat this document as planning guidance, not current fact.
4. Do not implement real trading, live profile changes, or runtime authority
   changes from this document.
5. Do not tune for maximum historical return as the first objective.
6. Add parameters through versioned parameter sets, not hidden constants.
7. Keep domain logic pure; loaders, files, DB, and exchange access belong
   outside domain.
8. Keep replay non-executing with explicit no-order flags.
9. Let LLM consume structured facts; never let LLM produce trading authority.
10. Prefer small, reviewable task cards for Claude implementation.

## Recommended Next Task Card Shape

Use this as a future Claude/Codex handoff seed when the Owner decides to start:

```markdown
# Task ID
STRAT-EVO-P0-001

## Goal
Create the non-executing Strategy Quality Loop v1 skeleton:
ReplayDatasetManifest, CandleQuality, ParameterSetVersion, StrategyReplaySpec,
ReplayRun, and StrategyReplayReport models plus one minimal fake replay test.

## Why
The runtime base is converging, but strategy evolution needs replayable,
versioned, non-hardcoded evidence before adding more strategies.

## Allowed files
- src/domain/strategy_replay.py
- src/application/strategy_replay_service.py
- tests/unit/test_strategy_replay_models.py
- docs/ops/strategy-evolution-agent-plan-2026-06-11.md

## Forbidden files
- src/application/execution_orchestrator.py
- src/application/order_lifecycle_service.py
- src/infrastructure/exchange_gateway.py
- live runtime profile/env files

## Requirements
1. No orders, ExecutionIntent, exchange calls, transfer, or withdrawal.
2. Domain models import no I/O frameworks.
3. Parameter values are versioned, not hard-coded into replay flow.
4. Dataset quality records closed-candle, gaps, duplicates, and source refs.
5. Report output is reproducible from run/spec/dataset/parameter IDs.

## Tests
- /opt/homebrew/bin/pytest tests/unit/test_strategy_replay_models.py -q

## Done When
- Models validate success/failure cases.
- No execution authority is introduced.
- The report can identify strategy ID, parameter-set ID, dataset ID, and
  no-order boundary flags.
```
