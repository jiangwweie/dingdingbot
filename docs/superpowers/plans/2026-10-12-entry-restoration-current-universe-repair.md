---
title: ENTRY_RESTORATION_CURRENT_UNIVERSE_REPAIR
status: RELEASE_CERTIFICATION_PENDING
implementation_authority: CODE_TEST_AND_AUTHORIZED_SOFTWARE_DEPLOYMENT
production_modified: NO
---

# Entry Restoration Current-Universe Repair

## Owner scope

Owner requested implementation and verification of the restoration defect.
Owner subsequently explicitly authorized complete server repair and execution.
This includes a certified same-Schema release, not a Policy/TOTP bypass,
automatic Dynamic activation, SOR resume or exchange write.

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
The regular-deployment wrapper is now aligned with current member evidence:
no automatic Entry enable, no Batch refresh/write, stop every Writer including
Owner API, repeat fresh-flat/source identity after stop, preserve current
Universe/Selection history and Policy/strategy/selection-control posture,
and poll only Reconciliation-owned current certification after startup. Unknown
identity-write outcomes keep old Writers stopped. Unit RED/GREEN and an actual
22-member Docker PG identity-rotation/preservation rehearsal cover this path.
Do not bypass the exact release certification or claim local code is installed.

The first frozen-candidate preflight exposed that an all-member serial readonly
probe could outlive its default five-second single-instrument fact TTL. Its
certification was interrupted before completion, not claimed PASS. Maintenance
callers now explicitly request the existing probe's bounded 30-second audit
window and still reject stale/future observation and expired rule evidence.
No Entry admission/dispatch action-fact TTL or trading parameter changed.

Owner explicitly authorized complete Tokyo software repair. The current
execution sequence freezes one clean R3 candidate, runs the complete Kernel
portfolio once, stages its exact archive, stops the Owner API and all Kernel
Writers, repeats fresh PostgreSQL/Binance flat/identity facts, rotates the
same-Schema runtime identity through the existing boundary and checks preserved
Universe/history/control posture. No Alembic migration or capital expansion is
part of this release. After software postflight, the paused-policy preparation
mode may make Entry operationally ready without trading permission. Final
production commit/tag/results are recorded only in MAIN_CONTROL_ROADMAP.

After the certified repair is installed, the explicit paused-Policy preparation
mode may finish maintenance/start the Worker without granting trading authority;
its unchanged paused Policy/current basis is checked again after external I/O.
Then Owner performs Resume in the Console with TOTP, with no further server step.
Default positive promotion still requires the exact Owner Resume proof. The Owner never
needs to provide API secrets, modify SQL, reconstruct manifests or delete fences.
