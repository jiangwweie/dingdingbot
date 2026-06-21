# CLAUDE-FINAL-TESTCARDS-004 Runtime Safety Test Cards

Generated: 2026-06-17
Source: CLAUDE-AUDIT-002 + CLAUDE-TEST-MAP-001 + CLAUDE-FINAL-TASKPACK-003
Mode: task card refinement — no implementation

---

## Summary

This report converts runtime safety audit findings and test coverage gaps into
7 actionable P1 test task cards. Each card is scoped to a specific safety
invariant or coverage gap identified in the red-team audit and test coverage
matrix. Cards are split into two categories:

- **Codex-Owned Source Change Cards (4):** Require source changes in Codex-owned
  files; Claude writes tests only after Codex lands the fix.
- **Tests-Only Cards (3):** Pure test additions; no source changes needed.

All cards are post-acceptance P1 — dispatch after mainline acceptance and
live-test close.

---

## Dispatch Boundary

| Condition | Action |
|---|---|
| Mainline acceptance not complete | Do not dispatch any card |
| Live-test not closed | Do not dispatch any card |
| Codex source change not landed (for Codex-Owned cards) | Write test first; test MUST FAIL until Codex fix lands |
| `live-config.env` or `.env*` present in Allowed files | Reject card — never allowed |
| Exchange gateway or credentials in Allowed files | Reject card — never allowed |

---

## P1 Test Cards

### Codex-Owned Source Change Cards

These cards require a source-level fix in a Codex-owned file. Claude writes the
test first (expected to fail), then Codex lands the fix. The test becomes the
acceptance gate for the fix.

---

#### TESTCARD-001: Stale Facts Confirmation Blocking

| Field | Value |
|---|---|
| **Task ID** | TESTCARD-001 |
| **Goal** | Verify that `_account_facts_unavailable_reason` blocks Operation Layer confirmation when account facts have `freshness in {"stale", "expired", "too_old"}` |
| **Why** | Audit Finding 1 (MEDIUM): `_account_facts_unavailable_reason` checks `source == "unavailable"` and `truth_level == "unavailable"` but does not check `freshness`. Operations like `create_gated_trial_from_admission` and `create_campaign_from_admission_binding` use this path. `ExecutionPermissionResolver._account_facts_permission` correctly blocks stale facts for intent recording, but the Operation Layer confirmation path does not. A stale-but-not-unavailable fact source passes through to execution. |
| **Allowed files** | `tests/unit/test_stale_facts_confirmation_blocking.py` (new), `src/application/brc_operation_layer.py` (read-only for test design reference) |
| **Forbidden files** | `src/**` (writes), `deploy/`, `live-config.env`, `.env*`, exchange gateway, credentials, `scripts/`, `docs/` |
| **Requirements** | 1. Unit test: construct `AccountFacts` with `freshness="stale"`, call `_account_facts_unavailable_reason`, assert returns non-None blocker string containing "stale". 2. Unit test: construct `AccountFacts` with `freshness="expired"`, assert same blocking behavior. 3. Unit test: construct `AccountFacts` with `freshness="too_old"`, assert same blocking behavior. 4. Unit test: construct `AccountFacts` with `freshness="fresh"` and valid source/truth_level, assert returns None (no blocker). 5. Integration test: mock `_account_facts_unavailable_reason` to return stale blocker, call `_confirm_failure_reason`, assert confirmation is blocked with the stale reason. |
| **Test design** | Test file: `tests/unit/test_stale_facts_confirmation_blocking.py`. Use `pytest` fixtures to construct `AccountFacts`-like objects with controlled `freshness` values. The first 4 tests are pure domain logic (fast, no I/O). The integration test mocks the facts source and exercises the `_confirm_failure_reason` → `_account_facts_unavailable_reason` call chain. All tests should initially FAIL until the Codex source change adds the freshness check to `_account_facts_unavailable_reason`. |
| **Verification command** | `python -m pytest tests/unit/test_stale_facts_confirmation_blocking.py -v` |
| **Done When** | All 5 tests pass. The freshness check exists in `_account_facts_unavailable_reason`. Tests serve as regression guard for the safety invariant. |
| **Hard Stop** | Do not modify `src/application/brc_operation_layer.py` — that is a Codex-owned core file. Write tests only. If the Codex source change has not landed, the tests are expected to fail and that is correct. |
| **Risk** | Medium — runtime safety boundary. Stale facts reaching execution could cause orders based on outdated account state. |
| **Codex review needed** | Yes — Codex must (a) approve the expected behavior (stale facts block confirmation), (b) land the source change in `brc_operation_layer.py`, (c) review the test for correctness. |

**Source change required (Codex-owned):**

```text
File: src/application/brc_operation_layer.py
Function: _account_facts_unavailable_reason (around line 6793)
Change: Add freshness check after existing source/truth_level checks:

    freshness = account_facts.freshness if hasattr(account_facts, 'freshness') else None
    if freshness in {"stale", "expired", "too_old"}:
        return f"account facts freshness={freshness}"
```

---

#### TESTCARD-002: Idempotency Repository Unavailable Degraded Mode

| Field | Value |
|---|---|
| **Task ID** | TESTCARD-002 |
| **Goal** | Verify that submit execution is blocked (not just warned) when `_submit_idempotency_repository` is `None` |
| **Why** | Audit Finding 4 (MEDIUM): When `submit_idempotency_repository` is `None`, `record_submit_idempotency_snapshot_for_authorization` appends `"runtime_execution_submit_idempotency_repository_unavailable"` as a blocker but returns a snapshot with `status=BLOCKED`. The gap is that callers may not consistently check the `BLOCKED` status. In degraded mode (no PG), rapid duplicate submissions within the same session could bypass protection if in-memory state is not yet updated. |
| **Allowed files** | `tests/unit/test_idempotency_degraded_mode_blocking.py` (new), `src/application/runtime_execution_intent_adapter_service.py` (read-only for test design reference) |
| **Forbidden files** | `src/**` (writes), `deploy/`, `live-config.env`, `.env*`, exchange gateway, credentials, `scripts/`, `docs/` |
| **Requirements** | 1. Unit test: construct `RuntimeExecutionIntentAdapterService` with `_submit_idempotency_repository=None`, call `record_submit_idempotency_snapshot_for_authorization`, assert snapshot `status` is `BLOCKED`. 2. Unit test: assert blocker list contains `"runtime_execution_submit_idempotency_repository_unavailable"`. 3. Unit test: verify that a second call with same authorization key still returns `BLOCKED` (no in-memory bypass). 4. Integration test: mock the submit path to use the degraded adapter, assert that the Operation Layer `_confirm_failure_reason` detects the idempotency blocker and returns a non-None failure reason. |
| **Test design** | Test file: `tests/unit/test_idempotency_degraded_mode_blocking.py`. Construct the adapter service with `None` repository. Tests 1-3 are pure domain logic. Test 4 exercises the confirm path with the degraded adapter. All tests should pass if the existing `status=BLOCKED` handling is correct; if any fail, it confirms the gap and the Codex source change is needed. |
| **Verification command** | `python -m pytest tests/unit/test_idempotency_degraded_mode_blocking.py -v` |
| **Done When** | All 4 tests pass. Degraded mode idempotency contract is verified: `BLOCKED` status is consistently enforced, not just warned. |
| **Hard Stop** | Do not modify `src/application/runtime_execution_intent_adapter_service.py`. Write tests only. If tests reveal that callers do not enforce `BLOCKED`, report the gap to Codex for a source-level fix. |
| **Risk** | Medium — duplicate submit risk in degraded mode. Without PG-backed idempotency, rapid duplicate submissions could create double orders. |
| **Codex review needed** | Yes — Codex must (a) confirm the expected degraded-mode contract (submit must block, not just warn), (b) review test assertions, (c) if tests fail, issue a source change task card for the caller-side enforcement. |

**Source change required (Codex-owned, only if tests reveal a gap):**

```text
File: src/application/runtime_execution_intent_adapter_service.py (or callers)
Scope: Verify that all callers of record_submit_idempotency_snapshot_for_authorization
       check snapshot.status == BLOCKED and halt submission.
If callers already enforce BLOCKED: no source change needed, tests are sufficient.
If callers do not enforce: Codex issues a follow-up task card.
```

---

#### TESTCARD-003: No-Safe-Executor Explicit Blocked Status

| Field | Value |
|---|---|
| **Task ID** | TESTCARD-003 |
| **Goal** | Verify that `_execute_no_safe_executor` returns `status="blocked"` (not `status="noop"`) when an operation type has no safe executor wired |
| **Why** | Audit Finding 6 (LOW): `_execute_no_safe_executor` at line 1799 returns `status="noop"`. The `noop` status is in `_TERMINAL_STATUSES`, meaning the operation is recorded as terminal without indicating a safety concern. If a new operation type is added with `executable_through_operation=True` but no executor, it would pass `_confirm_failure_reason` and silently noop — masking a configuration error. |
| **Allowed files** | `tests/unit/test_no_safe_executor_blocked_status.py` (new), `src/application/brc_operation_layer.py` (read-only for test design reference) |
| **Forbidden files** | `src/**` (writes), `deploy/`, `live-config.env`, `.env*`, exchange gateway, credentials, `scripts/`, `docs/` |
| **Requirements** | 1. Unit test: call `_execute_no_safe_executor` with a valid operation context, assert result `status` equals `"blocked"`. 2. Unit test: assert result contains a `blocked_reason` or `result_summary` indicating "no safe executor". 3. Unit test: verify that `"blocked"` is NOT in `_TERMINAL_STATUSES` (or if it is, that it is handled differently from `"noop"` in downstream status propagation). 4. Unit test: verify that `"noop"` is NOT returned by `_execute_no_safe_executor` after the fix. |
| **Test design** | Test file: `tests/unit/test_no_safe_executor_blocked_status.py`. Construct a minimal operation context that would trigger `_execute_no_safe_executor`. Test 1-2 verify the new blocked return. Test 3-4 verify the semantic difference between blocked and noop. Tests should initially FAIL until Codex changes the return status. |
| **Verification command** | `python -m pytest tests/unit/test_no_safe_executor_blocked_status.py -v` |
| **Done When** | All 4 tests pass. `_execute_no_safe_executor` returns `status="blocked"` with a clear blocked reason. |
| **Hard Stop** | Do not modify `src/application/brc_operation_layer.py`. Write tests only. The `noop` → `blocked` change may affect callers that check for `noop` — Codex must review the call graph before landing the source change. |
| **Risk** | Medium — behavioral change in execution path. Callers may depend on `noop` being terminal. Codex must verify no caller assumes `noop` means "safe to proceed". |
| **Codex review needed** | Yes — Codex must (a) approve the `noop` → `blocked` semantic change, (b) audit callers of `_execute_no_safe_executor` for `noop`-dependent logic, (c) land the source change, (d) review test assertions. |

**Source change required (Codex-owned):**

```text
File: src/application/brc_operation_layer.py
Function: _execute_no_safe_executor (around line 1793-1811)
Change: Replace status="noop" with status="blocked"
        Add blocked_reason="no safe executor wired for operation type"
        Update result_summary to indicate blocking instead of noop
```

---

#### TESTCARD-005: Admission Bootstrap Stale Facts / Duplicate Active Runtime Guard

| Field | Value |
|---|---|
| **Task ID** | TESTCARD-005 |
| **Goal** | Verify that admission bootstrap rejects (a) stale RequiredFacts and (b) duplicate ACTIVE StrategyRuntimeInstance |
| **Why** | Test Map Step 2 (HIGH risk): No test exists for admission with stale RequiredFacts (should block) or admission when a StrategyRuntimeInstance is already ACTIVE (duplicate guard). Admission is the gateway to the entire runtime path. A broken admission gate either blocks all automation or lets unsafe states through. |
| **Allowed files** | `tests/unit/test_admission_stale_facts_and_duplicate_guard.py` (new), `src/application/brc_admission_service.py` (read-only for test design reference), `src/application/strategy_runtime_service.py` (read-only), `src/application/strategy_runtime_promotion_gate_service.py` (read-only) |
| **Forbidden files** | `src/**` (writes), `deploy/`, `live-config.env`, `.env*`, exchange gateway, credentials, `scripts/`, `docs/` |
| **Requirements** | 1. Unit test: admission attempt with RequiredFacts where `freshness="stale"` → admission rejected with clear blocker. 2. Unit test: admission attempt with RequiredFacts where `freshness="expired"` → admission rejected. 3. Unit test: admission attempt when StrategyRuntimeInstance with `status=ACTIVE` already exists for same StrategyGroup → rejected with "duplicate active runtime" blocker. 4. Unit test: admission attempt when StrategyRuntimeInstance with `status=PAUSED` exists → allowed (not a duplicate). 5. Unit test: promotion gate with `stale_fact_behavior_confirmed=False` → gate status is BLOCKED, not READY. 6. Unit test: promotion gate with `stale_fact_behavior_confirmed=True` → gate can proceed to READY (assuming other conditions met). |
| **Test design** | Test file: `tests/unit/test_admission_stale_facts_and_duplicate_guard.py`. Tests 1-2 verify the stale facts gate at admission time. Tests 3-4 verify the duplicate active runtime guard. Tests 5-6 verify the promotion gate enforcement of `stale_fact_behavior_confirmed`. All tests use mocked repositories and fact sources. No DB or exchange I/O. |
| **Verification command** | `python -m pytest tests/unit/test_admission_stale_facts_and_duplicate_guard.py -v` |
| **Done When** | All 6 tests pass. Admission safety guards are verified for stale facts and duplicate runtime. |
| **Hard Stop** | Do not modify any `src/` file. Write tests only. If tests reveal missing guards in the source, report to Codex for source-level fixes. |
| **Risk** | High — admission is the gateway. Missing guards here either block all automation (false negative) or allow unsafe states through (false positive). |
| **Codex review needed** | Yes — Codex must (a) confirm the expected admission guard behavior, (b) if tests fail, issue source change task cards for the missing guards, (c) review test assertions for correctness against the actual admission contract. |

**Source change required (Codex-owned, only if tests reveal gaps):**

```text
Files: src/application/brc_admission_service.py, src/domain/strategy_runtime_promotion_gate.py
Scope: Verify that:
  - admission service checks RequiredFacts freshness before allowing admission
  - admission service checks for existing ACTIVE StrategyRuntimeInstance
  - promotion gate enforces stale_fact_behavior_confirmed=True as a hard blocker
If all guards exist: no source change needed, tests are sufficient.
If any guard is missing: Codex issues a follow-up task card.
```

---

### Tests-Only Cards

These cards require only test additions. No source changes needed — the existing
code already implements the correct behavior; the tests verify and guard it.

---

#### TESTCARD-004: FinalGate Blocker Class Consolidated Coverage

| Field | Value |
|---|---|
| **Task ID** | TESTCARD-004 |
| **Goal** | Consolidated test for all 6 FinalGate blocker classes plus hard_safety_stop bypass detection |
| **Why** | Test Map Step 8 (CRITICAL): No single test covers all 6 gate classes (`waiting_for_market`, `missing_fact`, `deployment_issue`, `active_position_resolution`, `hard_safety_stop`, `review_only_warning`). FinalGate is the last safety barrier before real order submission. Each class must be independently verified. AI_AGENT_CONSTRAINTS.md defines the gate classification contract. |
| **Allowed files** | `tests/unit/test_final_gate_all_blocker_classes.py` (new), `src/application/runtime_final_gate_preview_service.py` (read-only for test design reference), `src/domain/runtime_final_gate_preview.py` (read-only) |
| **Forbidden files** | `src/**` (writes), `deploy/`, `live-config.env`, `.env*`, exchange gateway, credentials, `scripts/`, `docs/` |
| **Requirements** | 1. Unit test: `waiting_for_market` class — no fresh signal → blocker classified correctly. 2. Unit test: `missing_fact` class — stale or absent RequiredFacts → blocker classified correctly. 3. Unit test: `deployment_issue` class — Tokyo/local deployment behind → blocker classified correctly. 4. Unit test: `active_position_resolution` class — position/order/protection conflict → blocker classified correctly. 5. Unit test: `hard_safety_stop` class — safety boundary violation → blocker classified correctly. 6. Unit test: `review_only_warning` class — weak strategy evidence → blocker classified correctly, but does NOT block execution. 7. Unit test: `hard_safety_stop` bypass detection — attempt to set `hard_safety_stop` blocker as non-blocking → rejected or overridden to blocking. 8. Unit test: blocker resolution mid-cycle — blocker present in preview, then resolved → next preview shows PASS. 9. Unit test: all 6 classes in a single preview with multiple blockers → all classified independently. |
| **Test design** | Test file: `tests/unit/test_final_gate_all_blocker_classes.py`. Each test constructs a `RuntimeFinalGatePreview` scenario with controlled inputs that trigger exactly one blocker class. Test 7 specifically tests the `hard_safety_stop` invariant: this class must ALWAYS block, regardless of other conditions. Test 8 verifies temporal resolution. Test 9 is a comprehensive multi-blocker scenario. All tests use mocked fact sources and position data. No DB or exchange I/O. |
| **Verification command** | `python -m pytest tests/unit/test_final_gate_all_blocker_classes.py -v` |
| **Done When** | All 9 tests pass. Every blocker class is independently verified. `hard_safety_stop` bypass detection is confirmed. |
| **Hard Stop** | Do not modify `src/application/runtime_final_gate_preview_service.py` or any `src/` file. Write tests only. |
| **Risk** | Critical — FinalGate is the last safety barrier. A misclassified blocker could allow unsafe execution or block safe execution. |
| **Codex review needed** | No — tests only, no source changes. But Codex should review test assertions against the actual gate classification contract to ensure tests match the intended behavior. |

---

#### TESTCARD-006: Post-Submit Partial Fill Settlement + Reconciliation Mismatch

| Field | Value |
|---|---|
| **Task ID** | TESTCARD-006 |
| **Goal** | Verify budget settlement and reconciliation behavior when an order partially fills, and when reconciliation detects a mismatch |
| **Why** | Test Map Step 10 (HIGH risk): No test exists for budget settlement when order partially fills, or for reconciliation mismatch detection and recovery flow. Incomplete finalize or settlement leaves the system in an inconsistent state. Budget drift accumulates silently. |
| **Allowed files** | `tests/unit/test_post_submit_partial_fill_and_reconciliation.py` (new), `src/application/runtime_post_submit_finalize_service.py` (read-only), `src/application/reconciliation.py` (read-only), `src/domain/runtime_post_submit_finalize.py` (read-only), `src/domain/runtime_execution_post_submit_budget_settlement.py` (read-only) |
| **Forbidden files** | `src/**` (writes), `deploy/`, `live-config.env`, `.env*`, exchange gateway, credentials, `scripts/`, `docs/` |
| **Requirements** | 1. Unit test: order with `filled_qty < order_qty` (partial fill) → budget settlement uses `filled_qty`, not `order_qty`. 2. Unit test: partial fill → settlement amount uses actual fill price, not intended price. 3. Unit test: partial fill → finalize packet records `partial_fill=True` and actual fill details. 4. Unit test: reconciliation detects local position count ≠ exchange position count → mismatch flagged. 5. Unit test: reconciliation detects local budget ≠ exchange balance → mismatch flagged. 6. Unit test: reconciliation mismatch → recovery flow triggered (verify recovery service is called). 7. Unit test: finalize with exchange returning unexpected status (e.g., `EXPIRED` instead of `FILLED`) → finalize handles gracefully, does not corrupt state. 8. Unit test: closed-trade review facts are complete after partial-fill finalize (verify all required fields are populated). |
| **Test design** | Test file: `tests/unit/test_post_submit_partial_fill_and_reconciliation.py`. Tests 1-3 verify budget settlement correctness with partial fills using Decimal arithmetic. Tests 4-6 verify reconciliation mismatch detection. Test 7 verifies error handling for unexpected exchange statuses. Test 8 verifies post-finalize data completeness. All tests use mocked exchange responses and local state fixtures. No DB or exchange I/O. |
| **Verification command** | `python -m pytest tests/unit/test_post_submit_partial_fill_and_reconciliation.py -v` |
| **Done When** | All 8 tests pass. Partial fill settlement is correct. Reconciliation mismatch detection and recovery are verified. |
| **Hard Stop** | Do not modify any `src/` file. Write tests only. If tests reveal settlement or reconciliation bugs, report to Codex. |
| **Risk** | High — incorrect settlement or missed reconciliation mismatches cause silent budget drift. Partial fills are common in real trading. |
| **Codex review needed** | No — tests only. But Codex should review Decimal precision assertions and reconciliation mismatch thresholds. |

---

#### TESTCARD-007: Notification / Review Outcome Propagation

| Field | Value |
|---|---|
| **Task ID** | TESTCARD-007 |
| **Goal** | Verify notification delivery on material state changes and review outcome propagation to StrategyGroup status |
| **Why** | Test Map Step 11 (MEDIUM risk): No test exists for Feishu notification delivery on position close, notification suppression on non-material changes, review outcome propagation to StrategyGroup status, or notification on reconciliation mismatch. Broken notifications mean the Owner operates blind, defeating the supervision model. |
| **Allowed files** | `tests/unit/test_notification_and_review_propagation.py` (new), `src/infrastructure/notifier.py` (read-only), `src/infrastructure/notifier_feishu.py` (read-only), `src/application/runtime_closed_trade_lifecycle_review_service.py` (read-only), `src/application/strategy_group_forward_review.py` (read-only), `src/domain/live_lifecycle_review.py` (read-only), `src/domain/forward_outcome_review.py` (read-only) |
| **Forbidden files** | `src/**` (writes), `deploy/`, `live-config.env`, `.env*`, exchange gateway, credentials, `scripts/`, `docs/` |
| **Requirements** | 1. Unit test: position close event → Feishu notification sent (mock notifier, verify `send` called with correct message). 2. Unit test: non-material state change (e.g., internal status update with no Owner impact) → notification suppressed (verify `send` NOT called). 3. Unit test: review outcome "保留" persisted to StrategyGroup forward review repository. 4. Unit test: review outcome "暂停" propagated to StrategyGroup status → status changes to PAUSED. 5. Unit test: review outcome "停用" propagated → status changes to DISABLED. 6. Unit test: reconciliation mismatch event → notification sent to Owner with mismatch details. 7. Unit test: protection health regression event → notification sent. 8. Unit test: forward review facts completeness — all required fields populated after a closed-trade lifecycle review. |
| **Test design** | Test file: `tests/unit/test_notification_and_review_propagation.py`. Tests 1-2 verify the notification contract (material vs non-material). Tests 3-5 verify review outcome persistence and propagation. Tests 6-7 verify event-driven notifications. Test 8 verifies data completeness. All tests use mocked notifier and repository fixtures. No DB, exchange, or Feishu I/O. |
| **Verification command** | `python -m pytest tests/unit/test_notification_and_review_propagation.py -v` |
| **Done When** | All 8 tests pass. Notification delivery contract is verified. Review outcome propagation to StrategyGroup status is confirmed. |
| **Hard Stop** | Do not modify any `src/` file. Write tests only. If tests reveal notification or propagation bugs, report to Codex. |
| **Risk** | Medium — broken notifications don't lose money but destroy the Owner supervision model. The Owner must know when positions close, reconciliation mismatches occur, or protection regresses. |
| **Codex review needed** | No — tests only. But Codex should review the notification message format and review outcome propagation logic. |

---

## Suggested Sequence

| Order | Task ID | Type | Rationale |
|---|---|---|---|
| 1 | TESTCARD-004 | Tests-only | FinalGate is CRITICAL risk; tests-only so no source dependency |
| 2 | TESTCARD-005 | Codex-owned | Admission is HIGH risk gateway; test first, Codex fix if needed |
| 3 | TESTCARD-006 | Tests-only | Post-submit settlement is HIGH risk; tests-only |
| 4 | TESTCARD-001 | Codex-owned | Stale facts blocking is MEDIUM risk; Codex source change required |
| 5 | TESTCARD-002 | Codex-owned | Idempotency degraded mode is MEDIUM risk; Codex source change required |
| 6 | TESTCARD-007 | Tests-only | Notification/review is MEDIUM risk; tests-only |
| 7 | TESTCARD-003 | Codex-owned | No-safe-executor is LOW risk; Codex source change required |

**Rationale:** Tests-only cards (TESTCARD-004, 006, 007) can proceed immediately
after mainline acceptance with no source dependency. Codex-owned cards
(TESTCARD-001, 002, 003, 005) require Codex to land source changes first; Claude
writes the tests (expected to fail) and Codex uses them as acceptance gates.

Within each category, order by risk level: CRITICAL → HIGH → MEDIUM → LOW.

---

## Do-Not-Run During Live Acceptance

All 7 test cards are post-acceptance P1. Do not dispatch during live acceptance
because:

1. **TESTCARD-001, 002, 003** require Codex source changes that alter runtime
   behavior. Landing these during live acceptance risks introducing regressions
   in the active runtime path.

2. **TESTCARD-004, 005, 006, 007** are tests-only but exercise safety-critical
   paths. If any test accidentally triggers a side effect (e.g., due to a test
   fixture misconfiguration), it could interfere with live acceptance validation.

3. **All cards** should be dispatched only after:
   - Mainline acceptance is complete
   - Live-test is closed
   - The branch is in a post-acceptance stabilization phase

---

## Summary Table

| Task ID | Category | Risk | Source Change? | Tests | Codex Review? |
|---|---|---|---|---|---|
| TESTCARD-001 | Stale facts blocking | MEDIUM | Yes (`brc_operation_layer.py`) | 5 | Yes |
| TESTCARD-002 | Idempotency degraded mode | MEDIUM | Maybe (depends on test results) | 4 | Yes |
| TESTCARD-003 | No-safe-executor blocked status | LOW | Yes (`brc_operation_layer.py`) | 4 | Yes |
| TESTCARD-004 | FinalGate blocker classes | CRITICAL | No | 9 | No (review recommended) |
| TESTCARD-005 | Admission stale facts + duplicate guard | HIGH | Maybe (depends on test results) | 6 | Yes |
| TESTCARD-006 | Post-submit partial fill + reconciliation | HIGH | No | 8 | No (review recommended) |
| TESTCARD-007 | Notification/review propagation | MEDIUM | No | 8 | No (review recommended) |
| **Total** | | | | **44** | |

---

*Report generated by CLAUDE-FINAL-TESTCARDS-004. Task card refinement only — no
tests implemented, no source files modified.*
