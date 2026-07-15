---
title: P0_PROTECTED_ACTIVE_LIFECYCLE_DEPLOYMENT_IMPLEMENTATION_PLAN
status: OWNER_APPROVED
authority: docs/current/P0_PROTECTED_ACTIVE_LIFECYCLE_DEPLOYMENT_IMPLEMENTATION_PLAN.md
last_verified: 2026-07-15
---

# Protected Active Lifecycle Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow Tokyo release deployment while all active real lifecycles are stable and protection-complete, while preserving every existing unsafe-state blocker.

**Architecture:** Extend the existing PG-only phase-two verifier with stable/unsafe lifecycle counts. Reuse the existing synchronous service quiescence and lifecycle mutation capability disable/enable sequence as the single-writer fence; do not add a second worker or source of truth.

**Tech Stack:** Python 3.12, SQLAlchemy, PostgreSQL, pytest, systemd deployment command generation.

## Global Constraints

- Owner accepts at most one hour of lifecycle maintenance interruption.
- Manual close ends only the current trade and does not pause automation.
- No exchange writes, order changes, profile changes, sizing changes, or scope expansion during deploy verification.
- Production current state remains PG-only; no JSON/Markdown runtime source or recurring writer may be added.

---

### Task 1: Classify protected and unsafe active lifecycles

**Files:**
- Modify: `tests/unit/test_ticket_lifecycle_phase_two_readiness.py`
- Modify: `scripts/verify_ticket_lifecycle_phase_two_readiness.py`

**Interfaces:**
- Consumes: PG lifecycle, attempt, and protection-set rows.
- Produces: `protected_active_real_lifecycles` and `unsafe_active_real_lifecycles` counts; only the unsafe count is a blocker.

- [ ] Add failing tests for protected `position_protected`, protected `runner_protected`, unprotected active, blocked protected, and critical-command cases.
- [ ] Run the focused tests and confirm the protected cases fail under the current global blocker.
- [ ] Implement aggregate SQL classification with exact stable statuses and protection/first-blocker requirements.
- [ ] Run the focused tests and confirm all cases pass.

### Task 2: Preserve deploy command safety and contract truth

**Files:**
- Modify: `tests/unit/test_tokyo_lifecycle_phase_two_deploy.py`
- Modify: `docs/current/TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md`

**Interfaces:**
- Consumes: the updated verifier behavior.
- Produces: a deploy sequence that still stops old services before disabling capability and performs zero exchange writes in acceptance.

- [ ] Add assertions that the generated deploy commands use typed protected-lifecycle readiness and keep capability disabled across migration/switch.
- [ ] Run the command-generation tests and confirm the new contract assertions fail where wording/behavior is absent.
- [ ] Update the deployment contract and command descriptions without introducing a force bypass.
- [ ] Run command-generation and deployment-contract tests.

### Task 3: Verify release and production readiness

**Files:**
- No production file additions.

**Interfaces:**
- Consumes: completed implementation.
- Produces: commit-ready and deploy-ready evidence.

- [ ] Run focused lifecycle readiness and deploy planner tests.
- [ ] Run deployment plan dry-run for the target commit.
- [ ] Run full unit tests, file-I/O audit, output-scope validator, migration-head check, and `git diff --check`.
- [ ] Review the diff for active-risk regression and commit the bounded release.

### Task 4: Deploy with an active protected AVAX lifecycle

**Files:**
- Tokyo release directory, symlink, systemd units, and PG capability state through the approved deploy command only.

**Interfaces:**
- Consumes: target commit, current Tokyo release, PG lifecycle classification, exchange/account read-only facts.
- Produces: exact-head deployed release with lifecycle capability restored and AVAX still exchange-protected.

- [ ] Run Tokyo read-only preflight and record protected versus unsafe lifecycle counts.
- [ ] Abort if any critical command, domain hold, unprotected attempt, or unsafe lifecycle exists.
- [ ] Apply the generated bounded deploy plan.
- [ ] Verify deployed head, migration, systemd units, capability, lifecycle service, watcher, monitor, account facts, AVAX position/protection, and forbidden effects.
- [ ] Roll back if lifecycle capability or AVAX protection cannot be proven after the switch.
