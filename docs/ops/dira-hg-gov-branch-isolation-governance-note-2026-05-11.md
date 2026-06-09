> [!NOTE]
> **HISTORICAL_EVIDENCE** — This document is a historical research artifact from an earlier project phase.
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

# DIRA-HG-GOV — Branch Isolation & Governance Note

Last updated: 2026-05-11

## 1. Should This Work Proceed on an Isolated Branch?

**Yes.**

All DIRA-HG documents (HG-001, HG-002, HG-003) are docs-only planning artifacts that belong on an isolated branch. They do not modify runtime code, strategy logic, risk rules, profiles, or configuration.

Branch isolation ensures:

- The old Live-safe mainline continues stable and uninterrupted.
- The DIRA-HG docs are visible and reviewable without being mixed into Live-safe task-board status.
- Future implementation work (if authorized) can be staged on the same branch without contaminating the mainline.

## 2. Suggested Branch Name

```
docs/dira-human-gating-level2-level3
```

Rationale:

- `docs/` prefix signals that the current content is documentation only.
- `dira-human-gating` scopes the branch to Direction A human-gating work.
- `level2-level3` references the two active Owner priorities: Level 2 (paper admission process design) and Level 3 (runtime permission hook inspect/design).

Alternative if preferred:

```
docs/dira-human-gate-permission-hook-inspect
```

## 3. How to Keep the Old Live-safe Mainline Stable

The Live-safe mainline continues on its existing branch (`dev` or `program/live-safe-v1`). Rules:

- DIRA-HG work does NOT touch any Live-safe P0/P1/P2 task-board items.
- DIRA-HG work does NOT modify core execution files (`execution_orchestrator.py`, `order_lifecycle_service.py`, `capital_protection.py`, `exchange_gateway.py`, `reconciliation.py`, `startup_reconciliation_service.py`, `position_projection_service.py`).
- DIRA-HG work does NOT modify config, profiles, tests, or runtime wiring.
- DIRA-HG work does NOT change ADRs or program files under `docs/ops/live-safe-v1-*`.
- DIRA-HG docs are committed on the `docs/dira-human-gating-level2-level3` branch only.

When DIRA-HG docs are ready for Owner review, they can be merged to `dev` as a docs-only commit. This merge is low-risk because no code, config, or runtime files change.

## 4. Which Parts Are Docs-Only and Can Move Quickly

All three artifacts are docs-only and can move quickly:

| Artifact | Content | Speed |
|---|---|---|
| DIRA-HG-001 | Human-gating decision-process draft (already exists). | Owner review only. |
| DIRA-HG-002 | Paper admission & human-gated process spec. | Owner review. Can be updated iteratively. |
| DIRA-HG-003 | Runtime permission hook inspect/design. | Owner review. Can be updated iteratively. |
| DIRA-HG-GOV | This governance note. | Reference only. |

No implementation, tests, adapters, or code changes are involved in this phase.

## 5. Which Parts Would Become Strict Later

The following would become strict (require Codex task cards, core-file review, risk assessment, and Owner approval) if the Owner authorizes future implementation:

| Future work | Why it becomes strict |
|---|---|
| Runtime human gate check in `execution_orchestrator.py` | Touches core execution path. Affects signal-to-order flow. |
| `HumanGateService` implementation | New service in `src/application/`. Requires architecture review. |
| Gate state persistence | New database tables or storage. Requires migration and fail-safe testing. |
| `ExecutionIntent` status extension (`GATE_BLOCKED`) | Changes the intent lifecycle model. |
| Decision Trace extension (`risk.human_gate_check`) | Extends the trace backbone. |
| Paper-mode configuration | New runtime profile or config. Requires isolation from live profiles. |
| `ON_ALLOWED_SMALL` / `REDUCE` sizing logic | Changes order sizing. This is a capital-risk decision. |

All of these would require:

- Owner authorization.
- Codex task card with allowed/forbidden files.
- Core-file review.
- Risk impact and rollback notes.
- Separate branch from the docs branch.

## 6. What Must Not Block Old Live-safe Work

The following DIRA-HG dependencies must not block Live-safe work:

- DIRA-HG-001 Owner review does not block any Live-safe P0 task.
- DIRA-HG-002 prerequisites (metric resolution, rehearsal logs) do not block any Live-safe task.
- DIRA-HG-003 design review does not block any Live-safe task.
- Branch isolation means DIRA-HG commits do not appear on the Live-safe branch.
- DIRA-HG does not modify the Live-safe task board, findings, or progress files.

Live-safe P0 tasks (LS-003, LS-004, LS-005, LS-006, LS-007) continue independently and should not be delayed by DIRA-HG review cycles.

## 7. Summary

| Question | Answer |
|---|---|
| Isolated branch? | Yes. |
| Branch name? | `docs/dira-human-gating-level2-level3` |
| Live-safe mainline stable? | Yes. No code, config, or runtime files touched by DIRA-HG. |
| Quick-moving parts? | All three DIRA-HG docs. |
| Strict-later parts? | Any runtime implementation of the gate (core files, persistence, trace extension, sizing). |
| Must not block Live-safe? | All DIRA-HG work. Live-safe P0 continues independently. |
