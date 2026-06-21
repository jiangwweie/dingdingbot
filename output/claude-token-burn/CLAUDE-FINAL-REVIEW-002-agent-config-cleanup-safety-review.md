# CLAUDE-FINAL-REVIEW-002 Agent Config Cleanup Safety Review

Generated: 2026-06-16
Mode: read-only review + report
Branch: codex/owner-runtime-console-v1

## Summary

The Codex cleanup pass replaced dead `docs/ops/*`, `docs/canon/*`, `docs/adr/*`
authority references with current `docs/current/*` paths across **27 agent
instruction files**. The diff is scope-safe: it touches only `.agents/skills/`,
`.claude/commands/`, and `.claude/team/` instruction markdown. No runtime source,
tests, scripts, deploy files, live config, or watcher code was modified.

The cleanup is **safe to keep as-is** during mainline acceptance. The active
entrypoints now consistently point to the correct current authority chain.
Remaining dead references exist only in quarantined/historical files and in
source code provenance strings, neither of which affects active agent routing.

## Current Diff Scope

27 files changed, 145 insertions, 127 deletions.

| Directory | Files Changed | Nature |
| --- | --- | --- |
| `.agents/skills/` | 8 SKILL.md files | Authority path rewrite |
| `.claude/commands/` | 10 command files | Authority path rewrite |
| `.claude/team/` | 9 files (README, WORKFLOW, 7 SKILL.md) | Authority path rewrite |

All changes are mechanical replacements of the same pattern:
- Remove: `docs/ops/live-safe-v1-*`, `docs/ops/agent-*`, `docs/canon/*`,
  `docs/adr/`, `docs/gpt/`
- Insert: `AGENTS.md`, `CLAUDE.md`, `docs/current/OWNER_RUNTIME_OPERATING_MODEL.md`,
  `docs/current/AI_AGENT_CONSTRAINTS.md`, `docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md`,
  `docs/current/MAIN_CONTROL_ROADMAP.md`,
  `docs/current/strategy-group-handoffs/main-control-handoff-index.md`

No semantic logic changes. No new behavioral rules. No file deletions.

## Safety Assessment

| Dimension | Verdict |
| --- | --- |
| Runtime source untouched | ✅ Safe — zero `src/` changes |
| Tests untouched | ✅ Safe — zero `tests/` changes |
| Scripts/deploy untouched | ✅ Safe — zero `scripts/` or `deploy/` changes |
| Live config untouched | ✅ Safe — `live-config.env` not modified |
| Watcher/Tokyo operations | ✅ Safe — no operational code touched |
| Exchange/credential risk | ✅ Safe — no exchange-facing changes |
| Git commit/push required | ❌ No — diff is uncommitted, can be held or committed at Codex discretion |
| Mainline interference | ✅ None — instruction files only, no runtime behavior change |
| New blockers introduced | ✅ None — cleanup removes dead paths, does not add gates or blockers |

**Overall: SAFE.** The diff cannot interfere with mainline close-loop or live
acceptance work.

## Active Entrypoints Now Clean

These files were successfully rewritten and now point to the correct current
authority chain:

### `.agents/skills/` (8 files)
- `architect/SKILL.md` — ✅ clean
- `backend/SKILL.md` — ✅ clean
- `kaigong/SKILL.md` — ✅ clean
- `pm/SKILL.md` — ✅ clean
- `pua-skill/SKILL.md` — ✅ clean
- `qa/SKILL.md` — ✅ clean
- `reviewer/SKILL.md` — ✅ clean
- `shougong/SKILL.md` — ✅ clean

### `.claude/commands/` (10 files)
- `architect.md` — ✅ clean
- `backend.md` — ✅ clean
- `diagnostic.md` — ✅ clean
- `frontend.md` — ✅ clean
- `kaigong.md` — ✅ clean
- `pm.md` — ✅ clean
- `product-manager.md` — ✅ clean
- `qa.md` — ✅ clean
- `reviewer.md` — ✅ clean
- `shougong.md` — ✅ clean

### `.claude/team/` (9 files)
- `README.md` — ✅ clean
- `WORKFLOW.md` — ✅ clean
- `architect/SKILL.md` — ✅ clean
- `backend-dev/SKILL.md` — ✅ clean
- `code-reviewer/SKILL.md` — ✅ clean
- `diagnostic-analyst/SKILL.md` — ✅ clean
- `frontend-dev/SKILL.md` — ✅ clean
- `product-manager/SKILL.md` — ✅ clean
- `project-manager/SKILL.md` — ✅ clean

## Remaining Dead References Classified

### Class 1: Quarantined Files With Stale CAUTION Headers (LOW RISK)

These files already have `QUARANTINED_AGENT_INSTRUCTION` or
`SUPERSEDED_AGENT_TEAM_REFERENCE` headers. However, their "Current authoritative
instructions" lists still point to `docs/canon/*` paths which no longer exist.
This is cosmetic — no active agent reads these as primary entrypoints — but the
CAUTION headers should eventually point to the real current authorities.

| File | Status | Dead Refs in Header |
| --- | --- | --- |
| `.claude/AGENTIC-WORKFLOW-GUIDE.md` | Quarantined | `docs/canon/AGENT_WORKSPACE_RULES.md`, `PROJECT_BASELINE_CURRENT.md`, `BRC_TARGET_SEMANTICS.md`, `RUNTIME_SAFETY_BOUNDARY.md` |
| `.claude/MCP-ORCHESTRATION.md` | Quarantined | Same as above |
| `.claude/TEAM-SETUP-SUMMARY.md` | Quarantined | Same as above + `RUNTIME_SAFETY_BOUNDARY.md` |
| `.claude/team/QUICKSTART.md` | Superseded | `docs/canon/AGENT_WORKSPACE_RULES.md`, `PROJECT_BASELINE_CURRENT.md`, `BRC_TARGET_SEMANTICS.md` |
| `.claude/team/QUICK-REFERENCE.md` | Superseded | Same as QUICKSTART |
| `.agents/skills/agentic-workflow/README.md` | Superseded | Same as QUICKSTART |
| `.claude/skills/agentic-workflow/README.md` | Superseded | Same as QUICKSTART |

**Risk**: Low. These files are not active agent entrypoints. The CAUTION header
itself prevents use. But the stale `docs/canon/*` paths in the header could
confuse a human reader or a model that sees the file in a file listing.

**Recommendation**: Wave 1 post-acceptance. Either delete these files entirely or
update the CAUTION header to point to `AGENTS.md` + `docs/current/*`.

### Class 2: Duplicate Skill Copy (LOW RISK)

| File | Dead Refs |
| --- | --- |
| `.claude/skills/pua-skill/SKILL.md` | Lines 27-28: `docs/ops/live-safe-v1-program.md`, `docs/ops/agent-working-rules.md` |

The active version at `.agents/skills/pua-skill/SKILL.md` was already updated.
This is a duplicate copy under `.claude/skills/`.

**Risk**: Low. If an agent resolves to `.claude/skills/pua-skill/SKILL.md`
instead of `.agents/skills/pua-skill/SKILL.md`, it would read dead paths.
However, the active skill routing in the diff points to `.agents/skills/`.

**Recommendation**: Wave 1. Align with the updated `.agents/skills/pua-skill/SKILL.md`.

### Class 3: Memory File Stale Authority Header (LOW RISK)

| File | Dead Refs |
| --- | --- |
| `.claude/memory/project-core-memory.md` line 60 | `docs/canon/` |
| `.claude/memory/project-core-memory.md` line 62 | `docs/product/v2` |
| `.claude/memory/MEMORY.md` | Stale project title "盯盘狗项目记忆系统索引" (2026-03-31) |

**Risk**: Low. The memory file content is informational. Line 60 says "Always
read AGENTS.md / CLAUDE.md and docs/canon/ first" — the first two are correct,
the third is dead. An agent reading this memory might attempt to access
`docs/canon/` and fail.

**Recommendation**: Wave 1. Update the agent reading rule to `docs/current/*`
and keep the rest of the memory content. Update MEMORY.md title.

### Class 4: Source Code Provenance Strings (NO RISK)

`src/` and `tests/` contain ~20 references to `docs/ops/*`, `docs/canon/*`, and
`docs/adr/*` as evidence_ref strings, source_ref annotations, and test fixtures.
These are **provenance strings**, not active instruction paths.

Per `docs/README.md`: "Such references are provenance strings, not current
operating instructions."

**Risk**: None. These are audit trail metadata embedded in domain models and
tests. They do not affect agent routing or runtime behavior.

**Recommendation**: Do not touch during mainline acceptance. Schema/domain
cleanup wave later if desired.

### Class 5: Dead Directory References in doc-manager Skill (NEGLIGIBLE)

| File | Dead Refs |
| --- | --- |
| `.agents/skills/doc-manager/SKILL.md` | `docs/archive/` |
| `.claude/skills/doc-manager/SKILL.md` | `docs/archive/` |
| `.agents/skills/doc-manager/references/rules.md` | `docs/active/`, `docs/constraints/`, `docs/archive/` |
| `.claude/skills/doc-manager/references/rules.md` | Same |
| `.claude/skills/SKILL_VERSIONS.md` | `docs/archive/skills/` |

**Risk**: Negligible. The doc-manager skill is not part of the active runtime
path. These are generic file-management instructions.

**Recommendation**: Low priority. Clean up in any future skill-rewrite wave.

## Potential Interference With Mainline

| Concern | Assessment |
| --- | --- |
| Diff touches runtime code? | **No.** Zero `src/`, `tests/`, `scripts/`, `deploy/` changes. |
| Diff changes agent behavior? | **No.** Only rewrites "read these files first" lists. No new rules, gates, or blockers. |
| Diff could cause agent confusion? | **No.** The new paths all exist and are the correct current authorities. |
| Diff breaks existing commands/skills? | **No.** All commands/skills retain the same structure; only the reference list changed. |
| Diff affects watcher/Tokyo/exchange? | **No.** No operational code touched. |
| Uncommitted diff could conflict? | **Minor.** If mainline also modifies these files, a merge conflict is possible. But these are instruction files, not hot runtime code, so conflict resolution is trivial. |

**Conclusion: Zero interference with mainline close-loop and live acceptance.**

## Recommended Next Actions

### During Mainline Acceptance (Now)

1. **Hold the diff uncommitted or commit it** — either is safe. No urgency.
2. **Do not expand cleanup** to src/, tests/, scripts/, deploy/, or live config.
3. **Do not delete or rewrite quarantined files** — not worth the risk during
   acceptance.

### After Mainline Acceptance (Wave 1)

1. Delete or rewrite CAUTION headers on 7 quarantined/superseded files
   (Class 1).
2. Align `.claude/skills/pua-skill/SKILL.md` with updated
   `.agents/skills/pua-skill/SKILL.md` (Class 2).
3. Update `.claude/memory/project-core-memory.md` agent reading rule from
   `docs/canon/` to `docs/current/*` (Class 3).
4. Update `.claude/memory/MEMORY.md` title and date (Class 3).

### After Mainline Acceptance (Wave 2+)

Per CODEX-CLEANUP-REVIEW-001, later waves should address:
- Frontend surface classification (`trading-console/` vs `owner-runtime-console`)
- Schema hygiene
- Runtime safety follow-up tests
- Structural slimming (SQLite removal, config unification, domain chain)

## Do-Not-Touch List During Live Acceptance

| Category | Files/Paths |
| --- | --- |
| Runtime source | `src/**` |
| Tests | `tests/**` |
| Scripts | `scripts/**` |
| Deploy | `deploy/**` |
| Live config | `live-config.env`, `.env*` |
| Watcher/Tokyo ops | Any watcher or Tokyo operational code |
| Exchange/credential | Exchange gateway, credentials, live profiles |
| Quarantined agent files | `.claude/AGENTIC-WORKFLOW-GUIDE.md`, `.claude/MCP-ORCHESTRATION.md`, `.claude/TEAM-SETUP-SUMMARY.md`, `.claude/team/QUICKSTART.md`, `.claude/team/QUICK-REFERENCE.md`, `.agents/skills/agentic-workflow/README.md`, `.claude/skills/agentic-workflow/README.md` |
| Memory files | `.claude/memory/project-core-memory.md`, `.claude/memory/MEMORY.md` (defer to Wave 1) |
| Source provenance strings | `docs/ops/*`, `docs/canon/*`, `docs/adr/*` references inside `src/` and `tests/` |

## Verification Commands

```bash
# Confirm no dead refs in active entrypoints (should return zero)
grep -rn "docs/ops/" .agents/skills/ .claude/commands/ .claude/team/ --include="*.md" | grep -v "Do not recreate"

# Confirm no source/test changes in diff
git diff HEAD --stat -- src/ tests/ scripts/ deploy/

# Confirm current authority files all exist
ls -la docs/current/OWNER_RUNTIME_OPERATING_MODEL.md \
       docs/current/AI_AGENT_CONSTRAINTS.md \
       docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md \
       docs/current/MAIN_CONTROL_ROADMAP.md \
       docs/current/strategy-group-handoffs/main-control-handoff-index.md

# Confirm dead directories are gone
ls docs/ops/ docs/canon/ docs/adr/ docs/gpt/ 2>&1

# Count remaining dead refs in quarantined files only
grep -rn "docs/canon/\|docs/ops/" .claude/AGENTIC-WORKFLOW-GUIDE.md \
  .claude/MCP-ORCHESTRATION.md .claude/TEAM-SETUP-SUMMARY.md \
  .claude/team/QUICKSTART.md .claude/team/QUICK-REFERENCE.md \
  .agents/skills/agentic-workflow/README.md \
  .claude/skills/agentic-workflow/README.md \
  .claude/skills/pua-skill/SKILL.md \
  .claude/memory/project-core-memory.md | wc -l
```
