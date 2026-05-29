---
title: PROJECT_BASELINE_CURRENT
status: CURRENT_CANON
authority: owner-correction + current-position-rebuild
last_verified: 2026-05-29
supersedes:
  - docs/ops/knowledge-pack/PROJECT_OVERVIEW.md
source_of_truth:
  - docs/ops/knowledge-pack/CURRENT_POSITION_REBUILD.md
  - docs/ops/knowledge-pack/TRUTH_REBUILD_PASS1.md
  - docs/ops/project-roadmap-v2.md (2026-05-29 amendment, line 540+)
  - docs/adr/0009-non-real-live-execution-authorization-boundary.md
  - docs/adr/0012-bounded-risk-campaign-system.md
---

# PROJECT_BASELINE_CURRENT.md

This is the current authoritative project baseline.
Supersedes all prior knowledge-pack documents for project positioning and capability claims.

---

## 1. Current definition

Bounded Risk Campaign (BRC) fast trial-and-review research system for small risk-capital Campaigns.

Source: Owner 2026-05-29 amendment in `docs/ops/project-roadmap-v2.md`.

The old positioning "BRC Reset / Opportunity Structure Discovery v0" is **no longer the formal current positioning**.
It has been explicitly superseded by the Owner correction above.

The preferred research funnel is:

```
wide admission -> broad coarse screen -> candidate -> risk disclosure -> Owner risk acceptance -> bounded live trial or continued fine screen -> review -> promote / revise / park
```

Hard boundaries:

- no uncontrolled capital risk
- no strategy self-elevation
- no bypass around Operation Layer

---

## 2. Current practical stage

```
BRC governance framework exists.
Broad OHLCV screening completed.
3 candidates are pending cost/baseline enrichment.
Pre-trial readiness has known account_equity blocker.
```

Sub-phase breakdown:

| Sub-phase | Status |
|---|---|
| BRC governance framework (campaign lifecycle + state machine + operation layer) | Implemented, testnet verified |
| Owner Console v0 (5 P0 pages) | Implemented |
| Admission Gate Phase 1-17 | Metadata operations complete |
| TF-001 Carrier Full-chain Smoke | Passed |
| Broad OHLCV Smoke Screen (BRC-R5-003) | Completed, 3 candidates selected |
| Cost/baseline enrichment for candidates | Not started |
| Trial readiness (account_equity, signal-to-intent) | Known blocker present |
| Signal-to-trade conversion | Not implemented |

---

## 3. Confirmed current facts

| ID | Fact |
|---|---|
| CF-001 | BRC governance framework is implemented and testnet verified |
| CF-002 | Real live trading is prohibited unless Owner separately authorizes (ADR-0009) |
| CF-003 | Testnet trading capability exists but only for controlled scenarios with Owner authorization |
| CF-004 | Broad OHLCV screening completed: 9 variants x 4 assets x 2 sides |
| CF-005 | 3 trial candidates selected: MI-001 BNB long, MI-001 SOL long, VI-001 ETH long |
| CF-006 | 3 candidates have no cost/slippage/funding/baseline enrichment |
| CF-007 | `auto_within_budget_enabled=False` (hardcoded) |
| CF-008 | `auto_execution_enabled=False` (hardcoded) |
| CF-009 | `trial_started` is only READ in service code, never SET to True |
| CF-010 | 21 tracked Alembic migrations (001-021) form the current deployable schema |
| CF-011 | 6 untracked migrations (022-027) exist but are not integrated into the tracked codebase |
| CF-012 | No tracked file imports any of the new untracked PG repositories or services |
| CF-013 | GKS (Global Kill Switch) is fail-closed by design |
| CF-014 | Execution permission system gates all actions (READ_ONLY / INTENT_RECORDING / EXECUTION_INTENT_ALLOWED / ORDER_CAPABLE) |
| CF-015 | CPM-1 (ETH Pinbar Pullback) is PAUSED (OOS negative) |

---

## 4. Current blockers

| Blocker | Impact | Status |
|---|---|---|
| `account_equity` unavailable (`wallet_equity` / `available_margin` = `not_available`) | Pre-trial readiness blocked | Known P0 blocker |
| 3 trial candidates have no cost/slippage/funding/baseline | Cannot judge if candidates are worth deepening | P0 research task |
| signal-to-intent conversion not implemented / not scoped | Cannot convert signals to trial trade intents | P1 design decision |
| 022-027 migrations not integrated | Historical research tables unavailable if trial depends on them | P1 Owner decision |

---

## 5. Not integrated / untracked

The following files exist in the working directory but are **not git-tracked and not imported by any tracked code**:

- Migrations 022-027 (6 files)
- Domain files: `historical_ohlcv.py`, `strategy_family_registry.py`, `strategy_family_signal.py`, `historical_research_sampling.py`, `historical_signal_evaluation.py`, `directional_opportunity_*.py`, `forward_outcome_review.py`, `sol_high_convexity_candidates.py`
- PG repositories: `pg_strategy_family_registry_repository.py`, `pg_historical_ohlcv_catalog_repository.py`, `pg_historical_research_sampling_repository.py`, `pg_historical_signal_evaluation_repository.py`
- Application services: `historical_research_sampling_service.py`, `historical_signal_evaluation_service.py`, `historical_signal_input_builder.py`, `cpm_historical_experiment_runner.py`, `cpm_regime_split_experiment_runner.py`
- Scripts: 8 research scripts under `scripts/`
- Tests: 16 test files under `tests/unit/`
- ORM additions in `pg_models.py` (+500 lines, unstaged modification)

These **must not be described as integrated capabilities**.
`exists` != `integrated`.

---

## 6. Disabled capabilities

| Capability | Status | Why |
|---|---|---|
| Automated strategy execution | DISABLED | `auto_within_budget_enabled=False`, `auto_execution_enabled=False` (hardcoded) |
| signal-to-order | NOT IMPLEMENTED | No code path exists |
| signal-to-intent | PARTIAL | Furthest state: `signal_evaluated_no_intent`; no automatic signal-to-intent conversion |
| account_equity read | NOT AVAILABLE | `wallet_equity` and `available_margin` are `not_available` in `_account_facts()` |
| Production deployment | NOT AVAILABLE | Local runtime only, no cloud/daemon infrastructure |
| Scheduler / daemon | NOT AVAILABLE | Process-local only in `src/main.py` |

---

## 7. Prohibited actions

| ID | Prohibition | Source |
|---|---|---|
| FORBID-001 | Real live trading | ADR-0009 |
| FORBID-002 | Using real funds to place orders | ADR-0009 |
| FORBID-003 | Automated strategy execution | No runtime-eligible strategy exists |
| FORBID-004 | Modifying execution permission | Codex-owned core file |
| FORBID-005 | Withdrawal / transfer | Out-of-scope |
| FORBID-006 | Strategy self-elevation | ADR-0012 |
| FORBID-007 | Bypassing the Operation Layer | ADR-0012 |
| FORBID-008 | Using research-only results for real trading | Research-runtime isolation |
| FORBID-009 | Modifying API keys / credentials | Security risk |
| FORBID-010 | Automated symbol/side/leverage expansion | ADR-0012 |

---

## 8. Current next actions

| Priority | Action | Type | Safety |
|---|---|---|---|
| P0 | 3 trial candidates: cost/slippage/funding/baseline enrichment | research-only | no execution, no trading |
| P0 | 3 trial candidates: random-entry/hold baseline comparison | research-only | no execution |
| P1 | Decide whether 022-027 and untracked files should be committed | Owner decision | — |
| P1 | Resolve account_equity blocker (determine read source) | infrastructure | no execution |
| P1 | Decide whether signal-to-intent conversion is in current scope | Owner decision | — |
| P2 | Owner reviews 3 trial candidate event samples | owner review | read-only |

---

## 9. Superseded claims

| Old claim | Why superseded | Current truth |
|---|---|---|
| "BRC Reset / Opportunity Structure Discovery v0" | Owner 2026-05-29 explicit correction | "fast trial-and-review research system for small risk-capital Campaigns" |
| "27 Alembic migrations (001-027)" | Only 001-021 are git-tracked | 21 tracked + 6 untracked (not integrated) |
| "Strategy Family Registry PG chain pending verification" | Untracked files, no tracked imports | Not integrated |
| "Historical Research Sampling pending verification" | Same | Not integrated |
| "Historical Signal Evaluation pending verification" | Same | Not integrated |
| "exchange + PG dual path for account facts" | `account_service.py` only has exchange path; `_account_facts()` dual path is positions/orders only; equity = not_available | account_equity unavailable |

---

## 10. Reading order

For new AI assistants joining this project:

1. **This file** (`PROJECT_BASELINE_CURRENT.md`) — project definition and current state
2. `CURRENT_FACT_REGISTRY.md` — verified facts, blockers, prohibited actions
3. `CURRENT_READINESS_BLOCKERS.md` — what blocks trial readiness
4. `DOCUMENT_GOVERNANCE.md` — how to read and trust project documents
5. `CURRENT_POSITION_REBUILD.md` — detailed position analysis
6. `TRUTH_REBUILD_PASS1.md` — which old claims are stale and why
7. `DOCS_GOVERNANCE_EXPLORATION_REPORT.md` — full docs audit

Then for deeper context:

- `docs/adr/0009-*.md` — non-real-live execution boundary
- `docs/adr/0012-*.md` — BRC system definition
- `docs/ops/project-roadmap-v2.md` — long-term direction (note: contains both old and new labels)
- `docs/ops/live-safe-v1-task-board.md` — task status
- `docs/ops/live-safe-v1-progress.md` — detailed progress log

**Do not start from** `docs/ops/knowledge-pack/PROJECT_OVERVIEW.md` — it is superseded.
