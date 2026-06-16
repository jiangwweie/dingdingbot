# CLAUDE-AUDIT-002 Runtime Safety Red-Team Audit

**Date:** 2026-06-16
**Scope:** StrategyGroup runtime path — read-only audit
**Branch:** codex/owner-runtime-console-v1

---

## Executive Summary

The StrategyGroup runtime path implements a layered defense-in-depth model with
multiple independent safety gates. The architecture is sound: domain models enforce
structural invariants (shadow_mode, execution_enabled, boundary constraints),
application services re-check conditions at confirm time, and forbidden operation
types are hard-blocked. The post-submit finalize packet uses Pydantic literal-type
validation to prevent execution metadata leakage.

**Key finding:** The FinalGate preview service and the actual ExecutionOrchestrator
execution path are architecturally decoupled. The FinalGate preview is
inspection-only; the ExecutionOrchestrator has its own independent guard chain
(CapitalProtection, GlobalKillSwitch, StartupTradingGuard, AccountRiskService,
CampaignStateService). This means a FinalGate PASS verdict does not automatically
grant execution authority — which is correct by design — but also means a FinalGate
BLOCK can be bypassed if the ExecutionOrchestrator's guards are satisfied. The
Operation Layer's `_confirm_failure_reason` re-checks readiness at confirm time,
providing a second line of defense.

**Overall risk level:** LOW-MEDIUM. No hard bypass found. Several areas warrant
monitoring and targeted test coverage.

---

## Safety Invariants Checked

| # | Invariant | Status |
|---|-----------|--------|
| 1 | FinalGate bypass | ✅ No bypass found — preview is inspection-only; execution path has independent guards |
| 2 | Operation Layer bypass | ✅ No bypass found — `_confirm_failure_reason` re-checks all conditions |
| 3 | Stale fact execution | ⚠️ Partial gap — `stale_fact_behavior_confirmed` is informational; `_account_facts_unavailable_reason` does not check freshness |
| 4 | Missing protection execution | ⚠️ Partial gap — FinalGate checks reference presence, not exchange-side confirmation |
| 5 | Duplicate submit risk | ⚠️ Partial gap — idempotency repository can be None in degraded mode |
| 6 | Conflicting active position | ✅ Guarded — FinalGate blocks when count >= max; Operation Layer re-checks market drift |
| 7 | Post-submit finalize / reconciliation / budget settlement | ✅ Strong — literal-type validation prevents metadata leakage; authorization frozen as replay-only |
| 8 | Chat confirmation blocker reintroduction | ✅ No reintroduction found — standing authorization enforced; confirmation_phrase limited to admission/activation |

---

## Findings Table

### Finding 1: Stale Fact Freshness Not Checked in Operation Layer Confirmation Path

| Field | Value |
|-------|-------|
| **Severity** | MEDIUM |
| **Invariant** | stale_fact_execution |
| **File** | `src/application/brc_operation_layer.py:6793-6821` |
| **Code Path** | `_account_facts_unavailable_reason()` → `_confirm_failure_reason()` |
| **Risk** | If account facts are marked "stale" but not "unavailable", the Operation Layer confirmation path will not block execution. The function checks `source == "unavailable"` and `truth_level == "unavailable"` but does not check `freshness == "stale"`. |
| **Evidence** | `_account_facts_unavailable_reason` at line 6793 only checks `source` and `truth_level` for "unavailable", and `reconciliation_status` for "mismatch". A stale-but-not-unavailable fact source passes through. |
| **Existing Guard** | `ExecutionPermissionResolver._account_facts_permission` at line 231 checks `freshness in {"stale", "expired", "too_old"}` and blocks. But this is only called for `record_trial_trade_intent_from_signal_evaluation` operations, not for all Operation Layer operations. |
| **Gap** | Operations like `create_gated_trial_from_admission`, `create_campaign_from_admission_binding`, etc. use `_account_facts_unavailable_reason` which does not check freshness. |
| **Recommended Test/Fix** | Add `freshness` check to `_account_facts_unavailable_reason`: `if freshness in {"stale", "expired", "too_old"}: return "account facts stale"`. Add unit test: stale facts → confirmation blocked. |

### Finding 2: FinalGate Preview and ExecutionOrchestrator Guard Chain Are Decoupled

| Field | Value |
|-------|-------|
| **Severity** | LOW |
| **Invariant** | FinalGate_bypass |
| **File** | `src/application/runtime_final_gate_preview_service.py` + `src/application/execution_orchestrator.py:1075` |
| **Code Path** | `RuntimeFinalGatePreviewService.preview()` ↔ `ExecutionOrchestrator.execute_signal()` |
| **Risk** | The FinalGate preview checks (runtime status, shadow flags, attempts, budget, symbol, side, leverage, margin, liquidation buffer, active positions, protection, review) are not called by the ExecutionOrchestrator. The ExecutionOrchestrator has its own guard chain (BRC permission, startup guard, GKS, circuit breaker, account risk, campaign state, capital protection). A candidate could pass ExecutionOrchestrator guards while failing FinalGate checks (e.g., leverage exceeds boundary). |
| **Evidence** | `ExecutionOrchestrator.execute_signal()` at line 1075 checks BRC permission, startup guard, GKS, circuit breaker, protection health, account risk, and campaign state — but does not call `RuntimeFinalGatePreviewService`. The FinalGate preview is used only for inspection/dry-run purposes. |
| **Existing Guard** | The Operation Layer's `_confirm_failure_reason` re-reads readiness data at confirm time. The `record_trial_trade_intent_from_signal_evaluation` path resolves execution permission with runtime safety readiness. The FinalGate preview is available as a pre-flight check surface. |
| **Gap** | There is no enforcement that FinalGate preview must PASS before ExecutionOrchestrator proceeds. The two systems are independent by design, but this means boundary checks (leverage, margin, liquidation buffer, symbol/side) in FinalGate are not enforced in the actual execution path. |
| **Recommended Test/Fix** | Document the architectural decision. Add integration test: candidate with leverage exceeding runtime boundary → verify ExecutionOrchestrator blocks via capital_protection or other guard. Consider adding a FinalGate-aware guard to ExecutionOrchestrator for defense-in-depth. |

### Finding 3: `stale_fact_behavior_confirmed` Is Informational Only

| Field | Value |
|-------|-------|
| **Severity** | LOW |
| **Invariant** | stale_fact_execution |
| **File** | `src/domain/strategy_runtime_promotion_gate.py:68` |
| **Code Path** | `RuntimeExecutionConfirmationFacts.stale_fact_behavior_confirmed` |
| **Risk** | The `stale_fact_behavior_confirmed` field in `RuntimeExecutionConfirmationFacts` defaults to `False`. It is checked during promotion gate evaluation but does not appear to be enforced as a hard blocker in the runtime execution path. A runtime could be promoted without this confirmation. |
| **Evidence** | `stale_fact_behavior_confirmed: bool = False` at line 68. The promotion gate checks this field but the enforcement path is through the promotion gate status, not through the runtime execution path itself. |
| **Existing Guard** | The promotion gate status must be `READY_FOR_*` before promotion. The `StrategyRuntimeLiveEnablementPreview` checks promotion gate status. |
| **Gap** | If the promotion gate is bypassed or the runtime is created directly (e.g., via bootstrap script), `stale_fact_behavior_confirmed` remains False without blocking execution. |
| **Recommended Test/Fix** | Verify that `stale_fact_behavior_confirmed=False` blocks promotion gate status. Add test: promotion gate with stale_fact_behavior_confirmed=False → BLOCKED. |

### Finding 4: Idempotency Repository Can Be None

| Field | Value |
|-------|-------|
| **Severity** | MEDIUM |
| **Invariant** | duplicate_submit_risk |
| **File** | `src/application/runtime_execution_intent_adapter_service.py:724` |
| **Code Path** | `RuntimeExecutionIntentAdapterService._submit_idempotency_repository` |
| **Risk** | The submit idempotency repository is optional. When `None`, the `record_submit_idempotency_snapshot_for_authorization` method returns a blocker warning but does not block execution. This means in degraded mode (no PG), duplicate submit protection is weakened. |
| **Evidence** | At line 911-913: `if self._submit_idempotency_repository is None: blockers.append("runtime_execution_submit_idempotency_repository_unavailable")`. The blocker is appended but the method still returns a snapshot (with `status=BLOCKED`), which may or may not block the caller depending on how it handles the status. |
| **Existing Guard** | The Operation Layer's idempotency_key check at line 3817 prevents re-confirmation with a different key. The `_confirm_failure_reason` checks operation status. |
| **Gap** | Without PG-backed idempotency, rapid duplicate submissions within the same session could bypass protection if the in-memory state is not yet updated. |
| **Recommended Test/Fix** | Add integration test: submit idempotency repository unavailable → verify execution is blocked (not just warned). Document the degraded-mode behavior. |

### Finding 5: Active Positions Count Can Be None in FinalGate

| Field | Value |
|-------|-------|
| **Severity** | LOW |
| **Invariant** | conflicting_active_position |
| **File** | `src/application/runtime_final_gate_preview_service.py:544-568` |
| **Code Path** | `_check_active_positions()` |
| **Risk** | When `active_positions_count` is `None`, the FinalGate correctly blocks with `active_positions_count_not_available`. However, when the count comes from `_local_active_positions_count`, it reads from `self._active_position_source.list_active()` which may return stale data if the local position projection is behind the exchange. |
| **Evidence** | At line 93-101: `_local_active_positions_count` catches all exceptions and returns `None` (which blocks). The source is `local_position_projection` which may lag behind exchange state. |
| **Existing Guard** | The FinalGate blocks when count is None. The Operation Layer's `_critical_market_drift` checks `active_position_count` changes between preflight and confirm. |
| **Gap** | If local projection shows 0 active positions but exchange has 1 (due to lag), the FinalGate could allow a new entry that creates a conflicting position. |
| **Recommended Test/Fix** | The `_critical_market_drift` re-check at confirm time mitigates this. Add test: local projection stale → verify market drift check catches it at confirm time. |

### Finding 6: `_execute_no_safe_executor` Returns noop Instead of Block

| Field | Value |
|-------|-------|
| **Severity** | LOW |
| **Invariant** | Operation_Layer_bypass |
| **File** | `src/application/brc_operation_layer.py:1793-1811` |
| **Code Path** | `_execute_no_safe_executor()` |
| **Risk** | When an operation type has no safe executor wired, `_execute_no_safe_executor` returns `status="noop"` instead of `status="blocked"`. This means the operation is recorded as terminal (noop is in `_TERMINAL_STATUSES`) without indicating a safety concern. |
| **Evidence** | At line 1799: `status="noop"`. The result_summary says "No safe Operation executor is wired; no mutation was performed." |
| **Existing Guard** | The `_confirm_failure_reason` checks `not policy.executable_through_operation and not policy.dry_run_only` at line 3826, which blocks non-executable operations before they reach `_execute`. |
| **Gap** | If a new operation type is added to the registry with `executable_through_operation=True` but no executor is wired, it would pass `_confirm_failure_reason` and then silently noop. |
| **Recommended Test/Fix** | Change `_execute_no_safe_executor` to return `status="blocked"` with `blocked_reason="no safe executor wired"`. Add test: operation with `executable_through_operation=True` but no executor → blocked. |

### Finding 7: Protection Reference Presence ≠ Exchange-Side Confirmation

| Field | Value |
|-------|-------|
| **Severity** | MEDIUM |
| **Invariant** | missing_protection_execution |
| **File** | `src/application/runtime_final_gate_preview_service.py:570-604` |
| **Code Path** | `_check_protection()` |
| **Risk** | The FinalGate protection check verifies that `protection_preview.stop_reference` or `stop_price_reference` or `take_profit_references` exists. This is a candidate-level check, not an exchange-side confirmation. A protection order could be specified in the candidate but fail to place on the exchange. |
| **Evidence** | At line 577-581: `reference_present = bool(protection.stop_reference or protection.stop_price_reference is not None or protection.take_profit_references)`. This checks the candidate snapshot, not exchange state. |
| **Existing Guard** | `ExecutionOrchestrator._confirm_sl_order_or_fail_safe` at line 986 confirms SL exists on exchange before treating position as protected. The `_protect_filled_entry` mounts protection after ENTRY fill. |
| **Gap** | The FinalGate preview could show PASS for protection while the actual exchange-side protection placement fails. The ExecutionOrchestrator handles this correctly, but the FinalGate preview gives a false sense of safety. |
| **Recommended Test/Fix** | Document that FinalGate protection check is candidate-level only. Add test: FinalGate PASS with protection reference → exchange protection placement fails → verify ExecutionOrchestrator handles correctly. |

---

## No-Issue Areas Checked

| Area | Files Checked | Status |
|------|--------------|--------|
| **Withdrawal/Transfer blocking** | `brc_operation_layer.py:64-65, 6834-6843` | ✅ `_FORBIDDEN_OPERATION_TYPES` hard-blocks `withdrawal`, `transfer`, `live_execution`, `llm_direct_execution` |
| **Shadow mode enforcement** | `strategy_runtime.py:174-194` | ✅ Pydantic model_validator prevents `execution_enabled=True` with `shadow_mode=True`; requires live enablement metadata |
| **Runtime status transitions** | `strategy_runtime.py:40-76` | ✅ `ALLOWED_RUNTIME_TRANSITIONS` is a strict allowlist; terminal statuses cannot transition |
| **Budget boundary enforcement** | `runtime_final_gate_preview_service.py:246-309` | ✅ Blocks when `intended > max_notional_per_attempt` or `reservation > budget_remaining` |
| **Symbol/Side boundary** | `runtime_final_gate_preview_service.py:311-345` | ✅ Blocks when candidate symbol/side outside runtime boundary |
| **Leverage/Margin boundary** | `runtime_final_gate_preview_service.py:347-437` | ✅ Blocks when leverage exceeds max or margin exceeds cap |
| **Liquidation buffer** | `runtime_final_gate_preview_service.py:439-542` | ✅ Blocks when buffer below minimum; checks directional buffer |
| **Audit ID completeness** | `runtime_final_gate_preview_service.py:627-671` | ✅ Blocks when audit IDs incomplete or mismatched |
| **Post-submit finalize metadata** | `runtime_post_submit_finalize.py:395-412` | ✅ `_reject_forbidden_metadata_fields` blocks execution fields in finalize packet |
| **Authorization frozen as replay-only** | `runtime_post_submit_finalize.py:96-98` | ✅ `consumed_authorization_replay_only=True`, `old_authorization_submit_retry_allowed=False` |
| **Next-attempt gate validation** | `runtime_post_submit_finalize.py:63-72` | ✅ Pydantic validator ensures blocked gate has blockers; ready gate has no blockers and requires active-position fact |
| **Startup trading guard** | `execution_orchestrator.py:1143-1172` | ✅ Blocks new entries until explicitly armed |
| **Global kill switch** | `execution_orchestrator.py:1175-1201` | ✅ Blocks new entries when active |
| **Circuit breaker** | `execution_orchestrator.py:1203-1237` | ✅ Blocks new entries for blocked symbols |
| **Account risk service** | `execution_orchestrator.py:1239-1259` | ✅ Blocks when `allowed_new_entry=False` |
| **Campaign state service** | `execution_orchestrator.py:1261-1274` | ✅ Blocks when `allowed_new_entry=False` |
| **Capital protection pre-order check** | `capital_protection.py:176+` | ✅ Checks min notional, price deviation, single loss, position size, daily loss, trade count, min balance |
| **Reconciliation read-model** | `reconciliation.py:169-198` | ✅ Report-only path; does not mutate runtime state |
| **Startup reconciliation** | `startup_reconciliation_service.py` | ✅ Reconciles local vs exchange state at startup |
| **Bootstrap script boundaries** | `bootstrap_strategygroup_runtime_pilot.py:57-63` | ✅ `FORBIDDEN_EFFECT_FLAGS` blocks order/intent/withdrawal/transfer creation |
| **BRC execution permission resolver** | `execution_permission.py:101-193` | ✅ Takes minimum of all contributors; stale facts block at `SIGNAL_ONLY` |
| **Operation Layer re-check at confirm** | `brc_operation_layer.py:3804-3997` | ✅ `_confirm_failure_reason` re-checks readiness, market drift, account facts, forbidden types |

---

## Recommended Codex Task Cards

### Task 1: Add Freshness Check to `_account_facts_unavailable_reason`

**Priority:** P1
**Goal:** Block Operation Layer confirmation when account facts are stale.
**Why:** The `_account_facts_unavailable_reason` function does not check `freshness`, allowing stale facts to pass through while `ExecutionPermissionResolver` correctly blocks them for intent recording operations.
**Allowed files:** `src/application/brc_operation_layer.py`
**Tests:** Unit test: stale facts → `_account_facts_unavailable_reason` returns non-None. Integration test: Operation Layer confirm with stale facts → blocked.

### Task 2: Add FinalGate-Aware Guard to ExecutionOrchestrator

**Priority:** P2
**Goal:** Enforce FinalGate boundary checks (leverage, margin, liquidation buffer) in the ExecutionOrchestrator execution path.
**Why:** The FinalGate preview and ExecutionOrchestrator are decoupled. Boundary checks like leverage/margin/liquidation buffer are only in FinalGate, not in the ExecutionOrchestrator guard chain.
**Allowed files:** `src/application/execution_orchestrator.py`
**Tests:** Integration test: candidate with leverage exceeding runtime boundary → ExecutionOrchestrator blocks.

### Task 3: Enforce `stale_fact_behavior_confirmed` in Promotion Gate

**Priority:** P2
**Goal:** Ensure `stale_fact_behavior_confirmed=False` blocks promotion gate status.
**Why:** The field defaults to False and may not be enforced as a hard blocker.
**Allowed files:** `src/domain/strategy_runtime_promotion_gate.py`
**Tests:** Unit test: promotion gate with stale_fact_behavior_confirmed=False → BLOCKED.

### Task 4: Block Execution When Idempotency Repository Unavailable

**Priority:** P1
**Goal:** Ensure duplicate submit protection is enforced even in degraded mode.
**Why:** When `submit_idempotency_repository` is None, the system appends a blocker warning but may not block execution.
**Allowed files:** `src/application/runtime_execution_intent_adapter_service.py`
**Tests:** Integration test: idempotency repository unavailable → submit blocked.

### Task 5: Change `_execute_no_safe_executor` to Block Status

**Priority:** P2
**Goal:** Return `status="blocked"` instead of `status="noop"` when no safe executor is wired.
**Why:** A noop status for a missing executor could mask a configuration error.
**Allowed files:** `src/application/brc_operation_layer.py`
**Tests:** Unit test: operation with no executor → blocked status.

---

## Hard Stops / Unknowns

1. **ExecutionOrchestrator is a Codex-owned core file.** Changes to it require explicit Codex task card authorization.
2. **The FinalGate preview and ExecutionOrchestrator decoupling appears intentional** — the FinalGate is a governance/audit surface, not an execution gate. This should be confirmed with Codex before adding enforcement.
3. **The `stale_fact_behavior_confirmed` enforcement path was not fully traced** — it may be enforced through the promotion gate status chain in a way not visible from the domain model alone.
4. **The idempotency repository degraded-mode behavior** depends on how callers handle `status=BLOCKED` return values — this was not fully traced.
5. **No test files were modified** per the task card constraints. All recommended tests are for Codex to issue as follow-up tasks.

---

*Report generated by CLAUDE-AUDIT-002. Read-only audit — no files modified.*
