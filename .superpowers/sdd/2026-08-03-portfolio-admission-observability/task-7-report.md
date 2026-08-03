## Task 7 Report — Exact 0002 to 0003 Deployment Path

### Scope and safety boundary

- Implemented the exact **`0002_sor_v3_strategy_group_capacity -> 0003_portfolio_admission_observability`** stopped, flat, forward-only deployment path.
- Successful compatible deployment starts only **Observation, Lifecycle, and Reconciliation**, runs the formal full six-Universe bootstrap, and leaves Entry inactive, disabled, and write-fenced.
- No Tokyo deployment, production database mutation, Entry enablement, exchange write, credential mutation, withdrawal, transfer, or scope expansion was performed.

### Review-fix behavior

1. **Exact source certification before service mutation**
   - Verifies the literal certified 0002 Registry manifest directly from active PostgreSQL Registry rows.
   - Requires exact Policy v3 with **`new_entry_submit_enabled=false`**, exact `tiny-live-v1` runtime profile, exact observation-only capabilities, independent position sides, cross margin mode, DB commit/schema/seed identity, and matching source release commit/schema/seed markers.
   - Registry, Policy, profile, capability, account-mode, or release-marker drift blocks before the first fence/stop operation.
   - Source identity sets are literal or derived from current Registry contracts; source authority is no longer derived from the target migration's vNext event list.

2. **Exact six-Universe activation**
   - Removed `--prepare-certification-batch-only` from the deployment backend.
   - Target activation is followed by safety-worker startup, formal full bootstrap, and readonly postflight.
   - Success requires six exact vNext current Active Universes, seven canonical members each, zero Warming Universes/scopes, canonical live Universe digests, a completed exact Certification Batch, and retired source generations.
   - A single Warming Universe is no longer an accepted deployment endpoint.

3. **Live semantic recomputation**
   - Readonly certification builds a canonical expected Registry manifest and independently hashes live active rows from StrategyGroup, StrategyVersion, EventSpec, FactDefinition, EventFact, and ExitPolicy tables.
   - Metadata `registry_semantic_hash` must match the committed Registry hash, and the live Registry manifest hash must independently match the expected live hash.
   - Certification Batch identity is recomputed from the actual ordered member rows; stored digest, live digest, exact seven-member set, member count, eligibility count, target identity, Policy, and completion state must all agree.
   - Controlled integration drift tests prove one Registry-row mutation and one equal-count batch-member substitution both fail certification.

4. **Database-bound preservation proof**
   - After exact preservation verification, PostgreSQL records source revision, target revision, preservation digest, immutable database identity, and proof digest in `brc_schema_metadata`.
   - Database identity is **PostgreSQL system identifier + current database OID**.
   - The release-local verified marker stores the PostgreSQL proof digest, not the source manifest digest.
   - Resume requires both the filesystem marker and the current database proof to match; a marker bound to another/restored database is terminally rejected rather than rebound.
   - Proof metadata is excluded from the projected 0002 preservation manifest because it is a 0003-only verification object.

5. **Fix-forward failure posture**
   - Explicit `target_activated` and `target_safety_started` states separate pre-target and post-target recovery.
   - Failure before a successful `0003` migration keeps Entry fenced and does not start target services.
   - Once `0003` exists, preservation or identity failure activates the target release with the last known Seed identity, so target workers rely on the Runtime Fence until target identity is certified.
   - Partial activation recovery reads the actual current-release symlink instead of trusting an in-process flag, then restores the three target safety workers while Entry remains inactive, disabled, and fenced.
   - Schema downgrade, 0002 worker restart on 0003, dual write, old-schema reader, and runtime fallback remain forbidden.

### RED / GREEN evidence

| Gate | RED evidence | GREEN evidence |
| --- | --- | --- |
| Full bootstrap and source pre-service gates | Focused command collected **4**, with **4 failed**: prepare-only flag remained and Registry/Policy/seed-marker drift did not block | Same focused command: **4 passed** |
| Failure posture and database proof reuse | Focused command collected **3**, with **2 failed / 1 passed**: pre-0003 failure restarted services and different-DB marker was rebound | Same focused command: **3 passed** |
| Live Registry drift | Metadata remained correct while a live EventSpec row changed; certification lacked `live_semantic_hash` and failed the new contract | Target integration test passes and returns live/expected hashes with `status=fail` after drift |
| PostgreSQL-bound proof | Integration test failed because record/verify proof functions did not exist | Record, verify, and restored-identity mismatch test passes |
| Batch member replacement | Mutation check removed live member checks and the regression test failed with `certification_batch_pass=True` | Restored live digest/member checks; focused test **1 passed** |

### Round 2 review-fix evidence

| Gate | RED evidence | GREEN evidence |
| --- | --- | --- |
| Post-migration preservation failure | Focused command collected **2**, with **2 failed**; no target activation was attempted after successful migration | Target release is activated with the last known Seed identity, all three safety workers start, and Entry remains inactive, disabled, and fenced |
| Partial target activation | The same RED command failed because the symlink had changed but `target_activated` remained false, so no safety worker restarted | Recovery rereads the current-release symlink and restores the target safety workers without starting Entry |

Fresh Round 2 verification: amended deployment unit plus compatible-upgrade integration **56 passed in 16.45s**; Ruff passed; Mypy reported **116 source files** clean; `git diff --check` passed.

### Fresh final verification

| Gate | Result |
| --- | --- |
| Task 7 deployment, source exactness, live drift, DB proof, 0003 migration, architecture, Universe bootstrap, Entry promotion, and runtime seed regression | **112 passed in 81.34s** |
| Direct cutover state-machine and production-adapter regression | **60 passed in 3.16s** |
| Fresh non-overlapping total | **172 passed, 0 failed** |
| Focused batch mutation restoration | **1 passed in 3.11s** |
| Ruff on all changed production/test files | **All checks passed** |
| Mypy on kernel source and scripts | **Success: no issues found in 116 source files** |
| `git diff --check` | **passed** |

### Remaining concerns

- A separate exploratory command including `test_strategy_universe_scripts.py` produced **5 setup errors** because that historical fixture still passes schema revision 0002 into the current 0003-only `RuntimeAuthoritySeedRequest`; the other **15 tests** in that command passed. This is previously identified current-runtime fixture debt outside Task 7 and production code was not weakened to support it.
- The database identity proof depends on readonly access to PostgreSQL `pg_control_system()`; the disposable PostgreSQL role used by the production-shaped integration test has that access. Tokyo must satisfy the same readonly permission before a real compatible deployment, and any permission failure is a safe deployment block.
