---
title: AGENT_WORKSPACE_RULES
status: CURRENT_CANON
authority: owner-instruction + code-verification + owner-workspace-correction-2026-06-13
last_verified: 2026-06-13
source_of_truth:
  - CLAUDE.md
  - AGENTS.md
  - docs/ops/agent-working-rules.md
  - docs/ops/codex-claude-handoff-template.md
  - owner semantic audit 2026-06-09
  - owner workspace / long-goal authorization 2026-06-13
---

# Agent Workspace Rules

This document defines agent operating rules for the BRC project.

---

## 1. Required Reading

Agent must read these files before starting project work, in order:

1. `AGENTS.md` / `CLAUDE.md` — root entry points and role definitions
2. `docs/canon/PROJECT_BASELINE_CURRENT.md` — current project reality
3. `docs/canon/BRC_TARGET_SEMANTICS.md` — target semantics and node status
4. `docs/canon/RUNTIME_SAFETY_BOUNDARY.md` — execution safety boundaries
5. `docs/canon/TECH_DEBT_BASELINE.md` — known debt classification
6. `docs/canon/DOCUMENT_GOVERNANCE.md` — document authority and trust rules

Then read the specific task card and any referenced ADRs.

---

## 2. Agent Role Boundaries

**Codex** owns:

- Requirements analysis, planning, architecture, core decisions.
- Core implementation and skeleton development.
- Review and merge readiness decisions.

**Claude** owns:

- Scoped implementation from Codex-issued task cards.
- Tests for a clearly scoped change.
- Localized docs updates when requested.

**Shared rules**:

- Real live trading / order placing is allowed by default only through the
  official auditable BRC runtime / Operation Layer path when current
  action-time gates pass.
- Do not infer current state from archive docs.
- Do not promote readmodel / metadata chain into execution chain.
- Do not treat one-shot execution as final architecture.
- Do not treat StrategyRuntimeInstance as execution authority by itself.

---

## 2.1 Current Workspace Discipline

Current mainline development must happen in:

```text
/Users/jiangwei/Documents/final
```

Current mainline branch:

```text
program/live-safe-v1
```

The older integration worktree path:

```text
/Users/jiangwei/Documents/final-sprint6-integration
```

has been retired after the 2026-06-13 workspace consolidation. It must not be
used for new mainline runtime, execution, deployment, or strategy runtime
governance changes unless a future Owner decision explicitly recreates and
verifies that worktree.

Before each stage commit, Codex must report:

1. current working directory;
2. current branch;
3. current HEAD commit;
4. whether the commit is deployed;
5. whether the stage touched exchange write, `OrderLifecycle`, or
   first-real-submit execution paths.

## 2.1.1 Long-running Goal Authorization Baseline

Owner confirmed the following long-running goal baseline on 2026-06-13 for
P0/P1/P2 runtime-governance continuation:

1. Codex may correct stale canon / agent workspace instructions that still
   point to retired worktrees.
2. Codex may create `codex/*` focused branches from `program/live-safe-v1`.
3. Codex may make local commits for completed and verified stages. Push and
   deploy remain separate actions unless the active stage explicitly requires
   them and the boundary is reported.
4. Codex may run focused tests, local dry-runs, read-only runtime / Tokyo /
   account / position / protection / budget probes, and browser UI validation.
5. Real order placement is excluded from the default goal scope. It may enter
   only through the official auditable BRC runtime / Operation Layer action
   path when current action-time gates pass.
6. Codex may use bounded Claude / side workers for non-core tasks such as
   runbooks, UI panels, focused tests, and archive hygiene.
7. Core execution / risk files remain Codex-controlled by default and must not
   be modified concurrently by side workers.
8. P2 archive hygiene means migration, namespace consolidation, and evidence /
   compatibility preservation. It does not mean broad deletion or evidence
   disposal.

## 2.2 Execution-Chain Stage Discipline

Runtime and execution-chain work must use a local-first verification cadence:

| Stage | Required proof |
| ----- | -------------- |
| Local domain | model / policy / packet unit test |
| Local application | service result test with fake repositories or fake gateway |
| Local API / script | dry-run JSON response or report file |
| Tokyo integration | deployment, migration, live-fact, or gated exchange-action proof |
| Stage commit | commit hash plus path, branch, deployment status, and touched-authority summary |

Tokyo is for integration and live-fact validation, not first-pass debugging of
new execution-chain nodes. Direct Tokyo debugging is allowed only when the
thing being verified is inherently remote: deployment state, real exchange
account/order/position facts, Tokyo PG state, service process state, or an
explicitly gated real exchange action.

After a real submit has produced a durable execution result, agents must not
retry the consumed authorization through pre-submit rehearsal or require local
orders to return to `CREATED`. The correct mainline is post-submit finalize,
budget / attempt settlement, protection and reconciliation review, then next
attempt gating from a fresh strategy signal and fresh authorization evidence.

---

## 3. Task Card Required Fields

A task card must include:

| Field | Purpose |
| ----- | ------- |
| Task ID | Unique identifier |
| Objective | One bounded outcome |
| Scope | Why this task exists and how it fits |
| Allowed files | Files the agent may read/write |
| Forbidden files | Files the agent must not touch |
| Safety boundary | Live/real-funds restrictions |
| Expected output | Specific deliverables |
| Validation | How to verify success |
| Rollback notes | How to undo if needed |

Agent must stop and report if it needs files outside Allowed files.

---

## 4. Red Lines

- No secret output (API keys, tokens, credentials, private keys, database URLs).
- No uncontrolled order path outside official ActionSpec -> FinalGate ->
  Operation Layer chain.
- No direct or unaudited exchange scripts outside the official runtime /
  Operation Layer action path.
- No treating StrategyRuntimeInstance as execution authority by itself.
- No treating one-shot execution as final architecture.
- No using docs/archive or docs/ops/ historical docs as current fact source.
- No running project without explicit instruction.
- No modifying files outside task scope.
- No optimizing strategy returns or tuning strategy parameters.
- No hard-coding return or drawdown targets as system constraints.

---

## 5. Evidence Standard

Agent conclusions must be graded:

| Level | Meaning | Example |
| ----- | ------- | ------- |
| Code fact | Verified by reading tracked code | "FinalGate exists in `final_gate_service.py`" |
| Verified report | Verified by reading current canon document | "Current project is BRC strategy runtime governance" |
| Historical evidence | Found in historical/archive docs | "Original project was research-only signal detection" |
| Static inference | Inferred from code structure but not directly observed | "This module likely connects to X based on imports" |
| Unknown | Cannot determine from available evidence | "Status of untracked migration 022 is unclear" |

Do not promote historical evidence or static inference to code fact without
verification.

---

## 6. Handoff Format

Agent must return results in this format:

```markdown
## Summary
One paragraph: what was done, key findings.

## Files inspected
- path/to/file (read-only)
- path/to/file (modified)

## Code facts
- Fact 1 (evidence: file:line)
- Fact 2 (evidence: file:line)

## Static inferences
- Inference 1 (confidence: high/medium/low)

## Risks
- Risk 1

## Hard blockers
- Blocker 1, or "none"

## Safety proof
How safety boundaries were preserved.

## Validation
- Validation 1

## Next questions
- Question 1 (for Owner / Codex to decide)
```

Do not include "Next recommended task" or "What should we do next". The project
controller decides sequencing.
