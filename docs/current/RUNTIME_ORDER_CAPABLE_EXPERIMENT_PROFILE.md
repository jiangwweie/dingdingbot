---
title: RUNTIME_ORDER_CAPABLE_EXPERIMENT_PROFILE
status: CURRENT
last_verified: 2026-07-22
---

# Runtime Order-Capable Experiment Profile

## Current Boundary

The Tokyo account is a live, small-capital experimental account. Allocated
capital is loss-capable experiment capital. The system must not silently reduce
approved size, leverage, or opportunity capture because a valid trade is risky.

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

The current approved seed is three concurrent Tickets, `0.03` planned stop-risk
fraction, `0.90` maximum initial-margin utilization, maximum leverage `10`, and
`cross` margin mode. The supported exchange instruments are configured at
fixed `5x`; the kernel freezes and revalidates that account fact and does not
submit leverage changes. Remaining executable margin is allocated by the
current Ticket's validated demand, not divided equally across unused Ticket
slots. The `new_entry_submit_enabled` setting controls only new ENTRY; it never
removes protection, controlled flatten, reconciliation, Settlement, or Review
authority from existing exchange exposure.

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
