---
title: P0_RUNTIME_LANE_IDENTITY_CONSERVATION_AND_CROSS_SCOPE_LEAKAGE_ELIMINATION_DESIGN
status: IMPLEMENTED_LOCAL_VERIFIED_PENDING_TOKYO_DEPLOY
authority: docs/current/P0_RUNTIME_LANE_IDENTITY_CONSERVATION_AND_CROSS_SCOPE_LEAKAGE_ELIMINATION_DESIGN.md
last_verified: 2026-07-13
---

# P0 Runtime Lane Identity Conservation And Cross-Scope Leakage Elimination

## Executive Decision

The next medium-scale P0 should establish one immutable production identity
before strategy evaluation:

```text
PG candidate scope
+ PG candidate-scope/Event-Spec binding
+ PG Event Spec
+ PG runtime scope binding
+ active runtime instance
-> RuntimeLaneIdentity
-> side-scoped evaluation
-> exact-lane signal materialization or no signal
-> promotion / action-time lane / Ticket with the same identity
```

The evaluator may compute broader market patterns internally. Production may
expose only the result for the registered Event Spec. It must not create,
switch, or overwrite the registered runtime lane.

This design replaces the proposed **Signal Disposition SSOT** as the primary
abstraction. The defect is not primarily a missing lifecycle state. It is a
missing identity invariant across PG scope, runtime input, evaluator output,
API projection, signal materialization, process outcome, and Owner notification.

The implementation must not:

- add a CPM/SOL conditional patch;
- treat `CPM-RO-001 + SOLUSDT + short` as a registered lane;
- add a sixth StrategyGroup;
- change the five current StrategyGroups or their Owner-authorized directions;
- expand symbol, side, profile, leverage, notional, capital, or submit authority;
- create a second JSON/Markdown authority path;
- add a broad `SignalDisposition` lifecycle model.

## Execution State

The Owner confirmed this design before implementation. Local implementation is
complete and verified; Tokyo rollout and the bounded runtime smoke remain
pending at this document revision.

| Verification surface | Local result | Remaining boundary |
| --- | --- | --- |
| Runtime identity transport | Immutable typed identity is carried from PG resolution through signal, promotion, action-time lane, and Ticket | Verify the same path against Tokyo PG after migration `118` |
| Cross-scope rejection | Wrong side/symbol/Event-Spec/timeframe materialization is fail-closed and cannot create a false lane | Observe three production watcher/monitor ticks |
| Known CPM short incident | Migration reconciles the legacy false process outcome without creating a CPM short lane | Confirm no new false outcome or notification on Tokyo |
| Regression and cadence safety | `3001 passed, 1 skipped`; production file-I/O audit is `clear` with zero recurring JSON/MD report-file risk | Natural eligible event remains the next live acceptance proof |

This state does not expand StrategyGroup, symbol, side, profile, leverage,
notional, capital, or exchange-write authority. FinalGate and Operation Layer
remain mandatory for every real order.

## Owner Confirmation Scope

This proposal contains no unresolved StrategyGroup policy choice. PG and the
current registry already define the active direction set:

| StrategyGroup | Current symbols | Registered event direction |
| --- | --- | --- |
| `CPM-RO-001` | `ETHUSDT`, `SOLUSDT`, `AVAXUSDT`, `SUIUSDT` | `CPM-LONG` only |
| `MPG-001` | `OPUSDT`, `SOLUSDT`, `AVAXUSDT`, `SUIUSDT` | `MPG-LONG` only |
| `MI-001` | `AVAXUSDT`, `ETHUSDT`, `SOLUSDT` | `MI-LONG` only |
| `SOR-001` | `ETHUSDT`, `SOLUSDT`, `AVAXUSDT`, `BTCUSDT` | explicit `SOR-LONG` and `SOR-SHORT` |
| `BRF2-001` | `BTCUSDT`, `AVAXUSDT`, `ETHUSDT` | `BRF2-SHORT` only |

Owner confirmation accepts these engineering decisions:

1. A market pattern on a different side is discarded at the production Event
   Spec boundary, not retained as an Observe-only strategy state and not
   converted into a new lane.
2. A valid opposite-side SOR event may materialize only through the separately
   registered SOR lane for that side.
3. A CPM short pattern may exist only inside a generic evaluator's local
   computation or offline Replay. Production CPM-LONG returns no event for that
   lane and may not persist CPM-short runtime evidence, signal, process outcome,
   promotion, Ticket, or Owner notification.
4. Active shadow runtimes with no current PG candidate-scope binding are
   retired through the official runtime lifecycle as stale engineering state.
5. The PG schema receives negative constraints so application code is not the
   only protection against cross-scope signal insertion.

## Admission Model: No Indefinite Observe-Only StrategyGroup

### Product Decision

For this single-Owner, low-frequency system, production StrategyGroup
governance is binary at the admission boundary:

```text
research / Replay
-> admit the versioned StrategyGroup + Event Spec scope
   or do not admit it

admitted + enabled
-> running
-> waiting for opportunity
-> processing
-> trade through the official path when gates pass
```

An admitted StrategyGroup is not kept in production merely to collect
Observe-only signals. A non-admitted strategy remains in research or is parked;
it does not consume an active production candidate lane.

For an active production candidate lane, admission is machine-checkable:

```text
semantic admission = trial_grade_capable
and current Event Spec signal grade = trial_grade_signal
and current Event Spec execution mode = trial_live
and execution_eligibility_enabled = true
```

Any other semantic conclusion is a non-admission result. It may remain as audit
or research evidence, but it cannot own an active production candidate lane.

### Necessary Distinction

| Concept | Meaning | May trade |
| --- | --- | ---: |
| Runtime market observation | The watcher continuously scans an admitted strategy while waiting for its event | Yes, when the event and official gates pass |
| Non-executing detector worker | A technical component cannot write orders directly; it feeds the Ticket/FinalGate/Operation Layer chain | The StrategyGroup may still trade through the official path |
| Observe-only StrategyGroup | A production strategy emits signals but is deliberately never eligible to trade | No; not a durable state for the current product |
| Replay / research candidate | Offline evidence used to decide admission | No; it is outside production scope |

`shadow_mode=true` on a detector runtime does not by itself mean that the
StrategyGroup is Observe-only. The detector should not own exchange-write
authority. The admitted StrategyGroup's live capability comes from PG Event
Spec eligibility, Owner policy, action-time gates, and the official Operation
Layer.

### Time Boundary

There is no open-ended production observation period.

| Phase | Maximum duration | Exit |
| --- | ---: | --- |
| Pre-admission strategy validation | No production clock; complete by deterministic Replay and explicit admission decision | Admit or do not admit |
| Predeploy engineering certification | Deterministic test run; no market wait | All six Event Specs pass or implementation remains blocked |
| Postdeploy runtime smoke | **3 watcher/monitor ticks and no more than 60 minutes** | Accept continued normal running or roll forward/fix |
| Natural-event acceptance | No Observe-only delay | The admitted strategy handles the event through the real official path |

Three consecutive ticks are sufficient because they prove initial load,
repeat-cadence stability, and idempotent re-evaluation. The 60-minute ceiling
prevents an unhealthy scheduler from turning engineering smoke into another
market-dependent waiting period; whichever limit is reached first ends the
window with pass or fail.

If a future strategy depends on live-only data that cannot be replayed, the
data-collection experiment belongs in research infrastructure with a defined
evidence target. It does not justify an indefinitely active Observe-only
production StrategyGroup.

### Current Five StrategyGroups

The current five StrategyGroups and six Event Specs are already the admitted
production candidate set. This P0 does not put them back into an observation
probation. It corrects their identity transport so the next matching natural
event may proceed to the real trading path.

Legacy/internal values such as `observe_only_signal`, `observe_only`, and
`OBSERVE_ONLY` may remain where they mean research evidence, a fail-closed
default, or a non-executing component boundary. They must not be presented as
the governance state of any of the current five admitted StrategyGroups, and
they must not replace the current Event Specs' registered
`trial_grade_signal + trial_live` authority.

## Objective Facts

### Current Production Registration

The current PG and contract surface contains five StrategyGroups, 22 candidate
lanes, and six current Event Specs. CPM has four long candidate lanes and no
short candidate lane. SOR is the only current StrategyGroup with both explicit
directions.

All 22 current semantic-admission rows are `trial_grade_capable`; the current
set contains zero `observe_only_by_design` admissions. All six v2 Event Specs
declare `trial_grade_signal + trial_live` and enable execution eligibility.

Sources:

- `docs/current/PRE_TRADE_RUNTIME_CONTRACT.md`;
- `docs/current/strategy-group-handoffs/STRATEGYGROUP_REGISTRY_CONTRACT.md`;
- `docs/current/RUNTIME_CONTROL_STATE_DB_TABLE_DESIGN.md`;
- verified Tokyo PG current rows on 2026-07-13.

### Confirmed CPM Incident

The production acceptance event did not create a signal, promotion, action-time
lane, Ticket, order, or position.

| Fact | Verified value |
| --- | --- |
| Alert identity | `CPM-RO-001 / SOLUSDT / short` |
| Registered CPM candidate lane | `CPM-RO-001 / SOLUSDT / long` |
| Source runtime | `strategy-runtime-d3e7af7d4f6e` |
| Source runtime side | `long` |
| Separate legacy short runtime | `strategy-runtime-81030da665ff` |
| Legacy short runtime watcher result | correctly excluded by candidate universe |
| Signal row | none |
| Promotion row | none |
| Action-time lane | none |
| Ticket | none |
| Durable wrong current row | `live_signal_materialization` process outcome scoped as fake short lane |

The wrong short identity came from the long runtime's nested evaluator output,
not from the excluded legacy short runtime.

### Confirmed Code Path

| Boundary | Current behavior | Defect |
| --- | --- | --- |
| Semantics catalog | `_cpm_binding` declares `supported_sides=["long"]` | Correct authority exists |
| CPM evaluator | Historical evaluator can report long or short patterns | Output is broader than the registered live Event Spec |
| Evaluation service | Blocks a would-enter side outside semantics | Exact blocker exists internally |
| Production API | Converts every non-ready evaluation into generic `waiting_for_signal` | Exact mismatch is hidden |
| Active runtime monitor | Uses `signal.side or runtime.side` | Evaluator output can overwrite registered lane side |
| Signal projector | Looks up PG scope using the overwritten side | Creates a fake-lane materialization failure |
| Process outcome | Persists the derived fake lane in `scope_key` | False current runtime identity becomes durable |
| Server monitor | Parses `scope_key` as lane truth | Sends an Owner notification for an unregistered lane |

Primary code sources:

- `src/domain/strategy_semantics.py`;
- `src/domain/cpm_historical_evaluator.py`;
- `src/application/runtime_strategy_signal_evaluation_service.py`;
- `src/interfaces/api_trading_console.py`;
- `scripts/runtime_active_observation_monitor.py`;
- `scripts/run_tokyo_runtime_server_monitor.py`.

### Additional Same-Class Exposure

The production API currently does not use the existing PG Event Spec loader in
`runtime_strategy_signal_input.py`. It builds the observation input with a fixed
`1h` primary window. This is not only a side problem:

| Identity dimension | PG authority exists | Current production transport |
| --- | ---: | --- |
| StrategyGroup | yes | partially conserved |
| StrategyGroup version | yes | runtime value, not cross-checked to Event Spec |
| Symbol | yes | partially conserved |
| Side | yes | may be overwritten by evaluator output |
| Event Spec | yes | not carried through the production API result |
| Event Spec version | yes | not carried through the production API result |
| Timeframe | yes | production API currently fixes `1h` |
| Candidate scope ID | yes | resolved only after candidate reconstruction |
| Runtime scope binding | yes | not part of evaluator/API identity |
| Runtime instance | yes | carried as provenance |

`SOR-LONG` and `SOR-SHORT` are `15m` Event Specs. Therefore a side-only patch
would leave the same identity class open through timeframe and Event Spec.

## Root Cause Analysis

### Direct Cause

`_live_signal_candidates_from_summaries()` treats evaluator output fields as a
candidate identity source:

```python
side = _normalize_side(signal.get("side") or row.get("side"))
```

The nested output wins over the registered runtime lane.

### System Cause

The chain has no immutable typed object that owns:

```text
StrategyGroup
+ StrategyGroup version
+ canonical symbol / asset class
+ side
+ Event Spec / version / event id
+ timeframe / time authority
+ candidate scope / event binding
+ runtime scope binding / profile
+ runtime instance provenance
```

Each boundary reconstructs a subset from loose dictionaries. That allows a
field emitted as evaluator evidence to become identity authority later.

### Test Escape

Existing tests prove several local rules:

- CPM short output is blocked by semantics;
- candidate-universe filtering excludes a short runtime;
- PG materialization rejects a missing candidate binding;
- downstream promotion and Ticket code compare several identity fields.

They do not prove this production-shaped invariant:

```text
registered long runtime
-> evaluator returns short pattern
-> API preserves registered long identity
-> monitor does not reconstruct a short candidate
-> PG receives neither a short signal nor a short process lane
-> Owner notification contains no short opportunity
```

The tests stop at local components and do not cross the producer-consumer seam
where nested output is reinterpreted.

## Bounded Analysis

The confirmed incident proves that the shared monitor path can leak an
evaluator side into runtime identity. It does not prove that all 22 lanes have
already failed in production.

The fixed `1h` production API path and the same loose dictionary transport make
Event Spec and timeframe leakage a reasonable high-risk inference. This task
must certify all 22 lanes and all six Event Specs rather than assume those
dimensions are safe.

## Alternatives

| Option | Shape | Benefit | Cost / residual risk | Decision |
| --- | --- | --- | --- | --- |
| Monitor precedence patch | Change to `row.side or signal.side` | Very small and stops this exact fake short lane | Event Spec/timeframe remain unowned; another consumer can repeat the defect | Reject |
| Make every detector a separate one-side implementation | Duplicate or split evaluator logic for each side/event | Simple output semantics at one layer | Does not conserve PG identity across API/projector; duplicates shared market logic | Reject as sole solution |
| Immutable PG lane envelope plus exact-match materialization | Establish identity before evaluation; output is evidence; every boundary validates the same lane | Closes side/Event Spec/timeframe class and supports all current/future strategies | Medium-scale coordinated change and schema guardrails | Adopt |

The adopted option may later allow evaluators to become more event-specific,
but correctness does not depend on every detector being rewritten first.

## Core Domain Contract

### RuntimeLaneIdentity

One pure typed value object owns the production pre-signal identity:

```python
class RuntimeLaneIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_scope_id: str
    candidate_scope_event_binding_id: str
    runtime_scope_binding_id: str
    runtime_instance_id: str
    runtime_profile_id: str
    policy_current_id: str

    strategy_group_id: str
    strategy_group_version_id: str
    symbol: str
    asset_class: str
    side: Literal["long", "short"]

    event_spec_id: str
    event_spec_version: str
    event_id: str
    timeframe: str
    time_authority: Literal["trigger_candle_close_time_ms"]
```

`identity_key` is a deterministic hash derived from all fields above. It is a
comparison and lineage value, not a second source of truth.

### Field Ownership

| Field family | Authority | Evaluator may change it |
| --- | --- | ---: |
| StrategyGroup/version | PG strategy version and Event Spec | No |
| Symbol/asset class | PG candidate scope | No |
| Side | PG candidate scope plus Event Spec | No |
| Event ID/spec/version | PG candidate-scope/Event-Spec binding | No |
| Timeframe/time authority | PG Event Spec | No |
| Runtime profile/policy | PG runtime scope binding | No |
| Runtime instance | current runtime record matched to PG lane | No |
| Signal type/confidence/reasons/facts | evaluator output | Yes, as evidence only |
| Computed output side | evaluator output | Yes, as an internal pattern claim only |

### Resolver Invariant

The PG resolver must return exactly one joined identity. It fails closed when
any of these is true:

- candidate scope is missing, paused, parked, revoked, duplicated, or expired;
- candidate scope and Event Spec disagree on group or side;
- candidate scope timeframe and Event Spec timeframe disagree;
- Event Spec is not current;
- runtime scope binding is missing, paused, revoked, expired, or ambiguous;
- runtime instance group/version/symbol/side disagrees with the PG lane;
- runtime boundary does not allow the same symbol and side;
- policy/profile references do not match the active runtime scope binding.

If no canonical lane can be resolved, the failure scope is
`runtime:<runtime_instance_id>`. The system must not synthesize a lane key from
an untrusted output.

## Evaluation Contract

### Separation Of Identity And Evaluator Evidence

`StrategyFamilySignalOutput` remains market/strategy evidence. Runtime
evaluation wraps it with the canonical lane:

```python
class RuntimeLaneEvaluationStatus(str, Enum):
    EVENT_NOT_SATISFIED = "event_not_satisfied"
    EVENT_READY = "event_ready"
    BLOCKED = "blocked"


class RuntimeLaneEvaluationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lane_identity: RuntimeLaneIdentity
    evaluation_status: RuntimeLaneEvaluationStatus
    output: StrategyFamilySignalOutput | None
    computed_output_side: SignalSide
    can_materialize_live_signal_event: bool
    lane_match_reasons: list[str]
    blockers: list[str]
    warnings: list[str]
```

This is not a new lifecycle or SignalDisposition state machine.

The old internal `RuntimeStrategySignalEvaluationStatus.OBSERVE_ONLY` may remain
for pre-admission/research compatibility while this P0 is implemented, but it
must not be the production lane status for an admitted Event Spec. Production
uses `event_not_satisfied`, `event_ready`, or `blocked`, which answer what
happened on this admitted lane without inventing an Observe-only strategy tier.

### Exact Behavior Matrix

| Evaluator result | Current lane | Runtime meaning | Signal materialization | Process outcome / Owner notification |
| --- | --- | --- | --- | --- |
| `NO_ACTION` | any registered lane | Current Event Spec did not fire | No | No PG write and no notification |
| `WOULD_ENTER long` | registered long lane | Exact event match | Allowed to continue to PG validation | Existing signal path |
| `WOULD_ENTER short` | registered short lane | Exact event match | Allowed to continue to PG validation | Existing signal path |
| `WOULD_ENTER short` | CPM registered long lane | Not a CPM-LONG event; production result is no event | No | No persisted CPM-short state and no Owner notification |
| `WOULD_ENTER short` | SOR registered long lane | Short event is not this lane's event | No through long lane; separately registered SOR short lane may materialize | No long-lane failure |
| `WOULD_ENTER` with `side=none` | any lane | Invalid producer result | No | Engineering failure on canonical lane |
| Group/version/symbol/timeframe mismatch | any lane | Cross-scope output corruption | No | Engineering failure on canonical lane |
| Missing/ambiguous PG lane identity | no canonical lane | Runtime registration defect | No | Runtime-instance-scoped engineering failure |

For a generic evaluator result that does not match the registered Event Spec:

```text
can_materialize_live_signal_event = false
lane_match_reasons = ["strategy_output_side_not_selected_lane:<computed_side>"]
blockers = []
persist_runtime_observation = false
owner_action_required = false
```

This prevents a legitimate multi-side detector from turning the non-selected
side into a fake strategy lane or engineering outage. The production result is
equivalent to no event for this Event Spec. Opposite-side pattern analysis
belongs in offline Replay/OFC and is not persisted as current runtime state.

## Production API Contract

The runtime evaluation API sequence becomes:

```text
load active runtime
-> resolve RuntimeLaneIdentity from PG
-> load closed candles using lane.timeframe
-> build signal input
-> evaluate
-> validate output against lane
-> return canonical lane plus the registered Event Spec result
```

Request fields such as `symbol`, `side`, `family`, and `carrier_id` are
compatibility assertions only. They cannot override the PG identity. A mismatch
returns an exact blocked response.

The response must carry:

```text
runtime_lane_identity
evaluation_result
can_materialize_live_signal_event
lane_match_reasons
exact blockers
```

Healthy no-action and discarded non-matching evaluator results may use the product status
`waiting_for_signal`. Invalid identity or evaluator corruption must use
`blocked` with its exact first blocker. The API must not collapse both classes
into `strategy_signal_not_ready_for_action_time_ticket`.

## Monitor And Signal Projection Contract

### Candidate Extraction

`_live_signal_candidates_from_summaries()` may select a candidate only when:

```text
runtime_lane_identity exists
and can_materialize_live_signal_event = true
and evaluation status is ready
and output signal_type = would_enter
and output side = runtime_lane_identity.side
and output group/version/symbol/timeframe match the lane
```

Candidate identity is copied only from `runtime_lane_identity`. The nested
`signal_summary.side` is compared, never selected as a fallback.

### Projection Revalidation

Before insert, the PG signal projector re-resolves:

```text
candidate_scope_id
+ candidate_scope_event_binding_id
+ event_spec_id
+ runtime_scope_binding_id
+ StrategyGroup/symbol/side
```

The resolved PG row must equal the transported `identity_key`. Any mismatch
fails closed on the canonical lane.

### Process Outcome Rules

| Condition | PG result |
| --- | --- |
| Healthy no-action | zero signal row, zero process-outcome write |
| Discarded non-matching evaluator result | zero signal row, zero process-outcome write |
| Exact lane match and valid PG authority | signal insert or immutable duplicate |
| Exact lane but projection/business failure | current outcome on that canonical lane |
| Missing canonical identity | runtime-instance-scoped failure, not a fabricated lane |
| Current process outcome references no registered lane | ignored as current authority and reconciled |

Lane-scoped process outcomes must store typed identity columns. `scope_key`
remains a derived display/idempotency key; server monitoring must not parse it
as the primary identity source.

## PG Constraint Design

Migration `118` will add relational guardrails for the current signal boundary.

### Composite Identity Constraints

1. Candidate scope exposes a unique composite identity:

   ```text
   candidate_scope_id + strategy_group_id + symbol + side
   ```

2. Event Spec exposes a unique composite identity:

   ```text
   event_spec_id + strategy_group_id + side
   ```

3. Candidate-scope/Event-Spec binding references both composite identities.
4. Runtime scope binding references the candidate composite identity.
5. `brc_live_signal_events` receives typed binding, runtime, version, timeframe,
   and `lane_identity_key` lineage columns in addition to its existing
   candidate/Event-Spec/group/symbol/side columns.
6. A live signal references the exact candidate/Event-Spec binding,
   runtime-scope binding, and runtime instance.
7. Fresh validated `live_market` signals require the complete typed lane
   identity; historical/replay rows remain non-authoritative provenance.

Constraints use `RESTRICT` semantics. Historical rows remain readable; retired
bindings are not deleted merely because they are no longer current.

### Process Outcome Typed Identity

`brc_runtime_process_outcomes` receives nullable typed scope columns:

```text
scope_kind
runtime_instance_id
candidate_scope_id
candidate_scope_event_binding_id
runtime_scope_binding_id
event_spec_id
event_spec_version
event_id
strategy_group_id
strategy_group_version_id
symbol
asset_class
side
timeframe
lane_identity_key
```

For `process_name=live_signal_materialization` and `scope_kind=lane`, the exact
candidate/Event-Spec identity is required. Other global or runtime processes may
remain non-lane scoped.

### Existing False Row Reconciliation

The migration must not delete history blindly. It will:

1. identify current lane outcomes with no active or historical matching
   candidate/Event-Spec identity;
2. replace their current blocking projection with a resolved/noop projection;
3. resolve matching active Owner notification state;
4. retain source watermark, run ID, timestamps, and notification delivery
   lineage for audit;
5. explicitly verify the known CPM/SOL/short row is no longer current blocking
   authority.

## Downstream Conservation

Existing promotion and Ticket code already performs several identity checks.
This task converts them into one shared negative invariant:

```text
live signal identity
= public/action-time fact lane
= promotion candidate lane
= arbitration lane
= Action-Time Ticket lane
```

The shared guard validates:

- StrategyGroup and version;
- symbol and asset class where present;
- side;
- candidate scope;
- Event Spec and version;
- runtime scope binding/profile;
- signal/promotion/lane lineage IDs.

The guard is used at the fact-snapshot, promotion, action-time lane, and Ticket
boundaries. Existing local checks are removed or delegated to the shared guard
so there is one rule owner rather than another compatibility layer.

## Legacy Runtime Hygiene

An active runtime instance is not itself a candidate lane. The current watcher
must continue to select only runtimes with an exact PG lane identity.

After deployment:

1. enumerate active runtimes against the 22 registered lanes;
2. verify one selected runtime per required watcher lane;
3. identify runtimes with no active candidate/Event-Spec/runtime binding;
4. retire stale shadow runtimes through the official runtime transition and
   audit event path;
5. do not create missing opposite-side scope to make a legacy runtime fit.

The known CPM short shadow runtime is hygiene debt, not the source of the
2026-07-13 false identity and not a new StrategyGroup.

## All-22-Lane Certification

### Positive Matrix

| Event Spec | Lane count | Positive event side | Primary timeframe |
| --- | ---: | --- | --- |
| `CPM-LONG` | 4 | long | 1h |
| `MPG-LONG` | 4 | long | 1h |
| `MI-LONG` | 3 | long | 1h |
| `SOR-LONG` | 4 | long | 15m |
| `SOR-SHORT` | 4 | short | 15m |
| `BRF2-SHORT` | 3 | short | 1h |

Each lane must prove:

```text
PG lane resolution
-> correct timeframe input
-> exact matching evaluator output
-> canonical signal identity
-> promotion/lane/Ticket identity conservation
-> stop before exchange write in certification
```

### Negative Matrix

Every Event Spec family must reject or safely classify:

- opposite evaluator side;
- unsupported/unregistered side;
- wrong StrategyGroup;
- wrong StrategyGroup version;
- wrong symbol;
- wrong candidate scope ID;
- wrong Event Spec ID or version;
- wrong timeframe;
- missing/ambiguous runtime scope binding;
- request override mismatch;
- fake lane process outcome;
- replay/historical/synthetic source presented as live;
- stale or terminal event identity;
- downstream fact/promotion/lane/Ticket side drift.

Required named cases include:

```text
CPM long runtime + short generic result -> production CPM-LONG no event; no short persistence
SOR long runtime + short generic result -> production SOR-LONG no event; short lane handles it
SOR short runtime + long generic result -> production SOR-SHORT no event; long lane handles it
BRF2 short runtime + long generic result -> production BRF2-SHORT no event; no long persistence
all 22 registered lanes -> exact PG identity and timeframe
```

## Replay / Live Parity

Replay and Live may share pure evaluator logic, but they use different
authority envelopes:

| Surface | Event scope source | May create live signal |
| --- | --- | ---: |
| Live | current PG RuntimeLaneIdentity | Yes, only after exact match |
| Historical Replay / OFC | version-pinned Event Spec fixture or PG read | No |
| Unit test / synthetic | typed in-memory fixture | No |

An opposite-side Replay result is calibration evidence. It must not be
promoted by reusing the live runtime's identity.

## Owner Notification Contract

Owner notification consumes typed PG identity only.

### Notify

- a registered lane becomes temporarily unavailable due to identity resolution,
  projector, or schema failure;
- an exact registered fresh signal progresses;
- normal lifecycle/safety events already defined by current contracts.

### Stay Quiet

- healthy no-action;
- evaluator computed a pattern for another registered lane and the current
  Event Spec correctly returned no event;
- evaluator computed an unregistered opposite-side pattern that production
  discarded;
- excluded legacy runtime with no authority, unless runtime hygiene itself
  cannot be repaired;
- repeated unchanged current state.

The Owner-facing primary message must name only registered StrategyGroup,
symbol, and direction. Internal identity details remain developer/audit fields.

## Cadence And Performance

| Dimension | Required behavior |
| --- | --- |
| Cadence | One indexed lane-identity resolution per monitored runtime observation; no full replay in cadence |
| No-signal file writes | `0` JSON/MD files |
| Healthy no-signal PG writes | `0` live-signal and process-outcome writes |
| Failure PG writes | At most one current upsert per failing canonical lane or runtime instance |
| CPU | Typed comparisons and indexed joins only |
| Network/API | Existing bounded public-market request; no new exchange-write call |
| Timeout | PG query and observation API remain bounded; no timeout extends fact freshness |
| Disk | No new recurring files or sidecars |
| Retention | Existing PG current/audit lineage; manual archive-only evidence remains outside cadence |

`scripts/audit_production_runtime_file_io.py --json --fail-on-risk` must report:

```text
performance_risk.status = clear
frequent_report_write = 0
```

## Rollout

### Deployment Order

1. Add RED production-shaped identity tests.
2. Add the typed identity and PG resolver.
3. Switch the production API to PG Event Spec timeframe and lane-aware result.
4. Switch monitor extraction and signal projection to canonical identity.
5. Add typed process-outcome identity and PG negative constraints.
6. Reconcile the existing false process/notification state.
7. Add downstream shared guard and all-22 certification.
8. Run targeted, action-time, monitor, migration, file-I/O, and full regression.
9. Deploy migration and code with watcher stopped during the short cutover.
10. Publish exact-head capability truth.
11. Start watcher, monitor, and lifecycle services.
12. Verify no fake CPM-short state and no unauthorized side expansion.

There is no dual-reader or JSON fallback. Mixed code/schema generation fails
closed.

### Rollback

Rollback must not restore evaluator-owned lane identity.

Allowed rollback:

- stop watcher signal materialization;
- leave schema constraints in place;
- roll application code back only to a release that cannot bypass the new
  constraints;
- keep live-submit progression paused while forward-fixing identity transport;
- preserve reconciled notification/process lineage.

Forbidden rollback:

- return to `signal.side or runtime.side` fallback;
- remove PG constraints to make old code insert;
- revive file-backed scope;
- recreate CPM short candidate scope;
- expand Owner policy or live profile.

## WIP And Natural-Event Interrupt

This task becomes the single active medium-scale P0 engineering lane. It does
not add a new StrategyGroup or candidate scope.

A different-identity natural fresh signal remains an interrupt. Work pauses at
the next committed transaction boundary, the natural event is accepted through
the deployed path, and identity evidence is captured before this task resumes.
No synthetic event may become production submit authority.

## Acceptance Criteria

1. One immutable `RuntimeLaneIdentity` is resolved from PG before evaluator
   output can be interpreted.
2. Production API uses the PG Event Spec timeframe; SOR uses `15m`.
3. Request fields and evaluator output cannot override StrategyGroup, version,
   symbol, side, Event Spec, timeframe, runtime profile, or candidate scope.
4. `CPM-RO-001 + SOLUSDT + short` cannot be materialized from the registered
   long runtime.
5. A CPM short generic evaluator result produces no persisted runtime
   observation, short signal, promotion, lane, Ticket, process lane, or Owner
   opportunity notification.
6. SOR long and short events can progress only through their separately
   registered lanes.
7. Missing or corrupt identity is persisted against the canonical lane or
   runtime instance, never a fabricated lane.
8. PG rejects cross-scope candidate/Event-Spec/live-signal inserts.
9. Existing false current process/notification state is resolved without
   deleting audit lineage.
10. All five StrategyGroups, 22 candidate lanes, and six Event Specs pass the
    positive and negative certification matrix.
11. Signal, fact, promotion, action-time lane, and Ticket identity remain equal.
12. Out-of-scope active shadow runtimes are retired without expanding policy.
13. No-signal ticks create zero JSON/MD files and zero new live-signal/process
    rows.
14. Targeted and full regression pass.
15. No FinalGate, Operation Layer, exchange write, live profile, sizing,
    leverage, notional, capital, withdrawal, transfer, or credential authority
    changes.

## Chain Position

```text
chain_position: pretrade_registered_runtime_lane_to_live_signal_event
strategy_group_id: all five current StrategyGroups
symbol: all 22 current candidate lanes
stage: PG lane identity -> runtime input -> evaluator output -> PG signal
first_blocker: evaluator output can overwrite registered lane side and production API does not conserve Event Spec/timeframe identity
next_action: implement immutable PG RuntimeLaneIdentity, exact-match materialization, typed process outcomes, and all-22 cross-scope certification
stop_condition: no evaluator/API/monitor/projector path can create, switch, or persist an unregistered StrategyGroup+symbol+side+Event-Spec lane
owner_action_required: confirmation of this design only
authority_boundary: no change to current five StrategyGroups, 22 candidate lanes, six Event Specs, risk, profile, sizing, FinalGate, Operation Layer, or exchange-write authority
```
