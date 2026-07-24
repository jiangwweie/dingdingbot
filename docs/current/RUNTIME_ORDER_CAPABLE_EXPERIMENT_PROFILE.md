---
title: RUNTIME_ORDER_CAPABLE_EXPERIMENT_PROFILE
status: CURRENT
last_verified: 2026-07-24
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
Those values are seeded from the current approved policy and must not be
invented or expanded during cutover.

The approved profile seed is three concurrent Tickets, `0.03` planned stop-risk
fraction, `0.90` maximum initial-margin utilization, maximum leverage `10`, and
`cross` margin mode. Supported exchange instruments use fixed `5x`; the kernel
freezes and revalidates that account fact and does not submit leverage changes.
Remaining executable margin is allocated by the current Ticket's validated
demand, not divided equally across unused Ticket slots. The
`new_entry_submit_enabled` setting controls only new ENTRY; it never removes
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
