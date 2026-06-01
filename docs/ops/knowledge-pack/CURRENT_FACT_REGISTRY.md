---
title: CURRENT_FACT_REGISTRY
status: CURRENT_CANON
authority: current-position-rebuild + tracked-code-state
last_verified: 2026-06-01
supersedes:
  - docs/ops/knowledge-pack/FACT_REGISTRY.md
source_of_truth:
  - docs/ops/knowledge-pack/CURRENT_POSITION_REBUILD.md
  - docs/ops/knowledge-pack/TRUTH_REBUILD_PASS1.md
  - tracked code verification (git status, git log, code reads)
---

# CURRENT_FACT_REGISTRY.md

This is the current authoritative fact registry.
Supersedes the old `FACT_REGISTRY.md` which contains known stale claims.

---

## A. Current confirmed facts

| ID | Fact | Evidence | Confidence |
|---|---|---|---|
| CF-001 | Project target is "fast trial-and-review research system for small risk-capital Campaigns" | Owner 2026-05-29 amendment in `project-roadmap-v2.md` line 540+ | HIGH |
| CF-022 | Current agent baseline is "BRC fast small-capital live trial system"; it is not research-only or signal-detection-only | Owner 2026-06-01 instruction governance baseline | HIGH |
| CF-002 | BRC governance framework is implemented and testnet verified | Commit history + task board | HIGH |
| CF-003 | Real live trading / real-funds order placement is prohibited unless Owner separately authorizes that live action | ADR-0009 as amended 2026-06-01 | HIGH |
| CF-004 | Testnet/dev/readiness/controlled rehearsal work may proceed through scoped verification and hard safety gates without additional testnet authorization | Owner 2026-06-01 instruction governance baseline | HIGH |
| CF-005 | Broad OHLCV screening completed: 9 variants x 4 assets x 2 sides | `reports/directional-opportunity-broad-smoke-20260529/` | HIGH |
| CF-006 | 3 trial candidates selected: MI-001 BNB long, MI-001 SOL long, VI-001 ETH long | Same report | HIGH |
| CF-021 | Cost/baseline enrichment completed (2026-05-30): BNB=refine_again, SOL=refine_again, ETH=park. No candidate passes to Owner Review. BNB has 3.5yr data gap. All candidates tail-sensitive. | `cost_baseline_enrichment.md` | HIGH |
| CF-007 | 21 tracked Alembic migrations (001-021) | `git ls-files migrations/versions/` | HIGH |
| CF-008 | 6 untracked migrations (022-027) | `git status` | HIGH |
| CF-009 | No tracked file imports any untracked PG repository | Code search confirmed | HIGH |
| CF-010 | GKS (Global Kill Switch) is fail-closed | `bc7e2ad` + code | HIGH |
| CF-011 | Owner Console v0 has 5 P0 pages, browser verified | Commit history | HIGH |
| CF-012 | Admission Gate Phase 1-17 metadata operations complete | Commit `668acba`, progress log | HIGH |
| CF-013 | TF-001 Carrier Full-chain Smoke passed | Commit `31075d1` | HIGH |
| CF-014 | CPM-1 (ETH Pinbar Pullback) is PAUSED (OOS negative) | `crypto-pullback-module-v1-oos-failure-classification.md` | HIGH |
| CF-015 | No strategy satisfies SRR-002 seven standards | Task board + roadmap | HIGH |
| CF-016 | LangGraph LLM operator is advisory only, cannot execute trades | `brc_operator_workflow.py` | HIGH |
| CF-017 | Execution permission system has 5 levels: READ_ONLY / SIGNAL_ONLY / INTENT_RECORDING / EXECUTION_INTENT_ALLOWED / ORDER_ALLOWED | `execution_permission.py` | HIGH |
| CF-023 | BNB first carrier advanced through live observation, strategy trial readiness, preflight facts, controlled testnet carrier path, and protected testnet same-path rehearsal | BNB strategy trial reports and tests | HIGH |
| CF-018 | Withdrawal is Owner-external behavior, not a system capability | Task board + progress log | HIGH |
| CF-019 | Operator authentication uses TOTP + password | `src/interfaces/operator_auth.py` | HIGH |
| CF-020 | 13 ADRs (0001-0013) are tracked and stable | `docs/adr/` | HIGH |

---

## B. Current blockers

| ID | Blocker | Impact | Evidence |
|---|---|---|---|
| BLK-001 | ~~`account_equity` unavailable~~ | **RESOLVED when cached AccountSnapshot exists** — Owner Console maps cached `total_balance` / `available_balance` to account equity / available margin | `_cached_account_equity_snapshot()` and account equity readiness report |
| BLK-002 | ~~3 trial candidates lack cost/baseline enrichment~~ | **RESOLVED** — enrichment completed 2026-05-30. No candidate passes: BNB needs data, SOL needs dedup/MAE filter, ETH parked | `cost_baseline_enrichment.md` |
| BLK-003 | signal-to-intent conversion not implemented | Cannot convert evaluated signals to trade intents | Furthest state: `signal_evaluated_no_intent`; no auto conversion |
| BLK-004 | 022-027 migrations not integrated | Historical research tables unavailable if trial requires them | Untracked files, no tracked imports |

---

## C. Not integrated / untracked

| ID | Component | Status | Evidence |
|---|---|---|---|
| NI-001 | Strategy Family Registry PG chain | NOT INTEGRATED | Untracked migration 022, untracked repository, unstaged ORM model, no tracked imports |
| NI-002 | Historical OHLCV Catalog | NOT INTEGRATED | Untracked migration 023, untracked repository |
| NI-003 | Historical Research Sampling | NOT INTEGRATED | Untracked migration 024, untracked service/repository |
| NI-004 | Historical Signal Evaluation | NOT INTEGRATED | Untracked migration 025, untracked service/repository |
| NI-005 | Historical Signal Owner Report | NOT INTEGRATED | Untracked migration 026 |
| NI-006 | Historical Regime Split Reports | NOT INTEGRATED | Untracked migration 027 |
| NI-007 | pg_models.py ORM additions (+500 lines) | NOT INTEGRATED | Unstaged modification, not committed |
| NI-008 | 8 research scripts under `scripts/` | NOT INTEGRATED | Untracked |
| NI-009 | 16 test files under `tests/unit/` for new modules | NOT INTEGRATED | Untracked |
| NI-010 | 8 domain files for new research modules | NOT INTEGRATED | Untracked |
| NI-011 | 5 application services for new research modules | NOT INTEGRATED | Untracked |

---

## D. Disabled capabilities

| ID | Capability | Status | Why |
|---|---|---|---|
| DC-001 | Automated strategy execution | DISABLED | `auto_within_budget_enabled=False`, `auto_execution_enabled=False` (hardcoded in `bounded_risk_campaign_service.py`) |
| DC-002 | signal-to-order | NOT IMPLEMENTED | No code path exists |
| DC-003 | signal-to-intent | PARTIAL | `signal_evaluated_no_intent` is the furthest state; no automatic signal-to-intent conversion |
| DC-004 | account_equity read | AVAILABLE WHEN CACHED | cached AccountSnapshot mapping exposes account_equity / wallet_equity / available_margin when present |
| DC-005 | `trial_started` | NEVER SET | Only READ in service code (line 2807+), never SET to True |
| DC-006 | Production deployment | NOT AVAILABLE | Local runtime only, no cloud/daemon |

---

## E. Prohibited actions

| ID | Action | Source |
|---|---|---|
| PA-001 | Real live trading | ADR-0009 |
| PA-002 | Using real funds to place orders | ADR-0009 |
| PA-003 | Uncontrolled automated strategy execution | No strategy self-elevation or Operation Layer bypass |
| PA-004 | Modifying execution permission | Codex-owned core file |
| PA-005 | Withdrawal / transfer | Out-of-scope |
| PA-006 | Strategy self-elevation | ADR-0012 |
| PA-007 | Bypassing the Operation Layer | ADR-0012 |
| PA-008 | Using research results for real trading | Research-runtime isolation |
| PA-009 | Modifying API keys / credentials | Security |
| PA-010 | Automated symbol/side/leverage expansion | ADR-0012 |

---

## F. Deprecated claims (from old FACT_REGISTRY.md)

| Old claim (old ID) | Why deprecated | Current truth |
|---|---|---|
| "BRC Reset / Opportunity Structure Discovery v0" (F-001) | Owner 2026-05-29 explicit rejection | "fast trial-and-review research system for small risk-capital Campaigns" |
| "27 Alembic migrations (001-027)" (F-011) | Only 001-021 are git-tracked | 21 tracked + 6 untracked (not integrated) |
| "Strategy Family Registry PG chain 待确认" (UF-001) | Untracked files, no tracked imports | NOT INTEGRATED |
| "exchange + PG dual path for account facts" (UF-002) | `account_service.py` only has exchange path; equity = not_available | account_equity unavailable |
| "Historical OHLCV import tool 待确认" (UF-003) | Untracked script, no evidence of execution | NOT INTEGRATED |
| "Historical Research Sampling 待确认" (UF-005) | Untracked service, no tracked imports | NOT INTEGRATED |
| "Historical Signal Evaluation 待确认" (UF-006) | Untracked service, no tracked imports | NOT INTEGRATED |
| "21 visible untracked docs" (multiple) | Historical snapshot; current untracked count is 60+ files | See NI-001 through NI-011 |

---

## G. Safety boundaries

| ID | Boundary | Rule |
|---|---|---|
| SB-001 | Real live trading | PROHIBITED unless Owner explicitly authorizes |
| SB-002 | Testnet operations | Available for controlled scenarios through scoped verification and hard safety gates; no additional testnet authorization required by default |
| SB-003 | LLM role | Advisory only; cannot write, trade, or confirm |
| SB-004 | Execution gating | 4-level permission system; live without exchange_live facts caps at intent_recording |
| SB-005 | Research-runtime isolation | Research outputs cannot modify runtime profiles or trigger strategy promotion |
| SB-006 | Tracked-only rule | Untracked files must never be described as integrated capabilities |
| SB-007 | GKS | Fail-closed by design |
| SB-008 | Default safety posture | `TRADING_ENV=simulation`, `EXCHANGE_TESTNET=true`, GKS fail-closed |
