---
title: RUNTIME_ORDER_CAPABLE_EXPERIMENT_PROFILE
status: CURRENT
last_verified: 2026-07-31
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

The approved post-`0003` Policy v4 target contract is:

```text
max_concurrent_tickets = 3
max_ticket_stop_risk_fraction = 0.02
max_gross_stop_risk_fraction = 0.06
max_ticket_initial_margin_fraction = 0.30
max_gross_initial_margin_utilization = 0.90
min_materialization_ratio = 0.50
directional_stop_risk_limit_fraction = 0.04
max_leverage = 10
supported_margin_mode = cross
```

This is a release target, not a claim about the active Tokyo deployment. The
currently deployed Policy v3, schema identity, release identity, and measured
runtime state remain owned solely by `MAIN_CONTROL_ROADMAP.md` until the
post-`0003` release completes and that roadmap is refreshed from direct
production evidence.

Supported exchange instruments use fixed `5x`; the kernel freezes and
revalidates that account fact and does not submit leverage changes. A Ticket
may target up to `0.02` planned stop risk only when it can materialize at least
`0.50` of that budget. Its `0.30` margin cap, the remaining `0.06` gross
stop-risk budget, the remaining `0.90` gross margin budget, the `0.04`
directional stop-risk budget, venue minimums, and current account facts bind.

Exposure Family is a Registry Event semantic and its limit is Owner Policy
authority: `long_continuation=1`, `opening_range=2`, and
`rally_failure_short=1`. StrategyGroup capacity, symbol, and side strings are
not current admission authority.

The pre-v4 policy model lacks the target contract's explicit Family,
directional-risk, and materialization boundaries. It remains current only where
the deployed production identity still says Policy v3. Current tracked code,
PostgreSQL and exchange facts remain the action-time authority for what
production enforces; exact deployed identity and measured state belong only to
`MAIN_CONTROL_ROADMAP.md`.

The `new_entry_submit_enabled` setting controls only new ENTRY; it never removes
protection, controlled flatten, reconciliation, Settlement, or Review authority
from existing exchange exposure.

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
