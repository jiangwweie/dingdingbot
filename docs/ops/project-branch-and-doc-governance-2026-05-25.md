> [!NOTE]
> **HISTORICAL_EVIDENCE** — This document is a historical operational, governance, sprint, product, or live-trial artifact from an earlier project phase.
>
> It may be useful for context, auditing, or traceability, but it does **not** represent current project state, constraints, product direction, or agent instructions.
>
> Current authoritative sources:
> - `docs/canon/PROJECT_BASELINE_CURRENT.md`
> - `docs/canon/BRC_TARGET_SEMANTICS.md`
> - `docs/canon/AGENT_WORKSPACE_RULES.md`
> - `docs/canon/RUNTIME_SAFETY_BOUNDARY.md`
> - `docs/canon/TECH_DEBT_BASELINE.md`
> - `docs/canon/DOCUMENT_GOVERNANCE.md`

# Project Branch And Document Governance

Last updated: 2026-05-25

Status: Active governance note

Runtime effect: none

Trading permission effect: none

Default state: docs/design governance only

## Purpose

This document reconciles local branches and documentation against the current
project plan.

The current planning authority is `docs/ops/project-roadmap-v2.md`. The active
Owner-facing mainline is Personal Leveraged Campaign Mainline v0, accepted by
ADR-0008. The authorized work surface remains docs/design/research/sandbox
only unless a separate promotion review explicitly widens it.

This document does not delete branches, move historical evidence, authorize
runtime integration, or change trading permissions.

## Current Working State

Current branch:

- `codex/personal-campaign-chain-v0`

Current uncommitted work:

- `docs/README.md`
- `docs/ops/live-safe-v1-progress.md`
- `docs/ops/live-safe-v1-task-board.md`
- `docs/ops/personal-leveraged-campaign-local-sandbox-v0.md`
- `src/application/personal_campaign_sandbox.py`
- `src/domain/personal_campaign.py`
- `tests/unit/test_personal_campaign_sandbox.py`

Current worktree:

- only `/Users/jiangwei/Documents/final` is attached;
- no additional linked git worktrees are active.

## Branch Governance Classes

### Active Branch

| Branch | Role | Status | Governance |
|---|---|---|---|
| `codex/personal-campaign-chain-v0` | Current PLC local sandbox task branch | Active | Continue PLC docs/design/sandbox/test work here until reviewed. Do not push unless Owner asks. |

### Integration And Protected Branches

| Branch | Role | Status | Governance |
|---|---|---|---|
| `dev` | Existing integration branch | Protected | Treat as integration history. Current PLC branch is 2 commits ahead of local `dev`; do not use as scratch. |
| `main` / `origin/main` | Historical default branch | Protected | Local `main` is stale relative to `origin/main`; do not base new work here unless repository policy is reset. |
| `stable/backtest-v2-fixed` | Stable historical backtest branch | Protected archive | Preserve as historical stable evidence. Do not update for PLC work. |
| `origin/release/v0.1.0-monitor-beta` | Remote release branch | Protected archive | Release evidence only. Do not update for PLC work. |
| `origin/v2`, `origin/v2-deploy-*` | Remote historical deploy branches | Protected archive | Deployment history only. Do not mix with current PLC planning. |

### Current Evidence / Research Branches

| Branch | Role | Status | Governance |
|---|---|---|---|
| `codex/ema60-1h-strategy-search-20260524` | EMA60 branch search evidence | Frozen research evidence | Preserve until evidence is summarized/archived; no runtime promotion. |
| `codex/research-lead-reset-001` | ORH-009 / research reset evidence | Frozen research evidence | Preserve as research-governance evidence. |
| `codex/pg-full-migration` / `origin/codex/pg-full-migration` | PG migration work | Dormant infrastructure branch | Keep only if PG migration work is still relevant; not part of PLC local sandbox. |

### Duplicate Or Stale Local Research Branches

The following local branches currently point at the same historical commit
`3d868b8` and have no upstream:

- `codex/baseline-trend-001`
- `codex/expert-system-review-001`
- `codex/htp-001`
- `codex/method-update-001`
- `codex/open-short-research-001`
- `codex/open-trend-research-001`
- `codex/regime-boundary-audit-001`
- `task/ls-r1da-indicator-derivatives`

Governance:

- treat as stale local research branch labels;
- do not continue new work from them;
- delete only after Owner confirmation or after their evidence is explicitly
  cited from current docs.

### Worktree-Agent Branches

| Branch | Status | Governance |
|---|---|---|
| `worktree-agent-a04aa70b` | No active linked worktree found | Candidate for deletion after confirmation. |
| `worktree-agent-a0a6f5b3` | No active linked worktree found | Candidate for deletion after confirmation. |

## Branch Rules Going Forward

1. Current PLC local sandbox work stays on `codex/personal-campaign-chain-v0`
   until review.
2. New focused task branches should use the `codex/` prefix unless Owner
   specifies another prefix.
3. `dev`, `main`, `stable/*`, `release/*`, and historical remote deploy
   branches are not scratch branches.
4. Research branches may produce docs/reports/sandbox artifacts only; they do
   not imply runtime, paper, testnet, tiny-live, live, account, leverage,
   sizing, or real order-path authorization.
5. Branch deletion, remote pruning, pushing, and PR creation require explicit
   Owner instruction.

## Document Governance Classes

### Current SSOT

These are the first-read documents for current planning:

- `docs/README.md`
- `docs/ops/project-roadmap-v2.md`
- `docs/ops/personal-leveraged-campaign-mainline-v0.md`
- `docs/adr/0008-personal-leveraged-campaign-business-chain.md`
- `docs/ops/research-to-runtime-promotion-gate.md`
- `docs/ops/runtime-safety-boundary.md`
- `docs/ops/personal-leveraged-campaign-local-sandbox-v0.md`
- `docs/ops/personal-campaign-risk-rule-matrix-v0.md`
- `docs/ops/personal-campaign-promotion-checklist-v0.md`
- `docs/ops/sq02-downside-cont-strategy-contract-skeleton-v0.md`
- `docs/ops/project-branch-and-doc-governance-2026-05-25.md`

### Active Governance

These documents control active work intake and status:

- `docs/ops/live-safe-v1-task-board.md`
- `docs/ops/live-safe-v1-progress.md`
- `docs/ops/live-safe-v1-findings.md`
- `docs/ops/agent-working-rules.md`
- `docs/ops/codex-claude-handoff-template.md`

### Active Research Context

These documents remain active for opportunity research and candidate labels:

- `docs/ops/opportunity-research-governance-v0.md`
- `docs/ops/opportunity-research-control-board.md`
- `docs/ops/opportunity-hypothesis-register.md`

### Runtime Safety Foundation

These documents remain relevant as runtime safety foundation material, but they
do not define the current business mainline:

- `docs/ops/live-safe-v1-program.md`
- `docs/adr/0001-live-safe-v1-scope.md`
- `docs/adr/0002-decision-trace-backbone-v0.md`
- `docs/adr/0003-post-merge-hardening-live-safe-v0.md`
- `docs/adr/0004-daily-risk-limits-runtime-closure-v0.md`
- `docs/adr/0005-reconciliation-read-model-v0.md`
- `docs/adr/0006-runtime-periodic-reconciliation-report-only-loop.md`
- `docs/adr/0007-reconciliation-read-model-persistence.md`

### Historical Evidence

The remaining large `docs/ops/**` research reports, `docs/gpt/**`, and archived
pre-reset material are evidence archive unless a current SSOT document
explicitly promotes them.

Governance:

- keep historical reports stable;
- do not edit old evidence to match new conclusions except to add explicit
  supersession notes when needed;
- prefer adding a new current governance note over rewriting older research
  reports;
- if physical archive cleanup is requested later, move only after producing a
  restore map.

## Immediate Recommendations

1. Keep `codex/personal-campaign-chain-v0` as the active branch for PLC-001
   until Owner review.
2. Do not merge or push until the current uncommitted PLC sandbox/docs/test
   changes are reviewed.
3. Treat the eight same-commit local research branches as stale labels and stop
   starting new work there.
4. Treat the two `worktree-agent-*` branches as deletion candidates, but do not
   delete without Owner confirmation.
5. Use `docs/README.md` plus this governance note as the docs entry point
   instead of physically moving the current 139 markdown files.

## Non-Authorization

This governance note does not authorize:

- branch deletion or remote pruning;
- commit, push, PR, or merge;
- runtime profile changes;
- paper/testnet/live/tiny-live trading;
- real API keys, real account access, real orders, transfers, or withdrawals;
- direct research-to-order wiring.
