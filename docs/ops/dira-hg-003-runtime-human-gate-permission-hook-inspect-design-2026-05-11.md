# DIRA-HG-003 — Runtime Human-Gate Permission Hook Inspect & Design

## 0. Boundary

This is a docs-only inspect and design document.

- No runtime code is modified.
- No implementation is authorized.
- No Claude task card is created.
- No adapter, backtest, parameter sweep, or experiment was run.
- No paper, testnet, live, small-live, or runtime activation is authorized.
- No LLM implementation is authorized.
- No automated decision-making is authorized.
- No Direction A entry, exit, stop, sizing, or risk parameter change is authorized.

The purpose is to inspect the current runtime signal-to-order path, design where a human-gate permission hook would be inserted, define its state model, specify fail-safe behavior, and identify what would change in a future implementation phase.

## 1. Current Runtime Signal-to-Order Path

The current Direction A signal would flow through this path (if Direction A were activated in runtime):

```
WebSocket K-line event
  -> SignalPipeline.process_kline()              [src/application/signal_pipeline.py]
    -> Strategy engine evaluates Donchian20 signal
    -> Risk calculation
    -> signal_executor(signal, strategy)
      -> ExecutionOrchestrator.execute_signal()  [src/application/execution_orchestrator.py:671]
        -> ExecutionIntent created (status: PENDING)
        -> Circuit breaker check                  [line 715]
        -> CapitalProtection.pre_order_check()    [line 731]
          -> Daily stats persistence check
          -> Balance fetch
          -> Price resolution
          -> Min-notional check
          -> Quantity precision check
          -> Price reasonability check
          -> Single-trade loss check
          -> Position limit check
          -> Daily loss check
          -> Daily count check
          -> Min balance check
          -> Returns OrderCheckResult (allowed: bool, reason: str, ...)
        -> If not allowed: intent -> BLOCKED, return
        -> If allowed: OrderLifecycleService.create_order()  [line 763]
        -> ExchangeGateway.place_order()                      [line 799]
        -> Backfill exchange_order_id, advance intent status
```

Key observations:

- The signal enters through `SignalPipeline` and reaches `ExecutionOrchestrator.execute_signal()`.
- There is currently **no human-gate layer** in this path.
- The only permission gate before order creation is `CapitalProtection.pre_order_check()`.
- `ExecutionIntent` already has a status lifecycle: `PENDING -> BLOCKED/SUBMITTED/PROTECTING/COMPLETED/FAILED`.
- Decision Trace v0 (ADR-0002) already captures risk decisions from `CapitalProtection.pre_order_check()` as `risk.pre_order_check` events.

## 2. Candidate Insertion Point for Human Gate

The natural insertion point is **inside `ExecutionOrchestrator.execute_signal()`, between the circuit-breaker check (line 715) and the `CapitalProtection.pre_order_check()` (line 731)**.

At this point:

- `ExecutionIntent` exists with status `PENDING`.
- The signal has passed the circuit breaker.
- No order has been created or submitted to the exchange.
- The human gate can inspect the signal and decide whether to allow or block the new entry.

Proposed position in the flow:

```
ExecutionOrchestrator.execute_signal()
  1. Create ExecutionIntent (PENDING)
  2. Circuit breaker check
  3. *** HUMAN GATE CHECK ***           <-- NEW: permission_layer.check(signal)
  4. CapitalProtection.pre_order_check()
  5. OrderLifecycleService.create_order()
  6. ExchangeGateway.place_order()
```

**Why this position and not elsewhere:**

- Before circuit breaker: wrong — the circuit breaker is a system-level safety gate that must remain unconditional. The human gate is a strategy-level permission layer that should not bypass system safety.
- After capital protection: wrong — capital protection is a risk gate that must run regardless of human gate state. The human gate should not prevent risk checks from running on allowed entries.
- After order creation: wrong — by then an order record exists, and blocking would leave orphan state.
- In `SignalPipeline`: wrong — the pipeline is strategy-agnostic and should not contain strategy-specific gating logic.

## 3. Should the Gate Be a New-Entry Permission Layer Only?

**Yes, explicitly.**

The human gate answers one question: "Is Direction A allowed to take new entries at this time?"

It does NOT:

- Block or modify exits (EMA60 lifecycle exit is unconditional).
- Block or modify stop-loss handling (initial stop is frozen).
- Block or modify partial exits (TP1, TP2, trailing stops).
- Modify position sizing.
- Allow manual position closure.
- Allow signal direction override.
- Allow timing override of individual trades.
- Modify risk parameters.
- Replace or bypass `CapitalProtection.pre_order_check()`.

The gate is a binary permission layer: new entries are either allowed or denied for the current Direction A state.

## 4. Explicit Non-Goals

The human-gate permission hook must NOT become:

| # | Non-goal | Why |
|---|---|---|
| 1 | Entry rewrite | Direction A entry rules (Donchian20 breakout) are frozen and unchanged. |
| 2 | Exit rewrite | EMA60 lifecycle exit is classified as PAYOFF_ENGINE. Modifying exits requires separate evidence. |
| 3 | Sizing change | Fixed notional unless separately authorized by Owner through a sizing spec. |
| 4 | Parameter change | All Direction A parameters are frozen. |
| 5 | Forced close | The gate must never force-close an existing position. |
| 6 | LLM runtime decision | The LLM provides manual briefing and devil's-advocate for the Owner's decision. It does not make or execute runtime decisions. |
| 7 | Strategy router | The gate is scoped to Direction A only. It does not route between strategies. |
| 8 | Portfolio allocator | The gate does not allocate across strategies or assets. |
| 9 | Regime engine | The gate does not include an automated regime classifier. |
| 10 | Automatic ON/OFF | The gate state is set by the Owner through the DIRA-HG-001 decision process. It does not auto-toggle. |

## 5. Gate State Model

| State | Meaning | New entries | Existing positions |
|---|---|---|---|
| `ON_ALLOWED` | Owner has completed the ON checklist. Direction A may take new entries per frozen rules. | Allowed | Lifecycle continues unchanged. |
| `ON_ALLOWED_SMALL` | Owner classifies conditions as constructive but fragile. This is a label only; it is NOT sizing approval. In fixed-notional mode, behaves identically to `ON_ALLOWED` unless the Owner separately authorizes a paper-mode sizing variant. | Allowed (no sizing change unless separately authorized) | Lifecycle continues unchanged. |
| `WAIT` | Owner has not completed a decision review, or evidence is mixed/event-risk-heavy. New entries blocked until next scheduled review. | Denied | Lifecycle continues unchanged. |
| `PAUSE_NEW_ENTRIES` | Owner has decided new entries should stop until a defined review condition is met. Existing positions are unaffected. | Denied | Lifecycle continues unchanged. |
| `TURN_OFF` | Owner has decided Direction A should be inactive. Broad hostile regime or shock risk. | Denied | Lifecycle continues unchanged. |

**States that require separate Owner authorization before runtime use:**

| State | Meaning | Requires |
|---|---|---|
| `ON_ALLOWED_SMALL` (as sizing) | Smaller position size for fragile conditions. | Separate paper/risk specification with approved sizing logic. |
| `REDUCE` | Reduce exposure for deteriorating conditions. | Separate paper/risk specification; must define what "reduce" means operationally. |

### State transitions:

```
              Owner ON decision
  WAIT/PAUSE ------------------> ON_ALLOWED / ON_ALLOWED_SMALL
              (logged checklist)

              Owner OFF decision
  ON_ALLOWED ------------------> TURN_OFF / PAUSE_NEW_ENTRIES / WAIT
              (logged checklist)

              Owner re-review
  TURN_OFF --------------------> WAIT (re-evaluation pending)
              (logged checklist)

              Owner re-enable
  WAIT ------------------------> ON_ALLOWED
              (logged checklist)

              Time passes, no review
  ON_ALLOWED -----(7+ days)----> WAIT (auto-stale, requires re-review)
```

### State is per-strategy, not per-signal:

The gate state applies to Direction A as a whole. Individual signals do not receive individual approval or denial. If `ON_ALLOWED` is active, every Direction A signal that passes circuit breaker and capital protection is allowed. If `PAUSE_NEW_ENTRIES` is active, every Direction A signal is denied at the gate.

## 6. Fail-Safe Behavior

The gate state may be missing, stale, unreadable, or conflicting. Fail-safe rules must be defined for each case:

| Condition | Fail-safe behavior | Rationale |
|---|---|---|
| Gate state file/store is missing | Deny new entries (`WAIT`). | When the gate state is unknown, the safe default is to block new entries. Existing positions continue via unchanged lifecycle. |
| Gate state is stale (last update > Owner-defined staleness threshold) | Deny new entries (`WAIT`). Log stale-state warning. | A stale gate state may not reflect current Owner judgment. The safe default is to require a fresh decision. |
| Gate state is unreadable (corrupt, parse error, I/O failure) | Deny new entries (`WAIT`). Log unreadable-state error. | Corrupt state is indistinguishable from unknown state. Block and alert. |
| Gate state is conflicting (e.g., both `ON_ALLOWED` and `TURN_OFF` are present) | Deny new entries (`WAIT`). Log conflict error. | Conflicting state is invalid. Block and require Owner resolution. |
| Gate state persistence is unavailable (database down, file locked) | Deny new entries (`DAILY_RISK_STATS_UNAVAILABLE` or `GATE_STATE_UNAVAILABLE`). | Consistent with existing LS-002b fail-closed pattern for daily risk stats persistence failure. |

**Core principle: fail-closed for new entries.** The human gate is a permission layer. If the permission state is unknown, the safe assumption is "permission not granted."

**Existing positions are never affected by gate-state failure.** The EMA60 lifecycle exit continues regardless.

## 7. Fail-Closed vs Fail-Open by Mode

| Mode | Fail-closed / fail-open for new entries | Rationale |
|---|---|---|
| **No-order rehearsal** | N/A | No orders are placed. The gate is purely observational. |
| **Paper** | **Fail-closed.** New entries blocked when gate state is unavailable, stale, or corrupt. | Paper mode has real signal-to-order flow. The safe default is to block unknown-state entries. |
| **Testnet** | **Fail-closed.** Same as paper. | Testnet has real order flow. Fail-closed prevents accidental unauthorized entries. |
| **Live** | **Fail-closed.** Same as paper and testnet, with stricter staleness and audit requirements. | Live mode has real capital at risk. Fail-closed is mandatory. No scenario justifies fail-open for new entries. |

**Fail-open is never appropriate for new entries.** A human gate that fails open is not a gate.

## 8. Decision Trace / Audit Logging Needs

The human gate must produce audit-traceable records compatible with Decision Trace v0 (ADR-0002).

### Trace events to emit:

| Event type | When | Payload |
|---|---|---|
| `risk.human_gate_check` | Every time `execute_signal()` reaches the gate check. | `gate_state`, `signal_id`, `symbol`, `decision` (allow/deny), `reason`, `state_last_updated`, `state_age_seconds`. |
| `risk.human_gate_state_change` | When Owner changes gate state via decision log. | `previous_state`, `new_state`, `decision_id`, `timestamp_utc`, `owner_thesis_summary`. |

### Non-goals for trace:

- Full decision-log content in trace metadata (the decision log is a separate manual artifact).
- LLM briefing content in trace.
- Portfolio or cross-strategy trace expansion.

### Trace failure policy:

Same as Decision Trace v0: trace writing failure must never block or change trading decisions. Trace is best-effort observability.

## 9. Persistence Needs

| Need | Requirement | Notes |
|---|---|---|
| Gate state | Must persist across runtime restarts. | Unlike LS-002 v0 in-memory stats, gate state must survive restart because it represents Owner judgment. |
| Gate state staleness | Must record timestamp of last state change. | Enables staleness detection. |
| Gate state history | Optional but recommended: append-only log of state changes. | Supports periodic review (R1-R4 from DIRA-HG-002). |
| Decision-log reference | Gate state change should reference a decision-log ID. | Links runtime state to the manual DIRA-HG-001 decision log. |

**Persistence technology:** To be determined in a future implementation note. Options include:
- PG table (consistent with LS-002b daily risk stats persistence pattern).
- File-based JSON (simpler but less robust).
- In-memory with PG backup (consistent with LS-002b v0 hybrid pattern).

The choice does not need to be made now. It should be made when a paper-mode implementation is authorized.

## 10. Paper vs Testnet vs Live Semantic Differences

| Dimension | Paper | Testnet | Live |
|---|---|---|---|
| **Orders** | Real orders on a designated paper-mode account or exchange subaccount. | Real orders on testnet exchange. | Real orders on live exchange. |
| **Capital** | Owner-designated paper capital. | Testnet virtual capital. | Real capital. |
| **Gate state** | Same state model. Owner decision process same. | Same state model. Same decision process. | Same state model. Same decision process. Stricter staleness and audit requirements. |
| **Fail-safe** | Fail-closed. | Fail-closed. | Fail-closed. |
| **Trace** | Required. | Required. | Required. Stricter audit expectations. |
| **Governance** | DIRA-HG-002 prerequisites must be met. | Separate approval required after paper. | Separate approval required after testnet. |
| **Activation** | Requires all DIRA-HG-002 prerequisites + Owner approval. | Requires paper evidence + separate Owner approval. | Requires testnet evidence + separate Owner approval. |

**Key principle:** The gate state model and fail-safe behavior are the same across paper/testnet/live. The difference is the capital and order-routing backend, and the governance bar for activation.

Paper is not a stepping stone to live. Each mode requires its own evidence and Owner approval.

## 11. Files to Inspect

For a future implementation, the following files would be inspected (NOT modified now):

| File | Role in inspect |
|---|---|
| `src/application/execution_orchestrator.py` | Contains `execute_signal()`. The insertion point for the gate check. |
| `src/application/capital_protection.py` | Contains `pre_order_check()`. The existing risk gate that runs after the human gate. Understanding the `OrderCheckResult` model informs the gate's own result model. |
| `src/domain/execution_intent.py` | Contains `ExecutionIntent` status lifecycle. A new `PENDING_APPROVAL` or `GATE_BLOCKED` status may be needed. |
| `src/domain/models.py` | Contains `SignalResult`, `OrderCheckResult`, and other domain models. |
| `src/application/decision_trace.py` | Contains `TraceEvent`, `TraceService`. The human gate trace events would use this backbone. |
| `src/infrastructure/jsonl_trace_sink.py` | The current trace sink. Human gate events would flow through this sink. |
| `src/application/signal_pipeline.py` | The signal pipeline that calls `execute_signal()`. Understanding the call context. |
| `src/main.py` | The runtime wiring. The gate service dependency would be wired here. |
| `docs/adr/0002-decision-trace-backbone-v0.md` | The ADR that defines trace semantics and extension rules. |

## 12. Files Likely to Change Later (Do Not Change Now)

| File | Future change |
|---|---|
| `src/application/execution_orchestrator.py` | Insert human gate check call between circuit breaker and `pre_order_check()`. |
| `src/domain/execution_intent.py` | Possibly add `GATE_BLOCKED` status to intent lifecycle. |
| `src/domain/models.py` | Possibly add `GateCheckResult` model (analogous to `OrderCheckResult`). |
| `src/application/human_gate_service.py` | New file: manages gate state, checks, and state transitions. |
| `src/infrastructure/gate_state_repository.py` | New file: persistence layer for gate state. |
| `src/application/decision_trace.py` | Extend with `risk.human_gate_check` and `risk.human_gate_state_change` event types. |
| `src/main.py` | Wire `HumanGateService` into `ExecutionOrchestrator`. |
| Tests | New tests for gate check logic, state transitions, fail-safe behavior, and trace emission. |

**All of these changes require future Owner authorization and Codex task cards.**

## 13. Risks and Stop Points Requiring Owner Decision

| # | Risk / Stop point | Severity | Owner decision needed |
|---|---|---|---|
| 1 | Gate state model is designed but not implemented. No evidence that the runtime gate check works correctly under fault conditions. | MODERATE | Owner must decide when implementation is warranted (after paper-mode prerequisites are met). |
| 2 | The `ExecutionIntent` status model may need a new `GATE_BLOCKED` status, which affects the existing lifecycle. This is a cross-core change. | MODERATE | Owner/Codex must decide whether to add `GATE_BLOCKED` or reuse `BLOCKED` with a reason code. |
| 3 | Gate state persistence technology is not chosen. PG, file-based, or hybrid each have tradeoffs. | LOW | Owner decides when a paper-mode implementation is authorized. |
| 4 | Staleness threshold is not defined. "How old is too old for a gate state?" requires Owner judgment. | MODERATE | Owner defines the threshold (e.g., 24h, 48h, 7d) based on review cadence. |
| 5 | The human gate adds latency to the signal-to-order path. For a 4h Donchian20 system, latency is not meaningful, but the pattern should be documented. | LOW | No action needed now. |
| 6 | If Direction A is eventually activated in runtime, the human gate becomes a critical-path dependency. Its failure mode (fail-closed) means the system will stop taking Direction A entries if the gate service is down. This is the intended behavior, but Owner must accept it. | MODERATE | Owner must accept fail-closed semantics for live mode. |
| 7 | `ON_ALLOWED_SMALL` and `REDUCE` are designed as labels only in this spec. If they ever become operational sizing states, a separate sizing spec is required. | MODERATE | Owner must not conflate label states with operational sizing without a separate spec. |

## 14. Risk Triage

| Item | Severity | Treatment |
|---|---|---|
| No implementation authorized | SUFFICIENT | This is an inspect/design document. No code change is expected. |
| Insertion point is architecturally clean | SUFFICIENT | Between circuit breaker and capital protection; does not bypass any existing safety layer. |
| Fail-closed default is consistent with existing safety model | SUFFICIENT | Matches LS-002b daily risk stats persistence failure behavior. |
| `ExecutionIntent` status model may need extension | MODERATE | Requires Owner/Codex decision on whether to add `GATE_BLOCKED` or reuse `BLOCKED`. Stop point for implementation. |
| Gate state persistence technology not chosen | LOW | Deferred until paper-mode implementation is authorized. |
| Staleness threshold not defined | MODERATE | Requires Owner input before implementation. |
| Decision Trace extension is feasible but not implemented | SUFFICIENT | Trace extension follows established ADR-0002 rules. |
| Live-mode fail-closed acceptance | MODERATE | Owner must explicitly accept that live-mode gate failure blocks all Direction A entries. |

No `BLOCKER` is identified for this inspect/design document.

DIRA-HG-003 is sufficient for Owner review.

## 15. Minimum Next Step

1. Owner reviews DIRA-HG-003 as a docs-only inspect/design document.
2. Owner confirms or adjusts the insertion point (Section 2).
3. Owner confirms or adjusts the gate state model (Section 5).
4. Owner decides on `GATE_BLOCKED` vs `BLOCKED` + reason code for `ExecutionIntent` (Risk #2).
5. Owner defines the staleness threshold (Risk #4).
6. Owner accepts or rejects fail-closed semantics for live mode (Risk #6).
7. After DIRA-HG-002 prerequisites are met (rehearsal logs, metric resolution, paper object choice), Owner may authorize a paper-mode implementation task card through Codex.

## 16. What Not To Do

- Do not implement the human gate.
- Do not modify `execution_orchestrator.py`, `capital_protection.py`, or any core file.
- Do not create a Claude task card.
- Do not choose persistence technology now.
- Do not add `ON_ALLOWED_SMALL` or `REDUCE` sizing logic.
- Do not implement LLM runtime decision-making.
- Do not expand the gate to exits, stops, sizing, or risk parameters.
- Do not treat this design as approval for paper/testnet/live.
- Do not start implementation before DIRA-HG-002 prerequisites are met.
- Do not let the gate design become a broad strategy router or portfolio system.
