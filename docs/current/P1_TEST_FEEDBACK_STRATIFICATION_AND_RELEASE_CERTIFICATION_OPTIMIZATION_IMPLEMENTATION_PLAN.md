---
title: P1_TEST_FEEDBACK_STRATIFICATION_AND_RELEASE_CERTIFICATION_OPTIMIZATION_IMPLEMENTATION_PLAN
status: CURRENT_IMPLEMENTATION
authority: docs/current/P1_TEST_FEEDBACK_STRATIFICATION_AND_RELEASE_CERTIFICATION_OPTIMIZATION_IMPLEMENTATION_PLAN.md
last_verified: 2026-07-13
---

# P1 Test Feedback Stratification And Release Certification Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic Fast, Mainline, and Release pytest tiers that shorten development feedback while preserving the complete release gate.

**Architecture:** A pure test-tier policy classifies pytest node IDs with conservative defaults. A thin pytest plugin in `tests/conftest.py` exposes `--test-tier`, deselects out-of-tier items, annotates selected items, and runs a masked PostgreSQL preflight only when the selected collection contains PostgreSQL certification.

**Tech Stack:** Python 3.14, pytest 9, pytest-asyncio, SQLAlchemy 2, psycopg 3, PostgreSQL 16.

## Global Constraints

- No production/runtime source, PG schema, strategy, risk, sizing, profile, FinalGate, Operation Layer, lifecycle, exchange, or Tokyo cadence change.
- Fast and Mainline are feedback surfaces only; Release remains the complete deploy-certification surface.
- New unit tests default to Mainline; new integration tests default to Release.
- No xdist in stable tier commands until deterministic database isolation is separately proven.
- No recurring or per-run JSON/MD/report artifacts.
- A different-identity natural signal preempts this task at the next committed boundary for R1B.

---

### Task 1: RED Tier Policy Contract

**Files:**
- Create: `tests/unit/test_feedback_tier_policy.py`
- Create after RED: `tests/feedback_tier_policy.py`

**Interfaces:**
- Produces: `FeedbackTier`, `classify_nodeid(nodeid)`, `selected_for_tier(nodeid, selected_tier)`, `validate_tier_manifest(repo_root)`.

- [x] **Step 1: Write failing tests for Fast, Mainline, Release-only, sentinel override, conservative unknown-path behavior, and manifest invariants.**
- [x] **Step 2: Run `python3 -m pytest -q tests/unit/test_feedback_tier_policy.py` and verify import failure because the policy does not exist.**
- [x] **Step 3: Implement the minimal typed policy, explicit file sets, sentinel map, selection matrix, and manifest validator.**
- [x] **Step 4: Re-run the policy tests and require zero failures.**

### Task 2: RED PostgreSQL Preflight Contract

**Files:**
- Modify: `tests/unit/test_feedback_tier_policy.py`
- Modify: `tests/feedback_tier_policy.py`

**Interfaces:**
- Produces: `FeedbackEnvironmentError`, `preflight_release_postgres(admin_url, connect_fn=None)`.

- [x] **Step 1: Add failing tests for missing dependency, unavailable database, successful `SELECT 1`, and secret masking.**
- [x] **Step 2: Run the focused tests and verify the new API is missing.**
- [x] **Step 3: Implement a three-second psycopg connection preflight with host/port/database-only diagnostics.**
- [x] **Step 4: Run the focused tests and require zero failures.**

### Task 3: Pytest Tier Plugin

**Files:**
- Modify: `tests/conftest.py`
- Modify: `pytest.ini`
- Modify: `tests/unit/test_feedback_tier_policy.py`

**Interfaces:**
- Consumes: policy APIs from Tasks 1 and 2.
- Produces: `--test-tier=fast|mainline|release`, `feedback_fast`, `feedback_mainline`, and `feedback_release_only` markers.

- [x] **Step 1: Add failing hook-level tests proving deselection, marker annotation, plain-pytest Release equivalence, and preflight only for selected PostgreSQL integration items.**
- [x] **Step 2: Run focused tests and verify the option/hook behavior is absent.**
- [x] **Step 3: Add the pytest option, marker registration, deterministic collection filtering, and release preflight.**
- [x] **Step 4: Run focused tests and collect each tier to verify stable counts.**

### Task 4: Benchmark And Coverage Acceptance

**Files:**
- Modify: `docs/current/P1_TEST_FEEDBACK_STRATIFICATION_AND_RELEASE_CERTIFICATION_OPTIMIZATION_IMPLEMENTATION_PLAN.md`

**Interfaces:**
- Consumes: three stable pytest commands.
- Produces: current command evidence and measured tier budgets in this plan.

- [x] **Step 1: Run Fast and require under `90s`.**
- [x] **Step 2: Run Mainline and require under `300s`.**
- [x] **Step 3: Run Release with the declared venv/PostgreSQL environment and require the exact complete collection with zero failures.**
- [x] **Step 4: Run the missing-dependency preflight probe and prove failure occurs before test execution without printing a password.**
- [x] **Step 5: Run production file-I/O audit, output-scope validation, `git diff --check`, and changed-file review.**
- [x] **Step 6: Record exact counts, timings, warnings, audit results, and skipped tests below.**

## Completion Record

This section is updated only from fresh command evidence.

| Item | Status | Evidence |
| --- | --- | --- |
| Tier policy RED-GREEN | passed | Initial RED failed at collection with missing `tests.feedback_tier_plugin`; invalid-URL RED exposed raw SQLAlchemy parsing; final GREEN is `17 passed in 0.03s` |
| Fast | passed | `328 passed`, `2724 deselected`; pytest `7.57s`, wall `9.94s` |
| Mainline | passed | `2462 passed`, `1 skipped`, `589 deselected`; pytest `151.06s`, wall `154.85s` |
| Release | passed | Complete `3052`-item collection: `3051 passed`, `1 skipped`, `0 failed`, three pre-existing SQLAlchemy warnings; pytest `552.87s`, wall `558.25s` |
| PostgreSQL preflight | passed | Missing dependency stops with zero executed tests in `4.12s`; unavailable PostgreSQL stops with zero executed tests in `4.85s`; injected password is absent from output |
| Runtime file-I/O and output scope | passed | `suspicious_runtime_file_authority=0`, `frequent_report_write=0`, `output_artifact_scope_valid` |
