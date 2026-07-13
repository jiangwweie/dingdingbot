---
title: P0_ACTION_TIME_FAILURE_CONSERVATION_AND_NATURAL_EVENT_ACCEPTANCE_DESIGN
status: CURRENT_IMPLEMENTATION_DESIGN
authority: docs/current/P0_ACTION_TIME_FAILURE_CONSERVATION_AND_NATURAL_EVENT_ACCEPTANCE_DESIGN.md
last_verified: 2026-07-13
---

# P0 Action-Time Failure Conservation And Natural-Event Acceptance

## Goal

Close the last non-market validation gap between a fresh eligible signal and the
real exchange-write boundary without creating exchange authority:

```text
natural live signal
-> Action-Time refresh sequence
-> exact PG process outcome and first blocker
-> Ticket / FinalGate / Operation Layer / Runtime Safety
-> protected submit preparation
-> durable exchange commands
-> STOP before gateway.place_order()
```

The same boundary is rehearsed against the five 2026-07-12 CPM Tickets that
expired after engineering latency and the separate ETH signal that did not
promote under the retired fixed-notional sizing path.

## Confirmed Historical Acceptance Set

| Source signal | Original Ticket | Symbol | Historical first failure | Current acceptance |
| --- | --- | --- | --- | --- |
| `signal:5bb26bea50c2f6a94503e7b265573bae` | `ticket:e0c3a9d496f79f64983e7efc1bac1528054f3a8aced4e32948f3293fd7a8896c` | `AVAXUSDT` | Operation Layer handoff timed out | durable exchange commands prepared without exchange write |
| `signal:3b3a9b3f2e47401c38f188701fcd4d66` | `ticket:999fe1c427c105bde3c1c8a2da833c6dc8294a3dcb5ad030de39db9f35972331` | `SUIUSDT` | FinalGate preflight timed out | durable exchange commands prepared without exchange write |
| `signal:24e6194f62ac955403b07a13edac46d5` | `ticket:24e323b0bfd6a9bb90f1dad96abac236471e5f584325c04ca35ffe0ca24df23d` | `SUIUSDT` | FinalGate preflight timed out | durable exchange commands prepared without exchange write |
| `signal:fe4b54bf2ea7328cc711831d11d303aa` | `ticket:9e41ab89baac01a830d5160b7ace230070356231e95ef8bb54128902c0512c54` | `SUIUSDT` | FinalGate preflight timed out | durable exchange commands prepared without exchange write |
| `signal:225cf22a6e943ab581d564ae4586f18d` | `ticket:3d7cda73572ec04d0c00d73a55e364518223e00b11306aac6e26f7c1eed487c8` | `ETHUSDT` | FinalGate preflight timed out | durable exchange commands prepared without exchange write |
| `signal:7dce92f66756ee63fa5612b45cee3ebb` | none | `ETHUSDT` | retired fixed-notional minimum sizing blocker | current dynamic sizing either prepares valid commands or preserves the exact legitimate sizing blocker |

Historical signal identity and fact observations are PG audit provenance. They
are represented as typed in-memory acceptance cases, never imported as fresh
live signals and never written back to production PG.

## Decision

### 1. Conserve the outer refresh result in PG

`run_server_product_state_refresh_sequence.py` must materialize one
`action_time_refresh_sequence` process outcome for each triggered Action-Time
run. The outcome records:

- exact lane scope when available;
- source signal, Ticket, lane, or handoff watermark;
- the first failed required step;
- the first technical blocker, including timeout identity;
- start/completion timestamps and total elapsed milliseconds;
- success after the same lane later reaches the pre-exchange boundary.

No-trigger watcher ticks write no acceptance outcome rows. A newer success for
the same process and lane replaces the unresolved failure through the existing
PG current outcome identity.

### 2. Preserve process failure over market-wait projection

Candidate Pool and Tokyo monitor must treat unresolved
`action_time_refresh_sequence` failures with a valid lane scope exactly like
unresolved Ticket-sequence engineering failures. They project
`action_time_boundary_not_reproduced`, not `market_wait_validated`.

Only a newer success for the same process and lane clears that specific
failure. Signal expiry alone cannot clear it.

### 3. Reuse the production chain for historical acceptance

Extend the existing full-chain simulation harness with a bounded pre-exchange
runner. It calls current production materializers in this order:

```text
fact/signal input
-> atomic promotion/lane/Ticket sequence
-> FinalGate preflight
-> Operation Layer handoff
-> Runtime Safety State
-> SubmitModeDecision
-> protected submit preparation
-> durable exchange commands
-> STOP
```

The runner does not record a mock exchange result and does not invoke an
exchange gateway. It returns the original PG lineage as provenance plus the new
isolated acceptance lineage.

## Failure Semantics

The first failed required stage is conserved as:

```text
<stage>_failed:<specific stdout blocker>
<stage>_timeout
<stage>_failed:<stderr tail>
```

Timeout and subprocess failures are engineering/runtime failures. They must not
be rewritten to `waiting_for_market`, `market_wait_validated`, or a generic
Ticket expiry.

## Cadence And Performance

| Surface | Cadence | Added work | Bound |
| --- | --- | --- | --- |
| No-signal watcher tick | recurring | none | zero PG acceptance rows; zero JSON/MD files |
| Triggered Action-Time refresh | natural event only | one bounded PG upsert after the sequence | existing 30-second sequence budget; outcome write is outside exchange authority |
| Historical acceptance | explicit local test/manual run | isolated DB rows only | six bounded cases; no production PG mutation |
| Archive/output | manual only | stdout/test evidence | no recurring files |

## Safety And Authority Boundary

This design does not:

- create a fresh live signal from replay;
- mutate production PG during historical acceptance;
- call `gateway.place_order()`;
- grant FinalGate or Operation Layer bypass;
- change StrategyGroup semantics, risk policy, leverage, sizing defaults, or
  live profile;
- create JSON/Markdown runtime authority.

## Acceptance

The task is complete when:

1. an Action-Time required-step timeout is persisted with exact stage and lane
   identity and continues to block false market-wait classification;
2. a newer successful run for the same lane clears that failure without
   deleting audit history outside the current projection;
3. all five historical Ticket cases reach durable prepared exchange commands
   under the current code within a fixed historical clock;
4. the sixth sizing-control signal produces current dynamic-sizing truth;
5. every historical case proves `exchange_write_called=false` and no gateway
   call;
6. production no-signal cadence creates no new acceptance rows or files.

## Chain Position

```text
chain_position: action_time_boundary
strategy_group_id: CPM-RO-001
symbol: AVAXUSDT, SUIUSDT, ETHUSDT
stage: production_refresh_failure_conservation_and_pre_exchange_acceptance
first_blocker: action_time_boundary_not_reproduced
evidence: five 2026-07-12 Tickets expired after outer refresh step timeouts; one ETH signal stopped at retired sizing logic
next_action: implement PG refresh outcome conservation and replay all six cases through durable exchange-command preparation
stop_condition: six cases are classified, five Ticket cases reach the pre-exchange boundary, and no exchange write occurs
owner_action_required: no
authority_boundary: replay and acceptance cannot create live signal, live authority, or exchange write
```
