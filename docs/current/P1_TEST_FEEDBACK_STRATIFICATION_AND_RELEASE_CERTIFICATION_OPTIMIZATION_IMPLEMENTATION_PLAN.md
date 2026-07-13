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

- [ ] **Step 1: Write failing tests for Fast, Mainline, Release-only, sentinel override, conservative unknown-path behavior, and manifest invariants.**
- [ ] **Step 2: Run `python3 -m pytest -q tests/unit/test_feedback_tier_policy.py` and verify import failure because the policy does not exist.**
- [ ] **Step 3: Implement the minimal typed policy, explicit file sets, sentinel map, selection matrix, and manifest validator.**
- [ ] **Step 4: Re-run the policy tests and require zero failures.**

### Task 2: RED PostgreSQL Preflight Contract

**Files:**
- Modify: `tests/unit/test_feedback_tier_policy.py`
- Modify: `tests/feedback_tier_policy.py`

**Interfaces:**
- Produces: `FeedbackEnvironmentError`, `preflight_release_postgres(admin_url, connect_fn=None)`.

- [ ] **Step 1: Add failing tests for missing dependency, unavailable database, successful `SELECT 1`, and secret masking.**
- [ ] **Step 2: Run the focused tests and verify the new API is missing.**
- [ ] **Step 3: Implement a three-second psycopg connection preflight with host/port/database-only diagnostics.**
- [ ] **Step 4: Run the focused tests and require zero failures.**

### Task 3: Pytest Tier Plugin

**Files:**
- Modify: `tests/conftest.py`
- Modify: `pytest.ini`
- Modify: `tests/unit/test_feedback_tier_policy.py`

**Interfaces:**
- Consumes: policy APIs from Tasks 1 and 2.
- Produces: `--test-tier=fast|mainline|release`, `feedback_fast`, `feedback_mainline`, and `feedback_release_only` markers.

- [ ] **Step 1: Add failing hook-level tests proving deselection, marker annotation, plain-pytest Release equivalence, and preflight only for selected PostgreSQL integration items.**
- [ ] **Step 2: Run focused tests and verify the option/hook behavior is absent.**
- [ ] **Step 3: Add the pytest option, marker registration, deterministic collection filtering, and release preflight.**
- [ ] **Step 4: Run focused tests and collect each tier to verify stable counts.**

### Task 4: Benchmark And Coverage Acceptance

**Files:**
- Modify: `docs/current/P1_TEST_FEEDBACK_STRATIFICATION_AND_RELEASE_CERTIFICATION_OPTIMIZATION_IMPLEMENTATION_PLAN.md`

**Interfaces:**
- Consumes: three stable pytest commands.
- Produces: current command evidence and measured tier budgets in this plan.

- [ ] **Step 1: Run Fast and require under `90s`.**
- [ ] **Step 2: Run Mainline and require under `300s`.**
- [ ] **Step 3: Run Release with the declared venv/PostgreSQL environment and require the exact complete collection with zero failures.**
- [ ] **Step 4: Run the missing-dependency preflight probe and prove failure occurs before test execution without printing a password.**
- [ ] **Step 5: Run production file-I/O audit, output-scope validation, `git diff --check`, and changed-file review.**
- [ ] **Step 6: Record exact counts, timings, warnings, audit results, and skipped tests below.**

## Completion Record

This section is updated only from fresh command evidence.

| Item | Status | Evidence |
| --- | --- | --- |
| Tier policy RED-GREEN | pending | Not yet executed |
| Fast | pending | Not yet executed |
| Mainline | pending | Not yet executed |
| Release | pending | Not yet executed |
| PostgreSQL preflight | pending | Not yet executed |
| Runtime file-I/O and output scope | pending | Not yet executed |

