---
title: STRATEGY_RUNTIME_GUIDE
status: CURRENT_CANON
authority: owner-strategy-design-decisions
last_verified: 2026-06-10
source_of_truth:
  - Owner strategy/risk design decisions 2026-06-10
  - docs/canon/PROJECT_BASELINE_CURRENT.md
  - docs/canon/BRC_TARGET_SEMANTICS.md
  - docs/canon/RUNTIME_SAFETY_BOUNDARY.md
---

# Strategy Runtime Guide

This document is the durable strategy-design guide for BRC runtime-governance
work. Agents must use it before adding, changing, or wiring strategy families,
strategy implementations, entry logic, protection logic, exit logic, strategy
facts, or runtime execution bridges.

---

## 1. Owner Objective

The system uses isolated small experimental risk capital to pursue asymmetric
right-tail opportunities under explicit boundaries.

The target is:

```text
bounded free trading inside an Owner-approved StrategyRuntimeInstance
```

Not:

```text
per-entry manual approval forever
stable yield
low-volatility compounding
automatic asset management
automatic withdrawal
```

The Binance subaccount capital supplied by the Owner is already the result of
Owner-level risk sizing. Within confirmed runtime boundaries, the system should
be allowed to trade without asking for confirmation on every candidate.

The system should not optimize for avoiding every losing trade. Small bounded
losses, failed experiments, and low win-rate trials are acceptable when they are
traceable and remain inside budget. The system must prevent loss of control:
budget breach, runaway attempts, stale or missing facts used as allow signals,
unprotected exposure, unauditable submits, duplicate submits, and boundary
expansion.

---

## 2. Admission Layers

Strategy readiness is layered:

- Semantic Admission: the strategy can be represented, audited, constrained,
  and reviewed. Lack of proven alpha is not a blocker.
- Economic Admission: the strategy deserves larger budget, lower confirmation
  burden, or higher autonomy. Lack of proven alpha restricts this layer.
- Execution Admission: one concrete candidate passes runtime boundary,
  FinalGate, account/position facts, protection readiness, idempotency, and
  deployment readiness.

Do not block a strategy from entering the architecture only because alpha has
not been proven. Do limit budget, leverage, autonomy, and review leniency until
live and review evidence improves.

---

## 3. Strategy Responsibility Boundary

The strategy chain is:

```text
StrategyFamilyVersion
  -> StrategyImplementation
  -> RequiredFacts
  -> StrategyEvaluationContext
  -> EntryPolicy
  -> ProtectionPolicy
  -> ExitPolicy
  -> OrderCandidate
```

A StrategyImplementation may define:

- thesis / archetype / payoff profile;
- required and optional facts;
- missing and stale fact behavior;
- entry setup and invalidation;
- protection reference;
- exit plan;
- review metrics and evidence fields.

A StrategyImplementation must not define or smuggle:

- executable order type;
- final quantity or notional authority;
- final leverage authority;
- exchange venue / route;
- submit permission;
- execution authorization;
- runtime budget expansion.

Those belong to runtime risk, FinalGate, account facts, market rules, and the
execution adapter.

---

## 4. Risk Stack

Risk is split across three layers:

| Layer | Owns | Does Not Own |
| --- | --- | --- |
| StrategyImplementation | stop/invalidation reference, expected risk shape, payoff profile, protection requirement, exit intent | final budget, final notional, final leverage, submit authority |
| StrategyRuntimeInstance | max attempts, max loss budget, max notional per attempt, max active positions, max leverage, max margin, review requirement | alpha proof, strategy-specific entry geometry |
| FinalGate / execution adapter | account facts, position facts, idempotency, market rules, concrete protection readiness, submit safety | strategy thesis, hidden budget changes |

Leverage is a risk amplifier and margin-efficiency tool. It must never expand
loss budget. A leveraged candidate must satisfy all constraints together:

- concrete max-loss reference is inside per-attempt loss budget;
- intended notional is inside notional boundary;
- proposed leverage is inside max leverage;
- margin use is inside margin boundary;
- liquidation boundary has buffer beyond hard stop;
- active-position boundary passes using trusted facts;
- protection is concrete and submit-ready.

---

## 5. Protection vs Exit

ProtectionPolicy and ExitPolicy must stay separate.

ProtectionPolicy exists to prevent uncontrolled loss:

- hard stop;
- invalidation boundary;
- liquidation buffer;
- protection-order readiness;
- behavior when protection creation fails.

ExitPolicy exists to express how the strategy releases profit:

- partial profit-taking;
- runner;
- trailing stop;
- trend invalidation exit;
- fixed risk/reward target;
- range target;
- time stop;
- manual review exit.

Do not reduce every strategy to one fixed TP/SL template. That would cap
right-tail winners while leaving losses intact.

---

## 6. Payoff-Specific Exit Defaults

Trend / right-tail strategies should default to:

```text
hard stop
TP1 partial realization
runner
trailing or structure-invalidation exit
time stop for failed follow-through
```

The goal is to let rare large winners pay for many small bounded losses.

Range / mean-reversion strategies should default to:

```text
hard stop
fixed RR or range target
stricter time stop
no mandatory runner
```

The goal is to monetize boundary reversion without pretending a range trade is
a right-tail trend trade.

---

## 7. Initial Strategy Set

The initial strategy set is for semantic coverage and live-path learning, not
proven-alpha production deployment.

| Strategy | Role | Direction | Payoff Profile | Entry Summary | Exit Default |
| --- | --- | --- | --- | --- | --- |
| CPM | reference implementation | long only | right-tail | pullback continuation / reclaim | TP1 + runner + trail / invalidation |
| BRF | reference implementation | short only | right-tail | bear rally failure / rejection | TP1 + runner + trail / invalidation |
| BTPC | near-term candidate | short only | right-tail | bear-trend pullback loses continuation support | TP1 + runner + trail / invalidation |
| LSR | near-term candidate | long / short | mean-reversion | liquidity sweep and reclaim / rejection | fixed RR or range target |
| RBR | near-term candidate | long / short | mean-reversion | range boundary rejection in chop/range context | fixed RR or opposite range target |
| VCB | near-term candidate | long / short | right-tail | volatility compression breakout | TP1 + runner + trail / invalidation |
| RMR | regime context | none | classifier | range/chop/trend state evidence | not a trading strategy |
| FCO | backlog | TBD | data-dependent | funding / OI / crowding evidence | not in P1-P3 |

CPM and BRF are reference implementations, not proven-alpha strategies.

BRF and other short-side strategies must start with a more conservative runtime
profile than long-only CPM: lower leverage, smaller notional, mandatory hard
stop, stricter max active positions, and squeeze-risk facts where available.

RMR must not become a broad hard filter. It may downgrade confidence, mark
observe-only, or raise review requirements. Missing or stale RMR must not act
as execution authority.

FCO remains backlog until deployment-backed funding/open-interest/crowding fact
coverage, freshness behavior, and Owner strategy semantics are confirmed.

---

## 8. Required Facts and Data Sources

Every StrategyImplementation must declare:

- required_facts;
- optional_facts;
- freshness_requirement;
- missing_fact_behavior;
- stale_fact_behavior.

Strategies must consume a normalized StrategyEvaluationContext / market-fact
snapshot, not call exchange gateways directly from domain logic.

Historical PG OHLCV, cached facts, and exchange-gateway read-only facts may all
feed the strategy context, but the context must preserve:

- source;
- observed_at / as_of time;
- freshness;
- symbol;
- timeframe;
- whether the fact is trusted, missing, stale, or observation-only.

Missing facts must resolve explicitly to `NO_ACTION`, `OBSERVE_ONLY`,
`BLOCK_MISSING_FACTS`, or `BLOCK_STALE_DATA`. The system must not infer missing
price, volume, funding, open-interest, account, position, or runtime facts to
allow execution.

Adding tables, downloading data, or expanding fact models is allowed when it
unblocks strategy semantics or reviewability, but new fact types must enter
through the same RequiredFacts / freshness / missing-behavior path.

---

## 9. Attempt, Budget, and Conflict Defaults

Default execution-semantics assumptions until superseded by a newer Owner
decision:

- The target mode is runtime-bounded automatic attempts after runtime/profile
  confirmation, not Owner-confirm-each-entry.
- A preflight-blocked candidate does not consume an attempt.
- A submitted order that receives any fill, including partial fill, consumes
  one attempt quota.
- Partial fills count against the same per-attempt budget and must not create a
  second free attempt.
- Budget reservation should prefer concrete max-loss evidence. Notional may be
  used only as a conservative fallback when loss-budget evidence is absent.
- Same-symbol/time opposite-side candidates must not both enter runtime
  planning. Opposite-side conflict blocks or requires explicit arbitration.
- Same-side candidates should be ranked by quality/evidence and should not
  create duplicate uncontrolled exposure.

---

## 10. Agent Implementation Rules

Before real OrderLifecycle adapter work or controlled runtime submit, agents
must preserve strategy semantics:

- Do not wrap OrderCandidate as a fake legacy SignalResult.
- Do not hide BRC runtime source context inside legacy strategy fields.
- Do not hard-code strategy behavior in execution adapters.
- Do not tune thresholds or optimize returns during architecture wiring unless
  the task explicitly authorizes strategy research.
- Do not add strategy-specific risk bypasses.
- Keep domain strategy logic pure and framework-free.
- Store strategy-specific semantics in typed models, registries, evaluators, or
  configuration objects that can be extended.
- Add review evidence for MFE, MAE, R multiple, tail win size, small-loss count,
  winner hold time, runner behavior, stop effectiveness, and attempt value.

If an implementation needs a new fact model, table, strategy variant, or exit
policy, document the semantic reason first, then implement the smallest
extensible slice that keeps future strategies from being forced into the same
shape.
