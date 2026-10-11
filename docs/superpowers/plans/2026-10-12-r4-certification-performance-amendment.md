---
title: R4_CERTIFICATION_PERFORMANCE_AMENDMENT
status: LOCAL_OPTIMIZATION_VERIFIED_PARTIAL
production_runtime_change: NONE
deployment_candidate_change: NONE
---

# R4 Certification Performance Amendment

## Owner scope

Owner requested an evidence-backed investigation and optimization of long R4
certification while continuing the authorized deployment to completion.
Optimization is isolated from the clean candidate already undergoing R4.
It must not restart that certification, weaken coverage, change trading code,
make a second runtime chain, or turn failed/incomplete evidence into PASS.

## Measured findings

- Integration contains 1,622 cases; Generic Selection contains 901 of them.
- One original Generic fixture executes 642 SQL statements: seed 326 / four
  Spec installation 316. Measured seed + installation cost is about 0.54s,
  plus clone 0.132s and drop 0.096s on the current Docker PostgreSQL host.
- Repeating only the 0.54s immutable setup across 901 cases accounts for about
  eight minutes by extrapolation, not the entire 82m54s prior Integration run.
- R4 reruns seven migration test files already covered by full Integration.
- The certifier buffers each entire command and emits no per-test progress.

## Implemented boundaries

1. A test-only initialized template uses the original seed and typed Spec
   installer. Each test still clones and drops its own independent database.
   Separate templates cover all-installed and each of four not-installed
   variants. Cache fingerprints cover production/migration source and fixture
   definitions; shared creation uses the existing cluster advisory lock.
2. Equality tests hash every current table, including target-only fields, and
   prove template/fresh setup equality and isolation after mutation.
3. R4 keeps complete Integration, Full-chain, Unit/Architecture, Ruff, Mypy,
   diff and Golden/Core parity. The redundant second migration invocation is
   removed, not the migration tests. Command-set drift still invalidates old
   manifests; the running candidate uses its original unchanged portfolio.
4. Command output is streamed before process completion. Failed commands retain
   only the last 8,000 characters; termination cleans up their exact subprocess.
   Integration prints its slowest 30 test durations.

## Direct local evidence

- Streaming-before-exit, bounded failure tail and no repeated pytest targets:
  RED demonstrated, then GREEN.
- Five installation variants: complete current-table digest parity and
  per-database mutation isolation PASS.
- Unit/Architecture: 1,536 passed; Ruff/Mypy/diff PASS.
- Representative shared twelve cases: original 9.41s; optimized approximately
  4.6s after excluding the two added parity tests from the 14-case 7.41s run.
- Eight additional Owner pause/read-only cases: 2.51s PASS.

These are bounded samples, not full optimized Integration/R4 certification or
a proven 50% whole-suite speedup. No blind xdist/auto-parallelism, no removal of
wall-time worker/fault coverage and no server performance experiment is added.
The deployed software candidate remains separate; this local tooling change
must not invalidate or fabricate its certification while it is running.
