# 6aad77ea + Dual-Position Account Risk V0 Final Merge Plan

## Objective

Create one local, reviewable merge commit whose first parent is the currently
deployed release commit `6aad77ea4c67609ceed9b545d392de4ff1eaab3b` and whose
second parent is the dual-position account-risk commit
`5b67181e2d287fb306bae953075c89e2c6be32ab`.

The merge runs only in
`/Users/jiangwei/Documents/brc-merge-6aad77ea-dual-position-risk-v0`. It must not
modify the release worktree, the feature worktree, the prior integration
worktree, Tokyo runtime state, credentials, or exchange-write authority.

## Known Facts

- Tokyo currently identifies `6aad77ea` as its release head and migration `125`
  as its database head.
- `6aad77ea` contains seven lifecycle/deployment repairs after `ffc73899`.
- The feature branch head is `5b67181e`.
- The prior local merge `fd3550e0` certified the `ffc73899 + 5b67181e`
  integration, including the linear migration chain `121 -> ... -> 133`.
- The release delta after `ffc73899` overlaps feature work in lifecycle
  scheduling, post-submit reconciliation, and lifecycle scheduler tests.

## Merge Strategy

1. Prove the isolated worktree starts clean at `6aad77ea`.
2. Run the release-delta baseline tests before changing the tree.
3. Start `git merge --no-commit --no-ff 5b67181e` so Git records the required
   two-parent topology.
4. Reuse the already certified `fd3550e0` conflict resolution as a mechanical
   base, without using it as a merge parent.
5. Reapply the complete `ffc73899..6aad77ea` release delta and resolve only the
   genuine semantic overlaps.
6. Preserve both invariant sets:
   - release lifecycle recovery, TP1 idempotency/repricing, and activation truth;
   - account-level hard caps, reservations, exact instrument identity, exposure
     episodes, and fail-closed capacity checks.
7. Preserve release migrations `121..125`, renumber feature migrations to
   `126..133`, keep migration `086` byte-identical, and prove one Alembic head.

## Verification Gates

### Gate A: Structure

- no unmerged paths;
- `HEAD` before commit remains `6aad77ea`;
- `MERGE_HEAD` is exactly `5b67181e`;
- no tracked `output/**` artifacts or runtime lock files;
- source worktrees remain clean and unchanged.

### Gate B: Focused Regression

- lifecycle recovery and TP1 tests introduced after `ffc73899`;
- account-risk domain, policy, capacity, reservation, and reprojection tests;
- conflict-adjacent scheduler and post-submit reconciliation tests;
- dual-position release acceptance tests.

### Gate C: Database and Migrations

- migration identifier and graph tests;
- fresh upgrade through the repository's required authority bootstrap path
  (`base -> 106 -> foundation seed -> 133`);
- deployed-path upgrade `125 -> 133`;
- round trip `133 -> 125 -> 133`;
- PG causal-integrity and account-risk concurrency/full-chain/scale tests.

### Gate D: Repository and Release Readiness

- complete test suite;
- production runtime file-I/O audit;
- output artifact scope audit;
- release-preparation validation with deployed head `6aad77ea` and expected
  migration head `133`.

## Commit and Delivery Boundary

After every gate passes, create one local merge commit with message:

`merge: integrate dual-position account risk v0 onto 6aad77ea`

Do not push, deploy, mutate Tokyo, run real orders, expand live scope, or alter
credentials in this task. The resulting state is local merge certified, not
production deployed.

## Execution Record

- Release-delta baseline: `94 passed`.
- Combined lifecycle/account-risk focused regression: `121 passed` after one
  test-isolation update for the release-added execution-binding dependency.
- PostgreSQL runtime causal integrity: `14 passed`, zero skips.
- Explicit PostgreSQL account-risk concurrency/full-chain/scale: `6 passed`,
  zero skips.
- Migration paths passed: seeded fresh `-> 133`, release-like `125 -> 133`,
  and round trip `133 -> 125 -> 133`.
- Complete suite: `3564 passed, 7 skipped, 0 failed`; six opt-in PG skips were
  separately executed in the explicit zero-skip PG run, and the remaining skip
  is the intentional removed Trading Console legacy proxy case.
- Current-doc authority, output scope, diff whitespace, and production runtime
  file-I/O audits passed with zero suspicious runtime file authority and zero
  frequent report writes.
