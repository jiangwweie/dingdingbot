---
title: ENTRY_RESTORATION_CURRENT_UNIVERSE_REPAIR
status: LOCAL_IMPLEMENTATION_VERIFIED
implementation_authority: CODE_AND_TEST_ONLY
production_modified: NO
---

# Entry Restoration Current-Universe Repair

## Owner scope

Owner requested implementation and verification of the restoration defect.
This task does not install a new release, change Policy, remove the production
Fence, activate Dynamic, resume retired SOR or write to the exchange.

## Root cause and boundary

The operational promoter relied on initial fixed 15-symbol Bootstrap counts and
historical Certification Batches even though a legitimate current Universe had
22 symbols. It could also arm Policy itself. The repair keeps the same promoter
and readonly certification path but replaces those inputs with a typed readonly
current-state projection under `src/trading_kernel/infrastructure`.

PostgreSQL current pointers / exact member certifications and the exact current
Policy's Owner Resume / TOTP authorization own the evidence. No new table,
migration, persisted authority, worker, config file or second trading chain is
added. Financial risk defaults, strategy logic, Dynamic modes, capacity and
existing Ticket lifecycle are unchanged.

## Observable invariants

1. Paused Policy cannot be armed by this operational tool.
2. Current member cardinality is derived, not fixed. The external probe and
   rule rows must match every current member once; no supplied subset exists.
3. Wrong account/mode/leverage, absent/expired/future certification, missing
   rules, unresolved incidents/activity, wrong Runtime Capability and missing
   Owner proof cannot remove the Fence.
4. Scope, Universe/version/digest, Policy, Strategy Control, runtime or Resume
   identity drift between preflight/postflight invalidates the whole attempt.
5. Certification validity is checked again after the external probe; expiry
   during I/O rejects restoration and keeps the Fence.
6. Starting a service never changes Policy; failure after startup refences and
   stops it. Completed promotion still rechecks external and service facts.
7. Existing Ticket gates remain final authority. No trade is submitted in
   local/readonly verification, and SOR remains paused.

## Verification evidence

- Unit RED identified fixed-count failure, unsafe auto-arm, omitted current
  Owner proof, idempotence bypass and postflight drift. GREEN follows each fix.
- PostgreSQL RED loaded the original deployed readonly certifier against the
  exact same 22-member fixture and failed on absent current recovery evidence.
- Real Docker PG creates the baseline through Bootstrap, then changes CPM's
  current Universe via the actual install/warm/activate path. The live union is
  22 members while the old batch/Bootstrap flag is false. Official application
  Owner Resume and the operational promoter recover without any exchange write.
- PG negative cases cover expired/future facts, mode/leverage/rule gaps,
  transient unavailability, wrong Capability identity, weak auth, wrong Owner
  scope and authorization/event time mismatch.
- A pure readonly execution of the candidate query on Tokyo confirmed current
  22-member readiness true and Owner Resume proof false. It performed no DML,
  installation, Policy mutation or Fence removal. This is supplementary source
  verification, not production release certification or trading authorization.
- Complete Unit/Architecture: 1,567 PASS; complete Full-chain: 54 PASS.
  Final restoration PG / full-chain slice: 13 PASS, including 11 distinct
  22-member/proof/fact cases. Additional Bootstrap/schema/Capacity/Owner slice:
  46 PASS. Final promotion/architecture focused rerun: 39 PASS.
  Ruff, Mypy (193 source files) and diff PASS.

## Release boundary / remaining work

This repair is local, not deployed. It requires an exact clean candidate's
same-schema Kernel release certification before installation. A whole-suite
Release manifest is not claimed from targeted/Full-chain evidence.
The existing regular-deployment wrapper also retains fixed Static Batch/count
assumptions; its actual-current stopped-flat release path must be reconciled and
verified before using that wrapper to install this repair. Do not bypass it or
pretend this local fix is already usable in production.

After the certified repair is installed, Owner performs Resume in the Console
with TOTP; then the operational promoter verifies and unfences. The Owner never
needs to provide API secrets, modify SQL, reconstruct manifests or delete fences.
