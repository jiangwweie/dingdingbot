# Post-fill rule freshness repair

## Problem and evidence boundary

ENTRY persists action-time instrument rules with Tokyo's 30-second admission
validity. Reconciliation fetches fresh account/rule facts after the Initial Stop,
but its post-fill assessment previously rejected an expired persisted rule copy
before comparing it with the fresh rules. It then waited for the unrelated
background instrument-certification rotation. Production cases first waited
33–49 seconds after Ticket issuance; BCH, LTC and INJ passed on the next
post-fill assessment after their matching background rule refresh.

The expired-cache behavior was reproduced directly and through real PostgreSQL.
Historical failed-input snapshots were not retained, so this repair does not
assert that every historical unavailable-facts retry had the same cause.

## Change

Post-fill assessment now locks the exact persisted rule row, validates fresh
account/rule identity, maintenance-margin digest, notional coefficient and exact
position quantity/average price, then refreshes an expired matching copy using
those already-fetched facts. No network request occurs within the transaction.
The refresh grants no longer validity than the supplied facts. Missing cached
identity, contradictory rules, stale live facts and exposure mismatches remain
blocked. The row lock prevents an intervening certification change from being
overwritten after an unlocked comparison. The aggregate lock preserves exactly
one stress event and TP1 generation during duplicate/concurrent assessment.

This leaves ENTRY's short action-time lifetime unchanged and removes the
post-fill dependency on background rotation. No schema, strategy, capital,
Owner, ENTRY control or release identity change is included.

## Validation

- New real-PG expired-cache/matching and expired-cache/contradictory cases failed
  with the old implementation, as expected.
- A real-PG concurrent rule-update case exposed the unlocked refresh race and
  passed after exact-row locking.
- Five added cases cover matching freshness, contradictory freshness, stale
  live rules, duplicate assessment and a concurrent certification change.
- The final targeted post-fill file passes 12 cases. Formal targeted Mypy
  (`mypy src/trading_kernel scripts/trading_kernel`) passes 199 source files.
- Full Unit/Architecture, Full-chain and unknown-outcome reconciliation:
  1,799 passed in 141.76 seconds. Ruff and git diff whitespace checks pass.
  The final post-fill file was rerun after import cleanup: 12 passed.

These are local checks, not a production release certification. The Owner
requested commit/push only; no kernel deployment is part of this delivery.

## Research recovery (separate authorized operation)

The Owner explicitly authorized restoring observation on 2026-10-19. The
existing official research control was restored from disabled/version3 to
enabled/version4 at the unchanged shared limit50 per UTC day. No trading or
Selection control was changed. Historical expired samples are not repaired by
SQL or deadline extension; their official unavailable outcomes remain evidence.
A bounded follow-up distinguishes protected automatic transient retries from
serious faults rather than disabling research for every transient Incident.
