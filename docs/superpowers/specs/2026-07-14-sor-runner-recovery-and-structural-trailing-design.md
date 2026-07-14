# SOR Runner Recovery And Structural Trailing Design

Status: proposed for Owner review

Date: 2026-07-14

Scope: current ETH Ticket recovery, runner lifecycle monitoring repair, and a
versioned structural trailing-stop policy for future SOR Tickets

## Objective

Restore the current ticket-bound lifecycle without changing the current ETH
position's strategy semantics, then extend the same lifecycle authority so a
future SOR runner can move its exchange-native protective stop monotonically
after TP1.

The target chain is:

```text
current ETH manual reduce-only close
-> exact EXTERNAL_CLOSE attribution
-> residual protection cleanup
-> lifecycle closure / budget settlement / Live Outcome
-> deploy runner monitoring repair
-> future SOR Ticket reaches TP1
-> runner remains exchange-protected
-> one structural trail evaluation per closed 15m candle
-> submit-new-before-cancel-old stop replacement
-> final exit / settlement / review
```

This design does not add a fixed TP2, modify the current live Ticket's stop,
expand symbol or side scope, change leverage or sizing, or create a second
lifecycle or exchange-command authority.

## Owner Decisions Captured

The design treats the following Owner direction as accepted for review:

1. The current ETH runner may be closed manually with an exact reduce-only
   close instead of forcing an active-lifecycle deployment.
2. The existing current Ticket is recovered as `EXTERNAL_CLOSE`; its current
   Runner_SL is not manually replaced or reinterpreted as a trailing order.
3. Future SOR Tickets use TP1 plus a structural trailing runner.
4. No fixed TP2 is created by default, preserving right-tail participation.
5. A long runner stop may move only upward; a short runner stop may move only
   downward.
6. A replacement stop must be confirmed at the exchange before the prior stop
   is cancelled.

The proposed initial strategy-policy values are:

| Field | Initial value | Meaning |
| --- | --- | --- |
| `trail_timeframe` | `15m` | Same closed-candle authority as SOR-LONG/SOR-SHORT |
| `structure_window_bars` | `3` | Use the last three fully closed 15m candles |
| `atr_period` | `14` | Closed-candle volatility reference |
| `atr_buffer_multiple` | `0.5` | Buffer the structural reference by half an ATR |
| `hard_tp2_enabled` | `false` | Runner has no fixed profit cap |
| `evaluation_cadence` | one evaluation per new closed 15m candle | No tick-by-tick order churn |

These values are versioned strategy policy. Changing them later requires a new
policy revision and replay/review evidence; it must not silently reinterpret an
already-created Ticket.

## Verified Starting State

- The active production Ticket is
  `ticket:715fc1e8ef5dec00a311e3be4bb64637794264f0fac6149a70e3f88a3fdea108`
  for `SOR-001 / ETHUSDT / long`.
- Entry filled quantity is `0.46` at average price `1784.8`.
- TP1 filled `0.23` at `1811.45`.
- The remaining runner is `0.23`.
- Binance exposes one open reduce-only conditional sell order for `0.23` with
  trigger price `1754.01` and position side `LONG`.
- PG lifecycle state is `runner_protected`.
- The 30-second lifecycle timer is healthy but repeatedly publishes
  `selected_scope_count=0` and `exchange_read_called=false`.
- `MAINTAINABLE_LIFECYCLE_STATUSES` and `SNAPSHOT_STATUSES` omit
  `runner_protected`.
- The official deployment interlock correctly blocks the release while the
  real lifecycle remains open.
- The current exit-protection table already supports multiple `RUNNER_SL` rows
  distinguished by local order identity and a
  `replaces_exit_protection_order_id` lineage field, but current role lookup
  returns the first matching role and is not generation-aware.

## Root Cause And Product Gap

### Current incident

The runner state transition is internally contradictory:

```text
runner_protection_adjuster
-> lifecycle.status = runner_protected
-> next_action = continue_runner_monitoring

lifecycle_maintenance_scheduler
-> runner_protected not in maintainable statuses
-> runner Ticket is never selected again
```

The exchange-native stop remains valid, but BRC can no longer detect a fill,
protection loss, external close, or final lifecycle outcome.

### Requested exit behavior

The existing runner is not a TP2. It is one residual position with a fixed
protective stop. The requested behavior is a monotonic, exchange-native
trailing protective stop after TP1. This is a strategy-semantic extension,
not a monitoring bug fix and not a generic order-manager toggle.

## Rejected Approaches

| Approach | Benefit | Rejection reason |
| --- | --- | --- |
| Force-deploy while the current runner is active | Preserves the live opportunity | Bypasses the active-lifecycle interlock and still deploys code that omits `runner_protected` |
| Manually replace the current Runner_SL | Locks more of the current profit | Breaks PG/exchange order identity and contaminates the current strategy sample |
| Add a fixed TP2 and move SL to breakeven | Simple and familiar | Caps the right tail and changes SOR into a fixed-target strategy |
| Run a local synthetic trailing stop without an exchange stop | Avoids repeated exchange replacement | Violates the exchange-native protection invariant and fails during local/runtime outage |
| Add a second trailing-stop daemon or command table | Isolates implementation | Creates a second lifecycle and exchange-command authority |

## Selected Architecture

The selected architecture has two sequential work packages. WP-A removes the
current incident and restores release safety. WP-B adds future trailing behavior
only after WP-A is deployed and certified.

## WP-A: Current Ticket Recovery And Runner Monitoring Repair

### A1. Manual-close recovery boundary

After the Owner submits one exact reduce-only close for the remaining runner,
the system performs signed read-only exchange collection before any cleanup or
PG closure:

```text
account + canonical instrument + position bucket
-> flat position proven
-> recent fill side / quantity / time proven
-> exactly one open Ticket owns the remaining quantity
-> no tracked exit order explains the fill
-> classify exact EXTERNAL_CLOSE
```

Attribution must fail closed when any of these differ:

- account or venue;
- canonical instrument or gateway symbol;
- long/short position bucket;
- fill direction;
- remaining quantity;
- fill time after entry;
- one unique exchange order identity;
- one unique open Ticket.

If the exchange is flat while the old Runner_SL remains live, the lifecycle
stays blocked as `position_flat_with_live_protection_orders`. The existing
ticket-bound orphan cleanup path cancels only the PG-linked reduce-only
Runner_SL. No broad symbol-level cancel is allowed.

After no residual protection remains, the existing finalizer records:

```text
EXTERNAL_CLOSE fill
-> final_exit_detected
-> post-submit closure
-> budget settlement
-> one Live Outcome row
-> review and Owner notification
```

### A2. Scheduler correction

Add `runner_protected` to both:

- `MAINTAINABLE_LIFECYCLE_STATUSES`;
- `SNAPSHOT_STATUSES`.

The lifecycle timer must then select an open runner and call the complete
exchange snapshot provider. It must not perform an exchange write merely
because the runner is healthy.

### A3. Runner selection invariant

Replace arbitrary first-role lookup for `RUNNER_SL` with an explicit active
runner selector:

```text
same exit_protection_set_id
and role = RUNNER_SL
and status in submitted/open/partially_filled/cancel_pending/replace_pending
order by generation descending, created_at_ms descending
```

The selection must return exactly one active generation. Zero active runner
orders while the position remains open is protection degradation. More than one
active generation after the replacement grace window is a reconciliation
mismatch and may not be treated as healthy.

### A4. Release sequence

WP-A uses the ordinary deployment path after the current Ticket is closed:

```text
flat exchange position
-> no residual conditional order
-> lifecycle_closed
-> active_real_lifecycles = 0
-> existing deploy quiescence gate passes
-> release switch
-> postdeploy verifier
-> lifecycle timer read-only certification
```

No active-lifecycle bypass or one-off production source edit is introduced.

## WP-B: Versioned Structural Trailing Runner

### B1. Policy model

Add a typed, versioned trailing policy attached to the StrategyGroup/Event Spec
policy snapshot used by the Ticket. The immutable Ticket snapshot carries:

```text
trailing_policy_version
enabled
trail_timeframe
structure_window_bars
atr_period
atr_buffer_multiple
hard_tp2_enabled
```

All numeric calculations use `decimal.Decimal`. Missing or malformed trailing
policy blocks trailing activation but never removes the existing hard stop.
Current PG policy and the immutable Ticket snapshot are the only authority;
repository JSON/Markdown and runtime defaults are forbidden.

### B2. Deterministic trailing reference

The runner is evaluated only after TP1 and only once for each newly closed 15m
candle watermark.

For a long runner:

```text
structure_reference = min(low of last 3 fully closed 15m candles)
buffer = ATR(14) * 0.5
candidate_stop = structure_reference - buffer
effective_stop = max(current_runner_stop, candidate_stop)
```

For a short runner:

```text
structure_reference = max(high of last 3 fully closed 15m candles)
buffer = ATR(14) * 0.5
candidate_stop = structure_reference + buffer
effective_stop = min(current_runner_stop, candidate_stop)
```

The candidate is rounded to the venue price tick in the risk-conservative
direction. An update is emitted only when it improves the stop by at least one
price tick. The stop never moves away from profit protection.

The design deliberately does not force an immediate breakeven move. If the
closed-candle structure has not advanced enough, the exchange keeps the prior
Runner_SL. This preserves breakout breathing room while ensuring every later
accepted structural advance is locked monotonically.

### B3. Closed-candle source and cadence

The lifecycle service's 30-second tick performs a cheap PG watermark check.
It does not fetch OHLCV or create an audit row when no new 15m close exists.

On a new closed-candle watermark, one active runner may perform one bounded
public OHLCV read through the existing exchange gateway. The read must:

- request only the bounded candle count required for the 14-period ATR and
  3-bar structure;
- exclude the current unclosed candle;
- use the canonical Ticket instrument mapping;
- time out within the existing lifecycle service deadline;
- never run inside a long PG transaction;
- create no JSON/Markdown output.

The PG current projection stores the most recent evaluated candle watermark,
current high-water mark, current runner stop, policy version, and evaluation
result. Append-only lifecycle audit is written only when the stop changes or a
blocking contradiction appears.

### B4. Durable replacement protocol

Every accepted stop improvement creates a deterministic replacement generation
under the existing `brc_ticket_bound_exchange_commands` authority:

```text
ticket_id + protection_set_id + prior_runner_order_id
+ policy_version + closed_candle_watermark + normalized_stop_price
-> deterministic replacement generation
```

Replacement ordering is mandatory:

```text
prepare new reduce-only RUNNER_SL
-> dispatch and durably record exchange outcome
-> signed GET confirms new order open with exact identity/qty/side/trigger
-> mark prior runner cancel_pending
-> cancel prior PG-linked runner order
-> signed GET confirms exactly one active runner generation
-> mark prior replaced and new open
```

Repeated timer invocations reuse the same deterministic generation. They must
not create duplicate stops or duplicate cancellation commands.

### B5. Failure behavior

| Failure | Required result |
| --- | --- |
| Candle or ATR data unavailable/stale | Keep old exchange stop; record bounded runtime-data blocker |
| Candidate stop does not improve protection | No command and no audit growth |
| New stop placement rejected | Keep old stop live; lifecycle remains protected with replacement failure warning |
| New stop outcome unknown | Freeze further replacement and reconcile exact command identity |
| New stop confirmed but old cancel fails | Keep both reduce-only stops visible; retry only the PG-linked old cancel |
| Position closes during replacement | Stop replacement, attribute exact final fill, clean residual PG-linked order |
| Position remains open with no valid stop | `hard_safety_stop`; no new ENTRY or further strategy progression |
| More than one unexplained active runner generation | `runner_reconciliation_mismatch`; fail closed |

No failure path may cancel the last confirmed valid exchange stop before a new
one is proven.

### B6. TP2 semantics

`TP2` remains absent from the default SOR exit plan. The remaining quantity is
closed by the current trailing Runner_SL, an exact external close, or an
explicit future versioned policy. Generic legacy support for TP2 must not be
mistaken for a Ticket-bound SOR TP2 command.

## Data Model Direction

The implementation may add one PG current projection for the trailing policy
state and the minimum columns required to identify runner generations. It must
not create a second order ledger.

Recommended current projection identity:

```text
ticket_id + exit_protection_set_id
```

Required fields:

- `trailing_policy_version`;
- `last_evaluated_candle_close_ms`;
- `structure_reference_price`;
- `atr_value`;
- `candidate_stop_price`;
- `current_runner_order_id`;
- `current_runner_generation`;
- `current_runner_stop_price`;
- `status`;
- `first_blocker`;
- `updated_at_ms`.

Historical order generations remain in the existing exit-protection order and
exchange-command rows. The current projection only identifies the active
generation and latest evaluation truth.

## Owner-Facing Semantics

Owner surfaces use product language:

| Internal state | Owner meaning |
| --- | --- |
| `runner_protected` | TP1 completed; remaining position is protected and running |
| trailing candidate unchanged | Runner remains protected; no action needed |
| replacement confirmed | Profit protection moved in the favorable direction |
| temporary replacement failure with old stop live | Runner remains protected; system is retrying |
| no valid exchange stop | Protection unavailable; intervention required |
| final trailing stop fill | Remaining position exited; trade completed |

Raw command ids, proof packets, FinalGate, and Operation Layer names remain
developer/audit details.

## Testing Strategy

### WP-A regression matrix

- `runner_protected` is selected by the scheduler.
- Healthy runner causes complete exchange reads and zero exchange writes.
- Runner fill produces one `final_exit_detected` event.
- Manual exact close produces one `EXTERNAL_CLOSE` outcome.
- Flat position plus residual Runner_SL blocks closure until exact cleanup.
- Ambiguous quantity, direction, Ticket ownership, or conditional lineage fails
  closed.
- Repeated scheduler ticks do not duplicate lifecycle events or Live Outcome.

### WP-B domain matrix

- Long and short formulas use Decimal and closed candles only.
- An unclosed candle cannot move a stop.
- Candidate stop is monotonic and tick-normalized.
- A non-improving candidate produces no command.
- Missing ATR or insufficient candles keeps the old stop.
- Policy version is immutable for an existing Ticket.

### WP-B lifecycle matrix

- First replacement submits new before cancelling old.
- Repeated generation input is idempotent.
- New-place rejection leaves old stop live.
- Unknown new-place outcome freezes cancellation.
- Old-cancel failure leaves the confirmed new stop live and retries exact old
  identity only.
- Fill during replacement closes the lifecycle without a duplicate order.
- Multiple active runner generations are reconciled explicitly.
- No fixed TP2 exchange command is created.

### Release certification

- Directed unit and PG integration suites pass.
- Full unit suite passes.
- `scripts/audit_production_runtime_file_io.py` reports
  `performance_risk.status=clear`.
- Output artifact scope validation passes.
- Deploy dry-run contains the explicit venv Python path.
- Tokyo read-only preflight proves zero active lifecycle before WP-A deploy.
- Postdeploy verifies exact release head, migration head, service health,
  lifecycle timer cadence, and zero unexpected exchange writes.

## Cadence And Performance Impact

| Surface | Target impact |
| --- | --- |
| 30-second lifecycle tick | One cheap PG runner/watermark selection; no file output |
| OHLCV reads | At most one bounded read per active runner per new 15m close |
| PG current writes | One update per evaluated closed candle per active runner |
| Append-only audit growth | Only stop changes and blockers, not unchanged ticks |
| Exchange writes | Only monotonic accepted replacements and exact cleanup/finalization |
| Subprocess/API timeout | Must remain inside the lifecycle service global deadline |
| Disk/report growth | Zero recurring JSON/Markdown files |
| Archive behavior | Manual, Owner-scoped, and outside production cadence |

## Deployment And Rollback

### WP-A

Deploy only after the current Ticket is strictly closed. If pre-switch facts
show a position, residual protection, open lifecycle, critical command, or
domain hold, stop before switching.

If postdeploy verification fails, restore the prior release and service state.
The exchange must remain flat; rollback does not recreate the closed position.

### WP-B

WP-B is deployed disabled for already-created Tickets. A new versioned SOR
policy may enable it only for Tickets created after policy activation.

Rollback behavior for a live trailing Ticket is fail-closed:

- never cancel the current exchange-native stop merely because application
  rollback occurs;
- preserve the last confirmed runner order identity in PG;
- old code must not be reactivated if it cannot select the active generation;
- forward-fix or use an explicitly certified compatible release.

## Acceptance Criteria

WP-A is accepted when:

1. the current ETH Ticket is closed with exact exchange attribution;
2. no ETH position or residual PG-linked protection order remains;
3. budget, lifecycle, Live Outcome, and Owner notification agree;
4. `runner_protected` is continuously selected and exchange-read capable in
   production code;
5. the ordinary Tokyo deployment path passes without bypass.

WP-B is accepted when:

1. every active runner retains one confirmed exchange-native hard stop;
2. trailing evaluations occur only once per closed 15m watermark;
3. accepted stops move monotonically and use the Ticket's immutable policy;
4. replacement is durable, idempotent, and submit-new-before-cancel-old;
5. final fills close lifecycle, settle budget, and produce one Live Outcome;
6. no fixed TP2 is created by the default SOR policy;
7. production no-op ticks create zero files and no unchanged audit rows.

## Live Enablement Transition

```text
Before:
SOR-001 / ETHUSDT / long
post_submit_runner_protected
first_blocker = runner_protected_not_in_lifecycle_scheduler_scope

After WP-A:
current Ticket = lifecycle_closed
deployment interlock = clear
runner lifecycle monitoring capability = certified

After WP-B:
future SOR Ticket after TP1
-> runner_protected
-> structural trailing policy active
-> one exchange-native monotonic runner stop
-> final exit / settlement / review
```

## Stop Conditions

- Do not implement or deploy before Owner review of this written design.
- Do not modify the current live Runner_SL as part of WP-B.
- Stop recovery if manual-close attribution is ambiguous.
- Stop deployment if any real lifecycle remains open.
- Stop trailing replacement if the prior or new exchange order identity is
  unknown.
- Stop live activation if the versioned trailing policy is absent or differs
  from the Ticket snapshot.
- Do not expand symbol, side, profile, leverage, sizing, capital, withdrawal,
  transfer, or credential authority.
