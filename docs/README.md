> [!IMPORTANT]
> **Current project baseline**: `docs/ops/knowledge-pack/PROJECT_BASELINE_CURRENT.md`
> **Current agent baseline**: `docs/ops/agent-current-brc-baseline.md`
> **Current fact registry**: `docs/ops/knowledge-pack/CURRENT_FACT_REGISTRY.md`
> **Current readiness blockers**: `docs/ops/knowledge-pack/CURRENT_READINESS_BLOCKERS.md`
> **Document governance rules**: `docs/ops/knowledge-pack/DOCUMENT_GOVERNANCE.md`
>
> Older docs may be historical, superseded, or research-only. Use the governance rules to determine authority.
> Project definition (Owner 2026-06-01): "BRC fast small-capital live trial system".

---

# Docs Index

Last updated: 2026-06-01

## Current Baseline (start here)

Read the current baseline documents first:

1. `docs/ops/knowledge-pack/PROJECT_BASELINE_CURRENT.md` — project definition and current state
2. `docs/ops/agent-current-brc-baseline.md` — current agent/task execution boundary
3. `docs/ops/knowledge-pack/CURRENT_FACT_REGISTRY.md` — verified facts and blockers
4. `docs/ops/knowledge-pack/CURRENT_READINESS_BLOCKERS.md` — what blocks trial readiness
5. `docs/ops/knowledge-pack/DOCUMENT_GOVERNANCE.md` — how to read and trust documents
6. `docs/ops/knowledge-pack/CURRENT_POSITION_REBUILD.md` — detailed position analysis with evidence
7. `docs/ops/knowledge-pack/TRUTH_REBUILD_PASS1.md` — which old claims are stale and why
8. `docs/ops/knowledge-pack/DOCS_GOVERNANCE_EXPLORATION_REPORT.md` — full docs audit

## Historical Mainline (superseded)

The following was the previous mainline pointer. It is preserved for historical context but is no longer the current entry point:

The previous Owner-facing project mainline was:

`Personal Leveraged Campaign Mainline v0`

Previous reading list:

- `docs/ops/personal-leveraged-campaign-mainline-v0.md`
- `docs/ops/personal-leveraged-campaign-local-sandbox-v0.md`
- `docs/ops/project-branch-and-doc-governance-2026-05-25.md`
- `docs/ops/personal-campaign-risk-rule-matrix-v0.md`
- `docs/ops/personal-campaign-promotion-checklist-v0.md`
- `docs/ops/sq02-downside-cont-strategy-contract-skeleton-v0.md`
- `docs/adr/0008-personal-leveraged-campaign-business-chain.md`
- `docs/ops/project-roadmap-v2.md`
- `docs/ops/research-to-runtime-promotion-gate.md`
- `docs/ops/runtime-safety-boundary.md`

The short chain is:

`small-capital risk control -> opportunity detection -> human arm/pause -> strategy contract -> trade intent -> risk order plan -> execution lifecycle -> position/campaign/profit-protection control`

## Active Research Context

Current research context is tracked in:

- `docs/ops/opportunity-research-governance-v0.md`
- `docs/ops/opportunity-research-control-board.md`
- `docs/ops/opportunity-hypothesis-register.md`

Research documents may inform strategy-contract design, but they do not
authorize real live trading, real-funds orders, real API key changes, live
account permission changes, withdrawal, transfer, leverage expansion, sizing
advice, or direct research-to-real-order wiring. Research-only/read-only labels
are scope-limited to those documents and do not globally prohibit controlled
testnet/dev/readiness work under `agent-current-brc-baseline.md`.

## Runtime Safety Context

Live-safe v1 documents remain useful as execution-safety foundation material.
They are not the current business mainline and do not authorize real trading.

Important runtime-safety references:

- `docs/ops/live-safe-v1-program.md`
- `docs/ops/live-safe-v1-task-board.md`
- `docs/ops/live-safe-v1-findings.md`
- `docs/adr/0001-live-safe-v1-scope.md`

## Historical Source Material

Older files under `docs/gpt/`, Direction A, CPM, Strategy Research Re-entry,
and BTC+ETH Phase 1 are historical source or evidence archive material unless a
current SSOT document explicitly promotes them.

Archived pre-reset material remains under:

- `archive/2026-04-29-pre-live-safe-replan/docs/`

## Local Schemas

Personal Leveraged Campaign local object schemas live under:

- `docs/schemas/personal_campaign/`

These schemas are docs/design contracts only. They do not authorize runtime,
paper/testnet/live/tiny-live, real API keys, real account actions, real orders,
or any withdrawal path. Owner handles withdrawals outside this system.
