---
title: CURRENT_READINESS_BLOCKERS
status: CURRENT_CANON
authority: current-position-rebuild
last_verified: 2026-06-01
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

- **Classification**: SUPERSEDED as a blanket blocker.
- **What changed**: `wallet_equity` / `account_equity` and `available_margin`
  can be mapped from a cached `AccountSnapshot` when present.
- **Current behavior**: missing or stale cached facts are still blockers for
  the specific preflight, but the project is no longer globally blocked on an
  absent mapping.
- **Evidence**: `src/interfaces/api_brc_console.py`
  `_cached_account_equity_snapshot()`; `reports/directional-opportunity-broad-smoke-20260529/account_equity_readiness_result.md`.
- **Status**: Resolved when cached AccountSnapshot exists; otherwise
  profile/preflight-scoped blocker.

### BLK-P0-02: 3 trial candidates have no cost/baseline enrichment

- **What**: MI-001 BNB long, MI-001 SOL long, VI-001 ETH long were selected by broad OHLCV smoke screen, but intentionally have no slippage, funding rate, exchange fee, or random/hold baseline
- **Why it blocks**: Cannot judge whether candidates warrant deepening to bounded trial
- **Evidence**: `reports/directional-opportunity-broad-smoke-20260529/trial_candidate_with_known_risks.md`
- **Historical note**: this was formerly framed as a research-only enrichment
  step; that label is scope-limited and does not globally prohibit
  testnet/dev/readiness work.
- **Status**: Not started
- **Enrichment result** (2026-05-30): `reports/directional-opportunity-broad-smoke-20260529/cost_baseline_enrichment.md`
  - MI-001 BNB: **refine_again** — 72h净收益3.16%但2023-2025数据断层3.5年，需补齐数据重跑
  - MI-001 SOL: **refine_again** — 数据完整但边际薄(72h净1.58%)、MAE -7.89%严重、正率仅+1.75pp vs随机
  - VI-001 ETH: **park** — 净收益太薄(72h净0.75%)，费用占比16.6%
  - **结论**: 无候选通过进入Owner Review；两个需重新细化，一个暂停
- **Status**: **Enrichment completed — no candidate passes to Owner Review**

### BLK-P0-03: signal-to-intent conversion not implemented

- **Classification**: SCOPE_LIMITED.
- **What**: Signal-to-intent / trial intent behavior is controlled by the
  current BRC chain and execution permission resolution.
- **Why it matters**: It is a readiness or implementation gap for a specific
  chain, not a global prohibition on testnet/dev carrier advancement.
- **Status**: Block only the specific conversion path when unavailable.

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

### BLK-P1-03: Blanket testnet authorization requirement

- **Classification**: WRONG_FOR_CURRENT_BASELINE / SUPERSEDED.
- **What**: Older instructions said runtime, paper, testnet, tiny-live, or
  exchange-connected steps require explicit Owner authorization for every
  action.
- **Current rule**: real live / real-funds order placement requires separate
  explicit Owner authorization. Testnet/dev/readiness/profile-scoped blockers
  should be inspected, safely repaired/reset/cleaned up when bounded, and
  continued through hard safety gates.

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
| 1 | account_equity readable | AVAILABLE when cached AccountSnapshot exists; otherwise profile/preflight-scoped blocker |
| 2 | Trial candidates have cost/baseline enrichment | **BLOCKED** (BLK-P0-02) |
| 3 | Owner risk acceptance for specific candidate | **NOT STARTED** |
| 4 | signal-to-intent conversion available | Scope-specific; not a global blocker for testnet/dev readiness |
| 5 | Execution permission allows at least intent_recording | AVAILABLE (testnet path) |
| 6 | Testnet API keys configured | AVAILABLE |
| 7 | GKS operational | AVAILABLE |
| 8 | Campaign lifecycle supports trial state | AVAILABLE |
| 9 | Owner explicitly authorizes trial | **NOT STARTED** |

---

## Current checks

| Priority | Check | Purpose |
|---|---|---|
| P0 | Verify cached account facts freshness in the active profile | Preflight-specific equity/account-facts evidence |
| P0 | ~~Design cost/baseline enrichment plan for 3 candidates~~ | **DONE** — enrichment report: `cost_baseline_enrichment.md` |
| P0 | BNB data gap: source 2023-2025 klines & re-run MI-001 BNB | Required before BNB candidate can proceed |
| P0 | SOL signal dedup + MAE filter re-run | Required before SOL candidate can proceed |
| P1 | Review 022-027 migration chain integrity | Inform Owner decision on BLK-P1-01 |
| P1 | Evaluate signal-to-intent conversion scope | Inform Owner decision on BLK-P0-03 |
