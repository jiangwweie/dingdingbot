# P0-3 Runtime Supervision, Semantic Admission, And Allocation Plan

**Goal:** Separate process health from business no-op, produce a machine semantic-admission conclusion for every active event scope, and replace implicit winner selection with Allocation Policy V0 while preserving one action-time lane.

**Architecture:** Migration 106 adds bounded PG current tables for process outcomes, semantic admissions, and versioned allocation decisions. Promotion remains execution-eligibility gated; allocation can only rank already eligible candidates and cannot expand Owner capital scope. The Tokyo monitor reads current process and lifecycle state without file authority.

## Task 1: Migration 106 And Typed Process Outcomes

- Add `brc_runtime_process_outcomes`, `brc_strategy_semantic_admissions`, and `brc_allocation_decisions`.
- Extend promotion candidates with allocation identity, rank, risk-at-stop, and state.
- Prove business no-op is `process_state=succeeded|noop`, not a process failure.

## Task 2: Allocation Policy V0

- Materialize one decision for each fresh-candidate arbitration cycle.
- Rank all eligible candidates and select at most one.
- Allocate only the selected candidate's existing risk-at-stop reservation.
- Record deferred candidates without changing signal grade, Owner policy, or Runtime Safety.

## Task 3: Full Active Semantic Admission

- Evaluate every active candidate/event binding from PG current contracts.
- Emit one of `trial_grade_capable`, `observe_only_by_design`, `semantics_incomplete`, `facts_incomplete`, `strategy_quality_blocked`, or `safety_blocked`.
- Reject unsupported-side mirroring and missing canonical instrument mapping.
- Keep admission non-authoritative for submit.

## Task 4: Monitor And Verification

- Surface retryable/hard process failures and overdue lifecycle gaps.
- Keep successful no-op and valid market wait quiet.
- Run migration, allocation, semantic admission, monitor, full-chain, compile, file-I/O, and output-scope checks.

## Stop Condition

P0-3 is complete when process health is not inferred from trade occurrence, every active scope has a machine semantic conclusion, every promotion cycle has a versioned allocation decision, at most one lane is selected, and no new file-backed runtime authority exists.
