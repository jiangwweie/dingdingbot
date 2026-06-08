---
title: PROJECT_BASELINE_CURRENT
status: CURRENT_CANON
authority: owner-correction + current-position-rebuild
last_verified: 2026-06-08
supersedes:
  - docs/ops/knowledge-pack/PROJECT_OVERVIEW.md
source_of_truth:
  - docs/ops/knowledge-pack/CURRENT_PRODUCT_OPERATING_MODEL.md
  - docs/ops/knowledge-pack/CURRENT_POSITION_REBUILD.md
  - docs/ops/knowledge-pack/TRUTH_REBUILD_PASS1.md
  - docs/ops/project-roadmap-v2.md (2026-05-29 amendment, line 540+)
  - docs/ops/agent-current-brc-baseline.md
  - docs/adr/0009-non-real-live-execution-authorization-boundary.md
  - docs/adr/0012-bounded-risk-campaign-system.md
  - docs/ops/trading-console-owner-action-flow-v1-deploy-governance-report-2026-06-07.md
  - docs/ops/mr-eth-review-ledger-budgeted-autonomy-v0-design-2026-06-08.md
---

# PROJECT_BASELINE_CURRENT.md

This is the current authoritative project baseline.
Supersedes all prior knowledge-pack documents for project positioning and capability claims.

---

## 1. Current definition

Bounded Risk Campaign (BRC) productized bounded-live operations system for fast
small-capital trial-and-review Campaigns.

Source: Owner 2026-06-08 product direction correction and Owner 2026-06-01
instruction governance baseline.

The old positioning "BRC Reset / Opportunity Structure Discovery v0" and the
intermediate "research-only signal detection" framing are **no longer the
formal current positioning**. They are historical or scope-limited to research
tasks.

The older "Trading Console is read-only" framing is also **not the product
model**. Read-only contracts remain valid for the specific read-model
namespace/report they describe, but the current console target is the Owner's
bounded-live operating surface.

The current core chain is:

```
StrategyFamily / Carrier
-> ActionCandidate
-> Owner risk understanding
-> Owner authorization or BudgetEnvelope authorization
-> ActionSpec
-> FinalGate
-> Operation Layer
-> official bounded live action
-> active position / TP/SL protection monitoring
-> close / TP / SL
-> Review Ledger
-> promote / revise / park
```

Hard boundaries:

- no uncontrolled capital risk
- no real live trading / real-funds order placement without separate explicit Owner authorization
- no strategy self-elevation
- no bypass around Operation Layer
- no FinalGate bypass
- no unscoped symbol / side / leverage / notional expansion
- no withdrawal / transfer

---

## 2. Current practical stage

```
BRC governance framework exists.
Strategy-family / carrier -> ActionCandidate chain is active.
Owner Action Flow v1 is deployed on Tokyo with runtime-bound health and
live_ready=false.
BNB first carrier has completed bounded live closeout/recovery evidence.
MR/ETH has tracked protected-open bounded-live evidence in the Review Ledger
design note.
Generic live action remains bounded by exact Owner/BudgetEnvelope scope,
FinalGate, Operation Layer, TP/SL protection, and Review Ledger.
```

Sub-phase breakdown:

| Sub-phase | Status |
|---|---|
| BRC governance framework (campaign lifecycle + state machine + operation layer) | Implemented, testnet verified |
| Owner Console / Trading Console product surface | Owner Action Flow v1 deployed to Tokyo; action enablement remains backend-gated |
| Admission Gate Phase 1-17 | Metadata operations complete |
| TF-001 Carrier Full-chain Smoke | Passed |
| Broad OHLCV Smoke Screen (BRC-R5-003) | Completed, 3 candidates selected |
| Cost/baseline enrichment for candidates | Completed for the initial broad-smoke candidates; outcomes remain evidence/warnings, not automatic promotion |
| Account equity mapping | Cached AccountSnapshot mapping available for readiness inputs |
| BNB StrategyTrialReadiness / controlled testnet carrier | Implemented, tested, and exercised through protected testnet same-path rehearsal |
| Generic action entry / Owner Action Flow | Implemented as product-facing read model/action-flow surface; real action requires official backend actionability |
| BudgetEnvelope / Budgeted Autonomy | BudgetEnvelope recommendation exists; Budgeted Autonomy v0 remains design-only and not direct trade permission |
| Signal-to-trade conversion | Only official bounded action paths may execute; no uncontrolled signal-to-order path |

---

## 3. Confirmed current facts

| ID | Fact |
|---|---|
| CF-001 | BRC governance framework is implemented and testnet verified |
| CF-002 | Real live trading / real-funds order placement is prohibited unless Owner separately authorizes the live action |
| CF-003 | Testnet/dev/readiness/controlled rehearsal work may proceed through scoped verification and hard safety gates without additional testnet authorization |
| CF-004 | Broad OHLCV screening completed: 9 variants x 4 assets x 2 sides |
| CF-005 | 3 trial candidates selected: MI-001 BNB long, MI-001 SOL long, VI-001 ETH long |
| CF-006 | Initial candidate cost/baseline enrichment was completed; weak evidence remains a disclosed warning, not a permanent blocker after Owner acknowledgement |
| CF-007 | `auto_within_budget_enabled=False` (hardcoded) |
| CF-008 | `auto_execution_enabled=False` (hardcoded) |
| CF-009 | `trial_started` is only READ in service code, never SET to True |
| CF-010 | 21 tracked Alembic migrations (001-021) form the current deployable schema |
| CF-011 | 6 untracked migrations (022-027) exist but are not integrated into the tracked codebase |
| CF-012 | No tracked file imports any of the new untracked PG repositories or services |
| CF-013 | GKS (Global Kill Switch) is fail-closed by design |
| CF-014 | Execution permission system gates action depth (READ_ONLY / SIGNAL_ONLY / INTENT_RECORDING / EXECUTION_INTENT_ALLOWED / ORDER_ALLOWED) |
| CF-015 | CPM-1 (ETH Pinbar Pullback) is PAUSED (OOS negative) |
| CF-016 | Current product model is productized bounded-live operations; Trading Console is not merely a read-only dashboard |
| CF-017 | Tokyo Owner Action Flow v1 deploy report records runtime-bound service health with `live_ready=false` |
| CF-018 | MR/ETH Review Ledger note records a protected-open bounded-live ETH position with TP and SL present as of its collected evidence |
| CF-019 | Budgeted Autonomy v0 is design-only and not direct trade permission |
| CF-020 | Read-only endpoint/report guarantees are artifact-scoped and must not be generalized into product-wide no-action policy |

---

## 4. Current blockers

| Blocker | Impact | Status |
|---|---|---|
| generic live / real-funds authorization missing | Generic live order placement must not proceed | Hard blocker unless an exact Owner or BudgetEnvelope-scoped authorization exists and FinalGate passes |
| active/protected position or PG/exchange uncertainty | New live entry must not proceed if exposure/protection facts are conflicting, stale, or unknown | Scope-specific hard blocker until reconciled |
| strategy evidence weakness / incomplete observation | Must be disclosed and acknowledged | Warning after Owner acknowledgement, not a hard blocker |
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
| Live automated strategy execution | DISABLED | Real live / real-funds action requires exact Owner/BudgetEnvelope scope, FinalGate, Operation Layer, and explicit enablement |
| uncontrolled signal-to-order | FORBIDDEN | Strategy self-elevation and Operation Layer bypass are prohibited |
| trial intent / readiness paths | PARTIAL | Evidence and readiness paths exist, but live conversion remains gated |
| account_equity read | AVAILABLE WHEN CACHED | `wallet_equity` / `account_equity` and `available_margin` map from cached AccountSnapshot when present |
| Owner Console deployment | AVAILABLE WITH CONSTRAINT | Tokyo deployment reports show runtime-bound Owner Console with `live_ready=false`; deployment is not live authorization |
| Scheduler / daemon autonomy | NOT ENABLED | No general autonomous live scheduler; Budgeted Autonomy v0 remains design-only |

---

## 7. Prohibited actions

| ID | Prohibition | Source |
|---|---|---|
| FORBID-001 | Real live trading | ADR-0009 |
| FORBID-002 | Using real funds to place orders | ADR-0009 |
| FORBID-003 | Uncontrolled automated strategy execution | No strategy self-elevation or Operation Layer bypass |
| FORBID-004 | Modifying execution permission | Codex-owned core file |
| FORBID-005 | Withdrawal / transfer | Out-of-scope |
| FORBID-006 | Strategy self-elevation | ADR-0012 |
| FORBID-007 | Bypassing the Operation Layer | ADR-0012 |
| FORBID-008 | Using research-only results for real trading | Research-runtime isolation |
| FORBID-009 | Modifying API keys / credentials | Security risk |
| FORBID-010 | Automated symbol/side/leverage expansion | ADR-0012 |

---

## 8. Current governance priorities

| Priority | Action | Type | Safety |
|---|---|---|---|
| P0 | Preserve hard live / real-funds authorization boundary | governance | hard stop without explicit Owner live authorization |
| P0 | Preserve productized bounded-live operating model | product / architecture | console is Owner action surface, not passive dashboard |
| P0 | Keep official action path unified | architecture | ActionSpec -> FinalGate -> Operation Layer -> protection -> Review |
| P0 | Continue testnet/dev/readiness/profile-scoped repair when blockers are bounded | engineering | no real funds |
| P0 | Surface Review Ledger and recovery facts | product safety | no hidden drift or missing protection |
| P1 | Decide whether 022-027 and untracked files should be committed | Owner decision | — |

---

## 9. Superseded claims

| Old claim | Why superseded | Current truth |
|---|---|---|
| "BRC Reset / Opportunity Structure Discovery v0" | Owner 2026-05-29 correction, then Owner 2026-06-08 product correction | "BRC productized bounded-live operations system" |
| "27 Alembic migrations (001-027)" | Only 001-021 are git-tracked | 21 tracked + 6 untracked (not integrated) |
| "Strategy Family Registry PG chain pending verification" | Untracked files, no tracked imports | Not integrated |
| "Historical Research Sampling pending verification" | Same | Not integrated |
| "Historical Signal Evaluation pending verification" | Same | Not integrated |
| "account_equity is unavailable" | cached AccountSnapshot mapping was added after this claim | account_equity / wallet_equity and available_margin are available when the runtime cached snapshot exists |
| "testnet requires Owner authorization" | 2026-06-01 Owner baseline supersedes blanket testnet authorization stops | testnet/dev/readiness work proceeds via scoped verification and safety gates |
| "Trading Console is a read-only product" | Owner 2026-06-08 product correction | read-model namespaces can be read-only, but the console product is the Owner bounded-live operating surface |
| "Production deployment is unavailable" | 2026-06-07 deploy governance reports | Tokyo Owner Console deployment exists with `runtime_bound=true`, `live_ready=false`, and no generic live authorization |

---

## 10. Reading order

For new AI assistants joining this project:

1. `CURRENT_PRODUCT_OPERATING_MODEL.md` — current product and execution model
2. **This file** (`PROJECT_BASELINE_CURRENT.md`) — project definition and current state
3. `CURRENT_FACT_REGISTRY.md` — verified facts, blockers, prohibited actions
4. `CURRENT_READINESS_BLOCKERS.md` — what blocks trial readiness
5. `DOCUMENT_GOVERNANCE.md` — how to read and trust project documents
6. `CURRENT_POSITION_REBUILD.md` — detailed historical position analysis
7. `TRUTH_REBUILD_PASS1.md` — which old claims are stale and why
8. `DOCS_GOVERNANCE_EXPLORATION_REPORT.md` — full docs audit

Then for deeper context:

- `docs/adr/0009-*.md` — non-real-live execution boundary
- `docs/adr/0012-*.md` — BRC system definition
- `docs/ops/project-roadmap-v2.md` — long-term direction (note: contains both old and new labels)
- `docs/ops/live-safe-v1-task-board.md` — task status
- `docs/ops/live-safe-v1-progress.md` — detailed progress log

**Do not start from** `docs/ops/knowledge-pack/PROJECT_OVERVIEW.md` — it is superseded.
