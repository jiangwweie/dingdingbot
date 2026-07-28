# Task 13: Universe Failure-Recovery Full-chain Checkpoint

Date: 2026-07-29

Scope: local disposable PostgreSQL and recording fake venues only. No Tokyo,
production database, systemd service, or exchange write was invoked.

## Objective

Close the dedicated Universe failure-recovery acceptance evidence without
adding a second recovery path or weakening the existing Kernel authority.

## RED evidence

The new worker-crash full-chain test initially failed because its assertion
used the retired fixture table name `brc_signals`. PostgreSQL correctly
rejected that query: the canonical current table is `brc_signal_events`.
This was a test-authority mapping error, not a Kernel behavior defect. The
test was corrected to the current schema before GREEN verification.

## Covered recovery chains

1. **Authenticated readonly timeout**: a timeout becomes
   `temporarily_unavailable`, creates no Owner action, releases the claim, and
   is visible to readonly certification as a bounded count.
2. **Worker crash after claim**: two claimed warming instruments survive the
   simulated process loss; after lease expiry one is reclaimed by the real
   Reconciliation worker, authenticated outside the transaction, certified,
   and left with no Signal, Ticket, Command, or exchange-setting mutation.
3. **Monitor convergence**: the same deterministic leverage blocker is
   re-checked twice and produces one Monitor event/current projection; the
   later eligible read produces exactly the second resolution event and a
   `running` current projection.
4. **Activation/ENTRY race**: the real PostgreSQL global Entry-lane trigger
   rejects pointer mutation with SQLSTATE `55000` while dispatch has completed
   preflight but has not reached the recording venue. Dispatch then completes
   its single durable ENTRY normally; the pointer remains the original frozen
   Universe.
5. **Removed member lifecycle**: a runner-protected Ticket is created through
   the official lifecycle, the current pointer switches to a replacement
   Universe, then the old Ticket reaches `external_flat_incident` -> owned
   cleanup -> `matched` -> Settlement -> Review -> `terminal` through existing
   APIs. Its frozen Universe id remains the old id.

No test directly writes a Ticket, aggregate, settlement, or review terminal
state. All venue mutation is a recording fake.

## Verification

Focused dedicated failure file:

```text
python3 -m pytest -q tests/trading_kernel/full_chain/test_crypto_universe_failure_recovery.py
5 passed in 4.82s
```

Full-chain regression:

```text
python3 -m pytest -qq tests/trading_kernel/full_chain
38 collected; completed successfully
```

Focused supporting regression was also executed:

```text
python3 -m pytest -q \
  tests/trading_kernel/full_chain/test_ticket_lifecycle.py \
  tests/trading_kernel/integration/test_universe_certification_worker.py \
  tests/trading_kernel/integration/test_command_dispatch.py \
  tests/trading_kernel/integration/test_ticket_lifecycle_maintenance.py
46 collected; completed successfully
```

Static gates:

```text
/tmp/brc-p1-static/bin/ruff check --select E4,E7,E9,F,I,UP037 \
  tests/trading_kernel/full_chain/test_crypto_universe_failure_recovery.py \
  scripts/trading_kernel/certify_readonly.py
All checks passed!

python3 -m py_compile \
  tests/trading_kernel/full_chain/test_crypto_universe_failure_recovery.py \
  scripts/trading_kernel/certify_readonly.py

git diff --check
```

The final two commands completed successfully.
