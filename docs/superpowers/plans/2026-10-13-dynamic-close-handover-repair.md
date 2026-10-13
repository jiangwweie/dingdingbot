# Dynamic close handover repair

## Goal

Complete the existing Owner-authorized first Generic Dynamic transition without
letting old Static Observation consume its selected members' due close while
the global warming slot is queued. Keep the real recovery rebase observable
before opening a new switching Vacuum.

## Production evidence

- CPM activated at 13:06 on 2026-10-13 Beijing time.
- MPG, MI and BRF2 first targets reached STAGED but activation repeatedly returned
  `GENERIC_CURRENT_CLOSE_ALREADY_CONSUMED`, then the fixed30-minute deadline
  expired. Later MI also waited on `GENERIC_RECOVERY_REBASE_PENDING` after the
  new Vacuum had already blocked the old recovery observations.
- The original Snapshot/epoch/Owner proof survived; this is a scheduling and
  formal-close-consumption problem, not another source parsing failure.

## Implementation boundary

- Active Static Observation defers only selected members' latest close when an
  exact same-epoch, precommitted, already-effective, unexpired READY Snapshot
  owns an unfinished or not-yet-created handover. Warming, existing born Signals,
  failed/expired sources and unrelated members remain on their existing paths.
- This is a negative observation coordination result, not an Entry grant or a
  cursor write. The resident retries the same current close after the handover;
  no fake historical input, duplicate Episode or rewritten Signal is permitted.
- An unarmed real recovery is allowed to observe its future NOT_TRIGGERED close;
  the next switching Generation remains unfenced DESIRED until rebase is ARMED.
- DESIRED must prove the latest close unconsumed before taking the global warming
  slot or opening Vacuum. A consumed close waits unfenced for the next eligible
  period/supersession. Source expiry and the30-minute materialization deadline
  are unchanged.

## Verification

- Test-first handover and resident retry cases.
- Four-family PostgreSQL test drives old Static Observation before the actual
  first activation and proves no old data fetch or formal cursor consumption.
- PostgreSQL negative gates prove rebase/consumed-close waiting creates no Vacuum
  and no Exchange Command and preserves original Owner intent.
- Existing pause/recovery/queue regressions, architecture, Ruff and Mypy.
- Freeze exact candidate, run required R3 portfolio once; use the normal stopped,
  flat same-schema deployment and formal Entry promoter. No long resource audit.

## Safety and acceptance

No schema change, risk/capital/leverage expansion, SQL repair, forged ARMED,
consumed-close reuse or timeout extension. Production activation is not PASS
until current Universe and Authority prove the real transition.
