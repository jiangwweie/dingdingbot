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

# Opportunity Research Governance v0

Last updated: 2026-05-25

Status: Active governance pointer

Runtime effect: none

Trading permission effect: none

## Role

This file is the lightweight governance entry point for the current research
surface. It exists so agents and humans have a stable SSOT pointer before
reading the active board and register.

## Current Owner-Facing Mainline

The business mainline is:

`Personal Leveraged Campaign Mainline v0`

Primary documents:

- `docs/ops/personal-leveraged-campaign-mainline-v0.md`
- `docs/adr/0008-personal-leveraged-campaign-business-chain.md`
- `docs/ops/project-roadmap-v2.md`

## Current Research SSOT

Read these for opportunity research state:

- `docs/ops/opportunity-research-control-board.md`
- `docs/ops/opportunity-hypothesis-register.md`

Research outputs are allowed to become no-order review aids, strategy-contract
design inputs, or evidence archive. They do not become runtime authority.

## Promotion Boundary

Any path from research toward runtime, paper, testnet, live, tiny-live, account
access, order placement, order modification, order cancellation, transfer,
withdrawal, leverage, sizing, or direct research-to-order wiring must pass:

- `docs/ops/research-to-runtime-promotion-gate.md`
- `docs/ops/runtime-safety-boundary.md`

## Current Design Candidate

`SQ02_DOWNSIDE_CONT_V0` is the first docs-only strategy-contract skeleton
candidate. It is not a scanner, alert, watchlist, runtime, paper, testnet,
tiny-live, live, account, leverage, sizing, or real order-path candidate.

## Historical Material

Direction A, CPM, BTC+ETH Phase 1, Strategy Research Re-entry, and old
Live-safe mainline wording are evidence archive or runtime-safety foundation
material unless a current SSOT document explicitly re-promotes them.
