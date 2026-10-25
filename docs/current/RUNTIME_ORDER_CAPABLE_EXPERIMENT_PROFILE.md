---
title: RUNTIME_ORDER_CAPABLE_EXPERIMENT_PROFILE
status: CURRENT
last_verified: 2026-10-12
---

# Runtime Order-Capable Experiment Profile

## Product Objective

BRC is a single-Owner, small-capital, loss-capable experiment for asymmetric
right-tail returns. It does not target stable yield, a smooth equity curve, or
preservation of every unit of experiment principal. It limits individual
stop-loss exposure, duplicate execution, unprotected exposure, unknown exchange
outcomes, and unauditable state while preserving the path for a small number of
large winners to cover a larger number of bounded small losses.

The Tokyo subaccount contains capital the Owner has already classified as
limited and loss-capable. Runtime controls therefore protect the approved
experiment boundary and prevent runaway loss; they must not silently convert
the system into a low-volatility asset-preservation product.

## Economic Semantics

- Stop-risk budget limits planned loss at invalidation.
- Leverage controls initial-margin use and does not enlarge stop-risk authority.
- A valid Runner may retain materially more upside than the initial loss budget.
- Fees, funding, slippage, liquidation distance, and path risk remain part of
  the downside envelope.
- Success or failure is evaluated from distributions and exact realized
  economics, not from one trade or a promised return.

## Required Profile Properties

```text
environment = live
position_mode = independent_sides
multi_position_capability = enabled
global_new_entry_lane = one
add_to_position = forbidden
entry_retry_after_rejection = forbidden
unknown_outcome_redispatch = forbidden
```

Multi-position capability is not guarded by a product toggle and is not limited
to two positions in the architecture. Current Owner budget policy may set a
finite `max_concurrent_tickets`, gross notional, risk, margin, or leverage cap.
Those values must come from the persisted policy applicable to the deployed
schema and must not be invented or expanded during cutover.

The approved Policy v4 contract is:

```text
max_concurrent_tickets = 3
max_same_strategy_side = 2
max_ticket_stop_risk_fraction = 0.02
max_gross_stop_risk_fraction = 0.06
max_ticket_initial_margin_fraction = 0.30
max_gross_initial_margin_utilization = 0.90
min_materialization_ratio = 0.50
directional_stop_risk_limit_fraction = 0.04
max_leverage = 10
supported_margin_mode = cross
```

This stable contract does not own active Tokyo deployment status. Exact Policy,
schema, release identity, and measured runtime state remain owned solely by
`MAIN_CONTROL_ROADMAP.md` and must be refreshed from direct production evidence.

Supported exchange instruments use fixed `5x`; the kernel freezes and
revalidates that account fact and does not submit leverage changes. A Ticket
may target up to `0.02` planned stop risk only when it can materialize at least
`0.50` of that budget. Its `0.30` margin cap, the remaining `0.06` gross
stop-risk budget, the remaining `0.90` gross margin budget, the `0.04`
directional stop-risk budget, venue minimums, and current account facts bind.

Exposure Family is a Registry Event semantic and its limit is Owner Policy
authority: `long_continuation=2`, `opening_range=2`, and
`rally_failure_short=1` under Capacity B. A second same-strategy/side Ticket
requires a different Instrument, Episode and Signal, valid current ENTRY
authority/membership, and all normal admission gates. Existing Tickets outside
the next Universe retain lifecycle and continue occupying capacity.

Admission remains first eligible: no reserved strategy slot, forced
diversification, preemption or cross-strategy rank. The effective limit is the
most restrictive global, directional, Family, strategy-side, Netting Domain,
risk and margin gate. BRF2 therefore remains limited to one SHORT by its Family.
Crypto `SOR-001` remains retired/ENTRY-disabled; capability does not authorize it.
Policy A's single continuation slot is preserved only as immutable history.

The pre-v4 policy model lacked this contract's explicit Family,
directional-risk, and materialization boundaries. It is historical semantics,
not runtime compatibility authority. Current tracked code, PostgreSQL and
exchange facts remain the action-time authority for what production enforces;
exact deployed identity and measured state belong only to
`MAIN_CONTROL_ROADMAP.md`.

The `new_entry_submit_enabled` setting controls only new ENTRY; it never removes
protection, controlled flatten, reconciliation, Settlement, or Review authority
from existing exchange exposure.

## Owner Directional Risk V1 — approved target

Status: **implemented locally, not deployed or activated**. Owner Directional
Risk V1 adds a tightening-only Crypto direction overlay to the base Policy
above. This section owns its approved initial numerical matrix:

| Owner view | LONG planned stop-risk ceiling | SHORT planned stop-risk ceiling |
| --- | --- | --- |
| bullish | 0.04 | 0.02 |
| neutral | 0.04 | 0.04 |
| bearish | 0.02 | 0.04 |

These fractions use action-time `total_wallet_balance`. The effective ceiling
is the minimum of current base Policy and the selected overlay. The matrix
does not change base single-Ticket/gross risk, materialization, leverage,
margin, Family, strategy-side, or Ticket-count limits. It is not a target
allocation, an instruction to fill capacity, or a guaranteed loss bound.

Scope is the explicitly Owner-authorized Crypto Events of CPM-RO-001, MPG-001,
MI-001, BRF2-001 and SOR-1H-001 on the exact account/venue. No special MPG pause,
new Event side, retired SOR-001 permission, or direct TradFi control is added.
The existing account-wide same-side nonterminal Ticket initial-risk sum still
counts when evaluating a scoped Crypto candidate; there is no new funds pool.
Existing exposure above a newly tightened ceiling remains protected and blocks
additional scoped risk until capacity is available. Pending Tickets count;
floating profit and moved stops do not create extra risk budget.

Explicit initial `unset` adds no overlay but is distinct from Owner-selected
neutral. **Missing or unreadable control is not neutral** and blocks affected
new ENTRY without removing existing-Ticket safety authority. Installation must
not invent an Owner selection or resume trading. Changes persist until another
authenticated Owner choice; the 24-hour reminder never resets the choice.

Product rationale, transition protocol and implementation gates are in the
[approved design](../superpowers/specs/2026-10-25-owner-directional-risk-v1-design.md).
The numbers are an approved experiment starting point, not an empirically
optimal parameter claim. Current activation requires formal runtime evidence
owned by `MAIN_CONTROL_ROADMAP.md`.

The local implementation stores immutable rule/scope facts, Owner request
events, current controls, Signal admission evidence and exact ENTRY send
authorizations in PostgreSQL. An ENTRY freezes a bounded Binance signing
window; a delayed sender cannot refresh its authorization timestamp. Exact
visible acceptance proceeds to protection immediately. Unknown absence and
pending control completion require proof that the old signing window has
closed; local lease expiry alone is insufficient. Installation starts with
explicit `unset` and does not change the Owner's trading controls.

## Real-Order Permission

Exchange-command capability may be enabled only after:

- exact deployed commit and schema baseline match;
- registry, policy, instrument, account, and runtime scope seed identity match;
- exchange account mode is verified readonly;
- positions, orders, protection, and unknown outcomes are clear at cutover;
- typed signal-to-Ticket certification passes;
- Initial Stop and controlled exit capability are certified.

This profile never authorizes withdrawal, transfer, credential mutation,
scope expansion, sizing-default expansion, or bypass of the official kernel.
