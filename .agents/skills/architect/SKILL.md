---
name: architect
description: Codex architecture workflow. Use for system-level decisions, ADRs, trade-offs, boundaries, or Live-safe v1 core design.
user-invocable: true
---

# Architect (Codex)

## Read First

- `AGENTS.md`
- `CLAUDE.md`
- `docs/current/OWNER_RUNTIME_OPERATING_MODEL.md`
- `docs/current/AI_AGENT_CONSTRAINTS.md`
- `docs/current/BLOCKER_CLASSIFICATION_CONTRACT.md`
- `docs/current/MAIN_CONTROL_DAILY_LIVE_ENABLEMENT_TABLE_CONTRACT.md`
- `docs/current/WIP_AND_STOP_RULE_CONTRACT.md`
- `docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md`
- `docs/current/MAIN_CONTROL_ROADMAP.md`
- `docs/current/strategy-group-handoffs/STRATEGYGROUP_REGISTRY_CONTRACT.md`
- `docs/current/strategy-group-handoffs/main-control-handoff-index.md`

Current required context is `AGENTS.md` plus `docs/current/*`.
Historical archive material is recovery/provenance only and must not be used as current project truth.

## Role

Codex owns architecture decisions. Provide options and trade-offs when the decision is meaningful, then wait for user confirmation before implementing high-impact changes.

Prefer current tracked code, `docs/current/*`, and accepted Owner decisions over historical ADR or archive material.

## Deliverables

- Architecture assessment.
- 2+ options with trade-offs when appropriate.
- Recommended direction.
- Affected core files.
- Test and rollback strategy.
- ADR when a durable decision is accepted.
- Live Enablement state transition when the decision touches StrategyGroup,
  detector, watcher, scope, blocker, replay/live parity, or execution path.
- WIP impact and stop condition when the decision changes active mainline work.

## Constraints

- Do not force OpenAPI or PRD artifacts unless the task actually changes an API/product contract.
- Do not optimize strategies during P0 Live-safe work.
- Do not change live profiles or real-funds permissions without explicit user
  approval. Testnet/dev/profile-scoped readiness or cleanup is governed by the
  current agent baseline.
- Treat new packet, bridge, adapter, readiness, evidence, compatibility, or
  other glue layers as architecture smell. Before accepting one, state whether
  the core abstraction should instead be extended, replaced, or deleted; whether
  the requirement or project goal has changed; and which old path is replaced,
  removed, or retired. Glue is acceptable only with a bounded replacement or
  removal condition and without becoming a second source of truth.
- Treat runtime JSON/Markdown file reads and recurring JSON/Markdown report
  writes as architecture debt, not as a stable integration layer. The preferred
  architecture action is delete; if current runtime state is needed, migrate it
  to PG/current services; if only provenance remains, move it to archive-only
  tooling. Do not design new production flows that depend on repo/output/report
  files.
- Treat dynamic-path evidence JSON writers, YAML config import/export file
  interfaces, JSONL trace/observe sidecars, and tests that create legacy report
  JSON fixtures as file-authority debt even when they are not literal
  `latest-*.json` paths. Delete them, migrate useful current semantics to
  PG/current services, or move pure history to archive-only provenance.
- Treat current artifact/proof/evidence scripts with JSON/Markdown file
  inputs/outputs, report directories, or artifact file CLI parameters as
  architecture debt even when they are outside production cadence. Delete them
  by family, migrate useful semantics to PG/current projections, or move pure
  history to archive-only provenance.
- Treat file-backed repositories, local comparison readers, artifact-file
  validators, and JSON fixture CLIs in current `src/` or runtime `scripts/` as
  architecture debt. They must be deleted from the current path or rewritten to
  PG/current services; "non-production fallback" is not an acceptable current
  abstraction.
- Every runtime, deploy, monitor, readmodel, watcher, action-time, or Owner
  explanation architecture decision must include cadence and performance
  impact: no-signal tick file growth target, PG row growth, CPU-heavy trigger,
  timeout boundary, disk/retention behavior, and archive-only cleanup rule.
- Do not accept explanation-only, audit-only, or artifact-only completion for
  live-enablement work. The architecture outcome must remove a blocker,
  reclassify it with per-symbol / per-fact evidence, prove
  `market_wait_validated`, or stop at explicit Owner policy / hard safety.
- Do not add or preserve active roadmap lanes outside the WIP contract unless a
  current lane exits mainline or Owner explicitly changes scope.
