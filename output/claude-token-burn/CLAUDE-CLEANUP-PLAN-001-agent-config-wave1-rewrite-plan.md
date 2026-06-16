# CLAUDE-CLEANUP-PLAN-001 Agent Config Wave 1 Rewrite Plan

Generated: 2026-06-16
Task ID: CLAUDE-CLEANUP-PLAN-001
Scope: Wave 1 — agent configuration alignment to current authoritative docs

---

## Summary

**Problem**: 35 active files under `.claude/` and `.agents/skills/` reference dead
documentation paths (`docs/canon/*`, `docs/ops/*`, `docs/adr/*`) that were removed
during the 2026-06-15 governance archive. Agents reading these files get broken
context instructions.

**Dead paths confirmed**:
- `docs/canon/` — does not exist
- `docs/ops/` — does not exist
- `docs/adr/` — does not exist

**Authoritative replacements** (from AGENTS.md and CLAUDE.md):

| Dead Path | Current Authority |
|---|---|
| `docs/canon/AGENT_WORKSPACE_RULES.md` | `AGENTS.md` |
| `docs/canon/PROJECT_BASELINE_CURRENT.md` | `AGENTS.md` (Product Objective, StrategyGroup Runtime Path) |
| `docs/canon/BRC_TARGET_SEMANTICS.md` | `AGENTS.md` (Product Objective), `CLAUDE.md` (Current Product Direction) |
| `docs/canon/RUNTIME_SAFETY_BOUNDARY.md` | `docs/current/AI_AGENT_CONSTRAINTS.md` |
| `docs/canon/TECH_DEBT_BASELINE.md` | No current equivalent — remove reference |
| `docs/canon/DOCUMENT_GOVERNANCE.md` | No current equivalent — remove reference |
| `docs/ops/agent-current-brc-baseline.md` | `AGENTS.md` |
| `docs/ops/live-safe-v1-program.md` | `docs/current/OWNER_RUNTIME_OPERATING_MODEL.md` |
| `docs/ops/agent-working-rules.md` | `AGENTS.md` + `CLAUDE.md` |
| `docs/ops/live-safe-v1-task-board.md` | No current equivalent — remove reference |
| `docs/ops/live-safe-v1-progress.md` | No current equivalent — remove reference |
| `docs/ops/live-safe-v1-findings.md` | No current equivalent — remove reference |
| `docs/adr/*` | No current equivalent — remove reference |

**Additional dead references found**:
- `docs/v3/phase3-risk-state-machine-contract.md` (in agentic-workflow README)
- `docs/arch/系统开发规范与红线.md` (in AGENTIC-WORKFLOW-GUIDE.md)
- `docs/planning/*` (in several files — already warned against, but still referenced)
- `docs/gpt/*` (in architect SKILL.md — already warned against)
- `docs/features/stop-loss.md` (in pua-skill — example reference)

---

## Rewrite Rules

### Rule 1: Read First sections → point to current authorities

Replace all `docs/canon/*` and `docs/ops/*` "Read First" lists with:

```markdown
## Read First

- `AGENTS.md`
- `CLAUDE.md`
- `docs/current/OWNER_RUNTIME_OPERATING_MODEL.md`
- `docs/current/AI_AGENT_CONSTRAINTS.md`
- `docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md`
```

Trim to role-relevant subset when the file is a narrow role skill (e.g., QA
doesn't need all five).

### Rule 2: Superseded/Quarantined headers → fix the authority list

Files with `> [!CAUTION]` headers that list `docs/canon/*` as "current
authoritative instructions" must be updated to list the actual current paths.

### Rule 3: Progress/task-board references → remove or replace with Memory MCP

References to `docs/ops/live-safe-v1-progress.md`, `live-safe-v1-task-board.md`,
and `live-safe-v1-findings.md` have no current equivalent. Replace with:
- "Use Memory MCP for durable decisions and rules only."
- Remove file-specific write instructions.

### Rule 4: ADR references → remove

`docs/adr/` doesn't exist. Remove "Relevant ADRs" and "Uses `docs/adr/`" lines.

### Rule 5: Dead example paths → remove or update

Paths like `docs/v3/...`, `docs/arch/...`, `docs/features/...` in example code
blocks should be removed or replaced with current paths.

### Rule 6: Duplicate structure — .agents/skills/ mirrors .claude/team/

`.agents/skills/` files are thin wrappers pointing to `.claude/team/` SSOT.
For those that also have their own "Read First" lists with dead refs, rewrite
the Read First list. The `.claude/team/` SKILL.md files are the SSOT and get
the full rewrite.

---

## File-by-File Plan

### Group A: Active Role Skills — .agents/skills/ (high priority, loaded at runtime)

| # | File | Current Problem | Exact Replacement Direction | Action | Risk |
|---|---|---|---|---|---|
| A1 | `.agents/skills/architect/SKILL.md` | 12 dead refs: all docs/canon/*, docs/ops/*, docs/adr/*, docs/gpt/* | Replace Read First with: `AGENTS.md`, `CLAUDE.md`, `docs/current/OWNER_RUNTIME_OPERATING_MODEL.md`, `docs/current/AI_AGENT_CONSTRAINTS.md`, `docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md`. Remove "Relevant docs/adr/" line. Remove docs/gpt warning (no longer needed). Remove "For Live-safe v1, prefer ADRs" line. | Rewrite | Low |
| A2 | `.agents/skills/kaigong/SKILL.md` | 6 dead refs: docs/ops/* files, "Relevant ADRs" | Replace Read with: `AGENTS.md`, `CLAUDE.md`, `docs/current/OWNER_RUNTIME_OPERATING_MODEL.md`. Remove task-board/progress/findings refs. Remove "Relevant ADRs". Keep "Do not use old docs/planning/*" warning. | Rewrite | Low |
| A3 | `.agents/skills/shougong/SKILL.md` | 6 dead refs: docs/ops/* read + write targets | Replace Read with: `AGENTS.md`, `CLAUDE.md`. Remove all docs/ops/* write targets. Replace with: "Write Memory MCP only for durable rules or accepted decisions." Keep "Do not recreate old docs/planning/*" warning. | Rewrite | Low |
| A4 | `.agents/skills/pm/SKILL.md` | 7 dead refs: docs/ops/* read + write targets | Replace Read First with: `AGENTS.md`, `CLAUDE.md`, `docs/current/OWNER_RUNTIME_OPERATING_MODEL.md`. Remove docs/ops/* write targets. Replace with Memory MCP guidance. | Rewrite | Low |
| A5 | `.agents/skills/backend/SKILL.md` | 3 dead refs: docs/ops/* | Replace Read First with: `AGENTS.md`, `CLAUDE.md`. Remove "Relevant ADRs and task board entries". | Rewrite | Low |
| A6 | `.agents/skills/qa/SKILL.md` | 2 dead refs: docs/ops/* | Replace Read First with: `AGENTS.md`, `CLAUDE.md`. Remove "The relevant task card or ADR" → "The relevant task card". | Rewrite | Low |
| A7 | `.agents/skills/reviewer/SKILL.md` | 3 dead refs: docs/ops/* | Replace Read First with: `AGENTS.md`, `CLAUDE.md`. | Rewrite | Low |
| A8 | `.agents/skills/pua-skill/SKILL.md` | 2 dead refs: docs/ops/* in "必须读取的项目文件" | Replace context read list with: `AGENTS.md`, `CLAUDE.md`, `.claude/team/backend-dev/SKILL.md`, `.claude/team/frontend-dev/SKILL.md`. Remove docs/ops lines. | Rewrite | Low |
| A9 | `.agents/skills/frontend/SKILL.md` | 0 dead refs | No change needed. | Keep | None |
| A10 | `.agents/skills/diagnostic/SKILL.md` | 0 dead refs | No change needed. | Keep | None |
| A11 | `.agents/skills/product-manager/SKILL.md` | 0 dead refs | No change needed. | Keep | None |

### Group B: Active Role Skills — .claude/team/ (SSOT for team roles)

| # | File | Current Problem | Exact Replacement Direction | Action | Risk |
|---|---|---|---|---|---|
| B1 | `.claude/team/architect/SKILL.md` | 7 dead refs: docs/canon/*, docs/ops/*, docs/gpt/* | Replace "Primary" context with: `AGENTS.md`, `CLAUDE.md`, `docs/current/OWNER_RUNTIME_OPERATING_MODEL.md`, `docs/current/AI_AGENT_CONSTRAINTS.md`, `docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md`. Remove "Additional context" docs/ops/* block. Remove docs/gpt note. | Rewrite | Low |
| B2 | `.claude/team/backend-dev/SKILL.md` | 2 dead refs: docs/ops/* | Replace "Before Editing" read list with: `CLAUDE.md`, `AGENTS.md`. | Rewrite | Low |
| B3 | `.claude/team/code-reviewer/SKILL.md` | 2 dead refs: docs/ops/* | Replace "Required Context" with: `CLAUDE.md`, `AGENTS.md`. | Rewrite | Low |
| B4 | `.claude/team/diagnostic-analyst/SKILL.md` | 1 dead ref: docs/ops/* | Replace "Required Context" with: `CLAUDE.md`. | Rewrite | Low |
| B5 | `.claude/team/frontend-dev/SKILL.md` | 1 dead ref: "不自动更新 docs/ops/*" | Change to: "不自动更新 docs/current/* unless explicitly asked." | Rewrite | Low |
| B6 | `.claude/team/product-manager/SKILL.md` | 1 dead ref: docs/ops/live-safe-v1-program.md | Change "active program scope" line to: `docs/current/OWNER_RUNTIME_OPERATING_MODEL.md`. | Rewrite | Low |
| B7 | `.claude/team/project-manager/SKILL.md` | 4 dead refs: docs/ops/* | Replace "Required Inputs" read list with: `CLAUDE.md`, `AGENTS.md`. Remove docs/ops/* write targets. Replace with Memory MCP guidance. Remove "Do not recreate old docs/planning/*" (keep as warning only). | Rewrite | Low |
| B8 | `.claude/team/README.md` | 6 dead refs: docs/ops/*, docs/adr/ | Replace "Active Docs" block with: `AGENTS.md`, `CLAUDE.md`, `docs/current/OWNER_RUNTIME_OPERATING_MODEL.md`, `docs/current/AI_AGENT_CONSTRAINTS.md`, `docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md`. Remove docs/adr/ line. | Rewrite | Low |
| B9 | `.claude/team/WORKFLOW.md` | 7 dead refs: docs/ops/*, docs/adr/, docs/planning/* | Replace "Active Planning Files" with current authorities. Remove docs/adr/ references. Keep "Do not use old docs/planning/*" warning. Remove "Uses docs/adr/ for accepted decisions" from Architect role section. | Rewrite | Low |
| B10 | `.claude/team/qa-tester/SKILL.md` | 0 dead refs | No change needed. | Keep | None |

### Group C: Active Slash Commands — .claude/commands/

| # | File | Current Problem | Exact Replacement Direction | Action | Risk |
|---|---|---|---|---|---|
| C1 | `.claude/commands/kaigong.md` | 6 dead refs: docs/ops/*, docs/adr/ | Replace Read list with: `CLAUDE.md`, `AGENTS.md`, `docs/current/OWNER_RUNTIME_OPERATING_MODEL.md`. Remove docs/adr/ line. Keep "Do not use old docs/planning/*" warning. | Rewrite | Low |
| C2 | `.claude/commands/shougong.md` | 5 dead refs: docs/ops/* read + write | Replace Read with: `CLAUDE.md`, `AGENTS.md`. Remove docs/ops/* write targets. Replace with Memory MCP guidance. Keep "Do not recreate old docs/planning/*" warning. | Rewrite | Low |
| C3 | `.claude/commands/architect.md` | 2 dead refs: docs/ops/* | Replace Read with: `CLAUDE.md`, `.claude/team/architect/SKILL.md`. | Rewrite | Low |
| C4 | `.claude/commands/pm.md` | 3 dead refs: docs/ops/* | Replace Read with: `CLAUDE.md`, `.claude/team/project-manager/SKILL.md`. | Rewrite | Low |
| C5 | `.claude/commands/backend.md` | 2 dead refs: docs/ops/* | Replace Read with: `CLAUDE.md`, `.claude/team/backend-dev/SKILL.md`. | Rewrite | Low |
| C6 | `.claude/commands/reviewer.md` | 2 dead refs: docs/ops/* | Replace Read with: `CLAUDE.md`, `.claude/team/code-reviewer/SKILL.md`. | Rewrite | Low |
| C7 | `.claude/commands/qa.md` | 2 dead refs: docs/ops/* | Replace Read with: `CLAUDE.md`, `.claude/team/qa-tester/SKILL.md`. | Rewrite | Low |
| C8 | `.claude/commands/frontend.md` | 2 dead refs: docs/ops/* | Replace Read with: `CLAUDE.md`, `.claude/team/frontend-dev/SKILL.md`. | Rewrite | Low |
| C9 | `.claude/commands/diagnostic.md` | 1 dead ref: docs/ops/* | Replace Read with: `CLAUDE.md`, `.claude/team/diagnostic-analyst/SKILL.md`. | Rewrite | Low |
| C10 | `.claude/commands/product-manager.md` | 1 dead ref: docs/ops/* | Replace Read with: `CLAUDE.md`, `.claude/team/product-manager/SKILL.md`. | Rewrite | Low |

### Group D: Quarantined/Superseded files — fix authority headers

These files are already marked as historical but their CAUTION headers list
`docs/canon/*` as "current authoritative instructions", which is itself wrong.

| # | File | Current Problem | Exact Replacement Direction | Action | Risk |
|---|---|---|---|---|---|
| D1 | `.claude/AGENTIC-WORKFLOW-GUIDE.md` | Header lists docs/canon/* as authority; body refs docs/v3/*, docs/arch/* | Fix header authority list to: `AGENTS.md`, `CLAUDE.md`, `docs/current/OWNER_RUNTIME_OPERATING_MODEL.md`, `docs/current/AI_AGENT_CONSTRAINTS.md`, `docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md`. Body is historical — leave as-is. | Rewrite header only | Low |
| D2 | `.claude/MCP-ORCHESTRATION.md` | Header lists docs/canon/* as authority | Same header fix as D1. Body is historical — leave as-is. | Rewrite header only | Low |
| D3 | `.claude/TEAM-SETUP-SUMMARY.md` | Header lists docs/canon/* as authority | Same header fix as D1. Body is historical — leave as-is. | Rewrite header only | Low |
| D4 | `.claude/team/QUICK-REFERENCE.md` | Header lists docs/canon/* as authority | Same header fix as D1. Body is historical — leave as-is. | Rewrite header only | Low |
| D5 | `.claude/team/QUICKSTART.md` | Header lists docs/canon/* as authority | Same header fix as D1. Body is historical — leave as-is. | Rewrite header only | Low |
| D6 | `.claude/skills/agentic-workflow/README.md` | Header lists docs/canon/* as authority | Same header fix as D1. Body is historical — leave as-is. | Rewrite header only | Low |
| D7 | `.agents/skills/agentic-workflow/README.md` | Header lists docs/canon/* as authority | Same header fix as D1. Body is historical — leave as-is. | Rewrite header only | Low |

### Group E: Skills with dead internal references

| # | File | Current Problem | Exact Replacement Direction | Action | Risk |
|---|---|---|---|---|---|
| E1 | `.claude/skills/pua-skill/SKILL.md` | 2 dead refs: docs/ops/* in context read list | Replace context read list with: `CLAUDE.md`, `AGENTS.md`, `.claude/team/backend-dev/SKILL.md`, `.claude/team/frontend-dev/SKILL.md`. | Rewrite | Low |
| E2 | `.claude/skills/doc-manager/SKILL.md` | References docs/active/, docs/constraints/, docs/archive/ which may not exist | Out of scope for Wave 1 — this skill manages docs/ structure itself. Flag for Wave 2 review. | Flag | Medium |
| E3 | `.claude/skills/doc-manager/scripts/classify.py` | References docs/planning/archive, docs/arch/archive, etc. | Out of scope for Wave 1 — script internals. Flag for Wave 2. | Flag | Medium |
| E4 | `.claude/skills/doc-manager/scripts/scan.py` | References docs/planning/task_plan.md, docs/templates/, docs/arch/ | Out of scope for Wave 1 — script internals. Flag for Wave 2. | Flag | Medium |

### Group F: Memory files

| # | File | Current Problem | Exact Replacement Direction | Action | Risk |
|---|---|---|---|---|---|
| F1 | `.claude/memory/project-core-memory.md` | 3 dead refs: "Always read docs/canon/ first", "Do not use docs/ops", "If memory conflicts with docs/canon" | Replace docs/canon with `docs/current/*`. Replace docs/ops with removed reference. Update conflict rule to: "If memory conflicts with docs/current/*, docs/current/* wins." | Rewrite | Low |

---

## Minimal Patch Scope

**Wave 1 minimum viable patch** — fix only the files that agents actually load at
runtime (Groups A + B + C = 31 files). Groups D, E, F are lower priority.

**Estimated edits**: ~31 files, ~120 line replacements total.

**Pattern**: Most edits are mechanical — replace a Read First bullet list. No
logic changes, no new files, no deletions.

---

## Validation Commands

After applying the rewrite plan, run these to verify:

```bash
# 1. Zero dead-path references remain in active files
rg -n 'docs/canon/|docs/ops/|docs/adr/' .claude/commands/ .claude/team/ .agents/skills/ .claude/skills/pua-skill/ .claude/memory/project-core-memory.md
# Expected: no output

# 2. Quarantined files have correct authority headers
rg -A5 'QUARANTINED|SUPERSEDED' .claude/AGENTIC-WORKFLOW-GUIDE.md .claude/MCP-ORCHESTRATION.md .claude/TEAM-SETUP-SUMMARY.md .claude/team/QUICK-REFERENCE.md .claude/team/QUICKSTART.md .claude/skills/agentic-workflow/README.md .agents/skills/agentic-workflow/README.md | grep 'docs/'
# Expected: only docs/current/* paths

# 3. All referenced current files actually exist
for f in AGENTS.md CLAUDE.md docs/current/OWNER_RUNTIME_OPERATING_MODEL.md docs/current/AI_AGENT_CONSTRAINTS.md docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md docs/current/MAIN_CONTROL_ROADMAP.md docs/current/strategy-group-handoffs/main-control-handoff-index.md; do
  [ -f "$f" ] && echo "OK: $f" || echo "MISSING: $f"
done

# 4. No broken cross-references between .agents/skills/ and .claude/team/
for f in .agents/skills/*/SKILL.md; do
  refs=$(grep -oP '(?<=\x60)[^\x60]+\.md(?=\x60)' "$f" 2>/dev/null)
  for ref in $refs; do
    [ -f "$ref" ] || echo "BROKEN: $f -> $ref"
  done
done
```

---

## Files Not Worth Preserving

The following files are pure historical artifacts with no runtime agent loading
value. Consider deleting in a future cleanup wave (not Wave 1):

| File | Reason |
|---|---|
| `.claude/team/QUICK-REFERENCE.md` | Superseded, MCP server table is outdated |
| `.claude/team/QUICKSTART.md` | Superseded, describes old parallel-agent workflow |
| `.claude/MCP-ORCHESTRATION.md` | Quarantined, MCP permission matrix is stale |
| `.claude/TEAM-SETUP-SUMMARY.md` | Quarantined, config summary from 2026-04-01 |
| `.claude/AGENTIC-WORKFLOW-GUIDE.md` | Quarantined, agentic workflow from old phase |
| `.claude/skills/agentic-workflow/README.md` | Superseded, skill design from old phase |
| `.agents/skills/agentic-workflow/README.md` | Duplicate of above |
| `.claude/skills/doc-manager/scripts/*.py` | Scripts reference non-existent docs/ structure |

---

## Suggested Codex Patch Order

### Patch 1: Group A — .agents/skills/ active skills (8 files)

Highest impact. These are the runtime-loaded skill definitions.

```
.agents/skills/architect/SKILL.md
.agents/skills/kaigong/SKILL.md
.agents/skills/shougong/SKILL.md
.agents/skills/pm/SKILL.md
.agents/skills/backend/SKILL.md
.agents/skills/qa/SKILL.md
.agents/skills/reviewer/SKILL.md
.agents/skills/pua-skill/SKILL.md
```

### Patch 2: Group C — .claude/commands/ slash commands (10 files)

These are the user-facing `/command` entry points.

```
.claude/commands/kaigong.md
.claude/commands/shougong.md
.claude/commands/architect.md
.claude/commands/pm.md
.claude/commands/backend.md
.claude/commands/reviewer.md
.claude/commands/qa.md
.claude/commands/frontend.md
.claude/commands/diagnostic.md
.claude/commands/product-manager.md
```

### Patch 3: Group B — .claude/team/ SSOT skills (9 files)

The authoritative skill definitions for team roles.

```
.claude/team/architect/SKILL.md
.claude/team/backend-dev/SKILL.md
.claude/team/code-reviewer/SKILL.md
.claude/team/diagnostic-analyst/SKILL.md
.claude/team/frontend-dev/SKILL.md
.claude/team/product-manager/SKILL.md
.claude/team/project-manager/SKILL.md
.claude/team/README.md
.claude/team/WORKFLOW.md
```

### Patch 4: Group D — Quarantined file headers (7 files)

Fix the authority list in CAUTION headers.

```
.claude/AGENTIC-WORKFLOW-GUIDE.md
.claude/MCP-ORCHESTRATION.md
.claude/TEAM-SETUP-SUMMARY.md
.claude/team/QUICK-REFERENCE.md
.claude/team/QUICKSTART.md
.claude/skills/agentic-workflow/README.md
.agents/skills/agentic-workflow/README.md
```

### Patch 5: Groups E+F — Skills and memory (2 files)

```
.claude/skills/pua-skill/SKILL.md
.claude/memory/project-core-memory.md
```

---

## Appendix: Exact Line-Level Replacements

### Standard "Read First" block replacement

**Before** (typical pattern):
```markdown
## Read First

- `AGENTS.md`
- `docs/ops/agent-current-brc-baseline.md`
- `docs/ops/live-safe-v1-program.md`
- `docs/ops/agent-working-rules.md`
- `docs/canon/PROJECT_BASELINE_CURRENT.md`
- `docs/canon/BRC_TARGET_SEMANTICS.md`
- `docs/canon/AGENT_WORKSPACE_RULES.md`
- `docs/canon/RUNTIME_SAFETY_BOUNDARY.md`
- `docs/canon/TECH_DEBT_BASELINE.md`
- `docs/canon/DOCUMENT_GOVERNANCE.md`
- Relevant `docs/adr/`
```

**After** (canonical replacement):
```markdown
## Read First

- `AGENTS.md`
- `CLAUDE.md`
- `docs/current/OWNER_RUNTIME_OPERATING_MODEL.md`
- `docs/current/AI_AGENT_CONSTRAINTS.md`
- `docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md`
```

### Standard CAUTION header replacement

**Before**:
```markdown
> [!CAUTION]
> **QUARANTINED_AGENT_INSTRUCTION** — ...
>
> Current authoritative instructions are:
>
> * `AGENTS.md`
> * `CLAUDE.md`
> * `docs/canon/AGENT_WORKSPACE_RULES.md`
> * `docs/canon/PROJECT_BASELINE_CURRENT.md`
> * `docs/canon/BRC_TARGET_SEMANTICS.md`
> * `docs/canon/RUNTIME_SAFETY_BOUNDARY.md`
```

**After**:
```markdown
> [!CAUTION]
> **QUARANTINED_AGENT_INSTRUCTION** — ...
>
> Current authoritative instructions are:
>
> * `AGENTS.md`
> * `CLAUDE.md`
> * `docs/current/OWNER_RUNTIME_OPERATING_MODEL.md`
> * `docs/current/AI_AGENT_CONSTRAINTS.md`
> * `docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md`
```

### Standard ops write-target removal

**Before**:
```markdown
- Update `docs/ops/live-safe-v1-progress.md` with session progress.
- Update `docs/ops/live-safe-v1-findings.md` if there are program-local findings.
- Update `docs/ops/live-safe-v1-task-board.md` if task status changed.
```

**After**:
```markdown
- Write Memory MCP only for durable rules or accepted decisions.
- Return a concise handoff note in chat.
```
