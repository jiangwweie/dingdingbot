# ADR-0001 Live-safe v1 Scope

## Status

Accepted

2026-05-09 stage note: Live-safe v1 remains accepted as the execution-safety
foundation, but the current Owner-facing mainline is now `Observation +
Research Methodology Reset`. BTC+ETH Phase 1 observation design is the only
current mainline strategy-research object. This note is docs-only and does not
authorize strategy runtime, paper/testnet/live trading, small-live execution,
portfolio/router work, SOL Phase 2, CPM reopening, short-side work, parameter
optimization, or runtime/profile/risk changes.

## Context

The project has been reset from a broad research and execution history into a focused live-safe replanning phase. The current system is treated as Sim-ready, not live-ready.

The user wants Codex to own global reasoning, architecture, planning, core decisions, and core implementation. Claude Code should execute bounded local work and tests from Codex-issued task cards.

The long-term direction is a full-auto, multi-asset, multi-direction, low-frequency portfolio platform. Fixed return and drawdown numbers are investor preferences and evaluation references, not system constraints.

## Decision

Live-safe v1 will focus on execution safety, account-level risk controls, reconciliation, observability, and runtime guardrails.

The program is an execution-layer track under the higher-level roadmap in `docs/ops/project-roadmap-v2.md`.

Program planning will live under `docs/ops/` instead of the old global `docs/planning/` files.

Memory MCP remains enabled for durable decisions and collaboration rules, but daily progress remains in plan-with-files.

System goals will be written as capability goals. Return and drawdown targets must not be encoded into architecture constraints, runtime policy, or agent task rules.

## Consequences

- P0 work does not optimize strategy returns.
- P0 work does not expand asset coverage.
- Claude Code does not self-direct architecture or broad implementation.
- Core execution files are Codex-owned by default.
- Every Claude implementation task requires a bounded task card.
- Future strategy and portfolio work can use return and drawdown metrics for evaluation without locking the system to fixed numeric targets.
