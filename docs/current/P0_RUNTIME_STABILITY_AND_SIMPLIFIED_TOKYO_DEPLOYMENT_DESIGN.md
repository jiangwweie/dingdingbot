---
title: P0_RUNTIME_STABILITY_AND_SIMPLIFIED_TOKYO_DEPLOYMENT_DESIGN
status: PROPOSED_OWNER_CONFIRMATION
authority: docs/current/P0_RUNTIME_STABILITY_AND_SIMPLIFIED_TOKYO_DEPLOYMENT_DESIGN.md
last_verified: 2026-07-15
---

# P0 Runtime Stability And Simplified Tokyo Deployment Design

## 1. Decision

**There is enough evidence to start a bounded repair.** Exact per-table memory
attribution is still unavailable because production PostgreSQL has not yet been
recovered for measurement, but exact byte attribution is not required before
removing a production-cadence full-state scan that is already forbidden by the
current runtime-control-state contract.

The previous four-release-unit proposal mixed two different problems:

1. restoring the current low-frequency, small-capital runtime after an OOM and
   PostgreSQL outage; and
2. building a long-horizon capacity, retention, and adversarial-certification
   program.

That combined proposal is too heavy as the normal release path. This design
replaces it with:

| Release | Purpose | Blocks the current recovery |
| --- | --- | --- |
| **R1 Runtime Recovery** | Remove the demonstrated unbounded watcher path, contain one process, restore PostgreSQL startup, and make deployment fail closed | **Yes** |
| **R2 Runtime Hardening** | Redesign current/history retention, unify host capacity governance, and run long-horizon fault certification | No |

The selected direction is **R1 first**. R2 is recorded but does not delay the
latest-code deployment.

### 1.1 Performance Priority And Functional-Parity Invariant

R1 treats **program/data-path optimization as the repair**, not operating-system
throttling. The mandatory order is:

1. stop loading data the watcher does not consume;
2. make the remaining reads explicit, paged, streamed, and projection-shaped;
3. prove the optimized path produces the same candidate coverage, signal
   decision, protection visibility, and PG materialization inputs as the full
   path; and only then
4. install cgroup, timeout, and swap controls as a final host-containment layer.

No acceptance result may be obtained by reducing the enabled StrategyGroups,
symbols, sides, Event Specs, RequiredFacts, position/lifecycle visibility, TP or
runner semantics, or scheduled observation coverage. The full observation API
and explicit manual full-diagnostic mode remain available; production cadence uses a
compact transport projection because no production decision consumer reads the
discarded duplicate payload.

## 2. Owner Question Answer

### 2.1 Confidence

| Conclusion | Confidence | Basis | Remaining uncertainty |
| --- | --- | --- | --- |
| The watcher contains an unbounded production hot path | **High** | It calls full `read_control_state()` although it consumes only four current tables | None material to the repair decision |
| The unbounded path can independently explain the OOM | **High** | It materializes all retained rows from 42 tables and recursively copies JSON-shaped values | Exact table and payload byte shares are unmeasured |
| It was the only contributor to every killed process | **Medium** | Kernel cgroup identity is exact, but no heap profile exists for the killed process | HTTP body and artifact share remain unmeasured |
| The R1 design prevents the demonstrated watcher path from taking down the host | **High** | The program stops materializing the 42-table state, pages only server-matched candidate runtimes, and avoids duplicate full artifacts; the 512 MiB cgroup ceiling is only a final fault boundary | Production proof still requires five scheduled ticks; an unmeasured second defect remains possible |
| The current candidate can be deployed unchanged | **Low / rejected** | Candidate `fb013a15` contains no watcher-query or PostgreSQL-restart repair | A new exact-SHA commit is required |

### 2.2 Low-Frequency And Small-Capital Interpretation

Low trade frequency permits shorter acceptance and simpler availability
handling. It does **not** reduce watcher cadence: the watcher still starts every
three minutes even when no order is created. Therefore low frequency is a
reason to simplify release ceremony, not a reason to leave the unbounded tick
in production.

Small experiment capital permits accepting ordinary strategy loss, slippage,
or an imperfect live calibration outcome. It does not make these automation
failures acceptable:

1. duplicate exchange submit;
2. unknown exchange outcome followed by redispatch;
3. a real position without confirmed protection; or
4. a damaged or ambiguous PostgreSQL authority state.

These four boundaries prevent an automation error from turning one bounded
experiment into repeated or unbounded actions. They are not discretionary
portfolio conservatism.

## 3. Objective Facts

| Fact | Evidence | Design consequence |
| --- | --- | --- |
| Tokyo has about **3.3 GiB RAM** and had **0 swap** before the incident | `free -h`, 2026-07-15 read-only Tokyo sampling | First reduce watcher working-set demand; then add a control-plane-only swap buffer and final cgroup fault boundary |
| The previous boot recorded **29 OOM kills** in `brc-runtime-signal-watcher.service` | `journalctl -b -1 -k`, 2026-07-15 | Treat watcher boundedness as P0 |
| Killed watcher RSS was approximately **1.57-1.88 GiB** | Kernel OOM records | The program must pass an unconstrained production-shape memory test; a 512 MiB service ceiling then contains regression faults |
| `_read_candidate_universe_from_pg()` calls `read_control_state()` | `scripts/runtime_active_observation_monitor.py` | Replace the call, not merely increase RAM |
| `read_control_state()` reads **42 tables**, normally without `WHERE` or `LIMIT` | `src/infrastructure/runtime_control_state_repository.py` | Add a dedicated four-table current query |
| Candidate-universe construction consumes only **four tables** | Candidate scope, event binding, runtime binding, Event Spec code paths | Preserve behavior with a narrow repository profile |
| Migration 086 already provides active/current partial indexes for all four watcher tables | `2026-07-04-086_create_pg_runtime_control_state_foundation.py` | The watcher query needs no new index; revision 124 separately adds durable enablement-proof storage plus latest-current and recent-window process-outcome indexes for deploy certification |
| PostgreSQL container restart policy is `no` | `docker inspect`, 2026-07-15 | Assign Docker one explicit restart policy |
| Backend entered a five-second restart loop while PG was unavailable | `systemctl show` and journal, 2026-07-15 | Add PG readiness and systemd start limiting |
| Active backend `ExecStart` still uses the old fixed venv through server-only `10-runtime-bound.conf` | `systemctl show/cat brc-owner-console-backend.service`, 2026-07-15 | Track the canonical drop-in and route it through `app/current/.venv` |
| Deployed head is `2001644581cccc968ba695d3ff129960db6a7e84`; candidate head is `fb013a150dba840e73e48c32fb69a5d7426c6d80` | release manifest and local git | Build the repair on the candidate, then deploy one new exact SHA |
| The pre-repair candidate advances from revision `120` to `123` and pins CCXT `4.5.56`; R1 adds proof-persistence/sentinel-index revision `124` | tracked migrations, `requirements.txt`, and this approved design | Keep linear migration and exact dependency/proof verification in the deployment |
| Revision 123 activates the previously Owner-approved SOR-LONG future-Ticket exit policy | `2026-07-15-123_activate_sor_long_exit_policy_canary.py` | The complete release has a bounded, future-ticket trading-chain effect even though R1 adds no new strategy parameter change |
| Post-reboot snapshot still has PostgreSQL `exited`, restart policy `no`, watcher service `failed`, watcher timer active, no memory limits, and 0 swap | read-only `systemctl`, `docker inspect`, and `free -m`, 2026-07-15 | The reboot restored host access but did not restore a healthy runtime; use incident-recovery deploy, not normal deploy |
| Tokyo PG port `127.0.0.1:55432` currently refuses connections, so the production session role's ability to assume `pg_read_all_data` is not yet verified | read-only Tokyo connection probe, 2026-07-15 | Add a pre-migration role/privilege preflight; failure stops before schema mutation and never auto-grants a role |
| The current boot has no new kernel OOM record while the watcher is failed and PG is down | read-only `journalctl -k -b`, 2026-07-15 | Do not interpret zero new OOM as stability evidence |
| Tokyo runs systemd 249 on cgroup v2; watcher `MemoryHigh`, `MemoryMax`, and `MemorySwapMax` are currently `infinity` | read-only `systemd --version`, cgroup filesystem, and `systemctl show`, 2026-07-15 | The existing host can enforce R1 cgroup limits without an OS upgrade or new process manager |
| Linux 5.15/systemd 249 does not expose a persistent oneshot `MemoryPeak` fact on this host | read-only `systemctl show` and cgroup filesystem inspection, 2026-07-15 | Use journal-tagged GNU-time stage RSS for measurement and cgroup limits for enforcement |

## 4. Options And Trade-Offs

| Option | Time to recovery | Host protection | Repeatable deploy | Long-term completeness | Decision |
| --- | --- | --- | --- | --- | --- |
| **A. Caps-only emergency deploy** | Shortest | Partial | Low | Low | Rejected: full scan and unsafe deploy path remain |
| **B. R1 bounded runtime recovery** | Short | Strong for the demonstrated class | Strong | Sufficient for current runtime | **Selected** |
| **C. Full R1 + R2 hardening before deploy** | Longest | Strong | Strong | Highest | Rejected as current blocking scope |

Option B is the smallest package that makes the current runtime operable rather
than merely less likely to crash.

## 5. R1 Scope

### 5.1 Included

1. Four-table bounded watcher candidate-universe read.
2. Server-side candidate-matched active-runtime identity pages that traverse
   every in-scope page without client-scanning unrelated runtimes.
3. Server-side compact observation responses and no accumulation of discarded
   full runtime artifacts.
4. Functional-parity and unconstrained production-shape memory certification.
5. Watcher memory, runtime, and restart containment as the final fault boundary.
6. Docker-owned PostgreSQL automatic restart plus bounded readiness checks.
7. Backend restart-storm prevention.
8. Deploy preflight coverage for `prepared`, `dispatching`, and
   `outcome_unknown` commands.
9. Deployment certification that cannot call the exchange gateway.
10. Bounded deploy/certification repository reads; deployment must not invoke the
   42-table full-state reader.
11. PG-aware postdeploy verification using the explicit production venv.
12. One-command normal deploy and one bounded recovery-deploy mode.

### 5.2 Explicitly Excluded From R1

1. Any new R1 change to entry, exit, TP1, runner, leverage, sizing, capital,
   symbol, side, or runtime-profile parameters. The complete release still
   contains the already approved revisions 121-123, including SOR-LONG
   future-Ticket exit-policy activation in revision 123.
2. Redesign of every current/history table.
3. A new generic chaos platform.
4. A parent cgroup slice for every BRC service.
5. A new PostgreSQL systemd container owner.
6. A new venv on every release when the dependency lock is unchanged. The
   current candidate does change the lock, so R1 creates one new immutable
   resolved-lock venv and binds it to the new release.
7. A 14-day growth simulation, 30-run benchmark, or 60-minute production
   observation as a blocking gate.
8. A PostgreSQL-independent Feishu infrastructure alert service.

Those excluded items may enter R2 only after R1 is stable.

## 6. Architecture

### 6.1 Watcher Current-Only Read Profile

Add one repository method:

```python
PgBackedRuntimeControlStateRepository.read_watcher_candidate_universe_current(
    *, row_limit_per_table: int = 256
) -> WatcherCandidateUniverseCurrentProjection
```

`WatcherCandidateUniverseCurrentProjection` and its four row models are frozen
Pydantic models with `extra='forbid'`; unexpected columns or nested payloads
cannot cross this boundary. The monitor converts the validated model to the
legacy four-key dictionary only at the existing pure consumer boundary.

It reads only:

| Logical table | Predicate | Maximum rows | Explicit selected fields |
| --- | --- | ---: | --- |
| `candidate_scope` | `status = 'active'` | 256 | candidate, group, symbol, asset class, side, policy and status identity only |
| `candidate_scope_event_bindings` | `status = 'active'` | 256 | binding, candidate, event, group, symbol, side and status identity only |
| `runtime_scope_bindings` | `status = 'active'` | 256 | runtime binding, candidate, group, symbol, side, profile and status identity only |
| `strategy_side_event_specs` | `status = 'current'` | 256 | event/version, group/version, side, timeframe, time authority and status only |

Each query requests at most `row_limit_per_table + 1`. The extra row detects
overflow. Overflow is a typed runtime error; it must not silently truncate a
candidate universe. The query must use `sa.select(*allowed_columns)`, never
`sa.select(table)`, so one oversized unused metadata/JSON column cannot defeat
the row bound.

The watcher must never call `read_control_state()` or
`read_monitor_control_state()` for candidate-universe construction. The latter
still iterates the full table registry and is not a valid substitute.

This R1 change does not alter schema or authority. The same
`_candidate_universe_from_control_state()` consumer receives a smaller payload
with the same four logical keys and source metadata.

The narrow reader must call the same one-active-binding, referential-integrity,
cross-table StrategyGroup/symbol/side identity, and duplicate-key fail-closed
validators used by the full reader before returning the projection. It may not
use dict-comprehension last-write-wins behavior or skip an identity mismatch.
Semantic-parity tests seed every invalid binding and mismatch shape against both
read paths and require the same typed rejection.

The watcher read optimization needs no schema change. The lifecycle enablement
proof does require **migration 124** so the canonical proof is durable rather
than represented only by a one-way hash. The final release is a linear
`120 -> 121 -> 122 -> 123 -> 124` upgrade; revision 124 adds bounded proof
columns to the existing current capability row, a partial latest-outcome index
on `(lane_identity_key,process_name,updated_at_ms DESC,process_outcome_id DESC)`
where `scope_kind='runtime_lane'`, and a recent-window index on
`(updated_at_ms DESC,process_outcome_id DESC)`. The two indexes separately serve
the bounded deploy sentinel's current and canary-window slices, not watcher
cadence. The capability remains disabled until the deployment setter restores
the captured desired policy.

### 6.2 Bounded Deploy And Capability Profiles

Deployment must not substitute one 42-table method for another. R1 adds two
explicit profiles:

| Profile | Allowed row tables | Bound |
| --- | --- | --- |
| `deploy_validation` | The four watcher identity tables plus `current_projection_ownership` | Explicit columns; status predicates on watcher tables; non-null primary-key predicate on ownership; at most 256 rows per table plus overflow row |
| `action_time_capability_certification` | strategy groups/versions, candidate/event/runtime bindings, current policies, required facts, and one release-activation outcome | Explicit columns; identity-driven predicates; 256 rows per identity table, 2,048 required-fact rows, one activation row |

Schema validation may inspect table/index metadata for all required tables, but
it must not materialize their rows. The deploy validator uses the
`deploy_validation` profile. Capability certification uses the dedicated
`action_time_capability_certification` profile; it must not use
`read_monitor_control_state()` or `read_action_time_control_state()` because
their current implementations still iterate the 42-table registry.

`current_projection_ownership` selects only
`projection_key,model_type,projection_scope_key,owner_projector,legacy_writer_allowed,current_source_mode,updated_at_ms`
with `projection_key IS NOT NULL`, primary-key order, and limits 256/257. It
excludes `export_paths` and `sunset_condition`; schema inspection separately
proves the DB-backed/no-legacy constraints.

SQL-capture tests must assert the exact table allowlist, explicit selected
columns, a predicate and `LIMIT` for every row query, plus overflow behavior.
Tests that only monkeypatch `read_control_state()` are insufficient.
Production watcher/profile reads use read-only transactions with a one-second
lock timeout and five-second statement timeout. Timeout is a typed unavailable
result; it never falls back to an unbounded reader.

The capability profile contract is exact:

| Table | Exact selected columns | Exact current predicate / order | Base / probe limit |
| --- | --- | --- | ---: |
| `brc_strategy_groups` | `strategy_group_id,current_version_id,status` | `status='active'`; PK ascending | 256 / 257 |
| `brc_strategy_group_versions` | `strategy_group_version_id,strategy_group_id,status` | referenced IDs and `status='current'`; PK ascending | 256 / 257 |
| `strategy_runtime_instances` | `runtime_instance_id,strategy_family_id,strategy_family_version_id,symbol,side,status` | exact active candidate `(strategy_group_id,symbol,side)` keys mapped to `strategy_family_id,symbol,side`, and `status='active'`; PK ascending | 256 / 257 |
| `brc_strategy_group_candidate_scope` | `candidate_scope_id,strategy_group_id,symbol,asset_class,side,policy_current_id,priority_rank,status` | `status='active'`; PK ascending | 256 / 257 |
| `brc_candidate_scope_event_bindings` | `binding_id,candidate_scope_id,event_spec_id,strategy_group_id,symbol,side,status` | referenced candidate IDs and `status='active'`; PK ascending | 256 / 257 |
| `brc_runtime_scope_bindings` | `runtime_scope_binding_id,candidate_scope_id,strategy_group_id,symbol,side,policy_current_id,runtime_profile_id,selected_strategygroup_scope,symbol_side_scope_closed,notional_leverage_scope_closed,live_submit_allowed,server_runtime_coverage_required,status`; guarded `conditional_hard_gates`; byte guard alias | referenced candidate IDs and `status='active'`; PK ascending; logical UTF-8 bytes `>16384` fail typed | 256 / 257 |
| `brc_strategy_side_event_specs` | `event_spec_id,strategy_group_id,strategy_group_version_id,event_spec_version,event_id,side,timeframe,execution_eligibility_enabled,declared_signal_grade,declared_required_execution_mode,freshness_window_ms,time_authority,protection_ref_type,status` | referenced event IDs and `status='current'`; PK ascending | 256 / 257 |
| `brc_owner_policy_current` | `policy_current_id,strategy_group_id,symbol,side,runtime_profile_id,enabled_state,pretrade_candidate_allowed,action_time_rehearsal_allowed,live_submit_allowed,planned_stop_risk_fraction,max_initial_margin_utilization,max_leverage,attempt_cap`; guarded `policy_event_ids`; byte guard alias | referenced policy IDs; PK ascending; logical UTF-8 bytes `>16384` fail typed | 256 / 257 |
| `brc_strategy_event_required_facts` | `event_required_fact_id,event_spec_id,required_facts_version_id,fact_key,fact_role,fact_surface,operator`; guarded `expected_value`; byte guard alias; `disable_on_match,freshness_ms,required_for_promotion,required_for_ticket,required_for_finalgate,missing_blocker_class,failed_blocker_class,value_source,status` | referenced event IDs and `status='current'`; PK ascending; logical UTF-8 bytes `>4096` or cumulative bytes `>8388608` fail typed | 2,048 / 2,049 |
| `brc_runtime_process_outcomes` | `process_outcome_id,process_name,scope_key,process_state,runtime_head,source_watermark,updated_at_ms` | exact release-activation name/scope/succeeded; `updated_at_ms DESC, process_outcome_id DESC` | 1 / 2 |

Each guarded JSON field uses `octet_length(<jsonb>::text)` in its `CASE` and
byte alias; `pg_column_size` is forbidden because TOAST/compression size does
not bound the logical Python payload. The activation probe deliberately uses `LIMIT 2`; two rows fail the uniqueness
contract. JSON-bearing fields are not unbounded exceptions:
`conditional_hard_gates` and `policy_event_ids` are each capped at 16 KiB, each
`expected_value` at 4 KiB, and total selected required-fact JSON at 8 MiB.
The implementation plan freezes the exact `CASE`/alias SQL captured by tests;
the byte-length companions are guards only and do not enter the semantic digest.
An oversize row fails typed without transferring the large JSON into Python. All Text/JSON
columns not listed above are excluded.

The capability profile resolves exactly one active `strategy_runtime_instances`
row for every active candidate key and constructs the existing complete
`RuntimeLaneIdentity`; a missing or ambiguous runtime, `asset_class`, profile,
policy, Event Spec, time authority, or identity-key mismatch fails. R1 also
removes current-authority writes for the five lane process names that omit this
identity. `live_signal_materialization`, `action_time_fact_snapshots`,
`promotion_action_time_lane`, `action_time_ticket_sequence`, and
`action_time_capability_certification` pass the same typed lane identity whenever
they materialize a lane outcome. A batch/no-signal orchestration summary may
remain only as `action_time_fact_snapshots_batch`,
`promotion_action_time_lane_batch`, or `action_time_ticket_sequence_batch`; it
cannot masquerade as one of those five current lane processes. Historical
`legacy_unscoped` rows remain
for provenance and are not backfilled into current authority.

Capability certification does not mix a read-only transaction with outcome
writes. A read-only prepare transaction computes a deterministic digest from
the bounded rows, runtime head, referenced-ID sets, and lane source watermarks.
A separate `SERIALIZABLE` read-write transaction re-reads the same profile,
requires an exact digest/head/watermark match, and atomically writes the bounded
process outcomes. Drift, timeout, or serialization failure writes nothing.
The digest contract is versioned as
`brc.action_time_capability_certification_input.v1` using
`brc.typed_canonical_json.v1`: typed SQL/JSON tokens, finite Decimal numbers,
sorted object keys, preserved array order, fixed table/column/row order, exact
release activation, referenced-ID sets, and per-lane watermarks. Binary float,
NaN/Infinity, wrong types, missing/extra columns, and stale prepare input fail
closed. The implementation plan freezes the exact encoding and test vectors.
The release-activation identity explicitly includes `source_watermark`; SQL
capture and golden vectors must prove a watermark-only change alters both the
certification input digest and `ActionTimeCertificationReferenceV2`.

The fact component is independently versioned as
`brc.action_time_fact_set_digest.v1`; it is not an implementation-private hash.
Its exact row model is `ActionTimeFactDigestRowV1` with, in order,
`fact_snapshot_id`, `strategy_group_id`, `symbol`, `side`,
`runtime_profile_id`, `fact_surface`, `source_kind`, `source_ref`, `computed`,
`satisfied`, `freshness_state`, `failed_facts`, `fact_values`, `blocker_class`,
`observed_at_ms`, and `valid_until_ms`. The certification input supplies the
complete expected fact-ID set: at most **128** unique IDs, sorted by
`fact_snapshot_id`; a duplicate, missing, extra, or out-of-scope row fails.
`failed_facts` and `fact_values` are each guarded with
`octet_length(jsonb::text) <= 65536`, and the canonical fact-set input is capped
at **1 MiB** before hashing. No oversize JSON is transferred into Python.

The fact-set digest uses `brc.typed_canonical_json.v1`. PostgreSQL numeric and
JSON numeric tokens are parsed as `Decimal`, rendered without binary-float
rounding, and reject NaN/Infinity. Object keys sort lexically, array order is
preserved, explicit null remains distinct from a missing field, and UTF-8 bytes
are hashed exactly. Prepare and `SERIALIZABLE` apply independently select and
rehash the same exact row model and byte limits; equality of IDs alone is never
sufficient. Golden vectors freeze shuffled SQL/key order, Decimal scale,
explicit null, multibyte Unicode, and one-field mutations for every semantic
column so a later implementation can independently recompute the durable
reference.

### 6.3 API Pagination And In-Process Memory Bounds

R1 adds a structurally read-only, explicit-column endpoint:

```text
POST /api/trading-console/strategy-runtimes/watcher-active-candidate-page
```

The request carries the already validated active candidate lane keys, an
immutable runtime-ID cursor, and `limit=16`. **Sixteen is a page size, not a
runtime ceiling.** The server joins active runtimes to those candidate lane
keys before pagination, selects only immutable runtime identity,
StrategyGroup/version, symbol, side, runtime profile/carrier, and status fields,
orders by `runtime_instance_id ASC`, and probes `limit + 1`. The watcher follows
the in-scope cursors until `has_more=false`; a repeated, missing, or non-
monotonic cursor fails the tick instead of returning partial success. Tests with
17, 33, and 256 in-scope runtimes prove exact-once coverage.

Out-of-scope inventory never creates one HTTP page per row. On the first page,
the server returns one SQL aggregate count and at most the first 32 ordered IDs
from a separate `NOT EXISTS(candidate_lane_keys)` sample query. It does not
build or return a complete ID list or aggregate string/digest. A fixture with
100,000 out-of-scope runtimes and candidate IDs at the lexical tail must still
discover every in-scope runtime and finish the complete tick below 120 seconds.
Thus a large unrelated inventory cannot permanently starve a candidate. A
runtime activated/deactivated during a scan is revalidated by the per-runtime
observation route and may enter the next three-minute tick; pagination never
grants execution authority.

The endpoint is additive. The existing full `/strategy-runtimes` endpoint and
its default updated-time ordering remain unchanged for existing callers.

The observation request adds
`response_projection="watcher_compact"`. The server still computes the same
market facts, Event Spec evaluation, blocker classification, and safety facts,
but serializes only the typed fields consumed by watcher status and PG live-
signal materialization. The default `response_projection="full"` remains
unchanged for explicit diagnostic use.

Response limits are endpoint-shaped rather than globally guessed:

| Response class | Maximum body | Reason |
| --- | ---: | --- |
| One candidate-matched runtime identity page | **128 KiB** | Exactly 16 explicit-column in-scope identities, one probe, and bounded out-of-scope count/sample |
| One compact observation response | **512 KiB** | Typed watcher projection; full diagnostic response is not transported on production cadence |
| Explicit full diagnostic response | **16 MiB** | Preserves the existing manual API mode outside production cadence |

The shared client reads at most `limit + 1` bytes and fails with a typed
`runtime_api_response_too_large` error before JSON parsing when the selected
limit is exceeded. The same bound applies to success and HTTP-error bodies.
Pages and runtime responses are consumed and released sequentially. R1 does not
add a total-runtime-count or cumulative-byte policy that could silently reduce
observation coverage. Total work is bounded by candidate-matched cursor progress,
the existing fail-closed 256-row active candidate admission contract, and the
120-second monotonic tick deadline. The 17/33/256 production-shape gates and the
100,000-out-of-scope/tail-candidate gate must complete in less than 120 seconds.
As a degraded defense, in-scope observation order rotates from the three-minute
tick slot so repeated downstream deadline exhaustion cannot always starve the
same candidate; an incomplete tick never reports complete coverage.

When `include_runtime_artifacts=false`, the monitor keeps only:

```text
status
summary
safety boolean projection
runtime identity
```

Every required safety key must be present and satisfy `type(value) is bool`.
Missing, null, string, integer, or nested values fail with a typed projection
error; coercion with `bool(value)` is forbidden.

It must not append the full runtime artifact and discard it only at final JSON
construction.

The compact summary is a new bounded projection, not the existing `_summary()`
function. It omits raw candles, evaluator traces, duplicated artifacts, and
review-only evidence, but it **must retain every current Action-Time decision
input**. A frozen `ActionTimeDecisionFactProjection` carries validated
`signal_snapshot`, `evidence_payload`, `action_time_fact_values`, and
`fact_observations` plus their timing/source fields. These are the current
inputs to RequiredFacts and typed-validity materialization; they are not
diagnostic baggage.

Logical size is always:

```text
len(json.dumps(value, ensure_ascii=False, allow_nan=False,
               sort_keys=True, separators=(",", ":")).encode("utf-8"))
```

Each decision map is at most 64 KiB, fact observations are at most 128 typed
rows and 96 KiB total, the combined decision projection is at most 192 KiB, and
the entire compact signal summary is at most 256 KiB. Reason codes, blockers,
and warnings are separate arrays of at most 64 strings; each string is at most
256 UTF-8 bytes and each array at most 16 KiB. **Nothing is truncated.** Any
count, field, aggregate, non-finite number, or overall limit violation is a
typed fail-closed compact-projection error and cannot materialize a partial live
signal. Blocker/reason codes are therefore never dropped. All current 22 lanes
must fit these bounds in regression; otherwise R1 returns to projection design
rather than raising limits or deleting facts.

Parity acceptance runs the same observation through full and compact paths,
persists the resulting `brc_live_signal_events.signal_payload`, then materializes
the Action-Time fact snapshot. For every active lane and every RequiredFact it
requires identical fact value, missing/failed set, validity, blocker,
candidate/Ticket readiness, and source watermark. The existing full endpoint
remains available for explicit diagnosis.

### 6.4 Service Containment

The following settings are a **last-resort host safety net**, not the performance
solution and not an acceptance substitute. The optimized program must first
pass the production-shape memory benchmark with no cgroup memory ceiling:

```ini
MemoryAccounting=true
MemoryHigh=384M
MemoryMax=512M
MemorySwapMax=0
OOMPolicy=stop
TimeoutStopSec=20s
StartLimitIntervalSec=2min
StartLimitBurst=3
KillMode=control-group
```

The start-limit window is intentionally shorter than the normal three-minute
timer cadence. systemd counts successful oneshot activations as starts; a
window longer than the cadence would eventually rate-limit a healthy watcher.
The two-minute window still blocks a manual or dependency-driven rapid-start
storm without consuming normal scheduled activations.

The watcher core cycle deadline becomes **120 seconds**. The complete oneshot
uses `TimeoutStartSec=300s`, covering PostgreSQL readiness, two fact-building
`ExecStartPre` commands, the core, and three existing `ExecStartPost` commands.
Every stage has an outer monotonic deadline: 10s PG readiness, 30s public facts,
30s account facts, 125s main-process envelope with a 120s internal deadline,
10s projection summary, 40s Action-Time refresh, 45s resume dispatcher with
internal network waits no greater than 30s, and 10s systemd/teardown margin.
Each stage deadline includes its TERM-to-KILL grace; those grace periods are not
added on top. The executable stages therefore consume at most 290 seconds and
leave 10 seconds for systemd teardown within the 300-second ceiling.
The 300s value is a degraded-state hard ceiling; measured normal no-signal
complete-unit SLO remains below 120s.

R1 installs a timerless **watcher canary service** and a loopback-only candidate
API canary unit. Both run the exact candidate SHA, but neither is a production
writer. Public/account fact refresh is a separate, explicitly bounded
pre-canary stage: it runs once while all scheduled production writers remain
behind the persistent deploy fence, may update only its already-owned fact
projection tables (`brc_runtime_fact_snapshots` and
`brc_exchange_account_modes_current`), passes no Action-Time invocation ID, and
records before/after table digests. The canary itself
consumes that frozen fact snapshot and never runs fact refresh, Ticket
materialization, signal/process-outcome persistence, Action-Time refresh,
FinalGate, Operation Layer, dispatcher, or exchange-submit code.

The API service imports a dedicated deny-by-default ASGI application rather
than the normal FastAPI application. Its actual server route set contains only:

```text
POST /api/trading-console/strategy-runtimes/watcher-active-candidate-page
POST /api/trading-console/strategy-runtimes/{runtime_id}/next-attempt-observation-cycle
```

The dedicated application creates its own database engine/ports. Every checked-
out connection must successfully `SET ROLE pg_read_all_data`, set the session
and transaction read-only defaults, and report
`current_user='pg_read_all_data'`. Startup proves that this current role has
`SELECT` and lacks `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE`, and sequence-write
privileges on every reachable production table. The original session role must
already be able to assume the built-in role; otherwise deployment stops without
creating a role, granting membership, or changing a secret. The canary code and
tests forbid `RESET ROLE`, `SET ROLE` to any other role, and `SET TRANSACTION
READ WRITE`. Because the underlying production login remains recoverable inside
that same database session, this is explicitly **defense in depth**, not an
independent credential-isolation claim. R1 does not claim PostgreSQL itself
rejects `RESET ROLE`. The accepted zero-write boundary is structural: the
dedicated two-route graph has no writer dependency, its SQL-capture allowlist
contains SELECT only, write/gateway ports are unreachable, exact-SHA counters
stay zero, and the bounded pre/post sentinel remains unchanged.

The watcher canary is **API-only**: it has no direct PG repository, materializer,
or fact builder and accepts only the two server routes above. Exact-SHA tests
replace Ticket materialization, promotion/lane/runtime-safety/authorization
writers, FinalGate, Operation Layer, dispatcher, and gateway dependencies with
counters and prove every counter stays zero. Direct injected DML while the
connection is under `pg_read_all_data` must fail, and SQL capture must report
zero role-reset or read-write-escalation statement. Read-only exchange position
and open-order identities plus a bounded `CanaryMutationSentinelProjection`
must remain unchanged across all five runs. The sentinel reads explicit columns
only for the frozen fact snapshot IDs, the 22 current lane keys and selected
runtime IDs, the exact explicitly listed mutation-sensitive
Ticket/authority/command/lifecycle/protection identities rooted in that scope,
and the target release/current-projection identity. This bounded sentinel is
not represented as an exhaustive writer-graph proof; the structural zero-writer
dependency/counter proof remains primary for every nonlisted relation.
Every query has an identity predicate, a five-second statement timeout, and a
fixed `LIMIT N + 1`; overflow fails instead of widening into a table scan. The
sentinel contract is:

| Relation | Predicate and maximum | Digested columns |
| --- | --- | --- |
| `brc_runtime_fact_snapshots` | exact frozen `fact_snapshot_id IN (...)`; **128** | `CANARY_FACT_COLUMNS_V1`: every fact semantic/identity column plus invocation and creation identity; each JSON field logical bytes <= **64 KiB** |
| `brc_live_signal_events` | exact selected `signal_event_id IN (...)`; **22** | `CANARY_SIGNAL_COLUMNS_V1`: every signal, candidate/runtime/Event-Spec/lane/authority identity and semantic column; each JSON field logical bytes <= **64 KiB** |
| `brc_runtime_process_outcomes` current slice | exact 22 `lane_identity_key` values crossed with the authoritative runtime lane process set; latest row per pair through an indexed `LATERAL ... ORDER BY updated_at_ms DESC,process_outcome_id DESC LIMIT 1`, plus the exact release-activation `process_outcome_id`; the bounded row limit is derived as `22 × process-name count + 1` (**133** with the current six names) | `CANARY_PROCESS_OUTCOME_COLUMNS_V1`: every schema-124 base, state, time, runtime-head, source, scope-kind, complete stored lane-identity, legacy-evidence and invocation column; `legacy_evidence` logical bytes <= **64 KiB** |
| `brc_runtime_process_outcomes` canary-window slice | `updated_at_ms >= canary_window_floor_ms` and either an exact 22 `lane_identity_key`, `scope_key='production:tokyo'`, or one authoritative runtime lane process name; no process restriction applies inside the exact lane/production scopes; **256** | the same `CANARY_PROCESS_OUTCOME_COLUMNS_V1`; pre/post row set and digest must be byte-identical |
| `brc_action_time_lane_inputs` | exact pre-canary lane IDs; **22** | `CANARY_LANE_COLUMNS_V1`: every schema-124 lane identity, fact, authority, blocker, scope and time column |
| `brc_action_time_tickets` | exact lane IDs above, with **no status predicate**; **22** | `CANARY_TICKET_COLUMNS_V1`: every schema-124 Ticket identity, version, fact, policy, amount, authority, lineage and time column |
| `brc_ticket_bound_protected_submit_attempts` | exact ticket IDs above; **44** | `CANARY_PROTECTED_ATTEMPT_COLUMNS_V1`: every FinalGate/Operation/runtime/fact/request/result/effect/authority column |
| `brc_ticket_bound_exchange_commands` | exact ticket IDs above, with **no command-state predicate**; **88** | `CANARY_EXCHANGE_COMMAND_COLUMNS_V1`: every account/instrument/order/claim/amount/authority/result/error/time column |
| `brc_ticket_bound_order_lifecycle_runs` | exact ticket IDs above; **22** | `CANARY_LIFECYCLE_COLUMNS_V1`: every entry/fill/protection/blocker/warning/authority/time column |
| `brc_ticket_bound_exit_protection_sets` | exact ticket IDs above; **22** | `CANARY_PROTECTION_SET_COLUMNS_V1`: every entry/SL/TP1/runner/reconciliation/blocker/warning/authority/time column |
| `brc_ticket_bound_exit_protection_orders` | exact protection-set IDs above, with **no status predicate**; **88** | `CANARY_PROTECTION_ORDER_COLUMNS_V1`: every set/ticket/order/replacement/price/quantity/status/time column including **generation** |
| `brc_ticket_exit_policy_current` | exact ticket IDs above; **22** | `CANARY_EXIT_POLICY_CURRENT_COLUMNS_V1`: every policy, TP1, runner, generation, blocker and evaluation column |
| `brc_exchange_account_modes_current` | exact frozen account-mode IDs; **22** | `CANARY_ACCOUNT_MODE_COLUMNS_V1`: every account/exchange/mode/fact/source/freshness column |
| `brc_runtime_capabilities_current` | exact lifecycle capability ID; **1** | `CANARY_LIFECYCLE_CAPABILITY_COLUMNS_V1`: status, reference, time, proof schema and payload |
| `brc_pretrade_readiness_rows` | exact 22 `(strategy_group_id,symbol,side)` lane keys; **22** | exact PK/candidate/lane identity, readiness/detector/watcher/public-fact/signal/risk/scope/promotion states, blocker/detail/next/stop/evidence/source/valid-until tuple; excludes `computed_at_ms` |
| `brc_goal_status_current` | `goal_status_current_id='strategygroup-runtime-goal-status'`; **1** | exact ID/status/fresh-signal/real-order/Owner-action booleans, guarded blockers/input-watermark, projection-run ID; excludes `updated_at_ms` |
| `brc_control_read_model_snapshots` | `is_current=true` and model type in `candidate_pool,daily_live_enablement_table,goal_status`; **3** | exact snapshot ID/type/source-watermark/owner/input-watermark/output-path/current/generated-by plus guarded canonical `payload - 'generated_at_ms'`; embedded code version must equal target SHA; excludes `generated_at_ms` |
| `brc_projection_runs` | exact three projection-run IDs referenced by the current snapshots/goal row; **3** | exact ID/type/owner/code-version/source-mode/target/input-watermark/source-priority/legacy flags/status/error tuple; require `code_version=target SHA`; excludes start/finish timestamps |

Immediately before the pre-canary sentinel, one read-only database query records
`canary_db_now_ms` from `clock_timestamp()` and fixes
`canary_window_floor_ms=canary_db_now_ms-1000`. The window slice is captured
both before and after all five canaries. It prevents a new or updated known or
unknown process row during the quiesced canary interval from hiding behind the
current selector, without scanning lifetime history. More than 256 window rows
fails closed but does not create a permanent history-size ceiling.

Rows are sorted by sentinel slice then relation then primary key and encoded with the same typed
canonical JSON v1 rules used by certification. Every relation executes one
query per declared slice with `LIMIT N+1`; a duplicate identity, out-of-scope row, or overflow is a
typed blocker. The process-outcome current query predicate/order must match the
revision-124 partial latest-outcome index and may not transfer or count
historical rows; a 100,000-history-row production-shape `EXPLAIN` fixture must
select the index path and finish inside the five-second statement budget.
The process-outcome window query must be one SQL statement/one MVCC snapshot:
a materialized bounded-ID CTE enters through the revision-124
`updated_at_ms`-leading recent-window index, applies its fixed floor before the
lane/production/global branch filter, orders by the index columns, and returns at
most 257 IDs; an outer primary-key join fetches/sorts only those complete rows.
The whole statement shares one five-second timeout. Production-
shape `EXPLAIN (ANALYZE, BUFFERS)` fixtures with **100,000** and **1,000,000**
retained historical rows independently cover the typed-lane, `production:tokyo`,
and each of the five global/legacy process branches; typed-lane and production
cases include a recent unknown process to prove it remains visible. Every case must avoid a sequential scan
and finish inside the same five-second statement budget. This is a program/data-
path requirement, not an OS-limit substitute. The window process-outcome,
Ticket, command, and protection-order queries first select every
row in the exact identity scope and only then validate the complete status
allowlist in application code; an unknown process or status is therefore
visible and fails rather than disappearing behind a SQL `WHERE`. The frozen
lane process set is
`live_signal_materialization,action_time_fact_snapshots,promotion_action_time_lane,action_time_ticket_sequence,action_time_capability_certification`;
the only accepted `production:tokyo` row is exactly one
`runtime_release_activation`. A canary-window row with a frozen lane process
name must have `scope_kind='runtime_lane'`, one of the exact lane identity keys,
and a complete matching stored identity; a new `legacy_unscoped`/`global` lane
process row fails. The versioned status allowlists contain all
schema-valid values: Ticket
`created,preflight_pending,finalgate_ready,finalgate_rejected,expired,superseded,submitted,closed,invalidated`;
exchange command
`prepared,dispatching,confirmed_submitted,confirmed_rejected,outcome_unknown,reconciled_submitted,reconciled_absent,hard_stopped`;
and exit-protection order
`planned,submitted,open,partially_filled,filled,cancel_pending,cancelled,replace_pending,replaced,failed`.
JSON-bearing sentinel
fields use `octet_length(jsonb::text)` before transfer: fact/signal fields are
bounded as above, goal/projection watermarks at **64 KiB** each, and each
canonical current-snapshot semantic payload at **1 MiB**. The sentinel never
hashes a whole production/history table. The implementation plan freezes every
constant as a literal column tuple—without `PK` or “fact refs” shorthand—and
requires schema-name-set equality before SELECT, fixed tuple order for digest,
**64 KiB** guards for every JSON/unbounded Text field, and a **16 MiB** total
canonical-input bound. Any added or missing schema column blocks review rather
than becoming an invisible mutation surface. The
structural route/dependency/SQL boundary is the primary non-mutation proof;
role-based DML denial, the bounded sentinel, and exchange identity comparison
are defense in depth. Missing role/privilege facts, any escalation statement, a
non-allowlisted route, a sentinel delta/overflow, or an exchange delta fails
closed. Canary units are stopped and remain disabled after the five runs.

Tokyo's Linux 5.15/systemd 249 stack does not expose a persistent
`MemoryPeak` property after an oneshot exits. R1 therefore wraps every watcher
stage with GNU `time` and emits one tagged maximum-RSS value to the journal; it
retains no report file. Canary and scheduled-tick acceptance use the maximum
tagged stage RSS, while `MemoryHigh`/`MemoryMax` remain the enforced whole-cgroup
containment boundary. Tests also prove no stage detaches a child from the unit
cgroup.

The host receives a **2 GiB swap file** with `vm.swappiness=1`. This buffer is
for SSH, systemd, Docker, PostgreSQL, and recovery control; watcher cgroup
configuration prevents the watcher from using it as working memory.

### 6.5 PostgreSQL Ownership And Readiness

R1 chooses **Docker `unless-stopped` as the single PostgreSQL container
owner**. It does not add a second systemd service that starts and stops the same
container.

Normal deploy verifies, and incident recovery applies only after WAL/schema and
backup acceptance:

```text
docker update --restart unless-stopped brc_prelive_pg_20260601
```

Systemd remains the application-service owner. A small PG readiness command is
installed at the release-independent control-plane path
`/home/ubuntu/brc-deploy/control-plane/check_runtime_postgres_ready.py`. Its
SHA-256 must equal the tracked candidate script and it imports no project
module. Every unit invokes that stable path with
`app/current/.venv/bin/python`, so the units remain executable during a
pre-migration rollback to the legacy release. The command performs a bounded
real `SELECT 1` using the configured production venv and DSN. The backend,
production watcher, canary API, monitor, and lifecycle
units each run this bounded readiness gate before their main command. Unit tests
must prove every one of those services fails before its business process when
PostgreSQL is unavailable.

The current dependency specification differs from the deployed release.
`requirements.txt` is not itself a reproducible lock because most constraints
use `>=`. R1 resolves against the read-only deployed `pip freeze` baseline,
allows only CCXT `4.5.56` and its proven incompatible dependency closure to
change, and rejects unrelated framework/database upgrades. It adds a Linux
x86_64 / CPython 3.10 resolved lock with hashes and
creates an immutable venv at
`/home/ubuntu/brc-deploy/venvs/by-lock/<lock_sha256>-cp310-linux_x86_64` before
quiescence. A deploy-wide lock prevents concurrent builders; a missing
`.complete` marker means the unreferenced directory is deleted and rebuilt.
This avoids renaming a Python venv whose scripts contain absolute paths.

Each release directory contains `.venv`, a symlink to that immutable venv. All
repository-owned units execute
`/home/ubuntu/brc-deploy/app/current/.venv/bin/python`. Therefore the single
atomic `app/current` switch changes code and dependency identity together, and
switching `app/current` back restores both. The candidate venv must pass
`pip --require-hashes`, `pip check`, core imports, Alembic import, and exact
`ccxt.__version__ == 4.5.56` before it can be referenced. A future release with
the same resolved-lock/ABI/platform identity reuses the venv and never mutates
it in place.

The switch primitive is not `ln -sfn app/current`. Under the deploy-wide lock,
a `.complete` venv marker is first created by temporary file, file `fsync`,
atomic rename, and parent-directory `fsync`. After release export, SHA/manifest/
import verification, the release-independent helper calls bounded `syncfs(2)`
once per unique filesystem containing the candidate release and immutable venv,
then rereads the release SHA, lock identity, `.complete` marker, and interpreter
import. A timeout or reread mismatch leaves the writer fence engaged; the
pointer is not switched. This makes target contents durable before making the
pointer durable.

Under the deploy-wide lock,
a release-independent helper creates a unique temporary symlink in the same
`app/` directory, verifies old and new targets are release directories on the
same filesystem, calls `os.replace`, opens and `fsync`s the `app/` parent
directory, then rereads the pointer and exact SHA before the journal advances.
Fault-injection tests prove interruption leaves `app/current` pointing to either
the complete old release or the complete candidate, never absent or partially
rewritten.

The currently deployed legacy release does not yet contain `.venv`. Before any
unit file is changed or `app/current` is switched, recovery creates
`previous_release/.venv` pointing to the existing deployed venv and proves that
`previous_release/.venv/bin/python -m src.main` imports from the previous
release. If this compatibility binding cannot be established, deployment stops.
Migration 121-124 runs from the candidate release working directory with
`candidate_release/.venv/bin/python -m alembic upgrade head`; it never uses
`app/current/.venv` before the switch. The previous release and its `.venv`
binding are retained through acceptance. Rollback to it is permitted only
before migration 121 begins. After the schema reaches 124, the old release's
Alembic tree cannot resolve revision 124 and no old-code/schema-124
compatibility is assumed; later failure keeps writers disabled and requires a
forward fix on the candidate line.

The backend receives:

```ini
StartLimitIntervalSec=300
StartLimitBurst=3
Restart=on-failure
RestartSec=15s
```

This prevents a five-second infinite restart storm without adding a new process
manager.

### 6.6 Simplified Deployment Interface

The Owner-facing operation is one command and one terminal result. Internal
steps remain automated because hiding checks is not the same as deleting them.
The local executor resolves, prints, and flushes the deployment transaction ID
and nonce **before opening the one mutating SSH session**, then passes both
explicitly to the remote state machine. `auto` is only a local CLI convenience;
no identifier is first generated remotely, so an SSH disconnect cannot hide the
resume key.

#### Normal Deploy

```text
exact-SHA, resolved-lock venv, and migration preflight
-> export release
-> capture desired scheduling/capability policy and audit evidence
-> verify `pg_has_role(..., 'SET')`, actual `SET ROLE pg_read_all_data`, and that
   the current-role privileges are read-only; make no role/grant/secret change
-> install and engage a boot-persistent production-writer fence
-> quiesce writers
-> migrate and durably switch app/current using same-filesystem rename plus
   parent-directory fsync
-> PG-aware candidate backend import/config smoke without starting the
   production backend service
-> record exact release activation
-> run bounded pre-canary fact refresh
-> prepare/apply exact-SHA Action-Time certification
-> publish and verify current projections from those fresh facts/certification
-> five structurally non-submitting, production-PG-readonly watcher canaries
-> run bounded post-canary fact refresh
-> rerun phase-two readiness and exact-SHA certification
-> republish/verify current projections and enforce the final freshness budget
-> restore the desired lifecycle-mutation policy with a fresh exact-SHA
   certification reference; clear transient oneshot failure state
-> atomically persist and reread the full runtime activation commit while the
   persistent fence and writer quiescence still hold
-> remove the persistent fence only from that commit
-> restore exact timer/backend scheduling policy
-> restore watcher timer to its exact pre-deploy state last
-> close/consume the mutation transaction, then observe five scheduled ticks
```

Expected maintenance duration is **20-30 minutes**. Normal future deploys keep
the same one-command interface; the extra incident-recovery prelude is not part
of every release.

#### Current Incident Recovery Deploy

```text
record durable timer/backend policy and transient incident evidence
-> stop restart storm and timers
-> add the supplementary control-plane swap buffer
-> start PG manually while restart policy remains no
-> verify WAL/SELECT/schema and record exact lifecycle-mutation capability pre-state
-> make one in-container pg_dump after recovery
-> set Docker PG restart policy to unless-stopped only after recovery acceptance
-> run schema-120-compatible explicit safety SQL and read-only exchange reconciliation
-> run the unconstrained candidate benchmark; install watcher resource limits
   only after the program passes
-> execute the normal deploy path
```

The accepted maintenance ceiling remains **one hour**. A slow PostgreSQL
recovery may use that window; it must not be hidden as deployment success.

### 6.7 Active Position Rule

An empty account is not required.

A deploy may continue with an active position only when the pre-switch read
proves all of the following:

1. every real exchange-write attempt is either lifecycle-closed or has exactly
   one matching lifecycle in `position_protected`/`runner_protected`;
2. that nonclosed lifecycle points to the same attempt, ticket, and exit
   protection set, whose protection is complete, exchange-reconciled, and has
   no lifecycle/protection blocker;
3. no real exchange-write attempt lacks that complete safe tuple;
4. no `prepared`, `dispatching`, or `outcome_unknown` exchange command exists;
   a historical terminal `hard_stopped` row blocks only when it still has an
   active domain freeze or belongs to a nonclosed unsafe lifecycle; and
5. writer units are quiesced before release switch.

An unprotected position or unknown exchange outcome stops deployment for
abnormal recovery. Ordinary strategy loss does not.

These gates use indexed `EXISTS(... LIMIT 1)`/correlated anti-joins rooted at
real-write attempts inside a read-only transaction with one-second lock and
five-second statement timeouts. They do not run unbounded historical
`count(*)` scans; a timeout blocks deployment and moves performance diagnosis
outside the mutation path.

### 6.8 Zero-Exchange Deployment Certification

Deploy certification may read PG, account facts, exchange position/open-order
facts, and service state. It must not invoke a maintenance worker after
mutation capability has been enabled merely to assert afterward that no write
occurred.

Certification uses **two non-circular identities**. The pre/post-canary prepare
freezes `ActionTimeCertificationReferenceV2` with schema
`brc.action_time_certification_reference.v2`; stage enum
`pre_canary|post_canary`; target head; canonical input digest schema fixed to
`brc.action_time_capability_certification_input.v1`; canonical input digest;
release-activation ID/watermark; lane outcome identities containing
`lane_scope_key,lane_identity_key,source_watermark,process_outcome_id`, sorted
by `lane_identity_key`; the outcome ID uses the existing deterministic
`process_name|lane_identity_key|source_watermark` hash before insertion; fact
snapshot IDs sorted lexically; fact-set digest schema
fixed to `brc.action_time_fact_set_digest.v1`; fact-set digest and minimum
validity; and deploy nonce. The fact-set digest follows the
exact `ActionTimeFactDigestRowV1` contract in section 6.2. Typed canonical JSON
v1 produces `action-time-cert:v2:<sha256>`. Prepare emits the full payload/ref;
SERIALIZABLE apply rereads inputs, reconstructs the byte-identical payload, and
rejects any mismatch before writing every current lane outcome as
`run_id="certification:<action-time-cert-ref>"`. Current projections are then
published from those outcomes. Golden vectors cover row order, stage, deploy
nonce, null, Unicode, and one-field semantic changes.

Only after publication does the lifecycle setter construct a frozen
`LifecycleMutationEnablementProof` containing target runtime head, the shared
Action-Time certification reference, the complete canonical post-canary
`ActionTimeCertificationReferenceV2` payload, lane-identity digest,
`certification_projection_digest_schema`, and
`certification_projection_digest`.
`certification_projection_digest_schema` is fixed to
`brc.certification_projection_digest.v1`. Its canonical row model is the 22
`brc_runtime_process_outcomes` certification rows selected by the exact
`process_outcome_id` values frozen in the post-canary reference. Each row must
also match that reference's `lane_scope_key`, `lane_identity_key`, and
`source_watermark`, plus
`process_name='action_time_capability_certification'`, with columns
`process_outcome_id`, `process_name`, `scope_key`, `run_id`, `process_state`,
`business_state`, `first_blocker`, `runtime_head`, `source_watermark`, and
`projector_owner`, plus `lane_identity_key`, sorted by `lane_identity_key`.
Exactly one row per frozen identity is required; a historical row at another
watermark, duplicate, missing row, or identity/watermark mismatch fails before
enable. It excludes start/complete/update and
generated-at timestamps. Typed canonical JSON v1 preserves explicit nulls,
rejects float/NaN, and hashes UTF-8 bytes. Row order and same-head republish do
not change the digest; any semantic-column change does.

The projection digest covers
only the target-SHA Action-Time certification-outcome slice and explicitly
excludes `ticket_lifecycle_durable_mutation`, its certification reference, and
any readmodel field derived from that row. The lifecycle reference is therefore
not an input to the projection it hashes. It is
`lifecycle-cert:v2:<sha256(canonical_proof)>`.

Migration 124 adds nullable `proof_schema` and `proof_payload JSONB` to
`brc_runtime_capabilities_current`, plus the invariant that an enabled lifecycle
capability must carry the v2 schema, canonical payload, and matching v2
reference. It also adds two process-outcome indexes: the partial
`idx_brc_runtime_outcome_lane_process_latest` index described above so the
deploy sentinel resolves **current** lane/process rows without reading retained
history, and
`idx_brc_runtime_outcome_canary_window(updated_at_ms DESC,
process_outcome_id DESC)` so all typed-lane, production-scope, and global/legacy
branches first narrow to the frozen recent window instead of scanning lifetime
history. The enable transaction writes all three proof fields together; disable
clears the payload. The payload is bounded to 64 KiB canonical UTF-8 JSON and
contains an exact lane-identity digest rather than unbounded rows. This durable
payload lets runtime validation hash the recorded proof directly; it never
searches history to guess which facts produced a hash.

The enable setter runs one bounded `SERIALIZABLE` transaction and recomputes the
input digest, release activation, current lane watermarks/outcomes and their
shared Action-Time reference, final fact validity, and the non-self-referential
certification-projection identity before updating
`ticket_lifecycle_durable_mutation`. Missing lanes, stale facts, a different
runtime head/watermark/run ID, an old/free-form reference, or any proof mismatch
writes nothing. Runtime capability decisions used by Runtime Safety State,
protected submit, lifecycle maintenance, and the exchange-command worker
hash the stored proof, then verify that its release head, lane-identity digest,
release activation, nested Action-Time payload hash/reference, and shared lane
outcome reference remain current. A normal fact refresh or same-head projection republish does not
invalidate the lifecycle capability merely because snapshot IDs or the
enablement-time projection digest changed; current fact freshness remains a
separate Action-Time gate. Head, lane, release-activation, or Action-Time
certification-reference drift fail-closes the capability before exchange
mutation.

The pre-migration schema-120 path is intentionally narrower. A dedicated
`read_lifecycle_mutation_capability_prestate_v1()` may read only legacy
`status`, `certification_ref`, and timestamp for audit and desired-policy
capture while the journal is `pre_migration`; it never reports runtime readiness
or enables mutation. Fail-safe disable is column-shape-aware: on known revisions
120, 121, 122, and 123 it updates only legacy status/ref, while on schema 124 it
also clears proof fields. Enable is rejected on 120-123 and is valid only on
schema 124 with a verified v2 payload. Normal runtime consumers never use the
legacy reader and reject enabled legacy/free-form references.

The certification sequence is:

1. record the full old `ticket_lifecycle_durable_mutation` row as audit evidence,
   but capture only its **desired enabled/disabled policy** as restoration input;
   also capture exact systemd enablement/activation policy and transient results;
2. engage the persistent fence and keep lifecycle mutation disabled;
3. before migration, verify readiness, blocking commands, position/protection,
   and the existing session role's `pg_has_role(..., 'SET')` ability to assume
   `pg_read_all_data`, followed by an actual `SET ROLE`; verify
   its current-role mutation privileges are false. Any failure stops before
   schema change and does not create/grant a role or mutate a secret;
4. after the durable candidate pointer switch, run
   `record_runtime_release_activation.py` for the exact candidate SHA;
5. run bounded pre-canary fact refresh, then capability-certification prepare
   and SERIALIZABLE digest-revalidate apply for that SHA/activation;
6. run `publish_runtime_control_current_projections.py` and prove the published
   candidate/fact/capability truth names the same fresh inputs and SHA;
7. run the API-only watcher against the dedicated two-route, privilege-reduced
   candidate API five times and prove production PG/exchange identity unchanged;
8. because account facts are valid for only 60 seconds and five canaries may
   exceed that, run a **post-canary bounded fact refresh**, rerun phase-two
   readiness, prepare/apply a new exact-SHA certification digest, and republish/
   verify current projections. This final refresh-to-enable segment has a
   30-second deadline and requires at least 30 seconds remaining validity; one
   bounded repeat is allowed, then it fails contained;
9. if the captured desired policy was disabled, leave
   `ticket_lifecycle_durable_mutation` disabled; if it was enabled, enable it
   only with a **new lifecycle certification reference** bound to the exact SHA,
   shared post-canary Action-Time reference/digest, release-activation identity,
   final facts, and certification-projection digest. Any certification/freshness
   failure leaves it disabled;
10. tear down both canary units; verify all pre-activation safety/certification
   facts; atomically write, fsync, and reread the hash-chained journal entry
   **`runtime_activation_committed`**, embedding `RuntimeActivationCommitV1` with the exact SHA, schema,
   release activation, current projections, lifecycle proof, desired unit
   policy, and final freshness facts. This is the safe irreversible activation
   boundary. Only then remove and directory-fsync the persistent fence, restore
   backend/timer policy by the captured state enumerations, and restore the
   production watcher timer last. Journal `activation_applied` and
   `deploy_transaction_terminal`, consume the deploy manifest, and release the
   mutation lock before the five scheduled ticks, which are post-commit
   stability observation rather than another trading-authority gate.

Incident state uses two linked mode-`0600`, SHA-256-verified manifests. The
**capture manifest** is written before quiescence and is valid for 15 minutes
only to begin maintenance; it records the still-live unit states. Once
quiescence and PostgreSQL recovery allow the exact lifecycle capability row to
be captured, the executor writes a new **sealed restore manifest** linked to the
capture checksum, deploy transaction ID, and deploy nonce. The sealed manifest
is valid for 90 minutes to start migration and is the only restoration input
for that deployment lineage. If `migration_in_progress` is durably journaled
before expiry, the manifest becomes **recovery-pinned**: that same lineage may
use it after 90 minutes only to finish forward recovery and restore the already
captured policy. It cannot start a new deployment, select another SHA, recapture
policy, or expand restoration authority. It is not consumed when first read.
The same host + transaction ID + nonce + old/target SHA may resume a nonterminal
journal idempotently; a different lineage may never reuse it. It becomes
terminally consumed only after the exact runtime activation has been durably
committed and idempotently applied, or after a pre-migration abort has exactly restored the old runtime and recorded
`terminal_aborted_pre_migration`. Ordinary post-migration failed containment
stays nonterminal so the same lineage can resume.

The only cross-lineage exception is an explicit **forward-fix handoff** when a
post-migration, pre-activation defect requires a different exact SHA. While the canonical lock is held, the parent
must be `forward_fix_required`, the fence durable, every writer stopped, and
schema/pointer/head/safety facts unambiguous. It then writes and fsyncs one
mode-`0600` `ForwardFixHandoffV1` bound to the parent manifest checksum, journal
digest, current/new exact SHA, parent/child transaction IDs and nonces, host,
current revision, captured desired lifecycle policy, and typed unit policy. It
transfers no old certification or fact freshness and cannot change scope, risk,
capital, leverage, credentials, or policy. The parent journals
`forward_fix_handoff_sealed` and names exactly one child; the child begins at
`forward_fix_inherited_containment`, reruns current safety/schema checks, then
the complete release-activation/fact/certification/canary/proof/activation path
for its new SHA. Atomic one-child consumption and parent-digest
linkage make crash retry idempotent and reject replay or a second child. This is
a new recovery artifact, not reuse or recapture of the old manifest.

Systemd `UnitFileState`, `ActiveState`, `SubState`, `Result`, `TriggeredBy`, and
`Triggers` are recorded as typed facts, not two booleans. Restoration maps
`enabled`, `disabled`, `static`, and pre-existing `masked` states explicitly. A
static service is accepted only when every owning timer/trigger is in the
captured production-unit allowlist; restoration acts on that owner and never
enables the static service directly. `indirect` is unsupported for this bounded
production graph and blocks before the first mutation. Transient `failed`,
`activating`, or `deactivating` observations are evidence and never a desired
target. The old capability row is likewise audit evidence only. Its
desired policy is restored through the current setter with a fresh
certification reference; no row is copied verbatim. Migration 122/123 owns
`ticket_exit_policy_v1`, whose expected ID/version/hash/status is verified and
never overwritten from schema-120 state. The executor rejects expired or
cross-lineage manifests, wrong state enumerations, and any host ID, transaction
ID, nonce, expected old SHA, captured pointer, approved target SHA, mode,
ownership, completeness, parent checksum, or checksum mismatch.

### 6.8.1 Crash-Safe Migration And Pointer Journal

Before migration, the release-independent control plane installs and hash-
verifies repository-owned `ConditionPathExists=!` drop-ins for every production
backend, watcher, monitor, lifecycle, and related timer/service writer. It then
atomically creates and directory-`fsync`s:

```text
/home/ubuntu/brc-deploy/control-plane/production-writers.blocked
```

The marker is a **boot-persistent deploy fence**. Every deployment and resume
opens the same canonical lock inode:

```text
/var/lib/brc-deploy/deploy-state/tokyo-runtime-deploy.lock
owner=root:root mode=0600 regular-file no-symlink
```

The one mutating SSH command cannot start with candidate Python because a fresh
target has not yet been exported or built. The local executor therefore sends
the exact tracked bytes of one **release-independent, stdlib-only bootstrap**
through a fixed transient service envelope:

```text
sudo -n /usr/bin/systemd-run --wait --pipe --collect
  --service-type=exec --unit=brc-deploy-<transaction-id>.service
  -p KillMode=control-group -p SendSIGKILL=yes -p TimeoutStopSec=30s
  -p RuntimeMaxSec=60min -p Restart=no
  /usr/bin/python3 -c <fixed-hash-loader> ...
```

The fixed `-c` loader reads stdin, verifies the expected SHA-256 before opening
the lock or writing any persistent file, and only then executes the bootstrap.
It verifies CPython 3.10, `EUID=0`, and the noninteractive sudo preflight. The
self-collecting transient unit is the only permitted pre-hash process-container
mutation; a hash/Python/EUID failure creates no persistent deploy/runtime state
and invokes no candidate or production command. SSH loss does not orphan an
uncontained child: the transient service either continues as the sole lock
owner or systemd tears down its complete cgroup.
`RuntimeMaxSec=60min` enforces the accepted outer deploy-session ceiling even if
the bootstrap itself hangs outside a child timeout. Before the persistent fence
is engaged, expiry is `pre_maintenance_abort`: systemd tears down the cgroup,
the pre-existing production runtime/policy remains unchanged, no fence is expected,
and any unreferenced staged release/venv is safe to verify or rebuild on the next
invocation. From durable fence engagement through the phase before
`runtime_activation_committed`, expiry leaves the fence engaged and preserves
the last durable journal phase for same-lineage resume. After that commit,
expiry cannot revoke or weaken the
already-certified exact-SHA activation; reentry may only finish idempotent unit
restoration or continue read-only post-activation observation. Neither case is
reported as postdeploy observation acceptance without the required evidence.
The transaction ID is lowercase hexadecimal and deterministically names the
unit. A read-only preflight that finds the same unit active returns
`deploy_in_progress` without starting a second service; an inactive unit must
already be collected before same-lineage resume.

The only permitted pre-lock mutation is first-install initialization of this
canonical lock hierarchy. Using directory FDs rooted at `/var/lib`,
`O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC`, and relative `mkdir/openat` operations, the
bootstrap creates missing `brc-deploy` and `deploy-state` directories as
`root:root 0700`, then creates the lock once with
`O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC` and mode `0600`. `/var/lib` must be a
root-owned, non-symlink directory that is not group/other writable; existing
managed directories must be `root:root 0700`, and the lock must be a
`root:root 0600` regular file with link count one. A newly created lock is
file-`fsync`ed and its parent directory is `fsync`ed before use. Every newly
created directory entry is also durably committed at its own level:
`fsync(/var/lib)` after `brc-deploy`, `fsync(brc-deploy)` after `deploy-state`,
then file `fsync` plus `fsync(deploy-state)` after the lock. Concurrent
first installers either open the same winning inode or fail closed; no process
may unlink, rename, truncate, chmod, or replace it. This initialization may
create only the hierarchy and lock, never a manifest, fence, release, schema,
pointer, or unit change.

The remote executor then uses `LOCK_EX | LOCK_NB`; a busy
lock returns typed `deploy_in_progress` with zero manifest/fence/schema/pointer/
production-unit mutation; its transient envelope is collected. The same process retains the original file descriptor until
terminal or contained exit. The lock file is never rotated, replaced, or
deleted. A resume and a new lineage contend on that same inode.

While holding that FD, the stdlib-only bootstrap performs approved git
fetch/export, constructs and verifies the immutable candidate venv, and invokes
every repository-owned migration, readiness, certification, projection, and
postdeploy command as a bounded subprocess through the candidate venv Python.
It never imports candidate application code into the bootstrap interpreter and
does not release/reopen the lock when candidate Python becomes available.

The lock is opened `O_CLOEXEC`, then deliberately inherited only by a
mutation-capable child through `pass_fds=(lock_fd,)`. Before `exec`, the child
verifies the FD's device/inode/owner/mode against the canonical path, sets
`PR_SET_PDEATHSIG=SIGKILL`, and rechecks the expected parent PID to close the
fork/death race. Every mutation-capable descendant must use the same guarded
spawn helper and inherit that same open-file description; nonmutating children
do not receive it. Repository commands may not daemonize, double-fork, start a
new session, invoke another `systemd-run`, or move themselves out of the
transient cgroup. Normal failure handling terminates and waits for the complete
child process group before closing the parent FD. If the bootstrap is killed,
the inherited FD keeps the lock busy while systemd's `KillMode=control-group`
removes the old child tree. A new deployment can acquire the lock only after
the old cgroup contains no mutation-capable process. Thus the first R1
deployment works on a host with no candidate directory while all
release-sensitive code still runs under the exact candidate interpreter.

The executor stops all writer
units and proves that an attempted start is skipped by the condition before
Alembic may run. Canary units are disabled and timerless; they are not exempt
from failure cleanup. The executor itself is one remote state-machine process
holding one deploy-wide `flock` for its whole mutation lifetime; the local
planner may open multiple read-only SSH sessions, but no independent SSH command
may mutate export, schema, pointer, manifest, unit, capability, or restore state.

The executor maintains a hash-chained monotonic deploy journal under the same
mode-`0600` deploy-state directory. Every entry includes `sequence`,
`previous_phase`, `previous_digest`, and `entry_digest`; it is written to a
same-directory temporary file, file-`fsync`ed, atomically renamed, and followed
by directory `fsync`. Each atomic journal snapshot retains the complete ordered
entry array for that deployment lineage (maximum 64 phases); no entry is pruned
before terminal consumption. Reentry verifies the whole chain from genesis, so
a skipped or replayed intermediate phase cannot be hidden by overwriting only
the latest state. Legal phases include:

```text
pre_migration
-> migration_in_progress
-> schema_124_requires_candidate
-> candidate_pointer_active
-> release_activation_recorded
-> pre_canary_facts_refreshed
-> pre_canary_capability_certified
-> pre_canary_current_projections_published
-> readonly_canary_accepted
-> post_canary_facts_refreshed
-> post_canary_phase_two_ready
-> post_canary_capability_certified
-> post_canary_current_projections_published
-> final_freshness_verified
-> restore_manifest_verified
-> restore_pending
-> lifecycle_desired_policy_restored
-> runtime_activation_committed
-> activation_applied
-> deploy_transaction_terminal
-> terminal_consumed

schema_124_requires_candidate | candidate_pointer_active |
release_activation_recorded | pre_canary_facts_refreshed |
pre_canary_capability_certified | pre_canary_current_projections_published |
readonly_canary_accepted | post_canary_facts_refreshed |
post_canary_phase_two_ready | post_canary_capability_certified |
post_canary_current_projections_published | final_freshness_verified |
restore_manifest_verified | restore_pending |
lifecycle_desired_policy_restored
-> forward_fix_required
-> forward_fix_handoff_sealed
-> superseded_by_forward_fix

forward_fix_inherited_containment
-> forward_fix_candidate_pointer_active
-> release_activation_recorded
-> pre_canary_facts_refreshed
-> pre_canary_capability_certified
-> pre_canary_current_projections_published
-> readonly_canary_accepted
-> post_canary_facts_refreshed
-> post_canary_phase_two_ready
-> post_canary_capability_certified
-> post_canary_current_projections_published
-> final_freshness_verified
-> restore_manifest_verified
-> restore_pending
-> lifecycle_desired_policy_restored
-> runtime_activation_committed
-> activation_applied
-> deploy_transaction_terminal
-> terminal_consumed

pre_migration
-> terminal_aborted_pre_migration
-> terminal_consumed
```

Journal authority is the monotonic `phase`. **`runtime_activation_committed` is
the single safe irreversible boundary.** Its fsynced entry binds the target SHA,
actual revision 124, durable release activation, exact pre/post fact and
certification references, current-projection digests, final freshness, restored
lifecycle proof/policy, captured unit desired policy, release pointer, and fence
identity. All trading-safety and zero-write canary checks finish before this
entry. The marker may not be removed and no production writer may be restored
until that complete entry is durably reread and verified.

After durable fence engagement, failure before `runtime_activation_committed`
leaves the boot-persistent marker present and every writer stopped. A post-migration, pre-activation defect that
needs a different SHA may advance only to the sealed `ForwardFixHandoffV1` path;
the parent never recaptures policy, changes target SHA in place, or removes the
fence. There is no bounded retry epoch and no automatic post-release deploy-
fence recreation protocol.

After `runtime_activation_committed`, fence removal and typed unit-policy
restoration are idempotent activation completion. If a crash occurs before
unlink, the marker remains and resume completes activation. If it occurs after
the directory-fsynced unlink but before `activation_applied`, reentry verifies
the durable activation commit, confirms the marker absence is authorized, and
finishes the captured unit policy; it does **not** recreate the marker. Under the
crash-consistent local-filesystem/fsync model, marker absence without the atomic
journal entry embedding `RuntimeActivationCommitV1` is unreachable. If storage
corruption nevertheless produces that combination, deployment resume refuses
all mutation and reports a host-isolation/manual-recovery incident; the systemd
path-condition alone is not misrepresented as journal-integrity attestation.
`deploy_transaction_terminal` and manifest consumption follow
successful activation application.

Five scheduled ticks are a separate post-activation observation:
`post_activation_observation_in_progress ->
postdeploy_observation_accepted|postdeploy_observation_degraded` (or
`postdeploy_observation_not_applicable` for an intentionally inactive captured
policy). They determine the final observation report, not trading authority and
not the mutation journal's safe boundary. SIGKILL, `RuntimeMaxSec`, SSH loss, or
host reboot during this observation cannot roll back the activation commit or
trigger synthetic deploy-fence recreation; systemd applies the production unit's own bounded
failure policy, and a degraded result requires diagnosis and a new exact-SHA
release if code repair is needed.
Observation creates no new JSON/Markdown/runtime authority. Tick evidence comes
from existing target-SHA PG process outcomes and exact systemd `InvocationID`
journald records; an interrupted observation restarts from **0/5**. Accepted,
degraded, or not-applicable is emitted only in the deploy result/Owner surface
and is never read by runtime or trading decisions.

Immediately before Alembic starts, the journal records
`migration_in_progress`, the candidate release path/SHA, old pointer, expected
revision 120, deploy transaction/nonce, and persistent-fence facts. After
Alembic commits, the actual revision is recorded as
`schema_124_requires_candidate`; the next action is a release-independent helper
that creates a same-directory temporary symlink, calls `os.replace`, opens and
`fsync`s the `app/` parent directory, rereads the pointer/SHA, and only then
writes `candidate_pointer_active`.

If the executor or host stops between migration and pointer replacement, the
old pointer may remain as **inert crash residue**, but no old code has execution
authority because the persistent marker blocks every writer after reboot. On
restart, the same deployment lineage reacquires the lock, validates the journal,
pointer, and actual Alembic revision, then resumes idempotently. Revision 120
permits pre-migration rollback. A single known revision 121-124 forces the
candidate pointer/forward-fix path. Multiple heads, an unknown/ambiguous
revision, missing/corrupt journal, or digest-chain mismatch remain permanently
fenced and require explicit forward-fix diagnosis; they never trigger an
automatic pointer switch or service start. The marker is removed with parent-
directory `fsync` only after pointer, release activation, current projections,
fresh capability certification, readonly canary, and restore facts all pass.

Before candidate staging, the incident recovery path does not use the old
phase-two verifier because its global terminal-`hard_stopped` predicate is no
longer the accepted safety rule. It runs explicit schema-120-compatible
read-only SQL for prepared/dispatching/unknown commands, active domain holds,
unsafe nonclosed real lifecycles, and unprotected real attempts. The candidate
verifier reruns those semantics after staging and before migration.

The next lifecycle timer tick belongs to normal runtime operation, not to the
deployment transaction. Once the normal watcher timer is restored, an eligible
ticket may legitimately produce an exchange write; that is recorded as normal
runtime activity, never as a deployment side effect.

For the current incident, the read-only snapshot shows the production timers
were enabled/active before maintenance, so exact-state restoration resumes the
runtime without creating new authority. Generic deployments whose recorded
pre-state is disabled finish as `accepted_disabled` and do not manufacture
scheduled-tick evidence.

### 6.9 Failure And Rollback Semantics

| Failure point | Required behavior |
| --- | --- |
| Normal deploy before quiescence | No mutation; report blocked |
| Normal deploy after quiescence but before migration | Under the same lock, restore the old pointer and desired scheduling/capability policy, then durably remove the fence |
| Current incident after maintenance begins | Keep the known-unsafe old watcher and lifecycle writers disabled; never restore the OOM-producing timer on a failed recovery path |
| Any failure after migration 121 begins | Keep **all** production writers and canaries stopped behind the boot-persistent fence; use a known-revision candidate forward-fix only; old pointer may exist only as inert residue |
| Postdeploy PG/readiness failure | Keep backend/watcher/monitor/lifecycle/canary stopped and fenced; do not declare health from `/api/health` alone |
| Watcher canary failure | Stop both canary units, keep all production writers fenced, and leave lifecycle mutation disabled |
| Unknown exchange outcome or missing protection | Stop automated deployment recovery and preserve evidence for abnormal handling |

R1 does not automatically run `alembic downgrade` in production and does not
claim old-code/schema-124 compatibility. The final automatic rollback boundary
is immediately before migration 121; after that boundary every failure path is
a writers-disabled forward fix.

## 7. Performance And Cadence Contract

| Dimension | R1 requirement |
| --- | --- |
| Production cadence | Watcher remains one oneshot every three minutes |
| Candidate PG reads | Four current tables, maximum 256 rows each plus one overflow probe row |
| Runtime API | Server-filter candidate lanes before following all 16-item in-scope keyset pages; one identity page at most 128 KiB; one compact observation at most 512 KiB; full 16 MiB diagnostic mode remains outside production cadence |
| Watcher PG writes | Existing bounded business writes only; R1 does not add a writer |
| Lifecycle capability proof | At most 256 current lane identities/outcomes plus one release activation and bounded final-fact/current-projection rows; indexed, timeout-bounded, no history scan |
| No-signal files | **0 JSON/MD files** |
| Full artifact retention | Zero unless explicitly requested outside production cadence |
| Watcher wall time | 17/33/256 production-shape selected-runtime runs complete with full coverage below 120 seconds; core internal deadline 120 seconds; degraded hard stop 300 seconds |
| Watcher memory | Unconstrained production-shape program peak below 256 MiB; every Tokyo stage below 384 MiB; cgroup hard stop at 512 MiB only as regression containment |
| Subprocess/network timeout | Every pre/main/post process has an explicit budget; the core watcher remains below 120 seconds |
| Disk/retention | Measure current/history size during recovery; current/history redesign is R2 |
| Archive | Manual and Owner-scoped only; no recurring report directory |

The R1 performance proof is query boundedness, functional-parity certification,
a reproducible unconstrained production-shape benchmark, and current production-scale
execution. A cgroup kill or a 60-minute wait without those proofs is not a
passing performance result.

The benchmark runs as a named stdout-only test process. On Linux it resolves the
current cgroup v1/v2 path and rejects the run as evidence when `memory.max` (or
its v1 equivalent) is finite; on macOS it records that cgroups are unavailable.
It normalizes `resource.getrusage().ru_maxrss` units by platform, uses the
default production Python allocator, lazily generates maximum-sized page/
compact responses and 256-KiB satisfied-signal summaries, includes a 100,000-
out-of-scope lexical-tail case and a 250-ms observation latency fixture, and
requires exact coverage, elapsed time below 120 seconds, and absolute peak RSS
below 256 MiB. An optional `PYTHONMALLOC=malloc` comparison is informational
only and cannot satisfy the gate. The same runner executes
from the staged Tokyo candidate venv before migration and before the watcher
cgroup is installed; both local and target-Linux evidence must pass.

## 8. R1 File Boundary

| Responsibility | Files expected to change |
| --- | --- |
| Bounded candidate read | New frozen watcher-candidate readmodel, `src/infrastructure/runtime_control_state_repository.py`, `scripts/runtime_active_observation_monitor.py` |
| API pagination and compact projection | `src/interfaces/api_trading_console.py`, `src/application/strategy_runtime_service.py`, `src/infrastructure/pg_strategy_runtime_repository.py`, `scripts/runtime_first_real_submit_api_flow.py`, `scripts/runtime_signal_watcher_tick.py`, `scripts/runtime_active_observation_monitor.py` |
| Bounded deploy/cert reads | `scripts/validate_runtime_control_state_repository.py`, `scripts/certify_action_time_capability.py`, bounded digest/apply logic in `src/application/action_time/capability_certification.py` |
| PG readiness | New standalone `scripts/check_runtime_postgres_ready.py`, installed by hash at the release-independent control-plane path |
| Service and dependency containment | watcher/monitor/lifecycle units, watcher post-step drop-ins, canonical backend runtime-bound drop-in, and backend stability drop-in under `deploy/systemd/` |
| Readonly canary boundary | New dedicated canary ASGI app/database ports, API-only watcher mode, and exact route/role/privilege tests |
| Deploy safety | `scripts/verify_ticket_lifecycle_phase_two_readiness.py`, `scripts/plan_tokyo_runtime_governance_git_deploy.py`, `scripts/execute_tokyo_runtime_governance_git_deploy.py`, its tracked stdlib-only remote bootstrap, plus release-independent persistent-fence and durable-pointer helpers |
| Postdeploy truth | `scripts/verify_tokyo_runtime_governance_postdeploy.py` |
| Durable lifecycle enablement proof | New revision-124 migration, `src/application/action_time/lifecycle_mutation_capability.py`, and all runtime consumers of that capability decision |
| Deployment authority contract | `docs/current/TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md` updated in the same implementation commit to replace its older PG-only invocation and enable/publish order |
| Regression | Focused unit/integration tests plus the stdout-only production-shape runner under `tests/performance/` |

R1 must not modify strategy semantics, execution sizing, exit-policy values,
`exchange_gateway.py`, credentials, environment secrets, or production scope.

## 9. Acceptance

### 9.1 Local Acceptance

1. SQL-capture tests prove candidate-universe construction executes only four
   allowed table queries, selects only explicit fields, and gives every query a
   predicate and limit.
2. Overflow at candidate-universe row 257 fails without truncation; narrow/full
   reader invalid-binding and cross-table identity fixtures fail identically.
3. Candidate-matched identity pagination discovers 17, 33, and 256 in-scope
   rows exactly once with monotonic cursors; 100,000 out-of-scope rows do not
   add client pages or hide a lexical-tail candidate; the existing full endpoint
   remains compatible.
4. Oversized success and error HTTP responses stop at the endpoint-specific
   limit plus one byte: 128 KiB per identity page, 512 KiB per compact
   observation, and 16 MiB only for explicit full diagnostics.
5. `include_runtime_artifacts=false` retains no full artifact list or arbitrary
   safety map, but retains the bounded typed Action-Time decision projection.
   Full and compact paths produce the same lane coverage, statuses, blockers,
   signal identities, safety booleans, live-signal payload, per-RequiredFact
   values/validity/missing/failed sets, Action-Time blockers, and Ticket readiness
   across all active lanes. Missing/non-boolean safety or truncated/oversized
   decision facts fail instead of being coerced or silently dropped.
6. With cgroup memory limits disabled, a production-shape 256-runtime fixture
   peaks below 256 MiB, finishes below 120 seconds, and processes every selected
   runtime exactly once. A 100,000-row out-of-scope inventory returns only exact
   count and a 32-ID sample, still discovers lexical-tail candidates, and
   completes below 120 seconds. The same benchmark must pass locally and
   from the staged Tokyo venv before any MemoryHigh/MemoryMax assertion is
   considered.
7. Deploy-validation and capability-certification SQL-capture tests prove their
   explicit table/column allowlists, predicates, limits, and overflow behavior;
   no 42-table profile is called. Prepare/apply independently rehash the exact
   `ActionTimeFactDigestRowV1` set under
   `brc.action_time_fact_set_digest.v1`; duplicate/missing/extra IDs, semantic
   JSON/numeric mutation, or byte overflow writes zero certification outcomes.
8. Systemd and behavior tests prove memory, per-stage timeout, the core's
   cumulative 120-second deadline, release-bound venv, and PG readiness for
   backend/watcher/canary/monitor/lifecycle.
9. Canary tests prove the dedicated server route set has exactly two shapes,
   every reachable engine runs as `pg_read_all_data`, direct DML under that role
   fails, SQL capture contains zero role-reset/read-write escalation statement,
   the watcher has no direct PG/fact/materializer port, and all writer/gateway
   counters, bounded sentinel deltas, and exchange deltas are zero. Every
   sentinel query is identity-scoped, limit-bounded, and timeout-bounded. Tests
   mutate fact/signal JSON, confidence, protection generation, every full
   process-outcome column, an unknown canary-window process, and an unknown
   Ticket/command/order status and observe a delta or typed failure; the release
   and all four current-projection relations use their frozen predicates,
   columns, and limits. Tests do not mislabel the recoverable production login
   as credential isolation.
10. Deployment tests prove `prepared` commands block; disabled capability stays
   disabled; enabled capability is restored only with a new exact-SHA
   certification reference plus durable proof payload; normal fact refresh and
   same-head projection publication do not invalidate it, while head/lane/
   Action-Time reference drift does. Static services restore only through their
   captured owning timer/trigger, `indirect` blocks before mutation, and
   transient failures are not recreated.
11. Failure/reboot tests prove the marker blocks every writer across host
   restart; a fresh root-owned `/var/lib/brc-deploy/deploy-state` hierarchy and
   lock are initialized once through verified dirfds, two concurrent first
   installers contend on one inode, one remote executor holds the canonical
   nonblocking deploy-lock FD, and a competitor performs zero persistent deploy/
   runtime mutation apart from its self-collected transient envelope;
   every mutation child inherits and verifies the same FD, and parent `SIGKILL`
   or SSH loss keeps a competitor at `deploy_in_progress` until the original
   transient cgroup and all lock-holding descendants are gone;
   release/venv contents pass bounded
   syncfs plus reread before pointer switch; pointer rename fsyncs the parent
   before journal advance; hash-chain phases cannot skip/replay; same-
   lineage and recovery-pinned manifest resume is idempotent;
   `runtime_activation_committed` is fsynced while the marker is still present;
   commit-before-unlink and unlink-before-`activation_applied` crashes complete
   idempotently; an out-of-model marker/journal corruption makes deploy resume
   refuse mutation and report host isolation/manual recovery without claiming
   the systemd condition validates journal content;
   pre-fence `SIGKILL`, `RuntimeMaxSec`, or SSH loss returns
   `pre_maintenance_abort` with pre-existing production policy unchanged; fenced
   pre-commit failure remains resumable behind the marker; and post-commit
   `SIGKILL`, `RuntimeMaxSec`, SSH loss, or reboot never fabricates
   observation acceptance or automatic deploy-fence recreation. A fenced post-migration,
   pre-activation parent can create only one atomic parent-digest-bound
   `ForwardFixHandoffV1`; replay, second child, policy recapture, or
   certification/freshness transfer fails, while the named child must rerun the
   complete activation path. Five target-SHA scheduled ticks are resumable post-
   activation observation and failures become a degraded observation, not a
   trading-authority rollback. A fresh-host
   fixture with no candidate directory launches through the SHA-verified
   stdlib-only `/usr/bin/python3` bootstrap, holds one lock FD while building the
   candidate, and runs every release-sensitive child through candidate Python;
   bootstrap hash mismatch performs zero persistent lock/manifest/fence/schema/
   pointer/production-unit mutation and collects its transient envelope.
12. Postdeploy tests prove real PG readiness, actual Alembic revision `124`,
   CCXT `4.5.56`, exact SHA, Docker restart policy, and watcher unit limits.
13. Existing approved SOR-LONG future-Ticket exit-policy regression remains
   green; R1 adds no further parameter change.
14. Focused tests, full pytest, `git diff --check`, output-scope validation, and
   production file-I/O audit pass.

### 9.2 Tokyo Acceptance

1. PostgreSQL starts under Docker `unless-stopped` and passes real `SELECT 1`.
2. Before migration, the disposable canary session proves
   `pg_has_role(session_user, 'pg_read_all_data', 'SET')`, actual `SET ROLE`,
   exact current user, SELECT access, and absence of DML/TRUNCATE/sequence-write
   privileges. Any failure leaves schema 120 unchanged.
3. Actual Alembic revision is `124` after migration; revision 124 proof columns,
   partial latest-process-outcome index, and `updated_at_ms`-leading canary-window
   index exist, and the migration leaves
   lifecycle mutation disabled pending restore.
4. Exchange/PG read-only reconciliation reports no unprotected or unknown
   state.
5. The deploy report contains exact IDs/digests for the pre-canary fact refresh,
   pre-canary Action-Time certification, and pre-canary current projections.
   Five API-only, privilege-reduced, structurally non-submitting canary one-
   shots then succeed with zero bounded-sentinel or exchange delta.
6. The report then contains the post-canary fact refresh IDs/digest, phase-two
   readiness result, post-canary Action-Time certification ref/digest, and
   post-canary certification-projection digest/head. Final refresh-to-enable
   elapsed time is at most 30 seconds and every required fact retains at least
   30 seconds validity; at most one bounded repeat is accepted.
7. When the captured watcher policy is active, after
   `runtime_activation_committed` five consecutive target-SHA scheduled ticks,
   approximately 15 minutes, succeed as post-activation stability observation.
   When that policy is intentionally inactive, the exact policy/SHA evidence
   produces `postdeploy_observation_not_applicable` instead of fabricated ticks.
   Neither result grants trading authority.
8. For active-policy ticks, every journal-tagged stage max RSS is below 384 MiB; the cgroup limits
   equal 384/512 MiB; the core watcher is below 120 seconds; the complete
   oneshot remains within its stage and systemd budgets; and there is no OOM,
   exit 137, timeout, or child-process leak. This containment evidence is valid
   only after the unconstrained local program benchmark passes.
9. Deployed head equals the new full 40-character repair SHA.
10. Exact-SHA handler tests report zero Ticket/authority/FinalGate/Operation/
   dispatcher/gateway calls, and each Tokyo canary reports the dedicated two-
   route server graph, `pg_read_all_data` current role, direct DML denial, zero
   escalation statement, and unchanged bounded PG sentinel/exchange identity.
   Scheduled post-activation runtime may trade only through the unchanged
   policy, Ticket, FinalGate, and Operation Layer path.
11. Lifecycle mutation equals its captured enabled/disabled policy. When
   enabled, the stored v2 reference hashes the persisted proof payload and
   verifies the deployed SHA, lane digest, release activation, and shared post-
   canary Action-Time ref. Timer/backend policy equals its typed pre-deploy
   state; transient oneshots are inactive/success; the persistent fence is
   absent only after the durable activation commit.
12. The terminal mutation journal records `runtime_activation_committed`,
   `activation_applied`, `deploy_transaction_terminal`, and
   `terminal_consumed`. Scheduled observation separately records exact target-
   SHA tick identities and `postdeploy_observation_accepted`,
   `postdeploy_observation_degraded`, or
   `postdeploy_observation_not_applicable`; it cannot reopen the mutation journal
   or recreate the deploy fence.
13. Deployment reports zero new profile mutation, zero sizing mutation, and
    zero scope expansion; revision 123's previously approved SOR-LONG
    future-Ticket policy is reported separately as a known release effect.
14. The previous release has a verified executable `.venv` compatibility
    binding before unit replacement; both interpreters execute the shared
    readiness helper; candidate migration runs from the candidate directory;
    automatic old-code rollback is limited to the pre-migration boundary.
15. Release activation and current projections name the exact deployed SHA;
    pointer parent-directory durability and the activation-commit receipt are
    verified before the fence is removed or any production unit is restored.
    Terminal manifest consumption follows idempotent policy restoration and
    precedes post-activation scheduled observation.

## 10. Live Enablement And Owner Boundary

| Item | Before R1 | After R1 |
| --- | --- | --- |
| Chain position | Runtime infrastructure unavailable; PG down; watcher unsafe | Runtime infrastructure healthy; normal lane state may be running, waiting, or processing |
| Blocker removed | `hard_safety_stop` / infrastructure unavailability | OOM and PG-start defects removed; market or actual lane blocker becomes visible again |
| Strategy authority | Deployed schema 120; SOR-LONG future-ticket exit policy not yet active | Previously approved revision 123 policy becomes active; R1 adds no further parameter or scope change |
| Real-submit authority | Not granted by deployment | Still granted only by current policy, Runtime Safety State, FinalGate, and Operation Layer |
| Owner operation | Manual incident supervision | One deploy command; normal runtime resumes automatically |

No further Owner policy decision is required for R1 implementation. Approval of
this design authorizes technical implementation and bounded deployment of the
new exact-SHA release after tests pass. Implementation must stop and report
only if recovery discovers an unprotected real position, an unknown exchange
outcome, database corruption, secret mutation need, or a requested strategy /
capital / leverage / scope change.

## 11. R2 Deferred Backlog

R2 may later address:

1. current/history table split and material-change-only history;
2. production retention scheduling and row-growth budgets;
3. PostgreSQL-independent infrastructure notification;
4. all-service cgroup slice and capacity model;
5. broader dependency-cache pruning and old-venv retention automation;
6. host-reboot and long-horizon growth certification;
7. optional host resize from approximately 4 GiB to 8 GiB.

R2 is not a prerequisite for restoring and deploying the latest R1 runtime.
Its first input is a **seven-day row-count and disk-growth review** after R1.
At the existing three-minute cadence there can be 480 ticks per day; any table
that appends once for each of the current 22 lanes could theoretically add
10,560 rows per day. This is a capacity upper-bound inference, not a measured
production rate, and must be replaced with the seven-day PG measurement before
retention work is scoped.
