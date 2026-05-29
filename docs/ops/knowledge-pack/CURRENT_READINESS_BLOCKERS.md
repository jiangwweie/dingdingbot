---
title: CURRENT_READINESS_BLOCKERS
status: CURRENT_CANON
authority: current-position-rebuild
last_verified: 2026-05-29
source_of_truth:
  - docs/ops/knowledge-pack/CURRENT_POSITION_REBUILD.md
  - reports/directional-opportunity-broad-smoke-20260529/pg_trial_readiness_fact_check.md
---

# CURRENT_READINESS_BLOCKERS.md

This document tracks what blocks the project from advancing to bounded live trial.
Updated as blockers are resolved or new ones emerge.

---

## P0 Blockers

### BLK-P0-01: account_equity unavailable

- **What**: `wallet_equity` and `available_margin` are explicitly `not_available` in `_account_facts()`
- **Why it blocks**: Cannot compute ratio-based budget for bounded trial; trial-start preparation requires reliable read-only account_equity source
- **Evidence**: `src/interfaces/api_brc_console.py` `_account_facts()` function; `reports/directional-opportunity-broad-smoke-20260529/pg_trial_readiness_fact_check.md`
- **Distinction**: `AccountService.get_balance()` can read exchange balance via `fetch_balance()`, but this is not the same as `wallet_equity` / `available_margin`
- **Status**: Known, unresolved

### BLK-P0-02: 3 trial candidates have no cost/baseline enrichment

- **What**: MI-001 BNB long, MI-001 SOL long, VI-001 ETH long were selected by broad OHLCV smoke screen, but intentionally have no slippage, funding rate, exchange fee, or random/hold baseline
- **Why it blocks**: Cannot judge whether candidates warrant deepening to bounded trial
- **Evidence**: `reports/directional-opportunity-broad-smoke-20260529/trial_candidate_with_known_risks.md`
- **Next step**: Cost/baseline enrichment research (research-only, no execution)
- **Status**: Not started

### BLK-P0-03: signal-to-intent conversion not implemented

- **What**: The furthest signal state is `signal_evaluated_no_intent`. There is no automatic or manual signal-to-trial-trade-intent conversion.
- **Why it blocks**: Even if cost/baseline enrichment passes, signals cannot become trial trade intents
- **Evidence**: Admission Gate Phase 1-17 state doc; `bounded_risk_campaign_service.py`
- **Status**: Not scoped; requires Owner decision on whether to implement in current scope

---

## P1 Blockers

### BLK-P1-01: 022-027 migrations not integrated

- **What**: 6 Alembic migrations (022-027) and related domain/infra/app files are untracked and not imported by any tracked code
- **Why it matters**: If trial depends on historical research tables (strategy family registry, OHLCV catalog, signal evaluation), those tables won't exist
- **Evidence**: `git status`, code search for imports
- **Status**: Requires Owner decision: commit these files, or proceed without them

### BLK-P1-02: Execution permission live gate

- **What**: If `TRADING_ENV=live` and account facts source is not `exchange_live` or `mixed`, execution permission caps at `intent_recording` only
- **Why it matters**: Even if other blockers resolve, live execution requires both live TRADING_ENV and exchange_live account facts
- **Evidence**: `src/application/execution_permission.py`
- **Status**: Design constraint, not a bug

---

## P2 Review Items

### BLK-P2-01: Owner has not reviewed trial candidate event samples

- **What**: The 3 broad smoke screen candidates have not been reviewed by Owner at the event/sample level
- **Evidence**: `trial_candidate_with_known_risks.md` notes this explicitly
- **Status**: Owner review pending

### BLK-P2-02: Production deployment capability

- **What**: No cloud/daemon infrastructure exists; system runs locally only
- **Why it matters**: Any bounded trial must run on a local machine
- **Status**: Not a blocker for local trial, but limits operational reliability

---

## Not blockers

| Item | Why not a blocker |
|---|---|
| BRC governance framework | Implemented and testnet verified |
| Owner Console v0 | Implemented with 5 P0 pages |
| Admission Gate Phase 1-17 | Metadata operations complete |
| GKS | Fail-closed, operational |
| Periodic reconciliation | Testnet verified |
| Backtester engine | Available for research |
| Broad OHLCV screening | Completed |

---

## Trial readiness checklist

A bounded live trial requires ALL of these:

| # | Requirement | Status |
|---|---|---|
| 1 | account_equity readable | **BLOCKED** (BLK-P0-01) |
| 2 | Trial candidates have cost/baseline enrichment | **BLOCKED** (BLK-P0-02) |
| 3 | Owner risk acceptance for specific candidate | **NOT STARTED** |
| 4 | signal-to-intent conversion available | **BLOCKED** (BLK-P0-03) |
| 5 | Execution permission allows at least intent_recording | AVAILABLE (testnet path) |
| 6 | Testnet API keys configured | AVAILABLE |
| 7 | GKS operational | AVAILABLE |
| 8 | Campaign lifecycle supports trial state | AVAILABLE |
| 9 | Owner explicitly authorizes trial | **NOT STARTED** |

---

## Next read-only checks

| Priority | Check | Purpose |
|---|---|---|
| P0 | Audit `_account_facts()` for possible equity source | Unblock BLK-P0-01 |
| P0 | Design cost/baseline enrichment plan for 3 candidates | Unblock BLK-P0-02 |
| P1 | Review 022-027 migration chain integrity | Inform Owner decision on BLK-P1-01 |
| P1 | Evaluate signal-to-intent conversion scope | Inform Owner decision on BLK-P0-03 |
