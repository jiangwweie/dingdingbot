# DIRA-HG-001 — Direction A Human-Gating Decision Process Draft

## 0. Boundary

This is a docs-only decision-process draft.

- No runtime control is authorized.
- No strategy change is authorized.
- No Direction A entry, exit, stop, sizing, or risk parameter change is authorized.
- No paper, testnet, live, small-live, or runtime activation is authorized.
- No LLM implementation is authorized.
- No automated decision-making is authorized.
- No backtest, adapter, or experiment was run for this draft.
- No Claude task card is created.
- No claim is made that Direction A is validated.

The purpose is to define how the Owner would rehearse manual ON/OFF judgment for Direction A before any future paper-admission discussion.

## 1. Current Evidence State

Direction A remains `REMAIN_WEAK_BEST_AVAILABLE / PAUSE_FRAGILE / NON_RUNTIME`.

Current evidence read:

- Direction A is the best-supported existing BTC/ETH execution-signal candidate, but the support is weak and fragile.
- Direction A is a 4h long-only Donchian20 breakout with EMA60 lifecycle exit.
- The EMA60 exit is currently classified as `PAYOFF_ENGINE`, not as an obvious defect. It preserves sparse multi-week payoff tails.
- False breakout and re-entry loss clusters are real. The loss profile is many failed breakouts while waiting for rare trend legs.
- 2022 and 2025 are broad negative periods for BTC+ETH, but loss clusters also occur inside positive years such as 2023 and 2024.
- Human-gated plausibility is `WEAK`, not `YES`.
- Bad periods are partly avoidable in theory, especially broad bear/chop regimes, but not trivially avoidable ex ante.
- A naive algorithmic daily EMA250 gate was not sufficient as a replacement for human judgment because it reduced 2022/2025 damage while also damaging sparse payoff tails.
- CPM-1 is parked as a weaker current candidate after bull-segment evidence failed to support reopening it as the mainline.

The central unresolved question is not "which exit should replace EMA60?"

The central unresolved question is:

> When would the Owner turn Direction A ON/OFF without damaging access to sparse payoff tails?

## 2. Human-Gating Objective

Human gating means the Owner manually decides whether Direction A is allowed to run.

The objective is not to predict every trade, avoid every loser, or manually approve each 4h signal. Direction A's historical profile expects many failed breakouts and a small number of large trend winners.

The objective is narrower:

- avoid obvious hostile regimes where Direction A is likely to keep paying re-entry cost without payoff tails;
- preserve access to multi-week trend winners when the market is in a plausible bull or recovery participation phase;
- prevent emotional ON/OFF decisions after pain, FOMO, or recent large wins;
- create a decision record that can later be audited against outcomes;
- test whether human judgment plus LLM briefing improves decision quality enough to justify further no-order or paper-process consideration.

Human gating must not become a post-hoc rationalization layer for weak signal evidence. If the Owner cannot write down why Direction A should be ON before the next signal, the default decision should be `WAIT` or `PAUSE_NEW_ENTRIES`.

## 3. ON Decision Checklist

Before turning Direction A ON, the Owner should review the following evidence. The review should be written before the decision is made.

Market phase:

- Is BTC/ETH in a plausible bull, recovery, or persistent uptrend participation phase?
- Is the market still in broad bear/chop where breakouts are likely to fail?
- Is the intended ON decision based on current structure, or only on the memory of prior bull-cycle returns?

BTC/ETH weekly and daily structure:

- Are weekly and daily closes showing constructive higher-timeframe structure?
- Are BTC and ETH confirming each other, or is one asset carrying the thesis alone?
- Is price reclaiming or holding important trend structure, or repeatedly failing near obvious resistance?

Recent trend strength:

- Are recent breakouts holding and extending, or immediately reverting?
- Is the market showing sustained directional participation rather than one-candle spikes?
- Are major trend legs still early/mid-cycle enough for a Donchian20 breakout system to participate?

Volatility context:

- Is volatility expanding with trend continuation, or expanding through disorderly two-sided liquidation?
- Are stop-outs and fast reversals increasing?
- Is volatility likely to improve payoff tails or only increase failed breakout cost?

Funding, leverage, and sentiment if available:

- Is funding extremely positive and crowded in the same direction as the intended long exposure?
- Are leverage and liquidation conditions hostile to new long breakouts?
- Is sentiment euphoric after an already extended move?

Major macro/news risk:

- Are there scheduled events that can invalidate trend participation quickly?
- Are there regulatory, exchange, macro, or liquidity events that make new entries unusually fragile?
- Is the Owner willing to keep Direction A ON through the event, or should the review wait?

Recent Direction A loss-cluster context:

- Have recent Direction A-like breakouts failed repeatedly?
- Is the current market similar to known false-breakout clusters from 2022, 2023 mid-year, 2024 post-winner chop, or 2025 churn?
- Is the Owner turning ON after the market already recovered from a pain point, or before the structure has repaired?

FOMO check:

- Is the ON decision driven by fear of missing a move after a large candle?
- Would the Owner still choose ON if the next three Direction A trades lose?
- Is the decision being made because the process says the environment is acceptable, or because recent price action feels urgent?

ON classifications:

| Classification | Meaning |
|---|---|
| `ON_ALLOWED` | Conditions are acceptable for normal Direction A observation/process rehearsal under the current approved scope. |
| `ON_ALLOWED_SMALL` | Conditions are constructive but fragile; only a smaller future paper/process posture could be considered if separately authorized. In this draft it is a label only, not sizing approval. |
| `WAIT` | Evidence is mixed, incomplete, event-risk-heavy, or emotionally contaminated. Re-review at a defined time. |
| `DO_NOT_TURN_ON` | Broad hostile regime, unresolved shock risk, obvious FOMO, or repeated failed-breakout context argues against activation. |

## 4. OFF / Reduce Decision Checklist

Before turning Direction A OFF or reducing exposure posture, the Owner should review whether the decision is risk-based or pain-based. The review should be written before the decision.

Broad bear/chop evidence:

- Are BTC and ETH both deteriorating on daily/weekly structure?
- Are breakouts repeatedly failing across both assets?
- Is the market losing trend participation and reverting to range/chop?

Repeated false-breakout clusters:

- Are recent Direction A-like entries failing quickly with shallow MFE and repeated stop/EMA exits?
- Is the failure pattern broad across BTC and ETH, or isolated to one asset?
- Is the loss cluster similar to 2022/2025 broad weakness or to known 2023/2024 in-bull chop clusters?

BTC/ETH structure deterioration:

- Are higher-timeframe supports failing?
- Is leadership narrowing or rotating away from BTC/ETH trend participation?
- Are recoveries weak and sold quickly?

Extreme funding / crowded trend:

- Is the long side extremely crowded after a large advance?
- Are funding, liquidation, or sentiment signals suggesting asymmetric downside risk?
- Is the market late-cycle euphoric rather than early/mid-cycle constructive?

Macro shock risk:

- Is there a near-term event that could make new breakouts unrepresentative?
- Is liquidity likely to deteriorate?
- Would the Owner still hold the ON decision if volatility spikes sharply?

Consecutive losses:

- Are losses clustered in a way that indicates hostile regime rather than normal low-win-rate behavior?
- Is the Owner reacting to a normal expected sequence of losses?
- Has the loss cluster occurred immediately before conditions that could produce a sparse winner?

Emotional pain check:

- Is the OFF decision being made immediately after a drawdown, stop-out streak, or embarrassing false breakout?
- Would the same decision have been made before the last losing trade?
- Is the Owner using OFF to stop discomfort rather than because market evidence changed?

Sparse-winner risk check:

- If Direction A is turned OFF now, what evidence will turn it back ON?
- Is that re-entry condition concrete enough to avoid missing the next multi-week trend winner?
- Is the Owner accepting that false breakout pain is the cost of maintaining access to payoff tails?

OFF classifications:

| Classification | Meaning |
|---|---|
| `KEEP_ON` | Hostile evidence is insufficient; loss pain is within expected Direction A behavior. |
| `REDUCE` | Conditions are deteriorating but not enough to fully disable the process. In this draft it is a decision label only, not sizing approval. |
| `PAUSE_NEW_ENTRIES` | No new Direction A entries should be allowed in the decision process until a defined review condition is met. Existing-position handling is not changed by this draft. |
| `TURN_OFF` | Broad hostile regime or shock risk is strong enough that Direction A should be considered inactive in the manual process. |

## 5. LLM Manual Briefing Role

The LLM supports Owner judgment. It does not make decisions.

Allowed LLM briefing functions:

- summarize BTC/ETH market structure, funding, leverage, sentiment, news, and macro context when available;
- compare current conditions against known Direction A failure modes;
- identify whether the Owner's intended decision appears FOMO-driven or pain-driven;
- argue against the Owner's intended decision as a structured counter-bias step;
- list the top risks of turning ON and the top risks of turning OFF;
- identify what evidence would change the decision;
- summarize prior decision-log outcomes for review.

Forbidden LLM functions:

- final ON/OFF decision-making;
- runtime commands;
- order submission;
- exchange/API interaction;
- automatic strategy enable/disable;
- parameter, entry, exit, or sizing changes;
- claims that Direction A is validated or live-ready.

The LLM briefing should always include a devil's-advocate section:

- If Owner intends `ON_ALLOWED`, argue why this may be late, crowded, or vulnerable to false breakouts.
- If Owner intends `TURN_OFF`, argue why this may be emotional after pain and may miss the next sparse winner.
- If Owner intends `WAIT`, argue what opportunity cost may be created.

The Owner must write the final decision in the log after reading the briefing.

## 6. Decision Log Format

Every ON/OFF/reduce decision should be logged manually.

Template:

```markdown
## Direction A Human-Gating Decision Log

- Decision ID:
- Date/time UTC:
- Reviewer:
- Proposed action:
- Current process state before decision:
- BTC structure:
- ETH structure:
- Current market phase:
- Recent Direction A-like signal / loss-cluster context:
- Funding / leverage / sentiment context:
- Macro / news risk:
- Owner thesis:
- LLM counterargument summary:
- Top 3 risks:
  1.
  2.
  3.
- Decision:
- Classification:
- Confidence 1-5:
- Invalidation condition:
- Re-entry or next-review condition:
- Review date/time UTC:
- Later outcome:
- Outcome review notes:
```

Required decision fields:

| Field | Purpose |
|---|---|
| Date/time UTC | Prevents hindsight editing and anchors context. |
| Proposed action | Records the Owner's initial impulse before counterargument. |
| Current market phase | Forces explicit regime read. |
| Owner thesis | States why Direction A should be ON/OFF now. |
| LLM counterargument summary | Records the anti-bias challenge. |
| Top 3 risks | Makes known risk explicit before action. |
| Decision | Final Owner choice. |
| Confidence 1-5 | Separates conviction from action. |
| Invalidation condition | Defines what would prove the decision wrong. |
| Review date | Prevents indefinite ON/OFF drift. |
| Later outcome | Enables process review without rewriting history. |

## 7. Known Failure Modes

Decision-process failures:

- turning off after a loss cluster and missing the next payoff tail;
- turning on due to FOMO after a trend is already extended;
- keeping Direction A ON because of sunk-cost bias after repeated failed breakouts;
- turning OFF because of emotional pain rather than changed market evidence;
- failing to define a concrete re-entry condition after `TURN_OFF` or `PAUSE_NEW_ENTRIES`;
- ignoring LLM warnings or counterarguments without writing why;
- letting LLM over-conservatism block every uncomfortable but necessary sparse-trend opportunity;
- treating LLM confidence as a decision rather than as briefing input;
- confusing paper/testnet/live readiness with process rehearsal;
- using human gating to rationalize weak signal evidence;
- allowing the Owner to reinterpret Direction A entry/exit rules while calling it "gating";
- reviewing only after losses and not after wins, creating asymmetric hindsight bias;
- failing to log decisions before outcomes are known;
- changing the meaning of `ON_ALLOWED_SMALL`, `REDUCE`, or `PAUSE_NEW_ENTRIES` into unapproved runtime sizing behavior.

A severe decision-process failure occurs if:

- a major ON/OFF decision has no pre-decision log;
- the Owner repeatedly overrides the checklist without written rationale;
- the process disables Direction A after pain but lacks a re-entry condition;
- the process turns Direction A ON after a large move without addressing FOMO;
- the LLM or any automated tool makes or executes the final decision;
- the decision process is used to claim Direction A validation.

## 8. Paper Admission Prerequisites

Paper trading is not approved by this draft.

Before any future paper-admission note can even be drafted, the following prerequisites should be satisfied:

- DIRA-HG-001 reviewed by Owner.
- Manual LLM briefing template tested for 2-4 weeks without runtime control.
- Decision logs created before decisions, not after outcomes.
- At least several ON/OFF/WAIT reviews completed across different market contexts.
- A1/A3 metric conflict resolved, including trade count and time-in-market definitions.
- Paper object chosen explicitly: baseline Direction A versus A1/A3 risk-shaped process. This draft does not choose.
- Decision log template accepted by Owner.
- Kill / pause conditions drafted separately as a docs-only note.
- Clear distinction maintained between process rehearsal, paper trading, testnet trading, and live trading.
- Owner accepts that human gating remains `WEAK` unless the logged decision process demonstrates useful discipline.

If these prerequisites are not met, the correct state remains docs-only review or no-order process rehearsal, not paper admission.

## 9. What This Does Not Authorize

This draft does not authorize:

- runtime control;
- human ON/OFF runtime implementation;
- LLM automation;
- LLM integration;
- paper trading;
- testnet trading;
- live trading;
- small-live execution;
- exchange/API activation;
- parameter changes;
- exit changes;
- entry changes;
- risk-profile changes;
- strategy validation;
- Direction A promotion;
- CPM reopening;
- SOL inclusion in the main decision path;
- short-side testing;
- Claude task cards.

Direction A remains weak-best-available, fragile, and non-runtime. This document only defines a manual decision-process draft for Owner review.

## 10. Risk Triage

Current review result:

| Item | Severity | Treatment |
|---|---:|---|
| Runtime / paper / testnet / live authorization risk | SUFFICIENT | Boundary explicitly denies authorization. No change required. |
| LLM overreach risk | SUFFICIENT | LLM is limited to manual briefing, counter-bias, and risk alert. Final decision remains Owner-only. |
| Direction A rule mutation risk | SUFFICIENT | Entry, exit, stop, sizing, risk profile, and parameters remain unchanged. |
| Emotional shutdown after losses | SUFFICIENT | OFF checklist includes emotional pain check and sparse-winner risk check. |
| FOMO-driven ON after large move | SUFFICIENT | ON checklist includes FOMO check and trend-extension review. |
| Tail-kill / over-gating risk | SUFFICIENT | Process requires explicit sparse-winner risk review before OFF / PAUSE decisions. |
| Decision reproducibility | SUFFICIENT | Manual decision-log template includes proposed action, thesis, counterargument, invalidation, review time, and later outcome. |
| Paper admission readiness | HIGH | Paper is not approved. Future paper note requires separate prerequisite review, A1/A3 conflict resolution, no-order rehearsal logs, and Owner decision. |
| Human-gating evidence strength | MODERATE | Human-gated plausibility remains WEAK. The process is only a rehearsal framework until logs show useful discipline. |
| Section completeness | HIGH | This Risk Triage section and Minimum Next Step section are required before treating DIRA-HG-001 as complete. |

No `BLOCKER` is identified.

DIRA-HG-001 is sufficient for the next docs-only step after this targeted section-completion edit.

No full re-inspect is required unless the document later adds runtime control, LLM implementation, strategy/risk/profile changes, paper/testnet/live authorization, or Claude execution scope.

## 11. Minimum Next Step

Minimum next step:

1. Owner reviews DIRA-HG-001 as a docs-only process draft.
2. If accepted, create one manual no-order decision-log entry using the template in Section 6.
3. Use LLM only to produce a manual briefing and devil's-advocate note.
4. Owner writes the final classification manually: `ON_ALLOWED`, `ON_ALLOWED_SMALL`, `WAIT`, `DO_NOT_TURN_ON`, `KEEP_ON`, `REDUCE`, `PAUSE_NEW_ENTRIES`, or `TURN_OFF`.
5. No runtime, paper, testnet, live, strategy, risk, profile, or parameter change follows from the log.

What not to do next:

- Do not create a Claude task card.
- Do not implement runtime ON/OFF control.
- Do not implement LLM automation.
- Do not run backtests, adapters, parameter sweeps, or mechanical filter searches.
- Do not reopen CPM-1.
- Do not rewrite Direction A exit logic.
- Do not treat this process draft as paper admission.
- Do not convert `ON_ALLOWED_SMALL` or `REDUCE` into actual sizing without a separate Owner-approved paper/risk specification.

The next valid artifact, if Owner wants to continue, is a single no-order manual rehearsal log, not implementation.
