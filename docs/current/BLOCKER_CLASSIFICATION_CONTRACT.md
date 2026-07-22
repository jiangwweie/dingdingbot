---
title: BLOCKER_CLASSIFICATION_CONTRACT
status: CURRENT
last_verified: 2026-07-22
---

# Blocker Classification Contract

## Rule

Report the earliest exact state that prevents the next chain transition. A
healthy lane is `waiting_for_opportunity` only after every non-market condition
passes.

## Classes

| Blocker | Meaning | Normal owner action |
| --- | --- | --- |
| `observation_unavailable` | Strategy signal source or required market input is unavailable | None |
| `signal_absent` | Observation is healthy and no fresh eligible signal exists | None |
| `signal_invalid_or_stale` | Signal identity, version, facts, or deadline is invalid | None |
| `scope_or_policy_mismatch` | Current strategy, account, instrument, side, profile, or policy does not authorize the signal | Scoped policy only when required |
| `account_mode_invalid` | Account does not expose independent long/short position sides | Intervention |
| `entry_lane_busy` | Another new ENTRY owns the global lane | None; process serially |
| `netting_domain_occupied` | The same Netting Domain already owns exposure, Ticket, order, or hold | None unless recovery fails |
| `budget_exhausted` | Current policy capacity cannot reserve the Ticket | Policy only when expansion is intended |
| `protection_unavailable` | A valid Initial Stop plan or accepted protection is missing | Intervention if recovery cannot close |
| `command_outcome_unknown` | Venue outcome cannot be proven and command must not be resent | Intervention if reconciliation cannot resolve |
| `runtime_incident_open` | Partial fill, orphan, mismatch, or other abnormal state is unresolved | Intervention only when requested |
| `schema_identity_mismatch` | Deployed code, schema, or seed identity differs | None; disable writes and repair |
| `hard_safety_stop` | Any official invariant would be bypassed | Intervention |

## Valid Waiting State

`signal_absent` may map to Owner state `waiting_for_opportunity` only when:

- StrategyGroup and event version are current;
- runtime scope and Owner policy are enabled;
- account, venue, instrument, side, and position mode match;
- facts and instrument rules are current;
- global runtime capability and schema identity are certified;
- no unresolved incident or unknown outcome exists;
- a future fresh signal can proceed directly to serialized Ticket issuance.

Generated reports and historical replay cannot satisfy this checklist or grant
exchange-write authority.
