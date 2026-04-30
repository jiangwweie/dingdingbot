# ADR-0002 Decision Trace Backbone v0

## Status

Accepted

## Context

The system needs lifecycle decision traceability because the project is now developed and evolved with AI-agent assistance, while also moving through live-safe hardening.

This creates several practical needs:

- AI-agent generated code increases the need for explainable runtime behavior.
- Live-safe work needs auditable risk and execution decisions.
- The owner needs to understand why the runtime allowed, rejected, or skipped a meaningful action.
- Structured trace events are preferable to scattered free-text logs when the goal is later replay, explanation, review, or UI presentation.

The immediate gap was not the absence of all logging. The gap was the absence of a minimal, stable, structured shape for recording lifecycle decisions.

At the same time, the project was not ready to build a full audit platform, event-sourcing model, or trace UI. The first step needed to be narrow, low-risk, and non-invasive.

## Decision

Decision Trace Backbone v0 introduces a minimal structured trace backbone with the following parts:

- `TraceEvent` model in [decision_trace.py](/Users/jiangwei/Documents/final/src/application/decision_trace.py)
- `TraceSink` abstraction in the same module
- `TraceService` as a best-effort fan-out wrapper over sinks
- `JsonlTraceSink` in [jsonl_trace_sink.py](/Users/jiangwei/Documents/final/src/infrastructure/jsonl_trace_sink.py)
- minimal runtime sink wiring in [main.py](/Users/jiangwei/Documents/final/src/main.py) and [api.py](/Users/jiangwei/Documents/final/src/interfaces/api.py)
- one first vertical slice in [capital_protection.py](/Users/jiangwei/Documents/final/src/application/capital_protection.py), where `CapitalProtectionManager.pre_order_check()` emits a risk decision trace event

The current sink writes JSONL to:

- `logs/runtime/risk_decision.jsonl`

The current vertical slice is intentionally narrow:

- a `RISK_DECISION` style event represented today by `event_type="risk.pre_order_check"`
- emitted only from the selected capital protection pre-order path

Tests exist for:

- `TraceEvent` and `TraceService` behavior in [test_decision_trace.py](/Users/jiangwei/Documents/final/tests/unit/test_decision_trace.py)
- JSONL sink output shape in the same test file
- `CapitalProtectionManager` trace emission in [test_capital_protection_trace.py](/Users/jiangwei/Documents/final/tests/unit/test_capital_protection_trace.py)

## Semantics

The current event envelope uses these fields:

### `trace_id`

`trace_id` is the identifier for one emitted trace event.

In v0 it is generated as a random UUID-like hex string. It should be treated as the unique id of the event record itself, not yet as a cross-event correlation id.

This semantic is stable enough for event identity, but still provisional regarding future correlation rules.

### `lifecycle_id`

`lifecycle_id` identifies the logical lifecycle context in which the event was emitted.

In the current capital protection slice, it is built as:

- `capital_protection:{symbol}:{order_type}:{timestamp_ms}`

In v0 this is a practical correlation handle, not yet a globally standardized lifecycle model across signal, risk, execution, and reconciliation.

Its exact generation rules are provisional in v0, but the concept is not: it is the field meant to connect related lifecycle events later.

### `event_type`

`event_type` names the kind of decision event.

In v0 the active value is:

- `risk.pre_order_check`

This is the stable semantic entry point for the current slice. The concrete set of event types is intentionally tiny in v0.

### `decision`

`decision` records the outcome of the lifecycle decision.

In the current slice it is emitted as:

- `allow`
- `deny`

The field is intended to stay outcome-oriented rather than implementation-oriented.

### `reason`

`reason` records the primary structured reason code for the decision.

In the current slice this is taken from `OrderCheckResult.reason`, for example:

- `DAILY_LOSS_LIMIT`
- `POSITION_LIMIT`
- `MISSING_PRICE`

It may be `None` when the decision is an allow path with no rejection code.

### `metadata`

`metadata` carries bounded, structured explanatory context for the decision.

In the current slice it includes explanatory fields such as:

- `symbol`
- `order_type`
- `amount`
- `price`
- `effective_price`
- `trigger_price`
- `stop_loss`
- `reason_message`
- check booleans under `checks`

In v0, metadata is intentionally flexible but must remain bounded and explanation-oriented. It is not a dump of arbitrary runtime state.

### `config_hash`

`config_hash` records the resolved runtime configuration hash when available.

In the main runtime wiring, it is passed from the resolved runtime config provider when present. In standalone API lifespan wiring, it may be absent.

This field is important for replay and attribution, but v0 does not yet guarantee universal availability across every caller.

## Current Scope

v0 covers only one selected trace slice:

- risk decision trace events emitted from the capital protection pre-order decision path

This means v0 does not attempt to cover the full lifecycle. It establishes the minimum common event format and one real call site, nothing more.

## Non-goals

Decision Trace Backbone v0 does not implement:

- a full audit platform
- event sourcing
- a frontend trace viewer
- PostgreSQL trace persistence
- strategy decision tracing
- execution or order lifecycle tracing beyond the current slice
- Regime, Portfolio, Multi-strategy, or Data Feature abstractions
- any change to trading behavior

It also does not redefine risk semantics, execution semantics, or runtime profile behavior.

## Failure Policy

Trace writing failures must never affect trading decisions.

Trace in v0 is best-effort observability, not a runtime dependency.

This is enforced through `TraceService.emit()`, which catches sink exceptions and downgrades them to warnings instead of allowing them to change the decision path.

The consequence is deliberate:

- trace may be incomplete under failure
- trading behavior must remain unchanged under failure

## Safety Boundaries

Decision Trace Backbone v0 must remain inside these boundaries:

- no strategy logic changes
- no risk rule changes
- no runtime profile changes
- no sensitive secret dumping into metadata
- metadata should remain explanatory, structured, and bounded

The trace layer should explain a decision, not become an uncontrolled shadow state channel.

## Future Extension Rules

Future trace extensions should only be added when tied to a concrete lifecycle decision point, such as:

- signal decision
- risk rejection
- execution intent creation
- order status update
- protection order creation or failure
- position close
- reconciliation mismatch

Each extension should follow these rules:

- tie the trace to a real lifecycle decision or state transition
- keep the call site non-invasive
- avoid changing trading behavior
- keep failure policy best-effort and non-blocking
- include focused tests
- preserve semantic stability of existing fields

Trace should grow by meaningful vertical slices, not by spraying generic logs into unrelated code paths.

## Consequences

### Positive

- establishes a common trace format
- supports live-safe observability
- supports future frontend explanation
- supports agent and code review
- creates a concrete base for later lifecycle trace expansion

### Tradeoffs

- JSONL is simple, but not query-optimized
- v0 coverage is intentionally narrow
- semantics must be kept stable or the trace layer will degrade into generic logs

### Constraints Going Forward

- keep v0 semantics stable unless there is an explicit migration decision
- do not widen scope just because the trace backbone now exists
- add new trace slices only when justified by a concrete lifecycle need
