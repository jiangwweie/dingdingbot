# Strategy Research P0 / P1 / P2 Goal Mode Plan

Status: ACTIVE_GOAL_MODE_PLAN
Last updated: 2026-06-16

## Scope

This file turns the current strategy research line into a continuously
executable goal-mode queue.

The strategy research window owns semantic research, StrategyGroup handoff
shape, RequiredFacts proposals, reproducible evidence, negative evidence,
revival conditions, and strategy-cabinet updates.

The strategy research window does not own runtime admission, FinalGate,
Operation Layer, deploy, exchange writes, credentials, live profile, or order
sizing defaults.

## Goal Mode Objective

Continue expanding and hardening the small-capital, regime-specific,
right-tail strategy pool without requiring every strategy to be stable across
all months, symbols, and regimes.

The target output is not a return promise. The target output is a set of
auditable candidates that main control can review as:

1. selectable strategy semantics;
2. observable signal rules;
3. RequiredFacts and freshness expectations;
4. risk and leverage boundaries as research proposals;
5. hard stops;
6. sample signal, no-signal, stale, and conflict packets;
7. negative evidence and revival conditions.

## Priority Model

| Priority | Name | Purpose | Primary Output |
| --- | --- | --- | --- |
| P0 | Handoff hardening | Improve the 5 existing handoff-ready StrategyGroups without changing their execution boundary. | Gap matrix, RequiredFacts deltas, blocker-to-next-evidence mapping. |
| P1 | Next handoff conversion | Convert the most mature non-handoff candidates into observe-only or conditional handoff shape. | Candidate handoff draft, sample packets, admission recommendation. |
| P2 | Strategy pool expansion | Keep discovering, parking, reviving, and classifying additional right-tail semantics. | Cabinet updates, revival queues, negative evidence, next replay tasks. |

## P0 Lane

P0 covers the existing handoff pack set:

| StrategyGroup | Current Role | P0 Objective |
| --- | --- | --- |
| `MPG-001` | Core momentum-persistence handoff. | Tighten drawdown, late-cycle disable, member attribution, and leverage-horizon interpretation. |
| `FBS-001` | Funding/crowding stress handoff. | Separate funding squeeze activation from missing derivatives facts and funding settlement timing. |
| `TEQ-001` | Equity-like momentum handoff. | Keep short-history TradFi evidence useful while making product availability, session, and margin blockers explicit. |
| `PMR-001` | Precious-metal observe-only overlay. | Clarify XAG-led role, target-pairing behavior, and when it may disable or support other candidates. |
| `SOR-001` | Session opening-range conditional handoff. | Narrow branch eligibility and protect against second-half decay and session/fill ambiguity. |

P0 success is not measured by promotion. It is measured by whether main control
can consume the StrategyGroup without guessing why it is armed, observe-only,
conditional, blocked, or stale.

## P1 Lane

P1 converts the strongest non-handoff semantics into reviewable handoff drafts.

Current queue:

| Rank | Candidate | Current Cabinet Status | P1 Direction |
| ---: | --- | --- | --- |
| 1 | `VCB-001` | `next_handoff_candidate` | Draft as observe-only true-breakout classifier lane, not broad breakout promotion. |
| 2 | `RSR-001` | `observe_only_scorer` | Draft as TEQ support scorer or conditional scorer packet, not standalone execution group. |
| 3 | `NLPD-001` | `research_candidate` | Draft as low-history event-study observer with strict product and survivorship blockers. |
| 4 | `LCF-001` | `facts_pipeline_required` | Keep fact-pipeline design first; no handoff until force-order/OI/depth facts exist. |
| 5 | `MDS-001` | `overlay_candidate` | Keep as PMR-adjacent overlay until session and settlement semantics are clearer. |

P1 success means at least one candidate reaches a draft handoff shape with
explicit no-execution flags and sample packets, even if the recommendation is
observe-only.

## P2 Lane

P2 maintains the broader strategy pool and revival backlog.

Current P2 work types:

| Work Type | Meaning | Output |
| --- | --- | --- |
| Community semantic intake | Extract simple non-deep-learning strategy vocabulary from credible frameworks, docs, and code sources. | Source intake note and hypothesis ledger entry. |
| Replay candidate scan | Test fixed, closed-candle rules over 1h data without future facts. | Summary, raw CSV, negative evidence. |
| Right-tail window mining | Keep windows that are high payoff, interpretable, and bounded even if full-period alpha is weak. | Window table plus regime attribution. |
| Disable classifier mining | Convert failure periods into activation, disable, parking, or revival facts. | Classifier summary and RequiredFacts deltas. |
| Cabinet governance | Keep alive, parked, killed, and revived semantics visible. | Markdown and JSON cabinet updates. |

P2 success means the pool keeps widening without losing auditability.

## Execution Rhythm

1. Start with the cabinet and current handoff state.
2. Run or inspect existing evidence before inventing new semantics.
3. Convert return evidence into market-structure semantics, blockers, and
   RequiredFacts.
4. Preserve negative evidence.
5. Update the strategy cabinet when a candidate changes lifecycle status.
6. Add handoff drafts only when sample packets and no-execution flags are
   clear.
7. Validate JSON, handoffs, and focused tests before checkpointing.

## Non-Execution Boundary

All P0 / P1 / P2 outputs are research artifacts only. They do not authorize:

1. exchange writes;
2. deploy;
3. runtime admission;
4. FinalGate bypass;
5. Operation Layer bypass;
6. live profile changes;
7. credential mutation;
8. order-sizing default changes;
9. real orders.
