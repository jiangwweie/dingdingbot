# P0 Runtime Stability And Simplified Tokyo Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and deploy one exact-SHA R1 release that runs the current
low-frequency StrategyGroup runtime without watcher OOM, PostgreSQL boot drift,
backend restart storms, or deployment-time exchange writes.

**Architecture:** Replace the watcher full control-state scan with a dedicated
four-table current-only repository method, server-filter and page candidate-
matched runtime identities, transport a typed compact observation projection
that preserves Action-Time decision facts, and prove full-chain semantic parity and
memory behavior before applying systemd containment as a final fault boundary.
Docker owns PostgreSQL restart, and the existing Tokyo deploy planner is repaired
rather than duplicated. Normal deployment remains one command; the current
incident adds a one-time recovery prelude before that command.

**Tech Stack:** Python 3, SQLAlchemy 2, psycopg 3, PostgreSQL 16, FastAPI,
pytest, systemd 249, Docker Engine, Alembic, CCXT 4.5.56, SSH.

## Global Constraints

1. **No new R1 strategy change:** R1 adds no entry, exit, TP1, runner, leverage,
   sizing, capital, symbol, side, Event Spec, runtime-profile, or Owner-policy
   parameter change. The complete 120-to-124 release still activates the
   previously Owner-approved SOR-LONG future-Ticket exit policy in revision 123;
   revision 124 persists the lifecycle enablement proof and adds the bounded
   deploy-sentinel latest-current and recent-window process-outcome indexes;
   neither changes strategy
   parameters.
2. **No authority expansion:** deployment never calls FinalGate, Operation
   Layer submit, exchange mutation, withdrawal, transfer, credential mutation,
   or scope expansion.
3. **PG/current only:** no JSON/Markdown/output fallback or recurring report
   writer is added.
4. **One deployment path:** modify the existing Tokyo git deploy planner and
   executor; do not add a parallel deploy script.
5. **One PostgreSQL owner:** Docker `unless-stopped` owns container restart;
   systemd performs readiness checks but does not start the same container.
6. **TDD:** every behavior change begins with a focused failing test.
7. **Program optimization first:** production uses 16-item keyset pages and a
   512-KiB typed compact observation response, traverses every page, and has no
   performance-motivated runtime-count cap. A cgroup-free 256-runtime fixture
   must peak below 256 MiB before `MemoryHigh=384M`/`MemoryMax=512M` are accepted
   as final containment.
8. **No automatic production downgrade:** post-migration failure remains
   fail-closed unless backward compatibility has been explicitly certified.
9. **Production cadence:** one no-signal tick creates zero JSON/MD files and no
   new recurring subprocess chain.
10. **Boot-persistent deployment interlock:** schema, pointer, release identity,
    projection, capability, and service mutations run inside one remote locked
    state machine. A persistent writer-fence marker—not a runtime mask—blocks
    old and new production writers across reboot until the atomic runtime
    activation commit is durable and verified.
11. **No feature removal as a performance technique:** enabled strategy,
    symbol, side, fact, protection, exit, runner, and observation semantics stay
    intact. Compact transport removes only duplicated/unconsumed representation.

---

## Execution Packet

| Field | Value |
| --- | --- |
| **Task ID** | `P0-RS-SD-R1` |
| **Goal** | Restore and deploy the latest runtime on Tokyo with bounded watcher and simple repeatable deployment |
| **Why** | The previous boot recorded watcher OOM and PostgreSQL did not restart; current candidate does not repair either defect |
| **Allowed files** | Files explicitly named in Tasks 1-7 |
| **Forbidden files** | Strategy research, Owner policy data, credentials, sizing profiles, `src/infrastructure/exchange_gateway.py`, and unrelated lifecycle semantics |
| **Global Authority Model** | Owner controls policy; system executes process; deployment grants no trading authority |
| **Chain Position Before** | Runtime infrastructure unavailable / unsafe; PostgreSQL down; watcher unbounded |
| **Chain Position After** | Runtime infrastructure healthy; real lane state can return to running, waiting, or protected processing |
| **Blocker Removed** | Host OOM recurrence path, PG boot drift, backend restart storm, and deployment exchange-write ambiguity |
| **Per-Symbol / Per-Fact Acceptance** | All existing 22 lane identities and scope rows remain unchanged; revision 123's approved SOR-LONG future-Ticket exit-policy binding is verified separately |
| **Stop Condition** | Unprotected position, unknown exchange outcome, DB corruption, secret change, or strategy/risk/scope change is discovered |
| **Capability Unlocked** | Latest exact-SHA runtime can start and remain observable on the existing Tokyo host |
| **Next Engineering Bottleneck** | Natural live lifecycle calibration or R2 retention hardening, whichever becomes factual first |
| **Rehearsal Boundary** | Local and postdeploy certification may read exchange facts but must call FinalGate, Operation Layer, dispatcher, and exchange gateway zero times |
| **Done When** | Local gates pass, Tokyo exact SHA and revision 124 are proven, and an active captured watcher policy completes five scheduled ticks within budgets; an intentionally inactive policy emits verified not-applicable evidence |
| **Hard Stop** | Duplicate-submit risk, unknown outcome, missing protection, or damaged PG authority |

---

## File Map

| File | Responsibility in R1 |
| --- | --- |
| `src/application/readmodels/watcher_candidate_universe.py` | Frozen explicit-field watcher candidate projection |
| `src/application/readmodels/watcher_decision_fact_projection.py` | Frozen bounded Action-Time decision facts carried by compact observation |
| `src/infrastructure/runtime_control_state_repository.py` | Explicit-column watcher, deploy-validation, and capability-certification profiles |
| `src/interfaces/api_trading_console.py` | Add structurally read-only candidate-matched runtime paging and compact observation projection |
| `src/interfaces/api_canary_readonly.py` | Dedicated deny-by-default two-route canary ASGI graph |
| `src/infrastructure/canary_readonly_database.py` | Dedicated privilege-reduced canary engine/ports and startup privilege proof |
| `src/application/readmodels/canary_mutation_sentinel.py` | Frozen identity-scoped tables, predicates, columns, limits, and canonical digest for canary defense-in-depth |
| `src/application/strategy_runtime_service.py` | Expose the typed candidate-matched watcher page without changing the existing full-list contract |
| `src/infrastructure/pg_strategy_runtime_repository.py` | Explicit-column keyset page ordered by immutable runtime ID |
| `scripts/runtime_active_observation_monitor.py` | Traverse all candidate-matched pages, consume compact projection, and retain bounded decision facts plus boolean-only effects |
| `scripts/runtime_first_real_submit_api_flow.py` | Shared bounded HTTP JSON response read |
| `scripts/runtime_signal_watcher_tick.py` | Global 120-second deadline and typed incomplete-tick result |
| `scripts/validate_runtime_control_state_repository.py` | Deploy validation through an explicit allowlist profile |
| `scripts/certify_action_time_capability.py` | Capability certification through an identity-driven allowlist profile |
| `src/application/action_time/capability_certification.py` | Digest-bound atomic capability outcome apply |
| `scripts/publish_runtime_control_current_projections.py` | Publish the three current projections with exact target-SHA lineage and bounded semantic payloads |
| `src/application/action_time/lifecycle_mutation_capability.py` | Typed v2 enablement proof and runtime currentness verification |
| `migrations/versions/2026-07-15-124_persist_lifecycle_mutation_enablement_proof.py` | Durable bounded v2 proof payload plus current-latest and recent-window process-outcome sentinel indexes; capability remains disabled until certified restore |
| `scripts/check_runtime_postgres_ready.py` | Bounded real PostgreSQL `SELECT 1` readiness probe |
| Repository-owned files under `deploy/systemd/` | Watcher memory/time/process containment and release-bound `app/current/.venv` interpreter |
| `deploy/systemd/brc-owner-console-backend.service.d/10-runtime-bound.conf` | Canonical backend `ExecStart` through release-bound `.venv` |
| `deploy/systemd/brc-owner-console-backend.service.d/40-runtime-stability.conf` | PG readiness and backend restart limiting |
| `scripts/verify_ticket_lifecycle_phase_two_readiness.py` | Block all critical pre-dispatch command states |
| `scripts/plan_tokyo_runtime_governance_git_deploy.py` | Docker policy, quiescence, zero-exchange certification, fail-closed phases |
| `scripts/execute_tokyo_runtime_governance_git_deploy.py` | Failure containment and one-result execution report |
| `scripts/tokyo_runtime_deploy_remote_state_machine.py` | Tracked stdlib-only stdin bootstrap that acquires the canonical root lock before staging and drives candidate-venv subprocesses |
| `scripts/set_production_writer_fence.py` | Atomic boot-persistent writer marker create/remove and unit-condition verification |
| `scripts/atomic_switch_release_pointer.py` | Same-directory pointer replace, parent-directory fsync, and exact-SHA reread |
| `scripts/verify_tokyo_runtime_governance_postdeploy.py` | PG, Alembic, Docker, systemd, exact-SHA and dependency verification |
| `docs/current/TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md` | Replace the older PG-only lifecycle invocation and enable/publish order with the approved zero-exchange state machine |
| Focused tests named below | Negative and production-shape proof |

---

### Task 1: Add Explicit Watcher, Deploy, And Certification Read Profiles

**Files:**

- Create: `src/application/readmodels/watcher_candidate_universe.py`
- Modify: `src/infrastructure/runtime_control_state_repository.py`
- Modify: `scripts/runtime_active_observation_monitor.py` near
  `_read_candidate_universe_from_pg` and its process-outcome writer
- Modify: `tests/unit/test_runtime_control_state_repository.py`
- Modify: `tests/unit/test_runtime_active_observation_monitor.py`
- Modify: `scripts/validate_runtime_control_state_repository.py`
- Modify: `scripts/certify_action_time_capability.py`
- Modify: `src/application/action_time/capability_certification.py`
- Modify: `src/application/runtime_lane_identity_service.py`
- Modify: `src/application/action_time/fact_snapshots.py`
- Modify: `src/application/action_time/promotion_action_time_lane.py`
- Modify: `src/application/action_time/ticket_materialization_sequence.py`
- Modify: `scripts/publish_runtime_control_current_projections.py`
- Create: `tests/unit/test_validate_runtime_control_state_repository.py`
- Modify: `tests/unit/test_certify_action_time_capability.py`
- Modify: `tests/unit/test_action_time_capability_certification.py`
- Modify: `tests/unit/test_certify_action_time_capability_script.py`
- Modify: `tests/unit/test_runtime_control_current_projection_publish.py`
- Modify: `tests/unit/test_runtime_lane_identity_service.py`
- Modify: `tests/unit/test_action_time_fact_snapshots.py`
- Modify: `tests/unit/test_promotion_action_time_lane.py`
- Modify: `tests/unit/test_action_time_ticket_materialization_sequence.py`

**Interfaces:**

- Produces:
  `PgBackedRuntimeControlStateRepository.read_watcher_candidate_universe_current(*, row_limit_per_table: int = 256) -> WatcherCandidateUniverseCurrentProjection`.
- `WatcherCandidateUniverseCurrentProjection` and each row DTO use
  `ConfigDict(extra="forbid", frozen=True)`; the repository cannot return
  unexpected metadata/JSON fields.
- Produces:
  `read_deploy_validation_state(*, row_limit_per_table: int = 256) -> dict[str, Any]`.
- Produces:
  `read_action_time_capability_certification_state(*, identity_limit: int = 256, fact_limit: int = 2048) -> dict[str, Any]`.
- Produces:
  `read_action_time_fact_digest_rows(*, expected_fact_snapshot_ids: tuple[str, ...], row_limit: int = 128) -> tuple[ActionTimeFactDigestRowV1, ...]`.
- Consumes: existing `_candidate_universe_from_control_state()` payload shape.
- Invariant: no call to `read_control_state()` or iteration over
  `CONTROL_STATE_TABLES` occurs in watcher candidate discovery.
- Invariant: deployment validation and Action-Time capability certification use
  only their named allowlists. They must not call `read_control_state()`,
  `read_monitor_control_state()`, `read_action_time_control_state()`, or iterate
  `CONTROL_STATE_TABLES`.
- Invariant: watcher and deploy-validation reads, plus capability-certification
  prepare reads, run in a read-only transaction with `lock_timeout='1s'` and
  `statement_timeout='5s'`; timeout never invokes a legacy reader. Capability
  certification apply uses a separate bounded `SERIALIZABLE` read-write
  transaction, re-reads the exact profile, compares the prepared input digest,
  and writes process outcomes atomically. It never writes from the read-only
  transaction.
- Invariant: the fact-digest reader accepts the full expected ID set from the
  bounded fact-refresh result, uses one exact `IN` query with explicit columns,
  `LIMIT 129`, logical JSON byte guards, and rejects duplicate/missing/extra
  rows. Both prepare and apply invoke it and recompute
  `brc.action_time_fact_set_digest.v1`; matching IDs without matching content
  never certify.
- Invariant: the narrow and full readers share one validator for unique active
  candidate IDs, exactly one active event binding and runtime binding per active
  candidate, referential integrity, and StrategyGroup/symbol/side identity.
  Duplicate dictionary keys and identity mismatches are typed failures, never
  last-write-wins or skipped rows.
- Invariant: current projection publication receives the exact target runtime
  head, persists it as `brc_projection_runs.code_version` and inside each
  current snapshot lineage payload, and rejects `"current"`, blank, or a
  different SHA. Timestamp fields remain available operationally but are
  excluded from the canary semantic digest.

- [ ] **Step 1: Write repository RED tests**

Add tests that create only the four required tables and therefore fail if the
new method tries to require or reflect any other control-state table:

```python
def test_watcher_candidate_read_uses_only_four_current_tables(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'watcher.db'}")
    with engine.begin() as conn:
        create_watcher_candidate_tables(conn)
        seed_active_and_historical_candidate_rows(conn)
        state = PgBackedRuntimeControlStateRepository(
            conn,
            now_ms=1_000,
        ).read_watcher_candidate_universe_current()

    payload = state.model_dump(mode="python")
    assert set(payload) >= {
        "schema",
        "source_mode",
        "projection_target",
        "candidate_scope",
        "candidate_scope_event_bindings",
        "runtime_scope_bindings",
        "strategy_side_event_specs",
    }
    assert {row["status"] for row in payload["candidate_scope"]} == {"active"}
    assert {row["status"] for row in payload["strategy_side_event_specs"]} == {"current"}
```

Add a separate overflow test with 257 active rows:

```python
with pytest.raises(
    RuntimeControlStateRepositoryError,
    match="watcher_candidate_row_limit_exceeded:candidate_scope:256",
):
    repository.read_watcher_candidate_universe_current(row_limit_per_table=256)
```

Add parametrized RED fixtures for duplicate candidate IDs, zero/two active event
bindings, zero/two active runtime bindings, missing current Event Spec, orphaned
runtime binding, and every StrategyGroup/symbol/side mismatch. Run each fixture
through the full current reader and the narrow watcher reader and require the
same typed failure class and reason. A consumer-level test proves no invalid row
can become a lane through dictionary overwrite or mismatch skipping.

- [ ] **Step 2: Run the RED tests**

Run:

```bash
python3 -m pytest -q \
  tests/unit/test_runtime_control_state_repository.py \
  -k 'watcher_candidate_read'
```

Expected: failure because
`read_watcher_candidate_universe_current` does not exist.

- [ ] **Step 3: Implement the bounded repository profile**

Add the exact logical profile and helper:

```python
WATCHER_CANDIDATE_PROFILE: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "candidate_scope": (
        "brc_strategy_group_candidate_scope",
        "active",
        (
            "candidate_scope_id", "strategy_group_id", "symbol",
            "asset_class", "side", "policy_current_id", "status",
        ),
    ),
    "candidate_scope_event_bindings": (
        "brc_candidate_scope_event_bindings",
        "active",
        (
            "binding_id", "candidate_scope_id", "event_spec_id",
            "strategy_group_id", "symbol", "side", "status",
        ),
    ),
    "runtime_scope_bindings": (
        "brc_runtime_scope_bindings",
        "active",
        (
            "runtime_scope_binding_id", "candidate_scope_id",
            "strategy_group_id", "symbol", "side", "runtime_profile_id",
            "status",
        ),
    ),
    "strategy_side_event_specs": (
        "brc_strategy_side_event_specs",
        "current",
        (
            "event_spec_id", "strategy_group_id", "strategy_group_version_id",
            "side", "event_spec_version", "event_id", "timeframe",
            "time_authority", "status",
        ),
    ),
}

def read_watcher_candidate_universe_current(
    self,
    *,
    row_limit_per_table: int = 256,
) -> WatcherCandidateUniverseCurrentProjection:
    if row_limit_per_table < 1:
        raise RuntimeControlStateRepositoryError(
            "watcher_candidate_row_limit_must_be_positive"
        )
    inspector = sa.inspect(self.conn)
    existing = set(inspector.get_table_names())
    missing = sorted(
        table_name
        for table_name, _status, _columns in WATCHER_CANDIDATE_PROFILE.values()
        if table_name not in existing
    )
    if missing:
        raise RuntimeControlStateRepositoryError(
            "PG watcher candidate tables missing: " + ", ".join(missing)
        )

    rows: dict[str, list[dict[str, Any]]] = {}
    for logical_key, (table_name, status, column_names) in WATCHER_CANDIDATE_PROFILE.items():
        table = sa.Table(table_name, sa.MetaData(), autoload_with=self.conn)
        statement = (
            sa.select(*(table.c[name] for name in column_names))
            .where(table.c.status == status)
            .order_by(*list(table.primary_key.columns))
            .limit(row_limit_per_table + 1)
        )
        selected = [
            {key: _json_safe(value) for key, value in row.items()}
            for row in self.conn.execute(statement).mappings()
        ]
        if len(selected) > row_limit_per_table:
            raise RuntimeControlStateRepositoryError(
                f"watcher_candidate_row_limit_exceeded:{logical_key}:"
                f"{row_limit_per_table}"
            )
        rows[logical_key] = selected

    projection = WatcherCandidateUniverseCurrentProjection.model_validate({
        "schema": "brc.watcher_candidate_universe_current.v1",
        "source_mode": self.source_mode,
        "projection_target": self.projection_target,
        "read_now_ms": self.now_ms,
        **rows,
    })
    self._validate_watcher_candidate_universe_current(
        projection.model_dump(mode="python")
    )
    return projection
```

Extract the four-table integrity checks into one shared pure validator and call
it from both the existing full reader and the narrow reader. Where the existing
full reader currently builds a dictionary before detecting duplicate active
bindings, validate the grouped rows first. Do not weaken the full-reader
contract merely to make parity pass.

If one of the four tables lacks a `status` column in the real reflected schema,
the RED test must stay and the profile must use that table's actual current
predicate rather than removing the bound.

Implement the other two profiles without reusing `_read_bounded_current_state`:

| Profile | Exact row-table allowlist | Row ceiling |
| --- | --- | ---: |
| `deploy_validation` | four watcher tables plus `brc_current_projection_ownership` | 256 each plus overflow row |
| `action_time_capability_certification` | `brc_strategy_groups`, `brc_strategy_group_versions`, `strategy_runtime_instances`, four watcher tables, `brc_owner_policy_current`, `brc_strategy_event_required_facts`, `brc_runtime_process_outcomes` | 256 identity rows per table, 2,048 fact rows, one latest release-activation row |

Implement the capability constants from this exact matrix; no extra column may
be selected:

| Table | Selected columns | WHERE / ORDER BY | Base / probe |
| --- | --- | --- | ---: |
| `brc_strategy_groups` | `strategy_group_id,current_version_id,status` | `status='active'`; PK ASC | 256 / 257 |
| `brc_strategy_group_versions` | `strategy_group_version_id,strategy_group_id,status` | referenced IDs and `status='current'`; PK ASC | 256 / 257 |
| `strategy_runtime_instances` | `runtime_instance_id,strategy_family_id,strategy_family_version_id,symbol,side,status` | exact active candidate `(strategy_group_id,symbol,side)` keys mapped to `strategy_family_id,symbol,side`, and `status='active'`; PK ASC | 256 / 257 |
| `brc_strategy_group_candidate_scope` | `candidate_scope_id,strategy_group_id,symbol,asset_class,side,policy_current_id,priority_rank,status` | `status='active'`; PK ASC | 256 / 257 |
| `brc_candidate_scope_event_bindings` | `binding_id,candidate_scope_id,event_spec_id,strategy_group_id,symbol,side,status` | referenced candidate IDs and `status='active'`; PK ASC | 256 / 257 |
| `brc_runtime_scope_bindings` | `runtime_scope_binding_id,candidate_scope_id,strategy_group_id,symbol,side,policy_current_id,runtime_profile_id,selected_strategygroup_scope,symbol_side_scope_closed,notional_leverage_scope_closed,live_submit_allowed,server_runtime_coverage_required,status`; guarded `conditional_hard_gates`; `conditional_hard_gates_bytes` | referenced candidate IDs and `status='active'`; PK ASC; logical UTF-8 bytes over 16 KiB fail typed | 256 / 257 |
| `brc_strategy_side_event_specs` | `event_spec_id,strategy_group_id,strategy_group_version_id,event_spec_version,event_id,side,timeframe,execution_eligibility_enabled,declared_signal_grade,declared_required_execution_mode,freshness_window_ms,time_authority,protection_ref_type,status` | referenced event IDs and `status='current'`; PK ASC | 256 / 257 |
| `brc_owner_policy_current` | `policy_current_id,strategy_group_id,symbol,side,runtime_profile_id,enabled_state,pretrade_candidate_allowed,action_time_rehearsal_allowed,live_submit_allowed,planned_stop_risk_fraction,max_initial_margin_utilization,max_leverage,attempt_cap`; guarded `policy_event_ids`; `policy_event_ids_bytes` | referenced policy IDs; PK ASC; logical UTF-8 bytes over 16 KiB fail typed | 256 / 257 |
| `brc_strategy_event_required_facts` | `event_required_fact_id,event_spec_id,required_facts_version_id,fact_key,fact_role,fact_surface,operator`; guarded `expected_value`; `expected_value_bytes`; `disable_on_match,freshness_ms,required_for_promotion,required_for_ticket,required_for_finalgate,missing_blocker_class,failed_blocker_class,value_source,status` | referenced event IDs and `status='current'`; PK ASC; logical UTF-8 row over 4 KiB or cumulative bytes over 8 MiB fail typed | 2,048 / 2,049 |
| `brc_runtime_process_outcomes` | `process_outcome_id,process_name,scope_key,process_state,runtime_head,source_watermark,updated_at_ms` | exact release activation/scope/succeeded; updated DESC, ID DESC | 1 / 2 |

The three guarded JSON projections are exactly:

```sql
CASE
  WHEN octet_length(conditional_hard_gates::text) <= 16384
  THEN conditional_hard_gates ELSE NULL
END AS conditional_hard_gates,
octet_length(conditional_hard_gates::text) AS conditional_hard_gates_bytes

CASE
  WHEN octet_length(policy_event_ids::text) <= 16384
  THEN policy_event_ids ELSE NULL
END AS policy_event_ids,
octet_length(policy_event_ids::text) AS policy_event_ids_bytes

CASE
  WHEN expected_value IS NULL THEN NULL
  WHEN octet_length(expected_value::text) <= 4096
  THEN expected_value ELSE NULL
END AS expected_value,
octet_length(expected_value::text) AS expected_value_bytes
```

The activation query uses `LIMIT 2`, not `LIMIT 1`, so a second row is a typed
uniqueness failure. Cap `conditional_hard_gates` and `policy_event_ids` at 16
KiB each, `expected_value` at 4 KiB each, and all returned expected values at 8
MiB total. The `CASE` expressions and byte aliases in the matrix are the exact
selected-column tuple asserted by SQL capture; they are not unspecified extra
columns. Use logical UTF-8 JSON text length rather than `pg_column_size`, because
TOAST/compression size is not a safe bound on the de-TOASTed Python payload. An
oversized JSON cell is rejected without being transferred whole to Python; the
`*_bytes` guard aliases never enter the semantic digest.

The certification reader is two-phase: read active candidates, exact matching
active `strategy_runtime_instances`, event bindings, and runtime bindings first;
collect referenced group-version/event/policy IDs; then query only those IDs.
Require one runtime row per candidate `(strategy_group_id,symbol,side)` and
construct the existing complete `RuntimeLaneIdentity` from the runtime ID,
candidate `asset_class`, Event Spec/time authority, runtime profile, and policy.
A missing/ambiguous runtime or any cross-table identity mismatch fails. Query
the release outcome only with
`process_name='runtime_release_activation'`, `scope_key='production:tokyo'`,
`process_state='succeeded'`, newest first, `LIMIT 2`. Every identity/fact select uses an
explicit column tuple and `limit + 1` overflow detection; the activation query
uses its explicit 1/2 uniqueness probe. Inspector-based table
and index existence checks may inspect metadata for all required tables but may
not select their rows.

Extend `ActionTimeCapabilityIdentity` with the frozen
`RuntimeLaneIdentity`. Every lane outcome written for
`live_signal_materialization`, `action_time_fact_snapshots`,
`promotion_action_time_lane`, `action_time_ticket_sequence`, and
`action_time_capability_certification` must pass that typed identity to
`materialize_runtime_process_outcome`; `scope_kind='legacy_unscoped'`,
`scope_key='global'`, or a null `lane_identity_key` is forbidden for those five
current lane names. If a batch/no-signal orchestration summary is retained, give
it exactly `action_time_fact_snapshots_batch`,
`promotion_action_time_lane_batch`, or `action_time_ticket_sequence_batch` and
no current-authority role. Do not
backfill historical legacy rows. RED tests cover all five writers, missing
runtime/asset class/time authority, ambiguous runtime, and cross-lane reuse.

The **certification command** has a separate prepare/apply transaction protocol:

1. a read-only prepare transaction reads this bounded profile and hashes the
   normalized row tuples, exact runtime head, referenced-ID sets, and per-lane
   source watermarks into `certification_input_digest`;
2. a new `SERIALIZABLE` read-write apply transaction sets the same lock and
   statement timeouts, re-reads the exact bounded profile, and recomputes the
   digest;
3. only an exact digest/runtime-head/source-watermark match may materialize the
   bounded `runtime_process_outcomes`, in that same transaction; and
4. mismatch, serialization failure, timeout, or row overflow rolls back the
   entire apply with no partial certification. There is no exchange call and no
   automatic stale-input retry.

Freeze the digest protocol; the current unversioned `default=str` behavior is
not allowed:

```python
CAPABILITY_INPUT_DIGEST_SCHEMA = "brc.action_time_capability_certification_input.v1"
LANE_IDENTITY_DIGEST_SCHEMA = "brc.action_time_capability_lane_identity.v2"
CANONICAL_ENCODING = "brc.typed_canonical_json.v1"
DIGEST_ALGORITHM = "sha256"
```

Table payload order is fixed to the ten-table order in the matrix. Within each
table, column order is the declared order and rows sort by primary-key Unicode
code-point order. The release-activation probe sorts by `updated_at_ms DESC,
process_outcome_id DESC` and must yield exactly one row. Duplicate/missing/
extra columns, wrong types, nonunique keys, or `*_bytes` guard failures stop
before digest construction. Guard aliases are discarded and never enter the
semantic payload.

Canonical scalar tokens are:

```text
SQL NULL -> ["sql:null"]
text     -> ["sql:text", exact_string]
boolean  -> ["sql:bool", true_or_false]
integer  -> ["sql:int", base10_integer_string]
numeric  -> ["sql:decimal", canonical_decimal]
JSONB    -> canonical_json_value(value)
```

Booleans require `type(value) is bool`; integers reject booleans; SQL numerics
must be finite `Decimal` and never binary `float`. Unicode is preserved without
normalization. Decimal canonicalization removes trailing coefficient zeros and
emits signed coefficient plus base-ten exponent, with every signed zero encoded
as `0e0`: `0.90 -> 9e-1`, `1000 -> 1e3`, `0.0300 -> 3e-2`.

JSON canonicalization uses tagged values: `json:null`, `json:bool`,
`json:number`, `json:string`, `json:array`, and `json:object`. Object keys must
be strings and sort by code point; array order is preserved; JSON numbers use
the same Decimal encoder. The certification connection configures JSON parsing
with `parse_float=Decimal`; any Python `float`, NaN/Infinity, non-string object
key, or unsupported type fails. For nullable `expected_value`, v1 preserves the
existing semantic identity by mapping both SQL NULL and JSON null to
`["json:null"]`; distinguishing storage form later requires a schema version
increment.

The top-level canonical payload is:

```python
payload = {
    "schema": CAPABILITY_INPUT_DIGEST_SCHEMA,
    "encoding": CANONICAL_ENCODING,
    "algorithm": DIGEST_ALGORITHM,
    "runtime_head": runtime_head,
    "release_activation": exact_release_activation_identity,
    "referenced_ids": {
        "strategy_group_ids": sorted_unique_group_ids,
        "strategy_group_version_ids": sorted_unique_version_ids,
        "candidate_scope_ids": sorted_unique_candidate_ids,
        "event_spec_ids": sorted_unique_event_ids,
        "policy_current_ids": sorted_unique_policy_ids,
        "runtime_scope_binding_ids": sorted_unique_runtime_binding_ids,
    },
    "lane_source_watermarks": [
        [scope_key, watermark]
        for scope_key, watermark in sorted(lane_source_watermarks.items())
    ],
    "tables": canonical_table_payloads_in_fixed_order,
}
canonical_bytes = json.dumps(
    payload,
    ensure_ascii=False,
    allow_nan=False,
    sort_keys=True,
    separators=(",", ":"),
).encode("utf-8")
certification_input_digest = "sha256:" + hashlib.sha256(canonical_bytes).hexdigest()
```

Prepare and apply compare digest schema, encoding, runtime head, release-
activation identity, referenced-ID sets, every lane watermark, and final digest.
Any drift writes zero outcomes and rolls the transaction back.
The release-activation identity includes its exact `source_watermark`. Add SQL-
capture and golden-vector assertions that this column is selected in the
declared order and that changing only it changes the certification input digest
and the resulting `ActionTimeCertificationReferenceV2`.

The nested fact-set component uses
`FACT_SET_DIGEST_SCHEMA = "brc.action_time_fact_set_digest.v1"` and the exact
`ActionTimeFactDigestRowV1` fields frozen in Task 4. It receives the complete
expected fact-ID set from the certification input, queries at most **128** rows
plus one overflow probe, sorts by `fact_snapshot_id`, applies the **64 KiB**
per-JSON-field and **1 MiB** total canonical-input guards, and hashes the typed
canonical rows. Prepare and apply compare `fact_set_digest_schema`, exact ID
set, and digest in addition to the enclosing certification input. Add golden
vectors for shuffled row/key order, Decimal, explicit null, Unicode, every
semantic column, duplicate/missing/extra IDs, and guard overflow; a matching ID
with mutated `fact_values` must fail apply with zero outcome writes.

For `brc_current_projection_ownership`, which has no historical/current status
column, select only
`projection_key,model_type,projection_scope_key,owner_projector,legacy_writer_allowed,current_source_mode,updated_at_ms`
with
`WHERE projection_key IS NOT NULL`, deterministic primary-key order, and
`LIMIT 257`; schema inspection separately proves the DB-backed/no-legacy check
constraints. Derive `strategy_group_count` for the deploy report from distinct
active candidate-scope `strategy_group_id` values; do not add an unbounded
strategy-group table scan merely to preserve the old count implementation.

- [ ] **Step 4: Switch the production watcher consumer**

Replace:

```python
repository.read_control_state()
```

with:

```python
repository.read_watcher_candidate_universe_current()
```

Call `.model_dump(mode="python")` exactly once at the existing pure
`_candidate_universe_from_control_state()` boundary. Do not replace it with
`read_monitor_control_state()`.

- [ ] **Step 5: Prove the exact watcher SQL shape**

Add:

```python
statements = capture_select_statements(engine)
universe, source = _read_candidate_universe_from_pg(
    database_url=database_url,
    allow_non_postgres_for_test=True,
)
assert selected_table_names(statements) == WATCHER_CANDIDATE_TABLE_NAMES
assert all(statement_has_where_and_limit(sql) for sql in statements)
assert all("metadata" not in sql.lower() for sql in statements)
assert source["source"] == "pg_runtime_control_state:candidate_scope"
```

Seed 10,000 historical rows and one active row per table. Assert the same four
queries and the same returned active universe. Add exact-limit tests for 256
rows accepted and 257 rows rejected. Re-run the invalid-binding matrix from
Step 1 against both readers and assert identical fail-closed behavior.

- [ ] **Step 6: Write deploy/certification SQL-shape RED tests**

Run both production entry points against fixtures containing large historical
tables. Capture SQLAlchemy `before_cursor_execute` events and assert:

```text
deploy validator row-table set == DEPLOY_VALIDATION_TABLE_NAMES
capability certifier row-table set == CAPABILITY_CERTIFICATION_TABLE_NAMES
every SELECT has explicit projected columns, WHERE, and LIMIT
every selected-column tuple and normalized predicate equals the matrix above
prepare path sets read-only, lock timeout, and statement timeout before rows
apply path is SERIALIZABLE, revalidates the exact digest before its first write
digest/runtime-head/source-watermark drift rolls back every outcome write
no SELECT references watcher history, fact-snapshot history, notification
history, lifecycle history, or any table outside its profile
256 identity rows pass; 257 fail closed
2,048 required-fact rows pass; 2,049 fail closed
latest release-activation query returns at most one row
second release-activation row fails the 1/2 uniqueness probe
exactly one active strategy runtime resolves each candidate key; zero or two fail
all five lane process writers persist the complete identical RuntimeLaneIdentity
no current lane process writer emits global/legacy_unscoped/null-key authority
oversized JSON fails before the full value reaches Python
```

Add canonical-digest vectors proving: row and JSON-object key order do not
change digest; JSON-array order does; `Decimal("0.90")` equals `Decimal("0.9")`;
JSON number `1` differs from string `"1"`; SQL NULL/empty string/zero/False are
distinct; boolean `True` differs from integer `1`; Python float fails; every
semantic column changes digest; guard aliases and storage compression do not;
prepare/apply row drift writes zero outcomes; and 4/16-KiB single-cell plus
8-MiB cumulative boundaries cover exact limit, one byte over, and a highly
compressible oversized JSON value.

In these entry-point tests, monkeypatch all three legacy readers
(`read_control_state`, `read_monitor_control_state`, and
`read_action_time_control_state`) to raise as a secondary guard. Do not make the
repository methods globally raise in R1 because unrelated bounded consumers
may still require a separately reviewed migration. The primary proof remains
captured SQL, not method names. Retain the existing 22-lane identity and
atomic-write assertions.

- [ ] **Step 7: Run focused GREEN tests**

Run:

```bash
python3 -m pytest -q \
  tests/unit/test_runtime_control_state_repository.py \
  tests/unit/test_runtime_active_observation_monitor.py \
  tests/unit/test_validate_runtime_control_state_repository.py \
  tests/unit/test_certify_action_time_capability.py \
  tests/unit/test_action_time_capability_certification.py \
  tests/unit/test_certify_action_time_capability_script.py \
  tests/unit/test_runtime_control_current_projection_publish.py \
  tests/unit/test_runtime_lane_identity_service.py \
  tests/unit/test_action_time_fact_snapshots.py \
  tests/unit/test_promotion_action_time_lane.py \
  tests/unit/test_action_time_ticket_materialization_sequence.py
```

Expected: all selected tests pass.

- [ ] **Step 8: Commit Task 1**

```bash
git add \
  src/application/readmodels/watcher_candidate_universe.py \
  src/infrastructure/runtime_control_state_repository.py \
  scripts/runtime_active_observation_monitor.py \
  scripts/validate_runtime_control_state_repository.py \
  scripts/certify_action_time_capability.py \
  src/application/action_time/capability_certification.py \
  src/application/runtime_lane_identity_service.py \
  src/application/action_time/fact_snapshots.py \
  src/application/action_time/promotion_action_time_lane.py \
  src/application/action_time/ticket_materialization_sequence.py \
  scripts/publish_runtime_control_current_projections.py \
  tests/unit/test_runtime_control_state_repository.py \
  tests/unit/test_runtime_active_observation_monitor.py \
  tests/unit/test_validate_runtime_control_state_repository.py \
  tests/unit/test_certify_action_time_capability.py \
  tests/unit/test_action_time_capability_certification.py \
  tests/unit/test_certify_action_time_capability_script.py \
  tests/unit/test_runtime_control_current_projection_publish.py \
  tests/unit/test_runtime_lane_identity_service.py \
  tests/unit/test_action_time_fact_snapshots.py \
  tests/unit/test_promotion_action_time_lane.py \
  tests/unit/test_action_time_ticket_materialization_sequence.py
git commit -m "fix: add bounded runtime control read profiles"
```

---

### Task 2: Page Candidate-Matched Runtimes And Transport A Decision-Safe Compact Projection

**Files:**

- Create: `src/application/readmodels/strategy_runtime_watcher_identity.py`
- Create: `src/application/readmodels/watcher_decision_fact_projection.py`
- Modify: `src/infrastructure/pg_strategy_runtime_repository.py`
- Modify: `src/application/strategy_runtime_service.py`
- Modify: `src/interfaces/api_trading_console.py`
- Modify: `scripts/runtime_first_real_submit_api_flow.py`
- Modify: `scripts/runtime_active_observation_monitor.py`
- Modify: `scripts/runtime_signal_watcher_tick.py`
- Create: `tests/unit/test_runtime_first_real_submit_api_flow.py`
- Modify: `tests/unit/test_strategy_runtime_backbone.py`
- Modify: `tests/unit/test_runtime_active_observation_monitor.py`
- Modify: `tests/unit/test_runtime_signal_watcher_tick.py`
- Create: `tests/integration/test_watcher_action_time_compact_parity.py`
- Create: `tests/performance/runtime_watcher_production_shape_runner.py`

**Interfaces:**

- Produces typed `StrategyRuntimeWatcherIdentity` and
  `StrategyRuntimeWatcherIdentityPage` readmodels; both use
  `ConfigDict(extra="forbid", frozen=True)`.
- Produces repository/service
  `list_watcher_candidate_identity_page(*, candidate_lane_keys: tuple[WatcherCandidateLaneKey, ...], after_runtime_instance_id: str | None, limit: int = 16)`.
- Produces read-only endpoint
  `POST /strategy-runtimes/watcher-active-candidate-page` with validated
  candidate lane keys, `limit=16`, and optional immutable-ID cursor. It performs
  no mutation despite POST being used for the bounded filter body.
- Adds `response_projection: Literal["full", "watcher_compact"] = "full"` to
  the non-executing observation request. Existing callers retain full output.
- Produces `_read_response_body_bounded(response, max_bytes: int) -> bytes` and
  uses 128 KiB for an identity page, 512 KiB for a compact observation, and 16
  MiB only for explicit full diagnostics.
- Produces exact named boolean-only runtime effects; it never copies an
  arbitrary `safety_invariants` map.
- Produces frozen `ActionTimeDecisionFactProjection` containing validated and
  bounded `signal_snapshot`, `evidence_payload`, `action_time_fact_values`, and
  typed `StrategyFactObservation` rows. Compact mode may remove duplicated raw
  artifacts but may not remove these decision inputs.

- [ ] **Step 1: Write pagination and SQL-shape RED tests**

Seed 17, 33, and 256 candidate-matched active runtimes, plus inactive and out-of-
scope history with oversized boundary/policy/metadata JSON. For each in-scope
cardinality, follow `next_cursor` until `has_more=false` and assert:

```text
every candidate-matched active runtime ID is returned exactly once
IDs are strictly ascending across page boundaries
each page contains at most 16 items
cursor always equals the last returned immutable runtime ID
the final page has next_cursor=null and has_more=false
inactive/out-of-scope and newly inserted lower-than-cursor rows do not duplicate a row
```

Capture SQL and assert the watcher page selects only runtime ID,
StrategyGroup/version, symbol, side, carrier, and status; applies
`status='active'`, a server-side join to the supplied candidate lane `VALUES`,
`runtime_instance_id > cursor` when present,
`ORDER BY runtime_instance_id ASC`, and `LIMIT 17`. It must not load boundary,
policy, or metadata JSON. Existing `/strategy-runtimes` list tests must remain
unchanged and continue to use their current updated-time ordering.

Add 100,000 out-of-scope active runtimes with all candidate-matched IDs sorting
after them. Assert the first request does not return 6,250 client pages: the
server returns one exact excluded count, at most 32 ordered sample IDs, and the
in-scope page. The complete scan discovers every candidate exactly once below
120 seconds with a bounded SQL/request count based on in-scope pages, not total
inventory. No full excluded-ID list or string aggregate/digest is constructed.

Add repeated, empty-with-`has_more`, and non-monotonic cursor fixtures. The
watcher must return `active_runtime_pagination_invalid`, not a partial-success
inventory. Changes concurrent with a scan are revalidated per runtime and may
enter the next tick; the cursor never creates submit authority.

- [ ] **Step 2: Write compact-projection and semantic-parity RED tests**

Run the same no-signal, satisfied-signal, blocked-fact, identity-fault, and
safety-fault fixtures once with `full` and once with `watcher_compact`. Assert
identical:

```text
selected runtime identities and candidate-universe coverage
overall and per-runtime status
blockers and warnings after documented bounded text normalization
lane identity and signal identity/timestamps/grade/mode
all named safety booleans
PG live-signal candidates, identity faults, and process outcomes
persisted live-signal `signal_payload`
Action-Time fact values, typed valid-until values, missing/failed fact sets,
blockers, source watermarks, candidate readiness, and Ticket readiness
```

Place independent multi-megabyte markers in raw signal-input candles, evaluator
trace, duplicated next-attempt gate, lifecycle audit, arbitrary unused safety
keys, and review-only evidence; compact mode must not retain them. Separately
seed valid bounded `signal_snapshot`, `evidence_payload`,
`action_time_fact_values`, and `fact_observations`; compact mode must preserve
their Action-Time semantics through live-signal and fact-snapshot materialization.
Default full mode must still expose the existing diagnostic shape.

For all current 22 lanes, enumerate every required fact and run:

```text
observation response
-> watcher signal summary
-> brc_live_signal_events.signal_payload
-> Action-Time fact snapshot
-> candidate/Ticket readiness
```

Full and compact outputs must match per fact. This is a release gate, not a
sample-only test.

Define a frozen `WatcherRuntimeEffect` DTO with `extra="forbid"` and one
`WATCHER_SAFETY_BOOLEAN_KEYS` constant containing every safety field
used by `_safety()` and `_summary()`. Tests fail if the producer adds a consumed
safety key without adding it to the projection, or if any projected value is
not exactly `bool`. Add missing-key, `None`, `0/1`, string `"false"/"true"`,
list, and nested-dictionary cases; every one must fail with
`watcher_safety_projection_invalid:<key>` rather than being coerced.

Freeze compact logical-size encoding as:

```python
def compact_json_size(value: object) -> int:
    return len(json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8"))
```

After Pydantic `mode="json"` conversion, enforce: each decision map at most
64 KiB; at most 128 typed fact observations and 96 KiB for that list; combined
decision projection at most 192 KiB; complete compact signal summary at most
256 KiB. `reason_codes`, `blockers`, and `warnings` each contain at most 64
strings, each string at most 256 UTF-8 bytes, and each array at most 16 KiB.
No field or array is truncated. Exact-limit succeeds; one-byte/one-item overflow,
multi-byte Unicode overflow, non-finite number, wrong observation type, or
overall overflow returns `watcher_compact_projection_oversize:<field>` and
materializes no partial live signal or Action-Time fact. Tests prove every
blocker/reason code is preserved exactly.

- [ ] **Step 3: Write HTTP-boundary and unconstrained-memory RED tests**

For success and `HTTPError`, assert exact-limit accepted and limit-plus-one
rejected at 128 KiB, 512 KiB, and 16 MiB. The fake response records `read()` and
must observe exactly `max_bytes + 1`; decode only the bounded bytes and never
retain raw bytes beside the parsed object.

In a fresh subprocess with the **default production Python allocator** and no
cgroup memory limit, run a production-shape
fixture containing 256 active identity rows and 256 selected compact
observations. Require every runtime to be processed exactly once, final compact
summaries no larger than 256 KiB each, every bounded Action-Time decision fact
preserved, no duplicated raw-artifact marker, elapsed time below 120 seconds,
and process maximum RSS below 256 MiB. Repeat with 17 and 33 rows to exercise
page transitions. Add a 100,000-out-of-scope case with candidate IDs at the
lexical tail and require exact candidate discovery below the same deadline with
no client page per excluded runtime. A MemoryMax kill, partial
coverage, or 120-second timeout is a failed test, not an acceptable bound.

The stdout-only runner
`tests/performance/runtime_watcher_production_shape_runner.py` is the sole
benchmark entry point. It:

```text
resolves /proc/self/cgroup and cgroup v1/v2 memory limit on Linux
refuses to emit passing evidence when the effective memory limit is finite
records cgroup-unavailable on macOS
normalizes resource.getrusage(RUSAGE_SELF).ru_maxrss bytes on macOS and KiB on Linux
lazily generates 128-KiB pages, 512-KiB compact responses, and maximum 256-KiB
satisfied-signal summaries with valid decision-fact projections
adds 250 ms observation latency per runtime
accepts `--out-of-scope-runtime-count 100000` and places candidates at the tail
prints exact count, excluded count/sample, request count, elapsed_ms,
peak_rss_bytes, cgroup fact, and full-chain semantic digest
creates no benchmark/report file
```

The default allocator run is the hard gate. An optional second run with
`PYTHONMALLOC=malloc` may be recorded only as diagnostic comparison and can
never replace or rescue a failed default-allocator result.

- [ ] **Step 4: Run Task 2 RED tests**

```bash
python3 -m pytest -q \
  tests/unit/test_strategy_runtime_backbone.py \
  tests/unit/test_runtime_first_real_submit_api_flow.py \
  tests/unit/test_runtime_active_observation_monitor.py \
  tests/unit/test_runtime_signal_watcher_tick.py \
  -k 'watcher_active_page or compact_projection or semantic_parity or bounded_response or unconstrained_memory'
```

Expected: selected tests fail against the current full-list, full-response, and
artifact-retention behavior.

- [ ] **Step 5: Implement the candidate-matched explicit-column keyset page**

The watcher loads/validates the candidate universe first and sends its unique
lane keys to the server. The server places at most 256 validated keys in a
bound `VALUES`/equivalent relation and joins active runtimes before keyset
pagination. The repository queries `limit + 1`, returns at most `limit`
readmodels, and derives `has_more`/`next_cursor` without returning the probe row.
`limit` is validated in `1..100`; production requests 16. The service delegates
without calling the existing full-domain list method. Add the dedicated static
POST route before `/{runtime_instance_id}`.

The watcher loops only over in-scope pages until `has_more=false`, validates
strict ascending IDs within/across pages, and releases each body before the next
request. Strict monotonicity proves no duplicate without an unbounded ID set.
The first response also carries an exact server-side excluded count plus at
most 32 ordered sample IDs from a separate bounded sample query. It carries no
complete excluded list and no `string_agg`/digest. A 100,000-row out-of-scope
fixture proves request count depends on in-scope pages and that lexical-tail
candidates finish below 120 seconds. Production does not pass `max_runtimes`;
an explicit manual diagnostic limit may remain, but it marks
`partial_by_operator_scope` and never `coverage_complete`.

- [ ] **Step 6: Implement server-side compact observation projection**

When `response_projection="watcher_compact"`, do not serialize raw
`signal_input`, candles, duplicated evaluator traces, review-only evidence, or
arbitrary gate/lifecycle dictionaries. Compute the same facts/evaluation and
return the typed fields consumed by `_compact_runtime_summary()`, live-signal/
identity-fault materialization, named safety booleans, and the frozen
`ActionTimeDecisionFactProjection`. The producer validates raw
`signal_snapshot`, `evidence_payload`, `action_time_fact_values`, and
`fact_observations` into that projection before discarding the larger artifact.
Default `full` behavior remains unchanged.

The watcher sets compact projection only on scheduled production/canary calls.
Manual `include_runtime_artifacts=true` continues to request full mode and is
not used by the systemd production unit.

- [ ] **Step 7: Implement bounded transport and boolean-only retention**

Add an explicit `max_response_bytes` argument to the shared client without
changing unrelated callers' semantics. Use the bound for both success and
`HTTPError`. Production watcher calls use 128 KiB for identity pages and 512
KiB for compact observations. No post-read cumulative byte budget is used;
sequential release plus the global monotonic deadline bounds working set and
time without capping runtime coverage.

Core retention shape:

```python
safety = artifact.get("safety_invariants") or {}
for key in WATCHER_SAFETY_BOOLEAN_KEYS:
    if key not in safety or type(safety[key]) is not bool:
        raise RuntimeError(f"watcher_safety_projection_invalid:{key}")
runtime_effect = WatcherRuntimeEffect.model_validate({
    "status": str(artifact.get("status") or "unknown"),
    "safety_invariants": {key: safety[key] for key in WATCHER_SAFETY_BOOLEAN_KEYS},
})
summary = _compact_runtime_summary(runtime, artifact)
assert compact_json_size(summary) <= 256 * 1024
```

There is no `dict(safety)` call. Full artifacts are retained only in explicit
manual mode. Scheduled production retains at most the existing 256-row active
candidate-scope set; unrelated active identities contribute only to the server-
computed count/sample. The 17/33/256 and 100,000-out-of-scope/tail-candidate
performance gates must finish below 120 seconds. If a later degraded tick still exhausts the deadline, observation
order rotates by `floor(now_ms / 180000) % selected_count`; the result is typed
`watcher_tick_incomplete`, contains no `coverage_complete` fact, and tests prove
successive ticks do not permanently starve the same tail IDs.

- [ ] **Step 8: Run Task 2 GREEN and performance gates**

```bash
python3 -m pytest -q \
  tests/unit/test_strategy_runtime_backbone.py \
  tests/unit/test_runtime_first_real_submit_api_flow.py \
  tests/unit/test_runtime_active_observation_monitor.py \
  tests/unit/test_runtime_signal_watcher_tick.py \
  tests/integration/test_watcher_action_time_compact_parity.py
```

Then run:

```bash
python3 tests/performance/runtime_watcher_production_shape_runner.py \
  --runtime-counts 17,33,256 \
  --out-of-scope-runtime-count 100000 \
  --candidate-placement lexical-tail \
  --page-size 16 \
  --observation-latency-ms 250 \
  --max-elapsed-seconds 120 \
  --max-rss-bytes 268435456
```

The runner exits 0 only for exact coverage, semantic digest match, elapsed below
120 seconds, RSS below 256 MiB, and no effective cgroup memory ceiling. Save
stdout in the test log only; do not create a repository report file.
If it fails, the implementation returns to profiling/query/transport/retention
optimization. It must not lower runtime counts, reduce semantic fixtures,
shorten required coverage, raise the 256-MiB program target, or cite the later
cgroup kill boundary as a pass.

- [ ] **Step 9: Commit Task 2**

```bash
git add \
  src/application/readmodels/strategy_runtime_watcher_identity.py \
  src/application/readmodels/watcher_decision_fact_projection.py \
  src/infrastructure/pg_strategy_runtime_repository.py \
  src/application/strategy_runtime_service.py \
  src/interfaces/api_trading_console.py \
  scripts/runtime_first_real_submit_api_flow.py \
  scripts/runtime_active_observation_monitor.py \
  scripts/runtime_signal_watcher_tick.py \
  tests/unit/test_strategy_runtime_backbone.py \
  tests/unit/test_runtime_first_real_submit_api_flow.py \
  tests/unit/test_runtime_active_observation_monitor.py \
  tests/unit/test_runtime_signal_watcher_tick.py \
  tests/integration/test_watcher_action_time_compact_parity.py \
  tests/performance/runtime_watcher_production_shape_runner.py
git commit -m "fix: optimize watcher paging and transport"
```

---

### Task 3: Add PostgreSQL Readiness And Service Containment

**Files:**

- Create: `scripts/check_runtime_postgres_ready.py`
- Create: `tests/unit/test_runtime_postgres_ready.py`
- Modify: `scripts/runtime_signal_watcher_tick.py`
- Modify: `tests/unit/test_runtime_signal_watcher_tick.py`
- Modify: `deploy/systemd/brc-runtime-signal-watcher.service`
- Create: `deploy/systemd/brc-runtime-signal-watcher-canary.service`
- Modify: `deploy/systemd/brc-runtime-monitor.service`
- Modify: `deploy/systemd/brc-ticket-lifecycle-maintenance.service`
- Modify: `deploy/systemd/brc-runtime-signal-watcher.service.d/80-product-state-refresh.conf`
- Modify: `deploy/systemd/brc-runtime-signal-watcher.service.d/85-action-time-refresh-if-needed.conf`
- Modify: `deploy/systemd/brc-runtime-signal-watcher.service.d/90-resume-dispatcher-after-refresh.conf`
- Create: `deploy/systemd/brc-owner-console-backend.service.d/10-runtime-bound.conf`
- Create: `deploy/systemd/brc-owner-console-backend.service.d/40-runtime-stability.conf`
- Create: `deploy/systemd/brc-owner-console-canary-readonly.service`
- Create: `src/interfaces/api_canary_readonly.py`
- Create: `src/infrastructure/canary_readonly_database.py`
- Modify: `scripts/runtime_active_observation_monitor.py`
- Modify: `scripts/plan_tokyo_runtime_governance_git_deploy.py`
- Modify: `tests/unit/test_runtime_signal_watcher_systemd_units.py`
- Modify: `tests/unit/test_runtime_signal_watcher_resume_dispatcher.py`
- Modify: `tests/unit/test_tokyo_lifecycle_phase_two_deploy.py`
- Modify: `tests/unit/test_trading_console_readmodels.py`
- Create: `tests/unit/test_canary_readonly_api.py`

**Interfaces:**

- Produces CLI:
  `check_runtime_postgres_ready.py --require-database-url --timeout-seconds N --json`.
- Exit `0`: real `SELECT 1` returned one.
- Exit `2`: DSN absent, connection failed until deadline, or query returned an
  invalid result.
- The command writes stdout only and creates no file.
- The planner installs the exact tracked readiness script at
  `/home/ubuntu/brc-deploy/control-plane/check_runtime_postgres_ready.py` and
  verifies its SHA-256; the script imports no project module.
- The watcher tick owns one injected monotonic 120-second global deadline; all
  per-runtime/API phases consume its remaining time rather than each receiving
  a fresh 120 seconds.
- Produces a loopback-only `brc-owner-console-canary-readonly.service` at the
  exact candidate SHA. It imports only `src.interfaces.api_canary_readonly`,
  loads no order-capable environment, and exposes exactly two routes.
- Every canary database connection assumes built-in role `pg_read_all_data`,
  sets read-only defaults, and fails startup unless `current_user`, table and
  sequence privileges, and transaction facts prove SELECT-only operation. A
  missing ability to assume the existing built-in role blocks deployment; R1
  never creates a role, grants membership, or changes a secret.
- Produces a timerless `brc-runtime-signal-watcher-canary.service` that talks
  only to that API and contains no direct PG engine/repository, public/account
  fact refresh, PG materializer, Action-Time refresh, FinalGate, Operation
  Layer, dispatcher, or submit flags.
- Canary CLI mode allows only
  `POST /api/trading-console/strategy-runtimes/watcher-active-candidate-page` and
  `POST /api/trading-console/strategy-runtimes/{id}/next-attempt-observation-cycle`
  with `response_projection=watcher_compact`, `non_executing=true`, and ticket
  materialization false; any other route is a typed failure printed to the
  journal.

- [ ] **Step 1: Write readiness RED tests**

```python
def test_postgres_ready_requires_dsn(monkeypatch, capsys):
    monkeypatch.delenv("PG_DATABASE_URL", raising=False)
    assert main(["--require-database-url", "--json"]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "unavailable"

def test_postgres_ready_executes_select_one(monkeypatch, capsys):
    runner = RecordingReadyRunner(result=1)
    assert check_postgres_ready(
        database_url="postgresql+psycopg://test",
        timeout_seconds=1,
        runner=runner,
    )["status"] == "ready"
    assert runner.statements == ["SELECT 1"]
```

Add a watcher deadline test with individually valid fake phases whose
cumulative monotonic time reaches 120 seconds. Assert the next phase is not
called and the tick returns `watcher_global_deadline_exceeded`. Add a
multi-runtime variant proving runtime two receives only the remaining budget.

- [ ] **Step 2: Implement the bounded readiness CLI**

Use `NullPool`, normalize the synchronous DSN, execute `sa.text("SELECT 1")`,
dispose every attempted engine, sleep at most one second between attempts, and
stop at the monotonic deadline. Return only masked error class/text tails; never
print the DSN.

Core shape:

```python
def check_postgres_ready(
    *,
    database_url: str,
    timeout_seconds: float,
    runner: ReadyRunner | None = None,
) -> dict[str, Any]:
    deadline = time.monotonic() + max(timeout_seconds, 0.1)
    last_error = ""
    while time.monotonic() < deadline:
        try:
            value = (runner or _select_one)(database_url)
            if value == 1:
                return {"status": "ready", "select_one": 1}
            last_error = "select_one_invalid_result"
        except Exception as exc:
            last_error = f"{type(exc).__name__}:{str(exc)[-200:]}"
        time.sleep(min(1.0, max(deadline - time.monotonic(), 0.0)))
    return {"status": "unavailable", "error": last_error}
```

In `runtime_signal_watcher_tick.py`, create the deadline once at tick entry,
check it before/after every API or runtime phase, and pass
`min(configured_phase_timeout, remaining_seconds)` downstream. The behavior
test, not only the CLI string, proves the global 120-second bound.

- [ ] **Step 3: Write systemd RED assertions**

Assert the watcher unit contains exactly:

```python
for required in (
    "MemoryAccounting=true",
    "MemoryHigh=384M",
    "MemoryMax=512M",
    "MemorySwapMax=0",
    "OOMPolicy=stop",
    "TimeoutStartSec=300s",
    "TimeoutStopSec=20s",
    "KillMode=control-group",
    "StartLimitIntervalSec=2min",
    "StartLimitBurst=3",
    "--cycle-timeout-seconds 120",
):
    assert required in watcher_service_text
```

Assert the backend drop-in contains the readiness `ExecStartPre`,
`StartLimitIntervalSec=300`, `StartLimitBurst=3`, `RestartSec=15s`, and does not
contain `docker start`.

Assert backend, production watcher, canary API, monitor, and lifecycle each
contain the same 10-second outer / 8-second inner PostgreSQL readiness gate and
place it before their business command. Simulate readiness exit 2 and assert the
business command is never invoked.

Assert the canary API binds only to loopback, imports the exact candidate tree,
imports the dedicated ASGI app rather than `src.interfaces.api`, and has no
production order-capable environment. Assert its actual FastAPI route table is
exactly the two allowlisted business routes; construct FastAPI with
`docs_url=None`, `redoc_url=None`, and `openapi_url=None`, and add no health or
root route. Every
reachable database port must report `current_user='pg_read_all_data'`, SELECT
allowed, and INSERT/UPDATE/DELETE/TRUNCATE/sequence writes denied. Tests fail if
any engine falls back to the global production engine, or if SQL contains
`RESET ROLE`, a second `SET ROLE`, or `SET TRANSACTION READ WRITE`.

Assert the tracked `10-runtime-bound.conf` clears the inherited `ExecStart` and
sets exactly:

```ini
[Service]
ExecStart=
ExecStart=/home/ubuntu/brc-deploy/app/current/.venv/bin/python -m src.main
```

Across every repository-owned systemd file, assert the old
`brc-bnb-prelive-20260601` path is absent and the interpreter path is exactly:

```text
/home/ubuntu/brc-deploy/app/current/.venv/bin/python
```

Assert production watcher stage budgets are 10s PG readiness, 30s public facts,
30s account facts, 125s main envelope, 10s projection summary, 40s Action-Time
refresh, 45s dispatcher, and 10s systemd margin. Assert the API-only watcher
canary contains only the core HTTP observation command under a 135-second
maximum plus a 15-second systemd margin. It has no PG readiness or fact stage
because it owns no database connection.

Every advertised outer slot includes its TERM-to-KILL grace period:

| Stage | Primary timeout | Kill-after grace | Maximum slot |
| --- | ---: | ---: | ---: |
| PG readiness | 8s | 2s | 10s |
| Public facts | 27s | 3s | 30s |
| Account facts | 27s | 3s | 30s |
| Core watcher | 122s | 3s | 125s |
| Projection summary | 8s | 2s | 10s |
| Action-Time refresh | 37s | 3s | 40s |
| Resume dispatcher | 42s | 3s | 45s |

The core's own monotonic deadline remains 120s inside its 122s TERM deadline.
The full production maximum is therefore 290s plus 10s systemd margin, not
300s plus uncounted kill grace. The watcher canary maximum is 135s plus 15s
margin; the separately started API canary has its own bounded startup/teardown.

Assert the canary unit text and generated canary command contain none of:

```text
runtime-order-capable.env
action_time_if_needed
runtime_signal_watcher_resume_dispatcher.py
--execute-preflight
--execute-operation-layer-submit
--production-submit-execution-policy
FinalGate
Operation Layer
```

Add server route-set and client-shape tests for every allowed and forbidden
method/path/body shape. Assert the route restriction is server-side in the
dedicated app, not merely a watcher-client guard. At the two allowed FastAPI handlers, inject counting fakes for Ticket,
promotion, lane, runtime-safety, authorization, FinalGate, Operation Layer,
dispatcher, and gateway writes and assert all stay zero under the exact
candidate code. Inject a fake global engine escape and require the test to fail
before a query executes. Require stdout to include `route_set_status=passed`,
`current_user=pg_read_all_data`, per-table privilege denial, read-only session/
transaction facts, and the systemd invocation ID.

Assert every watcher stage is wrapped with GNU `time` using a stable journal
tag containing invocation ID and stage name. Do not assert systemd
`MemoryPeak`: it is unavailable after oneshot exit on the deployed kernel.
Assert no watcher-stage command uses `systemd-run`, background `&`, `nohup`, or
another cgroup escape; the deployment transient service is a separate control-
plane contract.

- [ ] **Step 4: Modify the units**

Add watcher containment under the correct `[Unit]` and `[Service]` sections.
Change the watcher CLI cycle timeout from 180 to 120 seconds and set
`TimeoutStartSec=300s`. Use `/usr/bin/timeout --foreground --signal=TERM` with
the per-stage primary timeout and kill-after grace in the table above. The
maximum slots sum to 290 seconds, leaving exactly 10 seconds of systemd margin.
A timed-out dispatcher must leave its durable command in `dispatching` or
`outcome_unknown`; later ticks must not redispatch it.

Wrap each timeout command directly with:

```text
/usr/bin/time -f 'BRC_STAGE_MAX_RSS_KIB stage=<stage> value=%M' <timeout-command>
```

Journal metadata supplies `_SYSTEMD_INVOCATION_ID`, so no shell expansion or
sidecar file is needed. Acceptance queries the exact invocation ID and requires
one parseable RSS record per expected stage. A missing/duplicate/malformed
record fails the canary.

Set the dispatcher argument `--preflight-timeout-seconds 30`, below its 45-second
outer budget. Add a generated-unit test proving the 30/45 relationship and an
existing-dispatch test proving a second tick does not create another exchange
command after client timeout.

The normal no-signal SLO is below 120 seconds even though 300 seconds is the
full degraded-state hard stop. Because systemd does not run a second instance
of the same active oneshot, a slow tick may delay the next three-minute timer
event but cannot overlap it.

Create the watcher canary as a new API-only unit rather than duplicating the
production unit. Invoke the monitor with `--deployment-canary --api-only
--no-pg-materialization --no-fact-refresh`; construction fails if a direct PG
port is supplied. It has no timer and is never enabled. Add it to the planner's
install set solely for bounded deployment canaries. The API canary starts from
the dedicated ASGI app, uses only the privilege-reduced engine factory, and is
stopped after the fifth run on both success and failure.

Add this readiness line before the business command in all five services:

```ini
ExecStartPre=/usr/bin/timeout --foreground --signal=TERM --kill-after=2s 8s /home/ubuntu/brc-deploy/app/current/.venv/bin/python /home/ubuntu/brc-deploy/control-plane/check_runtime_postgres_ready.py --require-database-url --timeout-seconds 8
```

Before installing those units, copy the tracked helper to a unique temporary
file in `/home/ubuntu/brc-deploy/control-plane/`, verify its SHA-256 and mode,
then rename it to the stable path. Run it once with both the previous-release
and candidate-release interpreters against the recovered PG. Unit installation
is blocked unless both probes succeed. This shared helper is deployment control
plane, not a recurring report or runtime authority source.

Set monitor `TimeoutStartSec=75s` with a 60-second main envelope. Set lifecycle
`TimeoutStartSec=45s` with its existing 28-second internal deadline and a
30-second main envelope. The production watcher and watcher-canary values are
300s and 150s respectively.

Add both tracked backend drop-ins to the existing planner-owned systemd copy
set. After copying every unit/drop-in, run `systemctl daemon-reload` once and
verify `systemctl show brc-owner-console-backend.service -p ExecStart` resolves
to `app/current/.venv/bin/python -m src.main` before starting the backend.

Create the backend drop-in:

```ini
[Unit]
After=docker.service network-online.target
Wants=docker.service network-online.target
StartLimitIntervalSec=300
StartLimitBurst=3

[Service]
ExecStartPre=/usr/bin/timeout --foreground --signal=TERM --kill-after=2s 8s /home/ubuntu/brc-deploy/app/current/.venv/bin/python /home/ubuntu/brc-deploy/control-plane/check_runtime_postgres_ready.py --require-database-url --timeout-seconds 8
Restart=on-failure
RestartSec=15s
```

- [ ] **Step 5: Run Task 3 tests**

```bash
python3 -m pytest -q \
  tests/unit/test_runtime_postgres_ready.py \
  tests/unit/test_runtime_signal_watcher_tick.py \
  tests/unit/test_trading_console_readmodels.py \
  tests/unit/test_canary_readonly_api.py \
  tests/unit/test_runtime_signal_watcher_systemd_units.py \
  tests/unit/test_runtime_signal_watcher_resume_dispatcher.py \
  tests/unit/test_tokyo_lifecycle_phase_two_deploy.py
```

Expected: all selected files pass.

- [ ] **Step 6: Run the file-I/O audit against the new script**

```bash
python3 scripts/audit_production_runtime_file_io.py --all
```

Expected: `performance_risk.status=clear`, no new runtime file reader, and no
frequent report writer.

- [ ] **Step 7: Commit Task 3**

```bash
git add \
  scripts/check_runtime_postgres_ready.py \
  scripts/runtime_signal_watcher_tick.py \
  scripts/runtime_active_observation_monitor.py \
  src/interfaces/api_canary_readonly.py \
  src/infrastructure/canary_readonly_database.py \
  deploy/systemd/brc-runtime-signal-watcher.service \
  deploy/systemd/brc-runtime-signal-watcher-canary.service \
  deploy/systemd/brc-owner-console-canary-readonly.service \
  deploy/systemd/brc-runtime-monitor.service \
  deploy/systemd/brc-ticket-lifecycle-maintenance.service \
  deploy/systemd/brc-runtime-signal-watcher.service.d/80-product-state-refresh.conf \
  deploy/systemd/brc-runtime-signal-watcher.service.d/85-action-time-refresh-if-needed.conf \
  deploy/systemd/brc-runtime-signal-watcher.service.d/90-resume-dispatcher-after-refresh.conf \
  deploy/systemd/brc-owner-console-backend.service.d/10-runtime-bound.conf \
  deploy/systemd/brc-owner-console-backend.service.d/40-runtime-stability.conf \
  scripts/plan_tokyo_runtime_governance_git_deploy.py \
  tests/unit/test_runtime_postgres_ready.py \
  tests/unit/test_canary_readonly_api.py \
  tests/unit/test_runtime_signal_watcher_tick.py \
  tests/unit/test_runtime_signal_watcher_systemd_units.py \
  tests/unit/test_runtime_signal_watcher_resume_dispatcher.py \
  tests/unit/test_trading_console_readmodels.py \
  tests/unit/test_tokyo_lifecycle_phase_two_deploy.py
git commit -m "fix: contain runtime services and gate on postgres"
```

---

### Task 4: Make Deployment Certification Zero-Exchange And Fail Closed

**Files:**

- Modify: `scripts/verify_ticket_lifecycle_phase_two_readiness.py`
- Modify: `scripts/plan_tokyo_runtime_governance_git_deploy.py`
- Modify: `scripts/execute_tokyo_runtime_governance_git_deploy.py`
- Create: `src/application/readmodels/canary_mutation_sentinel.py`
- Create: `migrations/versions/2026-07-15-124_persist_lifecycle_mutation_enablement_proof.py`
- Modify: `src/application/action_time/lifecycle_mutation_capability.py`
- Modify: `scripts/set_ticket_lifecycle_mutation_capability.py`
- Modify: `src/application/action_time/runtime_safety_state.py`
- Modify: `src/application/action_time/exchange_command_worker.py`
- Modify: `src/application/action_time/protected_submit_attempt.py`
- Modify: `tests/unit/test_lifecycle_mutation_capability.py`
- Modify: `tests/unit/test_ticket_bound_exchange_command_worker.py`
- Modify: `tests/unit/test_ticket_bound_protected_submit_attempt.py`
- Modify: `tests/unit/test_ticket_lifecycle_phase_two_readiness.py`
- Modify: `tests/unit/test_tokyo_lifecycle_phase_two_deploy.py`
- Create: `tests/unit/test_canary_mutation_sentinel.py`
- Create: `tests/unit/test_lifecycle_mutation_enablement_proof_migration.py`
- Create: `tests/unit/test_tokyo_runtime_governance_git_deploy_execution.py`
- Modify: `docs/current/TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md`

**Interfaces:**

- Pre-switch critical command states are `prepared`, `dispatching`, and
  `outcome_unknown`.
- A historical terminal `hard_stopped` command is not a permanent global deploy
  blocker. It blocks through the existing `active_domain_holds` or
  `unsafe_real_write_attempt_exists` checks only while its safety condition remains
  active.
- Phase-two capability certification may atomically update only its bounded PG
  process outcomes after digest revalidation, but performs no exchange mutation.
  Before the canary, one explicit bounded fact-refresh stage may update only the
  existing public/account fact projections; it records exact before/after table
  digests and runs while all scheduled production writers stay fenced. Its SQL
  mutation allowlist is exactly `brc_runtime_fact_snapshots` and
  `brc_exchange_account_modes_current`; it passes no Action-Time invocation ID,
  and SQL capture fails on any other INSERT/UPDATE/DELETE target.
- Canary execution is stricter: it uses the dedicated two-route ASGI app under
  `pg_read_all_data`, and the API-only watcher has no direct PG/fact/materializer
  port. It updates no production Ticket, promotion, lane, runtime-safety,
  authorization, command, protected-submit, lifecycle, fact, signal, or process-
  outcome row. Lifecycle capability remains disabled until certification and
  canary acceptance pass.
- The production login behind `SET ROLE` remains technically recoverable, so R1
  treats role/read-only settings and direct-DML rejection as defense in depth,
  not independent credential isolation. The primary zero-write proof is the
  exact two-route dependency graph, SELECT-only SQL capture, unreachable writer/
  gateway ports, zero exact-SHA call counters, and unchanged bounded sentinel.
  Tests require zero `RESET ROLE`, alternate `SET ROLE`, or `READ WRITE`
  statement; they do not falsely assert PostgreSQL rejects a reset to session
  user.
- Success restores the captured **desired enabled/disabled policy**, not the old
  capability row. A previously enabled policy receives a fresh lifecycle ref
  and durable proof payload; a disabled policy stays disabled. Migration-owned
  exit-policy capabilities are verified, never overwritten.
- Certification uses two identities. `action-time-cert:v2:<hash>` is computed
  before projection publication from target head/input digest/release activation/
  lane watermarks/final facts/stage/deploy nonce and is written to every lane
  outcome. After publication, frozen `LifecycleMutationEnablementProof` binds
  that shared Action-Time ref to the lane digest, enablement-time fact evidence,
  and a certification-projection digest that excludes the lifecycle capability
  row and fields derived from it. The stored lifecycle ref format is
  `lifecycle-cert:v2:<64 lowercase hex>`; the two refs are never substituted for
  one another.
- Revision 124 adds nullable `proof_schema` and bounded `proof_payload JSONB` to
  `brc_runtime_capabilities_current` and two process-outcome indexes. The partial
  `idx_brc_runtime_outcome_lane_process_latest` on
  `(lane_identity_key,process_name,updated_at_ms DESC,process_outcome_id DESC)`
  where `scope_kind='runtime_lane'` resolves the canary's current slice. The
  generic recent-window index
  `idx_brc_runtime_outcome_canary_window(updated_at_ms DESC,
  process_outcome_id DESC)` narrows typed-lane, `production:tokyo`, and global/legacy process
  branches to the frozen time window before fetching full rows. Neither query
  scans retained lifetime history.
  Enabling uses one SERIALIZABLE transaction
  to write status/ref/schema/payload atomically after recomputation. An enabled
  row without a canonical payload of at most 64 KiB or without a matching ref is
  invalid. Disable clears proof fields. Runtime hashes the stored proof and
  verifies current head/lane digest/release activation/shared Action-Time ref;
  it does not scan history to recover a proof from its hash.
- Normal public/account fact refresh and same-head projection republish do not
  invalidate lifecycle mutation merely because enablement-time fact IDs or the
  projection digest changed. Current fact freshness remains an Action-Time gate.
  Head/lane/release-activation/Action-Time-ref drift fail-closes Runtime Safety
  State, protected submit, lifecycle maintenance, and command execution.
- Add `read_lifecycle_mutation_capability_prestate_v1()` for schema-120 deploy
  capture only. It reads legacy status/ref/timestamp under `pre_migration`,
  returns no readiness authority, and is unreachable from normal runtime.
  Fail-safe disable detects schema shape: known revisions 120-123 update only
  status/ref; schema 124 also clears proof fields. Enable is rejected on 120-123
  and requires schema 124 plus a verified v2 proof. Runtime decision rejects
  legacy/free-form enabled rows.
- Systemd restoration uses typed `UnitFileState`, `ActiveState`, `SubState`,
  `Result`, `TriggeredBy`, and `Triggers`. Static services restore only through
  captured allowlisted owners; `indirect` blocks before mutation. Transient
  failure is evidence, not a restore target.
- Before migration, the deploy connection must prove
  `pg_has_role(session_user,'pg_read_all_data','SET')`, successfully assume
  that role in a disposable session, report `current_user='pg_read_all_data'`,
  and show no mutation/sequence-write privileges on every canary-reachable
  table. Failure stops before schema mutation; R1 issues no CREATE/ALTER/GRANT or
  secret change.
- Any post-quiescence command failure durably engages the fence, stops every
  production/canary writer, and disables lifecycle capability.
- Normal-mode pre-migration failure may restore the healthy previous runtime;
  incident mode never restores the known-OOM watcher after maintenance starts.
  Any mode after migration 121 begins is writers-disabled forward-fix only.

- [ ] **Step 1: Write the prepared-command RED test**

```python
def test_phase_two_blocks_prepared_exchange_command(conn):
    seed_exchange_command(conn, command_state="prepared")
    result = evaluate_phase_two_readiness(conn, now_ms=1_000)
    assert result["status"] == "blocked"
    assert "phase_two_critical_exchange_command_exists" in result["blockers"]
```

Add `test_phase_two_ignores_closed_historical_hard_stop_without_active_freeze`:
seed one `hard_stopped` command, a closed lifecycle, and no active freeze; assert
`status == "phase_two_ready"`. Add
`test_phase_two_blocks_hard_stop_with_active_domain_freeze`: seed the same
command plus one active freeze and assert
`phase_two_active_domain_hold_exists` is present.
Add `test_phase_two_blocks_hard_stop_with_nonclosed_unsafe_lifecycle`: seed no
active freeze but one nonclosed, protection-incomplete real lifecycle and assert
`phase_two_unsafe_real_write_attempt_exists` is present.

Add negative cases beginning from a real-write attempt for: lifecycle missing;
complete protection not reconciled; mismatched ticket; mismatched attempt;
mismatched lifecycle `exit_protection_set_id`; lifecycle blocker; and protection
blocker. Each must block. A correctly
closed lifecycle and one exactly matching protected tuple are the only passing
real-write shapes.

- [ ] **Step 2: Write the zero-exchange deploy RED test**

Build the deploy phases and assert the phase-two command does not contain:

```python
for forbidden in (
    "run_ticket_bound_lifecycle_maintenance_once.py",
    "allow-exchange-mutation",
    "execute-operation-layer-submit",
    "runtime_signal_watcher_resume_dispatcher.py",
    "materialize_action_time_finalgate_preflight",
    "gateway.place_order",
    "real_gateway_action",
):
    assert forbidden not in certification_and_canary_commands
```

Execute the canary plan with fake Ticket, promotion, lane, runtime-safety,
authorization, FinalGate, Operation Layer, dispatcher, and gateway counters and
assert every counter remains zero. Assert the planner starts the loopback-only
`brc-owner-console-canary-readonly.service`, invokes
`brc-runtime-signal-watcher-canary.service` against it, and never invokes the
production backend or watcher during the five canaries.

Add a pre-migration role-preflight test. Missing role membership, failed
`SET ROLE`, unexpected `current_user`, or any INSERT/UPDATE/DELETE/TRUNCATE/
sequence-write privilege must stop before the first Alembic command. Assert the
plan contains no `CREATE ROLE`, `ALTER ROLE`, `GRANT`, password, or secret
mutation fallback.

Production mutation proof does not scan whole tables or rely on newest-row
watermarks. Require exact canary API sessions to report
`current_user=pg_read_all_data`, allowed SELECT, denied DML/TRUNCATE/sequence
privileges, and read-only session/transaction facts. Inject direct forbidden
insert/update/delete while the current role is `pg_read_all_data` and require
rejection. SQL capture must contain zero `RESET ROLE`, alternate `SET ROLE`, or
`SET TRANSACTION READ WRITE`; no test claims those statements are denied by the
underlying production login.

Freeze `CanaryMutationSentinelProjection` in one shared constants/model module:

| Relation | Exact predicate / `N` | Exact digested columns |
| --- | --- | --- |
| `brc_runtime_fact_snapshots` | exact frozen fact IDs / **128** | `CANARY_FACT_COLUMNS_V1`; each JSON field logical bytes <= **64 KiB** |
| `brc_live_signal_events` | exact selected signal IDs / **22** | `CANARY_SIGNAL_COLUMNS_V1`; each JSON field logical bytes <= **64 KiB** |
| `brc_runtime_process_outcomes` current slice | exact 22 `lane_identity_key` values crossed with the five frozen lane process names; latest per pair by indexed `LATERAL ... ORDER BY updated_at_ms DESC,process_outcome_id DESC LIMIT 1`, plus exact release-activation `process_outcome_id` / **111** | `CANARY_PROCESS_OUTCOME_COLUMNS_V1` |
| `brc_runtime_process_outcomes` canary-window slice | `updated_at_ms >= canary_window_floor_ms` and either an exact 22 `lane_identity_key`, `scope_key='production:tokyo'`, or one of the five frozen lane process names; no process restriction inside exact lane/production scopes / **256** | `CANARY_PROCESS_OUTCOME_COLUMNS_V1`; pre/post set and digest must match |
| `brc_action_time_lane_inputs` | exact pre-canary lane IDs / **22** | `CANARY_LANE_COLUMNS_V1` |
| `brc_action_time_tickets` | exact lane IDs, **no status predicate** / **22** | `CANARY_TICKET_COLUMNS_V1` |
| `brc_ticket_bound_protected_submit_attempts` | exact ticket IDs / **44** | `CANARY_PROTECTED_ATTEMPT_COLUMNS_V1` |
| `brc_ticket_bound_exchange_commands` | exact ticket IDs, **no command-state predicate** / **88** | `CANARY_EXCHANGE_COMMAND_COLUMNS_V1` |
| `brc_ticket_bound_order_lifecycle_runs` | exact ticket IDs / **22** | `CANARY_LIFECYCLE_COLUMNS_V1` |
| `brc_ticket_bound_exit_protection_sets` | exact ticket IDs / **22** | `CANARY_PROTECTION_SET_COLUMNS_V1` |
| `brc_ticket_bound_exit_protection_orders` | exact set IDs, **no status predicate** / **88** | `CANARY_PROTECTION_ORDER_COLUMNS_V1` |
| `brc_ticket_exit_policy_current` | exact ticket IDs / **22** | `CANARY_EXIT_POLICY_CURRENT_COLUMNS_V1` |
| `brc_exchange_account_modes_current` | exact frozen account-mode IDs from the pre-canary fact set / **22** | `CANARY_ACCOUNT_MODE_COLUMNS_V1` |
| `brc_runtime_capabilities_current` | `capability_id='ticket_lifecycle_durable_mutation'` / **1** | `CANARY_LIFECYCLE_CAPABILITY_COLUMNS_V1` |
| `brc_pretrade_readiness_rows` | exact 22 `(strategy_group_id,symbol,side)` keys / **22** | `readiness_row_id,candidate_scope_id,strategy_group_id,symbol,side,readiness_state,detector_state,watcher_state,public_facts_state,signal_lifecycle_status,signal_freshness_state,risk_state,scope_state,promotion_state,first_blocker_class,first_blocker_detail,next_action,stop_condition,evidence_ref,source_watermark,valid_until_ms`; exclude `computed_at_ms` |
| `brc_goal_status_current` | fixed ID `strategygroup-runtime-goal-status` / **1** | `goal_status_current_id,status,fresh_signal_present,ready_for_real_order_action,owner_action_required,blockers,input_watermark,projection_run_id`; exclude `updated_at_ms` |
| `brc_control_read_model_snapshots` | `is_current=true` and exact model types `candidate_pool,daily_live_enablement_table,goal_status` / **3** | `snapshot_id,model_type,source_watermark,owner_projector,input_watermark,output_path,is_current,generated_by` plus canonical expression `payload - 'generated_at_ms'`; embedded `code_version` must equal target SHA; exclude `generated_at_ms` |
| `brc_projection_runs` | exact three IDs referenced by the current snapshots/goal row / **3** | `projection_run_id,model_type,owner_projector,code_version,source_mode,projection_target,input_watermark,source_priority,legacy_diagnostics_read,legacy_diagnostics_affected_current,status,error_detail`; require `code_version=target SHA`; exclude `started_at_ms,finished_at_ms` |

The shared constants module freezes every schema-124 sentinel tuple without
`PK` or “fact IDs” shorthand:

```python
CANARY_FACT_COLUMNS_V1 = (
    "fact_snapshot_id", "strategy_group_id", "symbol", "side",
    "runtime_profile_id", "fact_surface", "source_kind", "source_ref",
    "computed", "satisfied", "freshness_state", "failed_facts",
    "fact_values", "blocker_class", "observed_at_ms", "valid_until_ms",
    "created_at_ms", "action_time_invocation_id",
)
CANARY_SIGNAL_COLUMNS_V1 = (
    "signal_event_id", "candidate_scope_id", "event_spec_id",
    "strategy_group_id", "symbol", "side", "detector_key", "signal_type",
    "source_kind", "status", "freshness_state", "confidence",
    "fact_snapshot_id", "reason_codes", "signal_payload", "event_time_ms",
    "trigger_candle_close_time_ms", "observed_at_ms", "expires_at_ms",
    "invalidated_at_ms", "created_at_ms", "candidate_scope_event_binding_id",
    "runtime_scope_binding_id", "runtime_instance_id", "runtime_profile_id",
    "policy_current_id", "strategy_group_version_id", "asset_class",
    "event_spec_version", "event_id", "timeframe", "time_authority",
    "lane_identity_key", "source_watermark", "signal_grade",
    "required_execution_mode", "execution_eligible", "authority_source_ref",
)
CANARY_PROCESS_OUTCOME_COLUMNS_V1 = (
    "process_outcome_id", "process_name", "scope_key", "run_id",
    "process_state", "business_state", "first_blocker", "started_at_ms",
    "completed_at_ms", "runtime_head", "source_watermark",
    "projector_owner", "updated_at_ms", "scope_kind", "candidate_scope_id",
    "candidate_scope_event_binding_id", "runtime_scope_binding_id",
    "runtime_instance_id", "runtime_profile_id", "policy_current_id",
    "strategy_group_id", "strategy_group_version_id", "symbol", "asset_class",
    "side", "event_spec_id", "event_spec_version", "event_id", "timeframe",
    "time_authority", "lane_identity_key", "legacy_evidence",
    "action_time_invocation_id",
)
CANARY_LANE_COLUMNS_V1 = (
    "action_time_lane_input_id", "promotion_candidate_id", "strategy_group_id",
    "symbol", "side", "runtime_profile_id", "lane_scope", "status",
    "signal_event_id", "public_fact_snapshot_id", "action_time_fact_snapshot_id",
    "runtime_scope_binding_id", "candidate_authorization_ref",
    "runtime_safety_snapshot_id", "first_blocker_class", "created_at_ms",
    "expires_at_ms", "closed_at_ms", "authority_boundary", "signal_grade",
    "required_execution_mode", "execution_eligible", "authority_source_ref",
    "lane_identity_key", "source_watermark", "action_time_invocation_id",
    "account_safe_fact_snapshot_id", "account_mode_fact_snapshot_id",
)
CANARY_TICKET_COLUMNS_V1 = (
    "ticket_id", "action_time_lane_input_id", "promotion_candidate_id",
    "signal_event_id", "event_spec_id", "event_spec_version_id",
    "candidate_scope_id", "runtime_scope_binding_id", "strategy_group_id",
    "strategy_group_version_id", "symbol", "exchange_instrument_id", "side",
    "event_id", "event_time_ms", "trigger_candle_close_time_ms",
    "runtime_profile_id", "public_fact_snapshot_id",
    "action_time_fact_snapshot_id", "account_safe_fact_snapshot_id",
    "account_mode_snapshot_id", "budget_reservation_id", "protection_ref_id",
    "execution_policy_id", "execution_policy_version", "owner_policy_version",
    "sizing_policy_version", "protection_policy_version", "target_notional",
    "leverage", "expires_at_ms", "status", "authority_boundary", "ticket_hash",
    "created_under_versions_hash", "created_at_ms", "signal_grade",
    "required_execution_mode", "execution_eligible", "authority_source_ref",
    "effective_notional", "selected_leverage", "planned_stop_risk_budget",
    "planned_stop_risk", "lane_identity_key", "source_watermark",
    "action_time_invocation_id", "exit_policy_id", "exit_policy_version",
    "exit_policy_snapshot", "exit_policy_hash",
)
CANARY_PROTECTED_ATTEMPT_COLUMNS_V1 = (
    "protected_submit_attempt_id", "ticket_id", "finalgate_pass_id",
    "operation_layer_handoff_id", "operation_submit_command_id",
    "runtime_safety_snapshot_id", "action_time_lane_input_id",
    "strategy_group_id", "symbol", "side", "runtime_profile_id",
    "submit_mode_decision_id", "submit_mode", "status", "submit_allowed",
    "blockers", "warnings", "trusted_fact_refs", "submit_request",
    "submit_result", "identity_evidence", "official_operation_layer_submit_called",
    "exchange_write_called", "order_created", "order_lifecycle_called",
    "withdrawal_or_transfer_created", "live_profile_changed",
    "order_sizing_changed", "authority_boundary", "created_at_ms",
    "updated_at_ms", "signal_grade", "required_execution_mode",
    "execution_eligible", "authority_source_ref",
)
CANARY_EXCHANGE_COMMAND_COLUMNS_V1 = (
    "exchange_command_id", "protected_submit_attempt_id", "ticket_id",
    "operation_submit_command_id", "account_id", "strategy_group_id",
    "runtime_profile_id", "exchange_instrument_id", "gateway_symbol", "symbol",
    "order_role", "side", "gateway_side", "local_order_id", "parent_order_id",
    "client_order_id", "command_generation", "request_fingerprint", "order_type",
    "amount", "price", "stop_price", "reduce_only", "authority_source_ref",
    "command_state", "outcome_class", "exchange_order_id", "exchange_error_code",
    "exchange_error_message", "prepared_at_ms", "dispatch_started_at_ms",
    "resolved_at_ms", "updated_at_ms", "exchange_id", "position_mode",
    "position_side", "position_bucket", "netting_domain_key", "reduce_intent",
    "command_kind", "command_source", "source_command_id",
    "target_exchange_order_id", "claim_owner", "claim_token",
    "claim_started_at_ms", "claim_expires_at_ms", "execution_attempt_count",
    "last_reconciled_at_ms", "exchange_result", "desired_leverage",
    "execution_style", "time_in_force", "post_only", "market_fallback_allowed",
)
CANARY_LIFECYCLE_COLUMNS_V1 = (
    "lifecycle_run_id", "ticket_id", "protected_submit_attempt_id",
    "strategy_group_id", "symbol", "side", "runtime_profile_id", "status",
    "entry_local_order_id", "entry_exchange_order_id", "entry_fill_confirmed",
    "entry_filled_qty", "entry_avg_price", "exit_protection_set_id",
    "first_blocker", "blockers", "warnings", "authority_boundary",
    "created_at_ms", "updated_at_ms",
)
CANARY_PROTECTION_SET_COLUMNS_V1 = (
    "exit_protection_set_id", "ticket_id", "protected_submit_attempt_id",
    "entry_local_order_id", "entry_exchange_order_id", "strategy_group_id",
    "symbol", "side", "entry_filled_qty", "entry_avg_price", "status",
    "sl_order_id", "tp1_order_id", "runner_qty", "protection_complete",
    "reconciled_with_exchange", "first_blocker", "blockers", "warnings",
    "authority_boundary", "created_at_ms", "updated_at_ms",
)
CANARY_PROTECTION_ORDER_COLUMNS_V1 = (
    "exit_protection_order_id", "exit_protection_set_id", "ticket_id", "role",
    "local_order_id", "exchange_order_id", "status", "order_type", "side",
    "qty", "price", "trigger_price", "reduce_only",
    "replaces_exit_protection_order_id", "created_at_ms", "updated_at_ms",
    "generation",
)
CANARY_EXIT_POLICY_CURRENT_COLUMNS_V1 = (
    "ticket_id", "exit_protection_set_id", "exit_policy_id",
    "exit_policy_version", "exit_policy_hash", "exit_execution_snapshot",
    "exit_execution_hash", "actual_r_per_unit", "resolved_tp1_price",
    "resolved_tp1_target_qty", "tp1_cumulative_filled_qty",
    "tp1_completion_state", "remaining_position_qty", "state",
    "last_evaluated_watermark_ms", "next_evaluation_not_before_ms",
    "last_decision_kind", "last_reason_code", "active_runner_order_id",
    "active_runner_generation", "active_runner_stop", "runner_break_even_floor",
    "runner_floor_applied_at_ms", "pending_runner_order_id", "pending_generation",
    "replaced_runner_order_id", "first_blocker", "updated_at_ms",
)
CANARY_ACCOUNT_MODE_COLUMNS_V1 = (
    "account_mode_current_id", "account_id", "exchange_id", "runtime_profile_id",
    "position_mode", "dual_side_position", "position_mode_safe", "status",
    "fact_snapshot_id", "source_kind", "source_ref", "observed_at_ms",
    "valid_until_ms", "updated_at_ms",
)
CANARY_LIFECYCLE_CAPABILITY_COLUMNS_V1 = (
    "capability_id", "status", "certification_ref", "updated_at_ms",
    "proof_schema", "proof_payload",
)
```

Before the first sentinel read, the inspected column-name set for each relation
must equal the corresponding constant's name set, while SELECT and digest order
must follow the tuple order above. A missing or newly added column blocks the
canary until this versioned contract is reviewed; it is never silently omitted.
Every constant must also satisfy `len(columns) == len(set(columns))`; duplicate
column names fail the schema-contract test before SQL construction.
The process-outcome schema golden combines the revision-106 base columns,
revision-118 stored lane columns, and revision-119
`runtime_profile_id,policy_current_id,time_authority,action_time_invocation_id`;
all **33** names must match exactly.
Every selected JSON or unbounded Text field has a **64 KiB** logical-byte guard,
each current-snapshot semantic payload retains its **1 MiB** guard, and the
complete canonical sentinel input is capped at **16 MiB**. Overflow fails before
large values cross into Python.

Immediately before the pre-canary sentinel, read
`canary_db_now_ms=floor(extract(epoch from clock_timestamp())*1000)` in the same
read-only database session and freeze
`canary_window_floor_ms=canary_db_now_ms-1000`. Capture the window slice both
before and after all five canaries. The current process-outcome slice is one
`VALUES` table of the exact **22 x 5** lane/process pairs joined to indexed
`LATERAL` latest-row probes, plus the exact release-activation ID. SQL capture
must prove predicate/order compatibility with
`idx_brc_runtime_outcome_lane_process_latest`; a 100,000-history-row PostgreSQL
`EXPLAIN` fixture must select that index path and complete under five seconds. A
historical count, window function over retained rows, or scope-only row fetch is forbidden. The
canary-window slice contains every row at or after the frozen floor that is in
the exact lane/production scope, plus every new legacy/global row using a frozen
lane process name. Exact lane/production scope rows have no process predicate. Its
pre/post row set and digest must match; overflow at **257** fails without
creating a lifetime-history ceiling.

Implement the window slice as one SQL statement and one MVCC snapshot, using a
`MATERIALIZED` bounded-ID CTE plus an outer primary-key lookup. The CTE enters
only through `idx_brc_runtime_outcome_canary_window`, applies the index condition
`updated_at_ms >= canary_window_floor_ms`, filters the three semantic branches
over only those recent heap rows, orders by the two index columns, and returns at
most **257** primary keys. The outer query fetches the exact 33-column tuples by
those keys and performs canonical primary-key sorting/digest over no more than
257 rows. The single statement has one five-second `statement_timeout`; two
statements and their TOCTOU window are forbidden. Production-shape
`EXPLAIN (ANALYZE, BUFFERS)` fixtures with both
**100,000** and **1,000,000** retained rows independently exercise typed-lane,
`production:tokyo`, and each of the five global/legacy frozen-process inputs.
Typed-lane and production fixtures each include a recent unknown-process row to
prove SQL does not hide it behind an allowlist. Every fixture must
use the time-leading index, avoid `Seq Scan`, return or overflow deterministically,
and finish inside the five-second deadline. This program/data-path gate must pass
before cgroup or swap containment is considered.

Each relation executes one explicit-column query per declared slice with the
stated predicate, five-second statement timeout, stable primary-key order, and
`LIMIT N+1`. The window process-outcome, Ticket, command, and exit-order queries
select every row in the exact identity scope; the application then validates
the complete allowed process/status sets. Thus an unknown process or status is
visible and fails.
Duplicate/out-of-scope identity, timeout, or overflow also fails. JSON guards
use `octet_length(jsonb::text)` before
transfer: fact/signal fields use the per-field limits above, goal/projection
watermarks use **64 KiB**, and each current-snapshot semantic payload uses
**1 MiB**. `pg_column_size` is forbidden.

The frozen status sets are:

```text
lane_process_name.v1 = live_signal_materialization,action_time_fact_snapshots,
                       promotion_action_time_lane,action_time_ticket_sequence,
                       action_time_capability_certification
production:tokyo process = runtime_release_activation exactly once
ticket_status.v1 = created,preflight_pending,finalgate_ready,finalgate_rejected,
                   expired,superseded,submitted,closed,invalidated
exchange_command_state.v1 = prepared,dispatching,confirmed_submitted,
                            confirmed_rejected,outcome_unknown,
                            reconciled_submitted,reconciled_absent,hard_stopped
exit_protection_order_status.v1 = planned,submitted,open,partially_filled,
                                  filled,cancel_pending,cancelled,
                                  replace_pending,replaced,failed
```

For every canary-window row whose process is in `lane_process_name.v1`, require
`scope_kind='runtime_lane'`, an exact frozen `lane_identity_key`, and byte-
matching complete stored identity. A new `legacy_unscoped`, `global`, null-key,
or cross-lane row fails even when its process name is known.

The canonical digest sorts by sentinel slice, relation, then PK and uses typed canonical JSON v1.
Compare it and exchange identities before/after all five runs. Contract tests
capture SQL and assert every shared relation/predicate/column/limit constant;
parametrize every literal column in every `CANARY_*_COLUMNS_V1` tuple, mutate
one field at a time, and require a nonzero digest or typed out-of-scope failure.
Add explicit JSON/numeric/generation, every process-outcome field, unknown
canary-window process, unknown-status, missing-column, duplicate-tuple-column,
and synthetic-added-column cases. There is no
per-lane historical query loop. The structural route/dependency/SQL
boundary and unreachable writers are primary proof; role-based DML denial and
the bounded sentinel are defense in depth. A missing role/privilege fact,
non-allowlisted route, accepted direct DML, any escalation statement, sentinel
delta/overflow/timeout, or exchange delta fails closed.

Also assert certification leaves lifecycle capability disabled. After canary,
disabled prepolicy stays disabled; enabled prepolicy is applied through the
current setter with a **new** certification reference. The old row remains audit
evidence only. Restore the watcher timer last only when its typed prepolicy
requires it.

Freeze the enablement proof:

```python
class LaneSourceWatermarkV1(FrozenModel):
    lane_scope_key: str
    lane_identity_key: str
    source_watermark: str
    process_outcome_id: str

class ActionTimeFactDigestRowV1(FrozenModel):
    fact_snapshot_id: str
    strategy_group_id: str | None
    symbol: str | None
    side: str | None
    runtime_profile_id: str | None
    fact_surface: str
    source_kind: str
    source_ref: str | None
    computed: bool
    satisfied: bool | None
    freshness_state: str
    failed_facts: tuple[str, ...]
    fact_values: dict[str, CanonicalJsonValue]
    blocker_class: str | None
    observed_at_ms: int
    valid_until_ms: int | None

class ActionTimeCertificationReferenceV2(FrozenModel):
    schema: Literal["brc.action_time_certification_reference.v2"]
    stage: Literal["pre_canary", "post_canary"]
    target_runtime_head: str
    certification_input_digest_schema: Literal[
        "brc.action_time_capability_certification_input.v1"
    ]
    certification_input_digest: str
    release_activation_outcome_id: str
    release_activation_source_watermark: str
    lane_source_watermarks: tuple[LaneSourceWatermarkV1, ...]
    fact_snapshot_ids: tuple[str, ...]
    fact_set_digest_schema: Literal["brc.action_time_fact_set_digest.v1"]
    fact_set_digest: str
    fact_min_valid_until_ms: int
    deploy_nonce: str

action_time_ref = "action-time-cert:v2:" + sha256(
    canonical_typed_json(action_time_payload.model_dump(mode="json"))
).hexdigest()

class LifecycleMutationEnablementProof(FrozenModel):
    schema: Literal["brc.lifecycle_mutation_enablement_proof.v2"]
    target_runtime_head: str
    lane_identity_digest: str
    action_time_certification_ref: str
    action_time_certification_payload: ActionTimeCertificationReferenceV2
    certification_projection_digest_schema: Literal[
        "brc.certification_projection_digest.v1"
    ]
    certification_projection_digest: str

certification_ref = "lifecycle-cert:v2:" + sha256(
    canonical_typed_json(proof.model_dump(mode="json"))
).hexdigest()
```

`CanonicalJsonValue` is the frozen recursive typed-canonical value union:
explicit null, boolean, UTF-8 string, finite `Decimal`, ordered tuple, or
string-keyed mapping. It never admits Python `float`, NaN, or Infinity. The
fact query receives the complete expected fact-ID set from certification,
requires at most **128** unique IDs sorted by `fact_snapshot_id`, and rejects a
duplicate, missing, extra, or out-of-scope row. Its selected columns are exactly
the `ActionTimeFactDigestRowV1` fields above. SQL uses
`octet_length(failed_facts::text)` and `octet_length(fact_values::text)` guards
of **64 KiB** per field, and the complete canonical fact-set input is capped at
**1 MiB**. Oversize rows fail before JSON transfer. Object keys sort, arrays
retain order, explicit null differs from missing, and PostgreSQL/JSON numeric
tokens normalize through `Decimal` without binary-float conversion.

Before projection publication, the final Action-Time command computes a separate
v2 payload with lane outcome identities
`(lane_scope_key,lane_identity_key,source_watermark,process_outcome_id)` sorted
by lane identity and fact IDs sorted lexically. Each process-outcome ID is
deterministically derived before insertion from the frozen process name, lane
identity, and source watermark using
`"process_outcome:" + sha256(f"action_time_capability_certification|{lane_identity_key}|{source_watermark}").hexdigest()[:32]`.
The command reselects and hashes the exact
`ActionTimeFactDigestRowV1` rows, uses
typed canonical JSON v1, and stores its ref in every current lane
outcome's `run_id="certification:<action-time-ref>"`. Prepare returns the full
payload/ref; SERIALIZABLE apply independently reselects the exact ID set,
recomputes both digest schemas and byte-compares the full payload/ref.
Publication then produces the
certification projection slice. The enable setter starts one SERIALIZABLE
transaction, re-reads the bounded certification profile, final fact evidence,
release activation, lane digest, shared Action-Time ref, and the projection
slice that explicitly excludes lifecycle capability/ref-derived fields. It
requires the nested `fact_min_valid_until_ms >= now_ms + 30_000`, rehashes the
nested payload to the shared Action-Time ref, computes the
lifecycle ref, and atomically writes status/ref/proof schema/proof payload.
Disable remains fail-safe, clears proof fields, and needs an audit reason rather
than an enablement proof.

Freeze `CertificationProjectionIdentityV1` as the exact
`brc_runtime_process_outcomes` rows named by the **22 process-outcome IDs** in
the post-canary `ActionTimeCertificationReferenceV2`. Require each row's
`process_name='action_time_capability_certification'`, `scope_key`,
`lane_identity_key`, and `source_watermark` to equal its frozen reference
identity. Select only
`process_outcome_id`, `process_name`, `scope_key`, `run_id`, `process_state`,
`business_state`, `first_blocker`, `runtime_head`, `source_watermark`, and
`projector_owner`, plus `lane_identity_key`; sort by `lane_identity_key`;
preserve explicit null; exclude all
start/complete/update/generated timestamps; encode with typed canonical JSON v1
and SHA-256 the UTF-8 bytes. Golden tests prove row order and same-head republish
do not change the digest, while every semantic field does. The digest input
contains no lifecycle capability row/ref or derived field.
Historical rows at another source watermark are deliberately ignored; a
duplicate frozen identity, missing/extra row, wrong process/scope/lane/watermark,
or mismatch between deterministic ID and identity fails before capability
enablement.

Add `ActionTimeCertificationReferenceV2` and `ActionTimeFactDigestRowV1` golden
vectors for shuffled SQL row/key order, duplicate/missing/extra IDs, Decimal
scale, both stage enums, deploy-nonce changes, explicit null, multibyte Unicode,
and every fact/reference semantic-field mutation. Prepare/apply must reproduce
the same bytes from independent reads. A pre-canary payload cannot be reused as
post-canary, and one deploy nonce cannot be reused by another lineage.

Add RED tests for free-form/old ref, missing/oversized/noncanonical proof payload,
wrong digest schema/digest/head/activation/fact evidence/projection digest,
projection digest self-reference, expired enablement fact, missing/extra lane
outcome, wrong lane watermark, mismatched Action-Time ref, serialization failure,
and drift between proof preparation and setter apply. Every failure writes zero
capability changes. After a passing enable, run a normal fact refresh and same-
head current-projection republish and prove capability stays ready; then mutate
release head, lane identity, activation, or shared Action-Time ref and prove
Runtime Safety State, protected submit, lifecycle maintenance, and exchange-
command worker all return the typed capability blocker before exchange mutation.

Add migration-124 RED tests. Upgrade must add `proof_schema VARCHAR(128)` and
`proof_payload JSONB`, disable `ticket_lifecycle_durable_mutation`, clear both
proof fields, and set a migration-124 fail-closed reference after revision 123
has installed the approved exit policy. The enabled-state constraint requires a
v2 lifecycle ref plus non-null proof schema/payload; application validation
proves the canonical hash and 64-KiB bound. Exit-policy ID/version/hash/status
from revision 123 must remain unchanged. The deploy manifest, not migration
124, owns restoration of the captured desired enabled/disabled policy.
The same upgrade must create both named process-outcome indexes with exact
  columns, order, and partial predicate where applicable. Downgrade removes only
those revision-124 indexes/columns/constraint. The 100,000/1,000,000-row
production-shape plans above are migration acceptance, not optional benchmarks.

Add schema-compatibility RED tests: schema-120 enabled and disabled rows can be
captured through the legacy prestate reader and pass/fail deploy-quiescence only
on the independent safety checks; schema-120 failure containment can disable
using legacy columns. Fault after each committed revision 121, 122, and 123 and
prove disable still succeeds using legacy columns, the marker is durable, and
all writers stop. Schema-124 disable clears proof fields; enable on every
revision 120-123 is rejected; and normal schema-124 runtime rejects an enabled
legacy ref or missing v2 payload. No schema-120 path may call the strict runtime
capability decision as deployment readiness authority.

- [ ] **Step 3: Write failure-containment RED tests**

Use a runner that fails the post-switch smoke command. Assert:

```python
assert report["status"] == "failed_contained"
assert report["checks"]["writers_left_disabled"] is True
assert any(
    "systemctl stop brc-runtime-signal-watcher.timer" in item["command"]
    for item in report["command_results"]
)
assert any(
    "set_ticket_lifecycle_mutation_capability.py --disable" in item["command"]
    for item in report["command_results"]
)
```

Add two success-path state tests:

```text
prestate lifecycle-mutation capability=enabled, timers=enabled+active
  -> poststate enabled with fresh target-SHA certification ref, enabled+active
prestate lifecycle-mutation capability=disabled, timers=disabled+inactive
  -> poststate exactly disabled, disabled+inactive
observed watcher oneshot=failed
  -> evidence preserves failed, target health becomes inactive/result=success
```

The second case returns `accepted_disabled` and contains no `systemctl enable`
or capability-enable command. Add mixed enabled/inactive timer coverage plus
`static`, `indirect`, pre-existing `masked`, `activating`, and `deactivating`
cases. Assert only stable policy states are restored, static units are never
enabled directly, an indirect unit blocks before mutation, and transient states
are not recreated.

Freeze this restore mapping in tests:

| Captured state | Restore action | Acceptance |
| --- | --- | --- |
| `UnitFileState=enabled` | `enable` only after candidate files are installed; start only when captured stable policy was active | enabled and requested active state |
| `UnitFileState=disabled` | keep/mark disabled; never enable | disabled; active only if explicitly captured as a manually active service |
| `UnitFileState=static` | require every `TriggeredBy`/`Triggers` owner in the explicit captured allowlist; never enable the service directly | still static; captured owner policy controls start |
| `UnitFileState=indirect` | block capture before first mutation | unsupported production graph; no guessed owner restoration |
| pre-existing `UnitFileState=masked` | preserve the pre-existing mask independently of the deploy fence | masked and inactive |
| `ActiveState=failed` for oneshot | retain as evidence, `reset-failed`, do not recreate failure | inactive with successful later invocation when required |
| `activating` / `deactivating` | poll up to 10 seconds for stable state; otherwise block capture before mutation | never accepted as restore policy |

Add the four failure-matrix tests:

| Mode | Failure boundary | Required result |
| --- | --- | --- |
| Normal | Before migration 121 | Atomic old-pointer and policy restore allowed |
| Normal | Migration 121 or later | `failed_contained_forward_fix`; all writers/canaries stopped behind persistent fence; candidate pointer active or `forward_fix_pointer_pending`; old pointer may be inert but cannot execute |
| Incident | Before migration 121 | `failed_contained_incident`; known-unsafe watcher/lifecycle remain disabled |
| Incident | Migration 121 or later | `failed_contained_forward_fix`; all writers/canaries stopped behind persistent fence; candidate pointer active or `forward_fix_pointer_pending`; old pointer may be inert but cannot execute |

Add a two-process lock test. Process A holds the canonical lock FD across a
blocked runner; process B, whether new or resume lineage, returns
`deploy_in_progress` nonblocking and cannot create/modify manifest, fence,
schema, pointer, or units. Symlink, wrong owner/mode, replaced inode, and a helper
that opens a second lock path all fail before mutation. Process A releases only
on terminal or contained exit.
Add planner/executor tests requiring the sole mutating remote command to use
the exact `sudo -n /usr/bin/systemd-run ... /usr/bin/python3 -c` transient-
service envelope plus the fixed stdin hash-loader, while every repository-owned
child command uses candidate venv Python and inherits the guarded lock FD.
Runtime tests prove bootstrap hash mismatch, non-CPython-3.10, nonzero EUID, or
failed sudo capability returns before persistent lock/manifest/fence mutation
and the transient unit is collected.

Add linked-manifest validation tests. A capture manifest may begin quiescence
only within 15 minutes. After quiescence and exact capability capture, a new
sealed restore manifest links capture checksum, deploy transaction ID, nonce,
old SHA, and target SHA, and allows migration to start for 90 minutes. Once
`migration_in_progress` is durably written before expiry, mark it recovery-
pinned for the same lineage only: later wall-clock expiry cannot prevent forward
recovery, but cannot authorize a new SHA, new deploy, or policy recapture. Test a
legal 60-minute incident path, a greater-than-90-minute post-migration recovery,
and a 600-second backup, plus failure for expired pre-migration capture/sealed manifest,
cross-lineage or terminally consumed nonce, wrong mode, machine ID/hostname, expected old SHA,
captured symlink target, approved target SHA, ownership/mode, parent checksum,
checksum, missing lifecycle desired-policy/audit evidence, or any attempt to
restore another capability. Prove same-lineage nonterminal reentry transitions
`restore_manifest_verified -> restore_pending -> lifecycle_desired_policy_restored
-> runtime_activation_committed -> activation_applied ->
deploy_transaction_terminal -> terminal_consumed` idempotently. The executor
never infers or recaptures pre-state after quiescence. Five scheduled ticks are
derived from existing target-SHA PG outcomes and exact-InvocationID journald
records; no new observation file/table is created, and observation never reopens
or blocks the consumed mutation manifest.

Freeze the only legal cross-lineage recovery artifact:

```python
class ForwardFixHandoffV1(FrozenModel):
    schema: Literal["brc.forward_fix_handoff.v1"]
    handoff_id: str
    parent_manifest_sha256: str
    parent_journal_digest: str
    parent_deploy_transaction_id: str
    parent_deploy_nonce: str
    child_deploy_transaction_id: str
    child_deploy_nonce: str
    machine_id: str
    hostname: str
    current_release_sha: str
    next_target_sha: str
    current_alembic_revision: Literal["124"]
    desired_lifecycle_policy: LifecycleDesiredPolicyV1
    production_unit_policy: tuple[ProductionUnitPolicyV1, ...]
    persistent_fence_path: str
    created_at_ms: int
```

Creation is legal only under the canonical root-held lock when the parent is
`forward_fix_required`, the persistent fence is fsynced, every writer/canary is
stopped, and the schema, pointer, runtime head, exchange safety state, and
parent journal chain are unambiguous. The parent supplies one predeclared child
transaction ID/nonce and one different exact SHA. The handoff is written
atomically as root-owned mode `0600`, file- and directory-fsynced, then the
parent journals `forward_fix_handoff_sealed` and
`superseded_by_forward_fix`. It can be consumed by exactly that one child; a
second child, replay, digest mismatch, in-place parent target change, policy
recapture, or policy/scope/risk/capital/leverage/credential mutation fails while
the fence remains engaged.

The handoff transfers only captured desired lifecycle policy and typed systemd
policy. It transfers **no** Action-Time certification, fact snapshot, freshness,
release activation, projection digest, Ticket/order authority, or exchange-
write authority. The child starts at `forward_fix_inherited_containment`,
revalidates host/schema/pointer/head/safety under the same lock, switches only
to its approved exact SHA, and reruns the complete release activation,
pre/post-fact refresh, certification, projection, readonly-canary, lifecycle-v2
proof, activation-commit, activation-apply, and post-activation observation path.

- [ ] **Step 4: Expand the critical-state query**

Replace historical `count(*)` gates with bounded `EXISTS(... LIMIT 1)` queries
under a read-only transaction, `lock_timeout='1s'`, and
`statement_timeout='5s'`. The command predicate is:

```sql
WHERE command_state IN (
  'prepared', 'dispatching', 'outcome_unknown'
)
```

Do not auto-cancel or auto-reconcile a prepared command during deployment.
Do not restore the old global `hard_stopped` predicate; active freezes and
unsafe real-write attempts are already independent fail-closed gates. Implement
the same attempt-rooted correlated safe-tuple query specified in Task 7 Step 6;
do not use an inner join rooted at lifecycle rows. A timeout is a blocker.

- [ ] **Step 5: Remove the lifecycle worker from certification**

Remove the complete shell block that captures output from
`run_ticket_bound_lifecycle_maintenance_once.py`. Split certification from
activation and keep this order:

```text
record lifecycle-mutation capability plus durable scheduling/backend policy;
record transient oneshot state as evidence only
-> install/engage persistent writer fence; quiesce all production writers;
   temporarily disable mutation
-> verify phase-two readiness
-> run file-I/O audit
-> assert lifecycle capability disabled
-> durably switch pointer; record exact release activation
-> run bounded pre-canary public/account fact refresh
-> prepare/apply exact-SHA pre-canary capability certification digest
-> publish/verify exact-SHA current projections from those facts/certification
-> run timerless API-only canary service five times against the dedicated
   privilege-reduced two-route API, with direct-DML denial, zero escalation
   statement, and production-
   table/exchange identity proof
-> run bounded post-canary fact refresh
-> rerun phase-two readiness and exact-SHA certification
-> republish/verify current projections; require at least 30 seconds remaining
   fact validity and finish this final segment within 30 seconds; one bounded
   repeat is allowed, then fail contained
-> verify exact release/PG/dependency/service facts
-> restore desired lifecycle policy with a fresh certification reference when
   previously enabled, bound to the post-canary digest; otherwise keep disabled
-> stop/disable canary units; verify all writer units still fenced
-> construct, file-fsync, rename, directory-fsync, reread, and verify the full
   runtime_activation_committed receipt while the writer fence remains present
-> durably remove the fence only from that commit; restore timer/backend policy
   from typed stable states and clear transient failures, with watcher timer last
-> journal activation_applied, deploy_transaction_terminal, and consume the
   sealed mutation manifest
-> start a separate target-SHA five-tick post-activation stability observation;
   record accepted, degraded, or not-applicable without rewriting the mutation
   journal or recreating the deploy fence
```

The lifecycle timer's next tick is normal runtime operation and is outside the
deployment certification transaction.

- [ ] **Step 6: Replace the unsafe EXIT trap**

On phase-two failure, execute:

```text
disable lifecycle capability
ensure persistent writer fence exists and is directory-fsynced
stop production backend, monitor, watcher, lifecycle, all related timers,
and both canary units
return failed_contained
```

Do not keep a PG-aware backend/monitor merely because its local health passed,
and do not start any production writer from a failure trap.
The incident-mode trap applies this containment even before migration. The
normal-mode trap may restore prestate only while the crash-safe deploy journal
is exactly `pre_migration` and the actual Alembic revision is 120. A
process-local `migration_started` boolean is not authority.

- [ ] **Step 7: Add activation-commit and crash recovery**

Add a phase-aware `failure_containment_commands` list to the remote state
machine. From quiescence through the phase before
`runtime_activation_committed`, failure ensures the persistent marker exists,
stops every production/canary writer with bounded timeouts, and records results
under the same lock. No path reports `failed_contained` unless every required
durable-fence/stop action succeeded; otherwise use
`failed_containment_incomplete`.

Freeze `RuntimeActivationCommitV1` as the complete payload embedded in the
hash-chained `runtime_activation_committed` journal entry, not as a second
authority file. The whole journal snapshot is written by same-directory
temporary file, file fsync, atomic rename, and directory fsync while the marker
is present and all writers/canaries are stopped, then reread byte-for-byte. Its
canonical digest binds transaction/nonce/host, exact target SHA and pointer, revision 124,
release activation ID/watermark, pre/post fact and Action-Time references,
current-projection identities/digests, zero-write canary result, phase-two and
final-freshness facts, exchange-safety result, desired lifecycle policy and v2
proof, typed production-unit desired policy, and writer-fence inode. Only that
receipt authorizes marker unlink and captured policy restoration.

Prove these hard-failure cases with parent `SIGKILL`, `RuntimeMaxSec`, SSH loss,
and host reboot at each boundary:

| Durable state | Marker state | Required recovery |
| --- | --- | --- |
| Before maintenance/fence engagement | Absent | `pre_maintenance_abort`; preserve pre-existing production runtime/policy, leave staged artifacts unreferenced, and perform no schema/pointer/unit-policy mutation |
| Before activation commit | Present | Remain contained; same lineage resumes or creates one fenced pre-activation forward-fix handoff |
| Activation commit valid | Present | Verify the receipt and idempotently remove the marker/apply captured unit policy |
| Activation commit valid | Absent | Treat activation as authorized; finish `activation_applied`/terminal consumption without recreating the marker |
| Activation commit missing or invalid | Absent | Unreachable under the crash-consistent fsync model; resume refuses all mutation and reports storage-integrity incident requiring host isolation/manual recovery |
| Mutation journal terminal | Absent | Do not reopen mutation authority; continue or restart only post-activation observation |

A post-migration, pre-activation defect may journal `forward_fix_required` only
while the fence remains fsynced and every writer is stopped. Under the same
canonical lock, exactly one atomic/fsynced handoff may name one child
transaction/nonce and new exact SHA; the parent advances through
`forward_fix_handoff_sealed -> superseded_by_forward_fix`. The child begins at
`forward_fix_inherited_containment` and completes the full fact/certification/
projection/canary/v2-proof/activation-commit path. Inject crashes before handoff
rename, after rename before parent journal append, after sealed journal, and
after child first consumption; every retry is idempotent. Reject a second child,
replayed nonce, digest mismatch, policy recapture, transferred certification/
freshness, and any expanded policy/scope/risk/capital/leverage/credential field.

After `activation_applied`, five target-SHA scheduled ticks run as a separate
read-only stability observation. Read exact tick/process-outcome identities from
existing PG and journald sources; after interruption restart counting from
**0/5**. Do not add a deploy-state JSON/Markdown file, recurring writer, or
runtime authority for observation. Tick failure, timeout, OOM, `SIGKILL`, `RuntimeMaxSec`, SSH
loss, or reboot produces `postdeploy_observation_degraded` or leaves observation
pending; it never recreates the deploy fence, invalidates the lifecycle proof,
or rewinds the consumed mutation manifest. A later code repair is a new normal
exact-SHA deployment; it is not an in-line post-activation handoff.

- [ ] **Step 8: Run Task 4 tests**

```bash
python3 -m pytest -q \
  tests/unit/test_ticket_lifecycle_phase_two_readiness.py \
  tests/unit/test_lifecycle_mutation_capability.py \
  tests/unit/test_lifecycle_mutation_enablement_proof_migration.py \
  tests/unit/test_canary_mutation_sentinel.py \
  tests/unit/test_ticket_bound_exchange_command_worker.py \
  tests/unit/test_ticket_bound_protected_submit_attempt.py \
  tests/unit/test_tokyo_lifecycle_phase_two_deploy.py \
  tests/unit/test_tokyo_runtime_governance_git_deploy_execution.py
```

Expected: all tests pass; certification/canary contains zero lifecycle worker,
FinalGate, Operation Layer, dispatcher, or gateway invocation; and enabled and
disabled desired policies are restored correctly without reusing an old
certification reference. The deployment contract describes the same zero-
exchange order and contains no PG-only lifecycle invocation after enablement.

- [ ] **Step 9: Commit Task 4**

```bash
git add \
  scripts/verify_ticket_lifecycle_phase_two_readiness.py \
  scripts/plan_tokyo_runtime_governance_git_deploy.py \
  scripts/execute_tokyo_runtime_governance_git_deploy.py \
  migrations/versions/2026-07-15-124_persist_lifecycle_mutation_enablement_proof.py \
  src/application/readmodels/canary_mutation_sentinel.py \
  src/application/action_time/lifecycle_mutation_capability.py \
  src/application/action_time/runtime_safety_state.py \
  src/application/action_time/exchange_command_worker.py \
  src/application/action_time/protected_submit_attempt.py \
  scripts/set_ticket_lifecycle_mutation_capability.py \
  tests/unit/test_ticket_lifecycle_phase_two_readiness.py \
  tests/unit/test_lifecycle_mutation_capability.py \
  tests/unit/test_lifecycle_mutation_enablement_proof_migration.py \
  tests/unit/test_canary_mutation_sentinel.py \
  tests/unit/test_ticket_bound_exchange_command_worker.py \
  tests/unit/test_ticket_bound_protected_submit_attempt.py \
  tests/unit/test_tokyo_lifecycle_phase_two_deploy.py \
  tests/unit/test_tokyo_runtime_governance_git_deploy_execution.py \
  docs/current/TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md
git commit -m "fix: make tokyo deploy certification fail closed"
```

---

### Task 5: Bind An Immutable Venv And Prove Postdeploy Runtime Readiness

**Files:**

- Create: `requirements-runtime.lock`
- Modify: `scripts/plan_tokyo_runtime_governance_git_deploy.py`
- Create: `scripts/tokyo_runtime_deploy_remote_state_machine.py`
- Create: `scripts/set_production_writer_fence.py`
- Create: `scripts/atomic_switch_release_pointer.py`
- Create: `deploy/systemd/production-writer-fence.conf`
- Modify: `scripts/verify_tokyo_runtime_governance_postdeploy.py`
- Modify: `tests/unit/test_tokyo_runtime_governance_release_prep.py`
- Modify: `tests/unit/test_tokyo_runtime_governance_postdeploy_verify.py`
- Modify: `tests/unit/test_tokyo_lifecycle_phase_two_deploy.py`
- Create: `tests/unit/test_production_writer_fence.py`
- Create: `tests/unit/test_atomic_switch_release_pointer.py`
- Create: `tests/unit/test_production_writer_fence_systemd.py`
- Create: `tests/unit/test_tokyo_runtime_deploy_remote_state_machine.py`

**Interfaces:**

- Dependency identity is
  `<requirements-runtime.lock sha256>-cp310-linux_x86_64`.
- Each release contains `.venv`, a symlink to one complete immutable venv.
- All systemd interpreter paths resolve through `app/current/.venv/bin/python`;
  `app/current` is the only release pointer switched during deployment.
- Before any repository-owned unit changes, the legacy previous release gains
  a compatibility `.venv` symlink to its already deployed fixed venv and passes
  an import probe from the previous release working directory.
- Candidate migrations run from the candidate release directory with
  `candidate_release/.venv/bin/python`; they never run through `app/current`
  before the atomic switch.
- All unit readiness commands use the SHA-verified release-independent helper
  under `/home/ubuntu/brc-deploy/control-plane/`, never a script that disappears
  when `app/current` points to the legacy release.
- Automatic old-code rollback ends before migration 121 starts. Post-migration
  failure is writers-disabled forward-fix because the old Alembic tree ends at
  revision 120.
- One remote state-machine process holds one deploy-wide `flock` across all
  mutations. Local planning and read-only probes may use separate SSH sessions;
  export, fence, schema, pointer, manifest, release-activation, projection,
  capability, and restore mutation may not. The local executor resolves, prints,
  and flushes the transaction ID and nonce before opening that mutating SSH
  session; remote `auto` generation is forbidden.
- The canonical lock is
  `/var/lib/brc-deploy/deploy-state/tokyo-runtime-deploy.lock`, a root-owned
  mode-`0600` regular non-symlink file that is never replaced/deleted. Acquire
  `LOCK_EX|LOCK_NB` before any durable deploy/runtime mutation and retain the
  same FD to terminal or contained exit. Busy returns `deploy_in_progress` with
  zero persistent manifest/fence/schema/pointer/production-unit mutation; its
  transient envelope is collected, and resume/new lineage contend on the same
  inode.
- After hash/Python/EUID validation, first-install initialization is allowed to
  create only the canonical hierarchy and lock. Open `/var/lib` with
  `O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC`, require root ownership and no group/other
  write bit, then use dirfd-relative `mkdir/openat` to create missing
  `brc-deploy` and `deploy-state` as `root:root 0700`. Create the lock once with
  `O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600`; on `EEXIST`, open without create.
  Require regular file, root ownership, mode `0600`, link count one, and the
  same device/inode via FD and canonical dirfd lookup. First creation file-
  `fsync`s the lock and directory. Durably commit every created directory level:
  `fsync(/var/lib)` after creating `brc-deploy`, `fsync(brc-deploy)` after
  creating `deploy-state`, and file `fsync` plus `fsync(deploy-state)` after
  creating the lock. Concurrent first installers must converge on
  one inode; symlink/hardlink/wrong-owner/mode/race fails. The lock is never
  unlinked, renamed, truncated, chmodded, or replaced.
- The single mutating SSH invocation starts one fixed transient service:
  `sudo -n /usr/bin/systemd-run --wait --pipe --collect --service-type=exec
  --unit=brc-deploy-<transaction-id>.service -p KillMode=control-group
  -p SendSIGKILL=yes -p TimeoutStopSec=30s -p RuntimeMaxSec=60min
  -p Restart=no /usr/bin/python3 -c
  <stdlib-loader> <expected-bootstrap-sha256> <transaction-id> <nonce> ...`.
  It sends the exact tracked bytes of
  `tokyo_runtime_deploy_remote_state_machine.py` on stdin. The loader verifies
  SHA-256, CPython 3.10, and `EUID==0` before opening the canonical lock or
  writing persistent state. The self-collecting transient unit is the only
  permitted pre-hash process-container mutation. The stdlib-only state machine
  then opens and retains that one FD, stages/builds the candidate, and invokes
  every repository-owned command through `candidate_release/.venv/bin/python`
  as a bounded subprocess.
  It never requires a candidate path to exist at launch and never releases or
  reopens the lock when candidate Python becomes available. A read-only
  `sudo -n true` preflight precedes maintenance; hash/Python/EUID/lock mismatch
  returns with zero persistent manifest/fence/schema/pointer/unit/release
  mutation and the transient unit is collected.
- `RuntimeMaxSec=60min` is the outer deploy-session ceiling. Bootstrap hang, SSH
  loss followed by hang, or an exhausted child deadline causes systemd to stop
  and then kill the complete cgroup. Before durable fence engagement this is
  `pre_maintenance_abort`: pre-existing production runtime/policy remains unchanged,
  no marker is expected, and unreferenced staged artifacts are verified/rebuilt
  by the next invocation. From fence engagement through the phase before
  `runtime_activation_committed`, the marker remains engaged and the last
  fsynced phase is resumable. After that commit, timeout preserves the safe activation receipt and may leave only
  idempotent activation completion or post-activation observation pending;
  timeout can never emit observation acceptance.
- Require a lowercase-hex transaction ID and derive exactly one escaped unit
  name. A read-only `systemctl show` preflight returns `deploy_in_progress` when
  that same transaction unit is active; same-lineage resume may start a new
  unit only after the old unit is inactive and collected. Other transaction
  units may start only to contend on the one canonical flock.
- Open the parent lock FD with `O_CLOEXEC`. Every mutation-capable child is
  launched only through `spawn_locked_mutation_child(...)` with
  `pass_fds=(lock_fd,)`; before `exec` it verifies the FD device/inode/owner/mode
  against the canonical dirfd path, sets `PR_SET_PDEATHSIG=SIGKILL`, and rechecks
  the expected parent PID. Mutation-capable descendants must use the same helper
  and inherit the same open-file description. Repository commands may not
  daemonize, double-fork, call `setsid`, invoke another `systemd-run`, or move
  outside `brc-deploy-<transaction-id>.service`. Normal failure kills and waits
  for the controlled child process group before parent lock release; parent
  `SIGKILL` or SSH loss leaves the inherited lock held until systemd's
  `KillMode=control-group` removes the complete old mutation tree. A competitor
  remains `deploy_in_progress` until that cgroup has no lock-holding process.
- A crash-safe mode-`0600` journal is a monotonic hash chain. Each entry contains
  `sequence`, `previous_phase`, `previous_digest`, `entry_digest`, transaction
  ID, nonce, host, old/target SHA, pointer, revision, and fence facts. Its phases
  extend through pointer activation, release activation, current projections,
  capability certification, bounded facts, readonly canary, activation commit,
  policy application, and terminal manifest consumption. Every atomic snapshot
  contains the whole ordered lineage (maximum 48 entries); no intermediate entry may be pruned or
  rewritten before terminal consumption. Reentry verifies the chain from
  genesis. Every update uses a same-directory
  temporary file, file `fsync`, atomic rename, and directory `fsync`.
- Journal transition authority is the monotonic `phase`.
  `runtime_activation_committed` is the one safe irreversible boundary and is
  fsynced while the marker exists and all writers/canaries remain stopped. It
  binds the exact SHA/schema/release activation, fact/certification/projection,
  zero-write canary, final freshness, exchange safety, lifecycle proof, pointer,
  unit desired policy, and fence identity. Marker removal and unit restoration
  are legal only after the receipt is reread and verified. Pre-commit failure
  remains fenced; a post-migration defect needing a new SHA may use one sealed
  `ForwardFixHandoffV1` child. Post-commit crash completes activation
  idempotently and never recreates the deploy fence merely because stability
  observation is unfinished. Five scheduled ticks are evaluated from existing
  PG/journald evidence and deploy output only; they cannot grant or revoke
  trading authority or introduce a new runtime source.
- Before migration, repository-owned `ConditionPathExists=!` drop-ins and the
  atomically fsynced marker
  `/home/ubuntu/brc-deploy/control-plane/production-writers.blocked` form a
  boot-persistent interlock for every production writer/timer.
- Pointer switching uses the release-independent helper: temporary symlink,
  `os.replace`, `fsync(app/)`, exact pointer/SHA reread, then journal advance.
- Postdeploy required facts include exact release SHA/lock, tracked remote
  state-machine SHA, stdlib launcher identity, candidate interpreter for every
  repository-owned command, real `SELECT 1`,
  actual revision 124, CCXT 4.5.56, Docker restart policy, watcher memory/time,
  pre-migration `SET`-role preflight, pre/post-canary fact IDs/digests, both
  Action-Time certification refs/digests, both projection heads/digests, post-
  canary phase-two result, final freshness elapsed/remaining, persisted v2
  lifecycle proof verification, activation-commit/apply/terminal identities,
  post-activation observation status, and zero
  deployment exchange side effect. The latter requires exact-SHA structural
  handler proof, dedicated route-set output, direct DML rejection, zero
  escalation statement, unchanged
  bounded PG sentinel/exchange identity, and not merely absence of a new order.
- `/api/health` remains an HTTP liveness signal and is never accepted alone as
  database readiness.

- [ ] **Step 1: Generate the Linux/CPython 3.10 resolved lock**

Do not freshly resolve every `>=` dependency. First capture the currently
deployed environment as a read-only baseline outside the repository, excluding
only CCXT because the candidate intentionally changes it:

```bash
BASELINE_FREEZE="$(mktemp -t brc-deployed-freeze.XXXXXX)"
ssh tokyo \
  '/home/ubuntu/brc-deploy/venvs/brc-bnb-prelive-20260601/bin/python -m pip freeze' \
  | awk 'tolower($0) !~ /^ccxt==/' > "$BASELINE_FREEZE"
```

Then run the resolver in an amd64 Linux container, not the local macOS
interpreter:

```bash
docker run --rm --platform linux/amd64 \
  --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "$PWD:/work" -v "$BASELINE_FREEZE:/tmp/deployed.freeze:ro" \
  -w /work python:3.10-slim \
  sh -euc 'python -m venv /tmp/resolver && \
    /tmp/resolver/bin/pip install pip-tools==7.4.1 >/dev/null && \
    /tmp/resolver/bin/pip-compile --generate-hashes --resolver=backtracking \
      --constraint=/tmp/deployed.freeze \
      --output-file=requirements-runtime.lock requirements.txt'
rm -f "$BASELINE_FREEZE"
```

Verify the lock contains exact `==` versions and hashes, including
`ccxt==4.5.56`. Compare it to the deployed freeze. Only CCXT and a dependency
that the CCXT 4.5.56 closure proves incompatible may change; an unrelated
framework/database upgrade fails Task 5. Do not accept an unbounded URL,
editable dependency, local path, or a second CCXT version.

- [ ] **Step 2: Write immutable-venv and postdeploy RED tests**

The planner test must prove:

```text
no `pip install -r requirements.txt` against the current/live venv
venv path contains lock SHA, cp310, and linux_x86_64
incomplete venv without `.complete` is rebuilt before quiescence
.complete uses temp+file-fsync+rename+parent-dir-fsync
release/.venv points to the complete immutable venv
previous_release/.venv exists and is executable before any unit-file change
previous-release import works from the previous release working directory
candidate migration command changes into candidate_release and uses candidate_release/.venv/bin/python
candidate migration command does not contain app/current/.venv
only app/current is switched through same-directory temp symlink, `os.replace`,
  parent-directory fsync, and exact-SHA reread
fault injection before/after rename leaves app/current old or candidate, never absent
candidate release and venv filesystems complete bounded syncfs before pointer rename
simulated power loss after syncfs leaves a rereadable target SHA, lock identity,
  complete marker, and interpreter; any mismatch keeps the marker engaged
pre-migration rollback restores the previous app/current target
pre-migration rollback resolves app/current/.venv/bin/python and imports src.main
post-migration failure leaves all old-code units stopped behind the persistent fence and
  either activates the candidate pointer or reports forward_fix_pointer_pending
crash after migration commit but before rename leaves the old pointer inert;
  restart reads journal+revision and switches candidate before fence removal/start
journal transitions are atomic, fsynced, hash-chained, monotonic, host/nonce/SHA bound, and
  reject missing, corrupt, skipped, replayed, or regressed phases
activation receipt is fsynced and reread while the marker exists and every writer
  remains stopped; no marker unlink is possible without that exact receipt
fenced pre-commit failure keeps the marker durable; one post-migration parent may
  seal at most one parent-digest-bound `ForwardFixHandoffV1`; the named child
  reruns the complete activation path and rejects replay/second child
crash after activation commit but before marker unlink resumes activation apply
crash after marker unlink+fsync but before activation-applied journal advance
  verifies the commit and completes without recreating the marker
post-commit SIGKILL/RuntimeMax/SSH loss/reboot never emits observation accepted,
  rewinds the terminal mutation journal, or recreates the deploy fence
five target-SHA scheduled ticks use existing PG/journald evidence only;
  interruption restarts from 0/5, and failure reports degraded
the same deploy lineage can resume a nonterminal restore idempotently, while
  cross-lineage and terminal manifest reuse fail
an attempted writer start is condition-skipped while the durable marker exists,
  including after a simulated host reboot
old and candidate interpreters both execute the shared readiness helper
fresh-host fixture has no candidate release/venv/bootstrap file and no
  `/var/lib/brc-deploy` hierarchy before launch; verified stdlib stdin bootstrap
  creates the root-owned hierarchy/lock once, acquires one canonical lock FD,
  stages/builds candidate, and every release-sensitive child uses candidate Python
bootstrap SHA mismatch, truncated stdin, non-CPython-3.10, or nonzero EUID
  produces zero persistent lock/manifest/fence/schema/pointer/unit/release mutation
pre-fence export/venv/syncfs `SIGKILL`, SSH loss, or RuntimeMax returns
  pre_maintenance_abort, leaves no fence expectation, preserves pre-existing
  production runtime/policy, and leaves only unreferenced rebuildable artifacts
the same canonical lock inode and original FD remain held before candidate
  staging, throughout every candidate subprocess, and until terminal/contained exit
two simultaneous first-install launchers converge on one lock inode; symlink,
  hardlink, wrong owner/mode, directory substitution, and inode-swap races fail
power-loss/reopen injection before and after each `/var/lib`, `brc-deploy`,
  `deploy-state`, and lock fsync never accepts a missing or replaced canonical inode
every mutation child receives `pass_fds=(lock_fd,)`, verifies the exact inode,
  stays in the transaction transient cgroup, and passes the parent-death race check
parent `SIGKILL` and SSH-disconnect injections during migration/pointer/projection
  keep a competing deploy at `deploy_in_progress` until the prior cgroup and all
  lock-holding descendants exit; no old child mutates after competitor acquisition
SSH loss plus bootstrap hang and mid-migration `RuntimeMaxSec=60min` expiry kill
  the complete cgroup, retain the durable fence/journal, and return resumable timeout
normal failure terminates and waits the complete controlled process group;
  daemonize/double-fork/setsid/nested-systemd-run/cgroup-escape attempts fail
the local executor emits exactly one remote mutating state-machine invocation;
  it prints+flushes transaction ID and nonce before opening SSH;
  no export/migration/pointer/restore mutation appears in a separate SSH command
```

Add postdeploy facts and a negative test per fact:

```python
{
    "postgres_ready": "ready",
    "alembic_current": "124",
    "process_outcome_latest_index": "idx_brc_runtime_outcome_lane_process_latest:valid",
    "process_outcome_canary_window_index": "idx_brc_runtime_outcome_canary_window:valid",
    "dependency_lock_sha256": expected_lock_sha256,
    "python_abi_platform": "cp310-linux_x86_64",
    "ccxt_version": "4.5.56",
    "readiness_helper_sha256": expected_tracked_helper_sha256,
    "remote_state_machine_sha256": expected_tracked_bootstrap_sha256,
    "remote_state_machine_launcher": "/usr/bin/systemd-run:transient_service:/usr/bin/python3:stdlib_hash_loader",
    "remote_state_machine_runtime_max_sec": 3600,
    "remote_state_machine_kill_mode": "control-group",
    "repository_command_python": expected_candidate_python,
    "postgres_container_restart_policy": "unless-stopped",
    "watcher_memory_high": "402653184",
    "watcher_memory_max": "536870912",
    "watcher_timeout_start_usec": "5min",
    "backend_exec_start": "/home/ubuntu/brc-deploy/app/current/.venv/bin/python -m src.main",
    "canary_role_preflight_before_migration": "passed",
    "canary_role_membership_mode": "SET",
    "ticket_exit_policy": {
        "capability_id": "ticket_exit_policy_v1",
        "capability_status": "enabled",
        "exit_policy_id": "exit-policy:SOR-001:SOR-LONG:right-tail-v1",
        "exit_policy_version": "2026-07-15-v1",
        "payload_hash": expected_migration_123_policy_hash,
        "policy_status": "current",
    },
}
```

Also require:

```python
{
    "canary_server_route_set_status": "passed",
    "canary_forbidden_route_attempts": 0,
    "canary_current_user": "pg_read_all_data",
    "canary_mutation_privileges": False,
    "canary_default_transaction_read_only": "on",
    "canary_transaction_read_only": "on",
    "canary_forbidden_dml_rejected": True,
    "canary_escalation_statement_count": 0,
    "canary_credential_isolation_claimed": False,
    "canary_bounded_sentinel_delta": 0,
    "canary_bounded_sentinel_overflow": False,
    "canary_exchange_identity_delta": 0,
    "runtime_release_activation_sha": expected_release_sha,
    "pre_canary_fact_refresh_ids": expected_pre_fact_ids,
    "pre_canary_fact_set_digest_schema": "brc.action_time_fact_set_digest.v1",
    "pre_canary_fact_set_digest": expected_pre_fact_digest,
    "pre_canary_certification_input_digest_schema": "brc.action_time_capability_certification_input.v1",
    "pre_canary_action_time_certification_ref": expected_pre_action_ref,
    "pre_canary_action_time_certification_digest": expected_pre_cert_digest,
    "pre_canary_projection_sha": expected_release_sha,
    "pre_canary_projection_digest": expected_pre_projection_digest,
    "post_canary_fact_refresh_ids": expected_post_fact_ids,
    "post_canary_fact_set_digest_schema": "brc.action_time_fact_set_digest.v1",
    "post_canary_fact_set_digest": expected_post_fact_digest,
    "post_canary_certification_input_digest_schema": "brc.action_time_capability_certification_input.v1",
    "post_canary_phase_two_status": "phase_two_ready",
    "post_canary_action_time_certification_ref": expected_post_action_ref,
    "post_canary_action_time_certification_digest": expected_post_cert_digest,
    "post_canary_projection_sha": expected_release_sha,
    "post_canary_certification_projection_digest": expected_post_projection_digest,
    "final_refresh_to_enable_elapsed_ms": expected_at_most_30_000,
    "final_fact_min_remaining_validity_ms": expected_at_least_30_000,
    "lifecycle_capability_v2_proof_verified": True,
    "runtime_activation_commit_sha256": expected_activation_commit_sha256,
    "runtime_activation_status": "applied",
    "deploy_mutation_journal_status": "terminal_consumed",
    "postdeploy_observation_status": expected_accepted_degraded_or_not_applicable,
    "parent_deploy_transaction_id": expected_parent_transaction_or_none,
    "forward_fix_handoff_id": expected_handoff_id_or_none,
    "production_writer_fence_absent_after_activation_commit": True,
    "release_pointer_parent_fsynced": True,
    "local_exact_sha_sensitive_handler_call_counts": {
        "ticket_and_authority_writers": 0,
        "finalgate": 0,
        "operation_layer": 0,
        "dispatcher": 0,
        "gateway": 0,
    },
    "deployment_exchange_write": False,
}
```

Required blockers are:

```text
postdeploy_dependency_identity_mismatch
postdeploy_readiness_helper_identity_mismatch
postdeploy_remote_state_machine_identity_mismatch
postdeploy_remote_state_machine_containment_mismatch
postdeploy_repository_command_interpreter_mismatch
postdeploy_postgres_not_ready
postdeploy_alembic_current_mismatch
postdeploy_process_outcome_latest_index_mismatch
postdeploy_process_outcome_canary_window_index_mismatch
postdeploy_postgres_restart_policy_mismatch
postdeploy_watcher_memory_limit_mismatch
postdeploy_watcher_timeout_mismatch
postdeploy_backend_interpreter_mismatch
postdeploy_ticket_exit_policy_mismatch
postdeploy_canary_structural_readonly_boundary_mismatch
postdeploy_runtime_release_activation_mismatch
postdeploy_current_projection_release_mismatch
postdeploy_lifecycle_capability_certification_stale
postdeploy_lifecycle_capability_proof_invalid
postdeploy_final_freshness_budget_invalid
postdeploy_activation_commit_invalid
postdeploy_activation_apply_incomplete
postdeploy_observation_degraded
postdeploy_production_writer_fence_state_invalid
postdeploy_release_target_durability_unproven
postdeploy_release_pointer_durability_unproven
```

- [ ] **Step 3: Build and bind the candidate venv before quiescence**

The local planner computes the lock SHA, generates the transaction ID and nonce,
prints and flushes them to the local terminal/execution result, and only then
emits one self-contained remote state-machine invocation with both explicit.
It reads the tracked stdlib-only remote state-machine source from the exact local
target SHA, computes/prints its SHA-256, and sends those bytes on stdin to the
fixed `systemd-run` transient-service envelope and `/usr/bin/python3 -c` hash-
loader. The loader must read and verify the
entire payload before opening the lock; no candidate release, venv, or remote
copy of the script is assumed to exist. The executed source imports only Python
stdlib modules. After the permitted first-install lock-hierarchy initialization,
that remote process acquires one deploy-wide `flock` before any other mutation
and retains the file descriptor until the mutation transaction is terminal or
failure containment completes. Every mutating child uses the inherited guarded FD and remains in
the same transient service cgroup. It uses:

```text
/home/ubuntu/brc-deploy/venvs/by-lock/
  <lock_sha256>-cp310-linux_x86_64
```

Python venv scripts contain absolute paths, so do not build under a temporary
path and rename it. Build directly at the final unreferenced path. If `.complete`
is absent, delete that unreferenced partial directory and rebuild it. Before
creating `.complete`, require all of:

```text
/usr/bin/python3 is CPython 3.10 on linux_x86_64
pip install --require-hashes -r requirements-runtime.lock succeeds
pip check succeeds
imports for sqlalchemy, psycopg, fastapi, alembic, and ccxt succeed
ccxt.__version__ == 4.5.56
python -m compileall -q src succeeds from the candidate release
```

Write `.complete` with a same-directory temporary file, file fsync, rename, and
parent-directory fsync. After candidate export, release manifest/SHA/import
verification, and `.venv` binding, call bounded `syncfs(2)` once per distinct
`st_dev` containing the release and immutable venv. Use a 30-second total
deadline, then reread target SHA, lock hash/ABI identity, `.complete`, symlink,
and interpreter imports. Only this reread authorizes entry into maintenance and
later pointer replacement. Timeout or mismatch at this pre-fence stage returns
`pre_maintenance_abort`, keeps the staged candidate unreferenced, and leaves the
pre-existing production runtime/policy unchanged.

The bootstrap continues to own the lock while calling candidate commands with
absolute `candidate_release/.venv/bin/python` paths and bounded subprocess
timeouts. It does not `exec` candidate code in-process, spawn a second remote
state machine, close/reopen the lock, or use `/usr/bin/python3` for migrations,
readiness, certification, projection, or postdeploy verification.

Create `candidate_release/.venv` as a symlink to the complete venv before any
writer is quiesced. Before installing or changing any repository-owned systemd
unit or switching `app/current`, create `previous_release/.venv` as a
compatibility symlink to the fixed
venv used by the deployed backend and watcher, then prove from the previous
release working directory that all of the following succeed:

```text
previous_release/.venv/bin/python is executable
previous_release/.venv/bin/python -c 'import src.main' succeeds
previous_release/.venv/bin/python -m alembic current succeeds
```

Record the previous release path, the resolved legacy venv path, and the
compatibility-link target in the deploy manifest. A missing or failed legacy
binding stops the deploy before unit installation or release switching. During
the switch, call the hash-verified release-independent
`atomic_switch_release_pointer.py`. It creates a unique temporary symlink beside
`app/current`, verifies both release targets share the same filesystem, calls
`os.replace`, opens and `fsync`s the `app/` parent directory, rereads the pointer
and target SHA, and returns the durable fact before the journal may advance.
Direct `ln -sfn app/current` and shell-only `mv -Tf` are forbidden. Delete the current planner
command that installs requirements into a shared venv. Keep both current and
previous immutable venvs through acceptance.

From the staged Tokyo candidate directory, before writer quiescence in a normal
deploy and before migration in incident mode, run the same stdout-only
17/33/256 benchmark through `candidate_release/.venv/bin/python`. The runner
must resolve the effective Linux cgroup as unlimited, finish all 256 selected
runtimes below 120 seconds, and stay below 256 MiB. Do not install or relax a
cgroup limit to make this benchmark pass; a finite inherited limit is
`benchmark_environment_not_unconstrained` and blocks performance certification.

- [ ] **Step 4: Add real PG, Alembic, lock, and dependency commands**

Before any Alembic command, open a disposable production-DSN session and run
the read-only canary-role preflight. It must prove
`pg_has_role(session_user,'pg_read_all_data','SET')`, actually assume that role,
verify exact `current_user`, and verify denied
mutation/sequence-write privileges for every canary-reachable table. Close the
session without resetting into candidate code. Failure leaves revision 120 and
stops the deploy; there is no role/grant/secret mutation fallback.

Before migration, atomically install and hash-verify the repository-owned
`ConditionPathExists=!/home/ubuntu/brc-deploy/control-plane/production-writers.blocked`
drop-in on every production backend/monitor/watcher/lifecycle service and timer,
then daemon-reload. Call the release-independent fence helper to create the
mode-`0600` marker by temporary file, file fsync, rename, and parent-directory
fsync. Stop all production writers and both canary units, and prove an attempted
writer start is condition-skipped. Record typed unit states in the sealed
manifest; do not use a runtime mask as the interlock.

The canonical fragment copied to every production writer/timer drop-in is:

```ini
[Unit]
ConditionPathExists=!/home/ubuntu/brc-deploy/control-plane/production-writers.blocked
```

Install it on both timers and their services plus the backend. A unit omitted
from the explicit planner allowlist is a failed preflight. The helper's remove
operation requires an already-fsynced and byte-reread
`RuntimeActivationCommitV1` receipt for the same host, transaction, nonce,
pointer, target SHA, schema, lifecycle proof, unit policy, and fence inode. It
unlinks the marker and fsyncs the control-plane directory; it cannot be invoked
as a standalone path deletion. If unlink and directory fsync complete before
`activation_applied` is journaled, reentry verifies the same durable receipt and
finishes policy application without recreating the marker. Marker absence
without a valid receipt is outside the crash-consistent fsync model; if detected,
the helper/resume process refuses mutation and reports a storage-integrity
incident requiring host isolation/manual recovery. The path condition is not
claimed to validate journal contents during boot.

Persist the hash-chained `pre_migration` entry, verify actual revision 120, then
persist `migration_in_progress` with sequence, previous digest, transaction ID,
deploy nonce, host identity, old/candidate SHA and paths, expected revision, and
durable fence facts. Run migration only from the candidate release directory
and through its bound interpreter:

```text
cd <candidate_release>
PYTHONPATH=$PWD <candidate_release>/.venv/bin/python -m alembic upgrade head
```

After Alembic returns, query the actual revision. If it is 124, persist
`schema_124_requires_candidate` and immediately replace `app/current` through
the release-independent pointer helper. Require `os.replace`, `fsync(app/)`, and
an exact target/SHA reread; only then persist `candidate_pointer_active`. Do not
run an intervening verifier through the old pointer.

At executor start and from every failure trap, call one recovery classifier:

```text
journal=pre_migration and actual_revision=120
  -> old-pointer rollback may run
journal=migration_in_progress and actual_revision=120
  -> keep persistent fence; rollback or retry migration from candidate is allowed
single known actual_revision in 121..124, or journal at/after schema_124_requires_candidate
  -> keep persistent fence; validate candidate venv/SHA; switch candidate pointer;
     continue forward-fix only
missing/corrupt journal or ambiguous revision
  -> failed_containment_incomplete; all writers remain persistently fenced;
     no automatic pointer switch or service start
```

Fault-injection tests terminate the executor before migration, during the
subprocess, after each committed revision, after journal fsync, before pointer
rename, and after rename. On restart, no test may start old code on schema
121-124 or remove the fence before the complete
`runtime_activation_committed` journal entry is durable and verified.

After the switch, run postdeploy probes from the new `app/current` directory
through `/home/ubuntu/brc-deploy/app/current/.venv/bin/python`:

```text
PYTHONPATH=$PWD <release_python> \
  /home/ubuntu/brc-deploy/control-plane/check_runtime_postgres_ready.py \
  --require-database-url --timeout-seconds 10 --json

PYTHONPATH=$PWD <release_python> -m alembic current
PYTHONPATH=$PWD <release_python> -c 'import ccxt; print(ccxt.__version__)'
```

While the persistent fence remains engaged, the same remote state machine then
executes this authority sequence through the candidate interpreter:

```text
record_runtime_release_activation.py for exact target SHA
-> verify active release identity and journal `release_activation_recorded`
-> bounded pre-canary public/account fact refresh; verify allowed-table-only delta
-> journal `pre_canary_facts_refreshed`
-> certify_action_time_capability.py pre-canary prepare
-> SERIALIZABLE digest-revalidate apply bound to target SHA, release activation,
   digest schema version, and deploy nonce
-> journal `pre_canary_capability_certified`
-> publish_runtime_control_current_projections.py for exact target SHA
-> verify every current projection uses the fresh fact/capability inputs; journal
   `pre_canary_current_projections_published`
-> five API-only readonly canaries; journal `readonly_canary_accepted`
-> bounded post-canary fact refresh; journal `post_canary_facts_refreshed`
-> rerun phase-two readiness; journal `post_canary_phase_two_ready`
-> compute post-canary `action-time-cert:v2` from pre-publication facts and run
   certification prepare/apply; every lane outcome uses that shared ref; journal
   `post_canary_capability_certified`
-> republish/verify current projections; journal
   `post_canary_current_projections_published`
-> require final refresh-to-enable elapsed <=30s and fact validity remaining
   >=30s; allow one bounded restart from post-canary fact refresh, otherwise
   remain fenced; journal `final_freshness_verified`
-> construct the non-self-referential lifecycle proof from the persisted Action-
   Time ref and certification projection slice; SERIALIZABLE setter restores the
   captured enabled/disabled policy and persists/validates v2 payload when
   enabled; journal `lifecycle_desired_policy_restored`
-> stop canaries and recheck every production writer condition-skipped
-> atomically write/fsync/reread the `runtime_activation_committed` journal
   snapshot embedding `RuntimeActivationCommitV1` with the complete safety,
   identity, proof, pointer, and desired-policy tuple while the marker exists
-> durably remove the fence and restore typed unit policy with watcher timer
   last; journal `activation_applied -> deploy_transaction_terminal ->
   terminal_consumed`
-> begin separate target-SHA post-activation stability observation
```

The watcher timer cannot be restored between these phases. If desired lifecycle
policy was enabled, the current setter receives the new lifecycle reference and
proof payload only after post-canary publication/freshness; an old ref is never
copied. If disabled, proof fields remain clear. Before migration, policy capture
uses only `read_lifecycle_mutation_capability_prestate_v1()` and schema-aware
disable; the strict v2 runtime decision is not invoked against schema 120.

Tests reject any unit or postdeploy command containing
`app/current/scripts/check_runtime_postgres_ready.py`.

Load the production env file without printing it. Parse the actual Alembic
revision and hash the actual lock file; do not infer either fact from filenames.
The rollback test runs only before migration starts, atomically points
`app/current` at the previous release, and reruns its import plus shared
readiness probe. It does not ask the old revision-120 Alembic tree to parse
schema 124. A separate post-migration failure test proves the old pointer is
never restored as executable authority: the candidate pointer is activated when
possible, otherwise the old pointer is inert while every writer remains
stopped behind the boot-persistent fence and the result is
`forward_fix_pointer_pending`.

- [ ] **Step 5: Add Docker and systemd facts**

Read only:

```text
docker inspect -f '{{.HostConfig.RestartPolicy.Name}}' brc_prelive_pg_20260601
systemctl show brc-runtime-signal-watcher.service \
  -p MemoryHigh -p MemoryMax -p TimeoutStartUSec -p Result
systemctl show brc-owner-console-backend.service -p ExecStart
readlink -f /home/ubuntu/brc-deploy/app/current/.venv
sha256sum /home/ubuntu/brc-deploy/control-plane/check_runtime_postgres_ready.py
```

Require the exact R1 values. Do not mutate the container from the verifier.

- [ ] **Step 6: Apply Docker ownership at the safe mode-specific boundary**

For a normal deploy whose PostgreSQL is already healthy, verify or run exactly
once before application readiness. For the current incident, do not run this
until Task 7 has manually started PostgreSQL under restart policy `no`, passed
WAL/schema/`SELECT 1`, and completed the bounded backup:

```text
sudo -n docker update --restart unless-stopped brc_prelive_pg_20260601
```

The deploy plan must assert that no systemd unit contains `docker start` or
`docker stop` for this container.

- [ ] **Step 7: Run Task 5 tests**

```bash
python3 -m pytest -q \
  tests/unit/test_tokyo_runtime_governance_release_prep.py \
  tests/unit/test_tokyo_runtime_governance_postdeploy_verify.py \
  tests/unit/test_tokyo_lifecycle_phase_two_deploy.py \
  tests/unit/test_production_writer_fence.py \
  tests/unit/test_production_writer_fence_systemd.py \
  tests/unit/test_atomic_switch_release_pointer.py \
  tests/unit/test_tokyo_runtime_deploy_remote_state_machine.py
```

Expected: all tests pass and an HTTP-green / PG-down or lock-mismatch case fails
postdeploy.

- [ ] **Step 8: Commit Task 5**

```bash
git add \
  requirements-runtime.lock \
  deploy/systemd/production-writer-fence.conf \
  scripts/set_production_writer_fence.py \
  scripts/atomic_switch_release_pointer.py \
  scripts/tokyo_runtime_deploy_remote_state_machine.py \
  scripts/plan_tokyo_runtime_governance_git_deploy.py \
  scripts/verify_tokyo_runtime_governance_postdeploy.py \
  tests/unit/test_production_writer_fence.py \
  tests/unit/test_production_writer_fence_systemd.py \
  tests/unit/test_atomic_switch_release_pointer.py \
  tests/unit/test_tokyo_runtime_deploy_remote_state_machine.py \
  tests/unit/test_tokyo_runtime_governance_release_prep.py \
  tests/unit/test_tokyo_runtime_governance_postdeploy_verify.py \
  tests/unit/test_tokyo_lifecycle_phase_two_deploy.py
git commit -m "fix: bind immutable runtime dependencies and verify readiness"
```

---

### Task 6: Run The R1 Local Release Gate

**Files:**

- Modify only tests whose assumptions are intentionally changed by Tasks 1-5.
- Do not modify production behavior to make an unrelated failing test green.

**Interfaces:**

- Produces one pushed full 40-character exact SHA based on current candidate
  `fb013a150dba840e73e48c32fb69a5d7426c6d80` plus R1 commits.
- Produces no committed `output/**` or deploy evidence.

- [ ] **Step 1: Run focused R1 tests**

```bash
python3 -m pytest -q \
  tests/unit/test_runtime_control_state_repository.py \
  tests/unit/test_runtime_active_observation_monitor.py \
  tests/unit/test_validate_runtime_control_state_repository.py \
  tests/unit/test_certify_action_time_capability.py \
  tests/unit/test_action_time_capability_certification.py \
  tests/unit/test_certify_action_time_capability_script.py \
  tests/unit/test_strategy_runtime_backbone.py \
  tests/unit/test_runtime_first_real_submit_api_flow.py \
  tests/unit/test_runtime_signal_watcher_tick.py \
  tests/integration/test_watcher_action_time_compact_parity.py \
  tests/unit/test_runtime_postgres_ready.py \
  tests/unit/test_canary_readonly_api.py \
  tests/unit/test_runtime_signal_watcher_systemd_units.py \
  tests/unit/test_runtime_signal_watcher_resume_dispatcher.py \
  tests/unit/test_ticket_lifecycle_phase_two_readiness.py \
  tests/unit/test_lifecycle_mutation_capability.py \
  tests/unit/test_lifecycle_mutation_enablement_proof_migration.py \
  tests/unit/test_canary_mutation_sentinel.py \
  tests/unit/test_ticket_bound_exchange_command_worker.py \
  tests/unit/test_ticket_bound_protected_submit_attempt.py \
  tests/unit/test_tokyo_lifecycle_phase_two_deploy.py \
  tests/unit/test_tokyo_runtime_governance_git_deploy_execution.py \
  tests/unit/test_tokyo_runtime_governance_release_prep.py \
  tests/unit/test_tokyo_runtime_governance_postdeploy_verify.py \
  tests/unit/test_production_writer_fence.py \
  tests/unit/test_production_writer_fence_systemd.py \
  tests/unit/test_atomic_switch_release_pointer.py
```

Expected: all selected tests pass.

Run the Task 2 cgroup-free 17/33/256 production-shape benchmark immediately
after the focused suite and require peak RSS below 256 MiB with full selected-
runtime coverage. Do not proceed on a cgroup kill, timeout, partial-coverage
status, or semantic-parity mismatch.

```bash
python3 tests/performance/runtime_watcher_production_shape_runner.py \
  --runtime-counts 17,33,256 \
  --out-of-scope-runtime-count 100000 \
  --candidate-placement lexical-tail \
  --page-size 16 \
  --observation-latency-ms 250 \
  --max-elapsed-seconds 120 \
  --max-rss-bytes 268435456
```

- [ ] **Step 2: Run current exit-policy and lifecycle regression**

```bash
python3 -m pytest -q \
  tests/unit/test_exit_execution_safety_migration.py \
  tests/unit/test_ticket_exit_policy_migration.py \
  tests/unit/test_ticket_exit_policy_canary_migration.py \
  tests/unit/test_ticket_exit_policy.py \
  tests/unit/test_ticket_exit_policy_binding.py \
  tests/unit/test_ticket_exit_policy_service.py \
  tests/unit/test_ticket_exit_policy_full_chain.py \
  tests/unit/test_ticket_bound_runtime_safety_state_materialization.py \
  tests/unit/test_ticket_bound_exchange_command_worker.py \
  tests/unit/test_ticket_bound_exchange_command_reconciliation.py \
  tests/integration/test_runtime_causal_integrity_postgres.py
```

Expected: all selected tests pass; the migration chain is exactly
`120 -> 121 -> 122 -> 123 -> 124`; revision 123 changes only the already
approved SOR-LONG future-Ticket policy/capability binding; revision 124 adds
fail-closed durable proof storage plus the deploy-sentinel latest-current and
recent-window indexes only; existing tickets are not retrofitted; and no exchange-write fixture
count changes.

- [ ] **Step 3: Run full regression**

```bash
python3 -m pytest -q
```

Expected: no failing tests. The existing skipped-test count may remain only if
the skip reason is unchanged and documented in pytest output.

- [ ] **Step 4: Run repository release checks**

```bash
python3 scripts/audit_production_runtime_file_io.py --all
python3 scripts/validate_output_artifact_scope.py --git-status --git-tracked
git diff --check
git status --short
```

Expected:

```text
performance_risk.status=clear
frequent_report_write=0
no tracked output artifact
no whitespace error
only intended source/test/doc changes
```

- [ ] **Step 5: Review the complete diff against the deployed head**

```bash
git diff --stat 2001644581cccc968ba695d3ff129960db6a7e84..HEAD
git diff --name-status 2001644581cccc968ba695d3ff129960db6a7e84..HEAD
```

Confirm migrations remain a linear `120 -> 121 -> 122 -> 123 -> 124` chain,
with revision 124 limited to the durable lifecycle-proof schema, fail-closed row
transition, partial deploy-sentinel latest-outcome index, and time-leading
canary-window index.

- [ ] **Step 6: Push the candidate branch**

```bash
git push origin codex/release-risk-analysis-20260714
```

Record:

```bash
git rev-parse HEAD
git ls-remote origin refs/heads/codex/release-risk-analysis-20260714
```

Expected: both full 40-character SHAs are identical.

---

### Task 7: Recover Tokyo And Deploy The New Exact SHA

**Files:**

- No repository file edits are allowed during this task.
- Server mutations are limited to swap, Docker restart policy, release export,
  immutable venv build, migration, symlink, SHA-verified control-plane helper,
  linked mode-`0600` deploy-state manifests, crash-safe deploy journal, approved
  systemd units/drop-ins, and bounded backup.

**Interfaces:**

- Consumes the pushed exact SHA from Task 6.
- The local executor generates, prints, and flushes the transaction ID and nonce
  before the remote mutating session; the remote state machine receives them as
  explicit immutable inputs.
- The one Owner-facing command creates a mode-`0600` capture manifest, linked
  sealed restore manifest, and journal inside the remote locked state machine.
  A resume invocation consumes the same lineage selected by transaction ID.
- For a post-migration, pre-activation defect while the persistent fence remains
  verified, the same command may create/consume one
  mode-`0600` `ForwardFixHandoffV1` that names an already approved child
  transaction/nonce and exact SHA; it never recaptures or expands policy.
- Steps 1-6 below are internal state-machine phases and acceptance details; they
  are not separate Owner commands or independent mutating SSH sessions.
- The manifests record typed systemd policy/observation states, the desired
  enabled/disabled lifecycle policy, and the old capability row as audit evidence.
  Same-lineage nonterminal recovery is idempotent; terminal or cross-lineage
  reuse is rejected.
- Produces one deployment report with `postdeploy_status=accepted`,
  `accepted_disabled`, `activated_observation_degraded`, or a precise pre-
  activation fail-closed status, plus parent transaction/handoff IDs when the accepted
  lineage is a forward-fix child.

- [ ] **Step 1: Have the remote state machine record policy/evidence and enter maintenance**

Before the first stop command, write a mode-`0600` incident **capture manifest**
under `/var/lib/brc-deploy/deploy-state/`. Record
`systemctl show -p UnitFileState -p ActiveState -p SubState -p Result
-p TriggeredBy -p Triggers` as typed facts. Stable timer/backend policy is a
restore target; transient oneshot
states are observed incident evidence only:

```text
brc-runtime-signal-watcher.timer
brc-ticket-lifecycle-maintenance.timer
brc-runtime-monitor.timer
brc-runtime-signal-watcher.service
brc-ticket-lifecycle-maintenance.service
brc-runtime-monitor.service
brc-owner-console-backend.service
```

The capture manifest includes capture time, the locally supplied cryptographic
transaction ID and deploy nonce, `mode=incident`, machine ID, hostname, expected old SHA,
exact current symlink target, Owner-approved target SHA, and a SHA-256 checksum. It expires after 15
minutes only for entering quiescence. Do not infer pre-state after stopping the
units. After PostgreSQL is restored in Step 3, read only the exact
`capability_id='ticket_lifecycle_durable_mutation'` row before any capability
mutation through `read_lifecycle_mutation_capability_prestate_v1()` and create a
new **sealed restore manifest**. It links the immutable
capture checksum, transaction ID, nonce, old/target SHA, includes the capability
row as audit evidence, captures only its desired enabled/disabled policy for
restoration, and includes `maintenance_started_at_ms`. It permits first entry to
migration for 90 minutes. Once `migration_in_progress` is durably recorded
before expiry, it is recovery-pinned for same-lineage forward recovery even
after 90 minutes, but cannot authorize another SHA/deploy or recapture policy.
The same lineage may reread it while the mutation journal is nonterminal; only
`deploy_transaction_terminal`, or an exact pre-migration rollback recorded as
`terminal_aborted_pre_migration`, advances to `terminal_consumed`. Ordinary
post-migration, pre-activation failed containment remains resumable and
nonterminal. Scheduled-tick observation is separate and cannot reopen the
consumed mutation manifest.
Both manifests use atomic same-directory write, file
`fsync`, rename, and directory `fsync`. Tests reject wrong age/nonce/mode/host/
old SHA/captured pointer/target SHA/owner/mode/parent checksum/checksum and any
capability row outside that ID.

Before mutation, every static production service must name only captured
allowlisted timer/trigger owners. Any `UnitFileState=indirect`, uncaptured owner,
or unresolved activating/deactivating state blocks before the fence or stop
sequence.

Before entering maintenance, install/hash-verify the repository-owned persistent
writer-condition drop-ins, daemon-reload, atomically create and fsync the fence
marker, stop the units below, and prove attempted starts are condition-skipped.
This persists across reboot; runtime masks are not the authority boundary.

On Tokyo:

```bash
sudo systemctl stop brc-runtime-signal-watcher.timer
sudo systemctl stop brc-ticket-lifecycle-maintenance.timer
sudo systemctl stop brc-runtime-monitor.timer
sudo systemctl stop brc-runtime-signal-watcher.service
sudo systemctl stop brc-ticket-lifecycle-maintenance.service
sudo systemctl stop brc-runtime-monitor.service
sudo systemctl stop brc-owner-console-backend.service
```

Expected: all commands return or report already inactive. Their exact stable
enablement policy stays in the sealed manifest; the persistent fence, rather
than destructive policy rewriting, prevents restart during maintenance.

- [ ] **Step 2: Add the supplementary host control-plane swap buffer**

Only when `/swapfile` is absent:

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

Persist one `/swapfile none swap sw 0 0` entry in `/etc/fstab` and one
`vm.swappiness=1` setting under `/etc/sysctl.d/`. Verify:

```bash
swapon --show
sysctl vm.swappiness
```

Expected: 2 GiB swap is active and swappiness is 1.

This is **not** watcher performance acceptance and does not permit the memory
benchmark, semantic-parity proof, pagination, or compact-projection work to be
skipped. Its only purpose is keeping SSH/systemd/Docker/PostgreSQL recovery
available if another process briefly exhausts RAM.

- [ ] **Step 3: Start PostgreSQL manually without enabling restart yet**

```bash
test "$(sudo docker inspect -f '{{.HostConfig.RestartPolicy.Name}}' brc_prelive_pg_20260601)" = no
sudo docker start brc_prelive_pg_20260601
```

The old deployed release does not contain the new readiness script. Before the
candidate is exported, verify inside the existing container without printing
credentials:

```bash
sudo docker exec brc_prelive_pg_20260601 sh -lc \
  'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" && \
   psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
     -Atqc "SELECT 1"'
```

Expected: `pg_isready` accepts connections and `psql` prints exactly `1`.
Before any candidate verifier or capability setter runs, read the explicit
columns `capability_id`, `status`, `certification_ref`, and `updated_at_ms` from
`brc_runtime_capabilities_current` where
`capability_id='ticket_lifecycle_durable_mutation'`, ordered by capability ID
with `LIMIT 2`, into the linked sealed restore manifest. Run in a read-only transaction
with `lock_timeout='1s'` and `statement_timeout='5s'`. Zero rows is an invalid
schema/safety blocker, one row is retained verbatim as audit evidence while only
its desired enabled/disabled status becomes restore policy, and two rows fail.
Do not copy the old row back and do not later restore `ticket_exit_policy_v1` or
any other migration-owned capability.

- [ ] **Step 4: Verify PostgreSQL recovery before any writer starts**

Read and record:

```text
container state and restart policy
PostgreSQL server version
SELECT 1
alembic current
database size
top 20 tables by total bytes
connection count by state
catalog row estimates and total bytes for watcher coverage and fact snapshots
```

Run every diagnostic statement in a read-only transaction with
`lock_timeout='1s'` and `statement_timeout='10s'`. The table-size query uses
catalog statistics and `LIMIT 20`; row-growth diagnostics use `pg_class.reltuples`
and relation bytes, not production-path `count(*)`. Timeout, recovery error, or
missing required relation stops recovery; exact historical counts are deferred
to the nonblocking R2 measurement.

Stop the deployment if WAL recovery fails, schema inspection fails, or the
database reports corruption.

- [ ] **Step 5: Create one bounded incident backup**

Use `pg_dump` inside the PostgreSQL container and write a gzip-compressed file
under `/home/ubuntu/brc-deploy/backups/`. Do not print credentials. Apply mode
`0600`, record SHA-256, and set a seven-day manual retention date in the deploy
report. This is manual incident provenance, not a recurring runtime writer.
Use a unique partial path and a 600-second outer timeout; rename only after
`gzip -t` and checksum succeed. Timeout or a partial dump blocks deployment and
the partial file is removed.

Only after the dump, checksum, WAL/schema checks, and `SELECT 1` all succeed,
assign the single restart owner:

```bash
sudo docker update --restart unless-stopped brc_prelive_pg_20260601
test "$(sudo docker inspect -f '{{.HostConfig.RestartPolicy.Name}}' brc_prelive_pg_20260601)" = unless-stopped
```

If recovery or backup fails before this point, leave restart policy `no` so a
corrupt container cannot enter an automatic restart loop.

- [ ] **Step 6: Run schema-120-compatible read-only safety SQL and exchange probe**

Do not run the old deployed phase-two verifier: its global `hard_stopped`
predicate conflicts with the R1 terminal-history rule, and the candidate
verifier is not yet staged. Run explicit read-only SQL inside PostgreSQL against
the currently deployed schema 120. Begin a read-only transaction and bound
every statement:

```sql
BEGIN TRANSACTION READ ONLY;
SET LOCAL lock_timeout = '1s';
SET LOCAL statement_timeout = '5s';

SELECT EXISTS (
  SELECT 1
  FROM brc_ticket_bound_exchange_commands
  WHERE command_state IN ('prepared', 'dispatching', 'outcome_unknown')
  LIMIT 1
) AS critical_exchange_command_exists;

SELECT EXISTS (
  SELECT 1
  FROM brc_ticket_bound_scope_freezes
  WHERE status = 'active'
  LIMIT 1
) AS active_domain_hold_exists;

SELECT EXISTS (
  SELECT 1
  FROM brc_ticket_bound_protected_submit_attempts AS a
  WHERE a.submit_mode = 'real_gateway_action'
    AND a.exchange_write_called = true
    AND NOT (
      EXISTS (
        SELECT 1
        FROM brc_ticket_bound_order_lifecycle_runs AS closed_l
        WHERE closed_l.protected_submit_attempt_id = a.protected_submit_attempt_id
          AND closed_l.ticket_id = a.ticket_id
          AND closed_l.status = 'lifecycle_closed'
        LIMIT 1
      )
      OR EXISTS (
        SELECT 1
        FROM brc_ticket_bound_order_lifecycle_runs AS l
        JOIN brc_ticket_bound_exit_protection_sets AS s
          ON s.exit_protection_set_id = l.exit_protection_set_id
         AND s.protected_submit_attempt_id = a.protected_submit_attempt_id
         AND s.ticket_id = a.ticket_id
        WHERE l.protected_submit_attempt_id = a.protected_submit_attempt_id
          AND l.ticket_id = a.ticket_id
          AND l.status IN ('position_protected', 'runner_protected')
          AND l.first_blocker IS NULL
          AND s.status IN ('submitted', 'reconciled', 'runner_protected')
          AND s.protection_complete = true
          AND s.reconciled_with_exchange = true
          AND s.first_blocker IS NULL
        LIMIT 1
      )
    )
  LIMIT 1
) AS unsafe_real_write_attempt_exists;

COMMIT;
```

Execute with `psql -v ON_ERROR_STOP=1`; do not import or execute candidate
Python. All three booleans must be false. The anti-join starts from every real
write attempt and accepts only a closed lifecycle or an exactly matching safe
lifecycle/protection tuple; it therefore catches missing lifecycle rows,
unreconciled complete sets, mismatched tickets/attempts/set IDs, and blockers.
Tests seed each negative shape. Query timeout is itself a deploy blocker, not a
reason to remove the bound.

```text
critical_exchange_command_exists=false
active_domain_hold_exists=false
unsafe_real_write_attempt_exists=false
```

A closed historical `hard_stopped` row is not counted by itself. Its still-live
safety condition is caught by an active domain hold or an unsafe nonclosed
lifecycle.

Then run the existing exchange probe in its explicitly read-only position and
open-order mode. Required combined result:

```text
no prepared command
no dispatching command
no outcome_unknown command
no active domain hold
no unprotected real attempt
active position absent or protection-complete
```

If an active position exists, additionally require lifecycle status
`position_protected` or `runner_protected` and exchange-confirmed protection.
The candidate deploy verifier reruns the same readiness rules after staging and
must have a schema-120 compatibility test before migration.

- [ ] **Step 7: Execute the one-command deployment**

From the local R1 worktree, substitute the Task 6 full SHA as
`<R1_FULL_SHA>`:

```bash
python3 scripts/execute_tokyo_runtime_governance_git_deploy.py \
  --json \
  --apply \
  --git-ref codex/release-risk-analysis-20260714 \
  --target-commit <R1_FULL_SHA> \
  --release-name brc-runtime-stability-<R1_SHORT_SHA>-20260715 \
  --previous-release /home/ubuntu/brc-deploy/releases/brc-real-trade-fact-truth-20016445-20260714 \
  --expected-deployed-head 2001644581cccc968ba695d3ff129960db6a7e84 \
  --expected-remote-migration-count 120 \
  --expected-remote-latest-migration 2026-07-13-120_reconcile_terminal_predispatch_commands.py \
  --expected-latest-migration 2026-07-15-124_persist_lifecycle_mutation_enablement_proof.py \
  --runtime-lock requirements-runtime.lock \
  --incident-recovery \
  --deploy-state-dir /var/lib/brc-deploy/deploy-state \
  --deploy-transaction-id auto \
  --deploy-nonce auto \
  --venv-python /home/ubuntu/brc-deploy/app/current/.venv/bin/python
```

The local command resolves and prints+flushes the generated transaction ID and
nonce before opening SSH, then prints manifest/journal paths when available. A
host or SSH interruption is resumed with `--deploy-transaction-id <printed-id>
--deploy-nonce <printed-nonce>`; the state machine validates the same nonce/SHA
lineage and continues from the first incomplete journal phase. It does not ask
the Owner to re-enter internal phase commands.

Expected: `status=applied`, exact head match, revision 124, resolved-lock
identity, CCXT 4.5.56, PostgreSQL ready, exact-SHA release activation and current
projections published, pre/post-canary fact refresh IDs/digests, pre/post
Action-Time refs/digests, post-canary phase-two readiness, deterministic
certification-projection digest, final freshness budget, persisted lifecycle v2
proof, and five API-only canary runs accepted. Lifecycle desired
policy is restored with the v2 proof when enabled; typed
timer/backend scheduling policy is restored, transient oneshot failures clear to
inactive/success, the persistent fence is durably removed only after the atomic
activation commit,
the watcher timer restores last only when its pre-state was active, and zero
deployment forbidden effects. The complete release also activates the already
Owner-approved revision-123 SOR-LONG future-Ticket exit policy; R1 adds no
further strategy parameter, symbol, leverage, capital, or authority expansion.

- [ ] **Step 8: Verify the five bounded canary one-shots from the deploy report**

The executor runs these with lifecycle mutation disabled and the watcher timer
stopped. Verify each recorded service sample contains:

```bash
systemctl show brc-runtime-signal-watcher-canary.service \
  -p Result -p ExecMainStatus -p InvocationID -p ActiveEnterTimestamp
```

Every run must have:

```text
Result=success
ExecMainStatus=0
every stage max RSS < 393216 KiB
exactly one journal-tagged max-RSS row for the API-only core stage
server_route_set_status=passed
forbidden_route_attempts=0
current_user=pg_read_all_data
mutation_privileges=false
default_transaction_read_only=on
transaction_read_only=on
direct forbidden Ticket/authority/order DML rejected under current readonly role
role-reset/alternate-role/read-write escalation statement count = 0
credential isolation claimed = false
bounded sentinel digest unchanged with no timeout/overflow across all five canaries
exchange position quantity and open-order IDs unchanged
no kernel OOM record
no exchange write
```

Query journal rows by the exact systemd `InvocationID`; do not use time-window
grep that could mix two ticks. A missing `InvocationID`, RSS tag, server route-
set/role/privilege fact, rejected direct-DML/zero-escalation fact, bounded sentinel
digest, or exchange snapshot is a failed canary. Systemd 249
on the current 5.15 kernel does not provide a persistent oneshot `MemoryPeak`,
so that property is not an acceptance source.

- [ ] **Step 9: Verify the timer was restored last and observe normal runtime**

```bash
systemctl is-enabled brc-runtime-signal-watcher.timer
systemctl is-active brc-runtime-signal-watcher.timer
```

For the current incident, both must match the recorded `enabled/active`
pre-state without another mutation command. A generic deploy with a disabled or
inactive pre-state must remain disabled or inactive and returns
`accepted_disabled` with `postdeploy_observation_not_applicable`; it does not
fabricate scheduled-tick acceptance. When the recorded pre-state is
enabled/active, observe five completed target-SHA scheduled ticks, normally
about 15 minutes. A non-success, timeout, OOM, exit 137, or memory-budget
violation records `activated_observation_degraded`; the deploy observer does not
recreate the fence or rewrite the already-consumed mutation manifest. Existing
systemd StartLimit/cgroup and Runtime Safety State policies retain their normal
operational authority. These scheduled ticks are normal runtime: an eligible
ticket may legitimately trade through the unchanged official chain and is not
classified as a deployment side effect.

- [ ] **Step 10: Produce the final deployment record**

Record:

```text
interaction_level=Tokyo deploy apply
target_commit=<R1_FULL_SHA>
deployed_head=<R1_FULL_SHA>
postgres_ready=true
alembic_current=124
process_outcome_latest_index=idx_brc_runtime_outcome_lane_process_latest:valid
process_outcome_canary_window_index=idx_brc_runtime_outcome_canary_window:valid
ccxt_version=4.5.56
dependency_lock_sha256=<measured sha256>
readiness_helper_sha256=<measured sha256>
remote_state_machine_sha256=<measured tracked sha256>
remote_state_machine_launcher=/usr/bin/systemd-run:transient_service:/usr/bin/python3:stdlib_hash_loader
remote_state_machine_runtime_max_sec=3600
remote_state_machine_kill_mode=control-group
repository_command_python=<candidate_release>/.venv/bin/python
python_abi_platform=cp310-linux_x86_64
canary_role_preflight_before_migration=passed
canary_role_membership_mode=SET
watcher_canary_ticks=5/5 success
watcher_scheduled_ticks=<5/5 success | not_applicable | measured degraded progress>
watcher_stage_max_rss_kib=<measured journal maximum>
postdeploy_status=<accepted | accepted_disabled | activated_observation_degraded>
prestate_manifest_sha256=<measured sha256>
lifecycle_mutation_capability_prestate_audit=<exact old row>
lifecycle_mutation_desired_policy=<enabled_or_disabled>
lifecycle_mutation_capability_poststate=<same desired policy plus v2 ref/schema/payload when enabled>
lifecycle_mutation_capability_v2_proof_verified=true
lifecycle_mutation_capability_proof_sha256=<measured hash>
ticket_exit_policy_v1_poststate=<revision 123 id/version/hash/status>
runtime_release_activation_sha=<R1_FULL_SHA>
pre_canary_fact_snapshot_ids=<measured bounded IDs>
pre_canary_fact_set_digest_schema=brc.action_time_fact_set_digest.v1
pre_canary_fact_set_digest=<measured digest>
pre_canary_certification_input_digest_schema=brc.action_time_capability_certification_input.v1
pre_canary_action_time_certification_ref=<measured v2 ref>
pre_canary_action_time_certification_digest=<measured digest>
pre_canary_projection_sha=<R1_FULL_SHA>
pre_canary_projection_digest=<measured digest>
post_canary_fact_snapshot_ids=<measured bounded IDs>
post_canary_fact_set_digest_schema=brc.action_time_fact_set_digest.v1
post_canary_fact_set_digest=<measured digest>
post_canary_certification_input_digest_schema=brc.action_time_capability_certification_input.v1
post_canary_phase_two_status=phase_two_ready
post_canary_action_time_certification_ref=<measured v2 ref>
post_canary_action_time_certification_digest=<measured digest>
post_canary_projection_sha=<R1_FULL_SHA>
post_canary_certification_projection_digest_schema=brc.certification_projection_digest.v1
post_canary_certification_projection_digest=<measured digest>
final_refresh_to_enable_elapsed_ms=<measured <=30000>
final_fact_min_remaining_validity_ms=<measured >=30000>
durable_unit_policy_prestate=<typed UnitFileState/ActiveState/SubState/Result/TriggeredBy/Triggers>
durable_unit_policy_poststate=<restored stable policy and healthy observation>
transient_oneshot_incident_state=<observed evidence>
transient_oneshot_target_health=inactive_success
durable_policy_restored=true
old_capability_certification_reused=false
runtime_activation_commit_sha256=<measured sha256>
runtime_activation_status=applied
production_writer_fence_absent_after_activation_commit=true
release_target_syncfs_verified=true
release_pointer_parent_fsynced=true
parent_deploy_transaction_id=<null unless ForwardFixHandoffV1 child>
forward_fix_handoff_id=<null unless ForwardFixHandoffV1 child>
deploy_journal_terminal_state=terminal_consumed
postdeploy_observation_status=<accepted | degraded | not_applicable>
deployment_approaches_real_order=false
deployment_exchange_write=false
canary_exchange_write=false
canary_server_route_set_status=passed
canary_forbidden_route_attempts=0
canary_current_user=pg_read_all_data
canary_mutation_privileges=false
canary_default_transaction_read_only=on
canary_transaction_read_only=on
canary_forbidden_dml_rejected=true
canary_escalation_statement_count=0
canary_credential_isolation_claimed=false
canary_bounded_sentinel_delta=0
canary_bounded_sentinel_overflow=false
canary_exchange_identity_delta=0
local_exact_sha_sensitive_handler_call_counts=0/0/0/0/0
scheduled_runtime_exchange_write=<actual normal runtime fact>
deployment_order_created=false
profile_mutation=false
sizing_mutation=false
scope_expansion=false
authority_expanded=false
known_release_effect=revision_123_owner_approved_sor_long_future_ticket_exit_policy
remaining_blocker=<actual runtime state>
```

Do not commit the deployment report into `output/**`.

---

## R2 Non-Blocking Follow-Up

After R1 production stability is proven, a separate accepted plan may cover
current/history material-change storage, retention scheduling, a PG-independent
infrastructure notification, all-service cgroup capacity, host reboot
certification, and optional 8 GiB host capacity. None of those items may be
silently added to R1 implementation scope.

R2 starts from a seven-day read-only row-count and disk-growth review. With the
current three-minute cadence there can be 480 ticks per day; across the current
22 lanes, an append-on-every-lane design could theoretically create 10,560 rows
per day in one table. The review must replace that upper-bound inference with
measured per-table growth before retention or host-resize work is approved.

## Plan Completion Gate

This plan is complete only when Tasks 1-7 are checked from fresh command
evidence. Documentation approval alone does not mean the runtime is fixed, and
local green tests alone do not mean Tokyo is deployed.
