# Worktree Commit Boundary Audit

Task ID: CLAUDE-FINAL-COMMITAUDIT-012
Generated: 2026-06-17
Branch: codex/owner-runtime-console-v1
Mode: read-only audit — no files modified, staged, committed, or reverted

---

## 1. Executive Summary

The current dirty worktree contains **36 modified tracked files** and **4 untracked entries**. The changes cleanly separate into **3 commit candidates** and **1 mainline-sensitive exclusion group**. No `src/`, `deploy/`, or `owner-runtime-console/` changes are present. However, `tests/` has 2 modified files that are **directly coupled** to the `scripts/` changes and must be excluded from the safe commit candidates.

**Key finding:** The dirty tree has **mixed concerns** that should be split into at least 2 separate commits (agent cleanup + docs cleanup), with a third optional commit for token-burn artifacts. The scripts/tests group is a separate mainline-sensitive concern that must not be staged alongside the cleanup commits.

**Recommendation:** Commit Candidates A, B, and C are safe to commit now as 2-3 separate commits. The scripts/tests group should wait for mainline acceptance.

---

## 2. Current Dirty Tree Classification

### Summary Table

| Category | File Count | Status | Risk |
|----------|-----------|--------|------|
| **Candidate A:** Agent/Claude authority cleanup | 27 modified | Safe | LOW |
| **Candidate B:** docs/current semantic cleanup | 4 modified | Safe | LOW |
| **Candidate C:** Token-burn evidence artifacts | 19 untracked | Safe | NONE |
| **Exclude:** scripts/ + coupled tests/ | 3 modified + 2 modified | Mainline-sensitive | MEDIUM |
| **Exclude:** Untracked non-token-burn | 3 entries | Irrelevant | NONE |

### Verification: No forbidden directory changes

```bash
git diff --stat -- src/ deploy/ owner-runtime-console/
# Expected: empty (confirmed — zero changes)
```

**⚠️ tests/ has 2 modified files** — these are coupled to scripts/ changes (see Section 6).

---

## 3. Commit Candidate A: Agent/Claude Authority Cleanup

### Rationale

27 files containing agent instruction configurations had dead-path references to `docs/ops/`, `docs/canon/`, and other archived paths. These were rewritten to point to the current authority chain (`docs/current/*`) per CLAUDE-DOC-DEBT-001 and CLAUDE-CLEANUP-PLAN-001 Wave 1. This is a pure documentation/configuration cleanup with zero runtime impact.

### Files (27)

**`.agents/skills/` (8 files):**
| File | Status |
|------|--------|
| `.agents/skills/architect/SKILL.md` | modified |
| `.agents/skills/backend/SKILL.md` | modified |
| `.agents/skills/kaigong/SKILL.md` | modified |
| `.agents/skills/pm/SKILL.md` | modified |
| `.agents/skills/pua-skill/SKILL.md` | modified |
| `.agents/skills/qa/SKILL.md` | modified |
| `.agents/skills/reviewer/SKILL.md` | modified |
| `.agents/skills/shougong/SKILL.md` | modified |

**`.claude/commands/` (10 files):**
| File | Status |
|------|--------|
| `.claude/commands/architect.md` | modified |
| `.claude/commands/backend.md` | modified |
| `.claude/commands/diagnostic.md` | modified |
| `.claude/commands/frontend.md` | modified |
| `.claude/commands/kaigong.md` | modified |
| `.claude/commands/pm.md` | modified |
| `.claude/commands/product-manager.md` | modified |
| `.claude/commands/qa.md` | modified |
| `.claude/commands/reviewer.md` | modified |
| `.claude/commands/shougong.md` | modified |

**`.claude/team/` (9 files):**
| File | Status |
|------|--------|
| `.claude/team/README.md` | modified |
| `.claude/team/WORKFLOW.md` | modified |
| `.claude/team/architect/SKILL.md` | modified |
| `.claude/team/backend-dev/SKILL.md` | modified |
| `.claude/team/code-reviewer/SKILL.md` | modified |
| `.claude/team/diagnostic-analyst/SKILL.md` | modified |
| `.claude/team/frontend-dev/SKILL.md` | modified |
| `.claude/team/product-manager/SKILL.md` | modified |
| `.claude/team/project-manager/SKILL.md` | modified |

### Risk Assessment

- **Risk level:** LOW
- **Runtime impact:** Zero — these are agent instruction files, not source code
- **Mainline sensitivity:** None — no overlap with Codex-owned core files
- **Reversibility:** Fully reversible via `git checkout -- .agents/ .claude/commands/ .claude/team/`

### Verification Command

```bash
# Confirm no dead paths remain in cleaned files
grep -rn "docs/ops/\|docs/canon/" .agents/skills/ .claude/commands/ .claude/team/ --include="*.md" | grep -v "Do not recreate"
# Expected: zero matches
```

### Proposed Commit Title

```
fix(agent): rewrite dead authority paths to docs/current chain
```

---

## 4. Commit Candidate B: Current Docs Semantic Cleanup

### Rationale

4 files in `docs/current/` received semantic clarifications from CLAUDE-FINAL-DOCFIX-010:
- Review outcome vocabulary mapping (backend English → Owner Chinese)
- Gate class → Owner-facing sentence mappings
- Candidate Packet Freshness clarification (watcher metadata, not runtime gate)
- Stale facts clarification (upstream status/enum)

These are authority-document improvements that strengthen the current operating model.

### Files (4)

| File | Status | Change Summary |
|------|--------|----------------|
| `docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md` | modified | +16 lines: Review Outcome Vocabulary Mapping section |
| `docs/current/AI_AGENT_CONSTRAINTS.md` | modified | +2 lines: gate class → Owner sentence mappings |
| `docs/current/strategy-group-handoffs/main-control-conflict-policy.md` | modified | +5 lines: stale facts upstream clarification |
| `docs/current/strategy-group-handoffs/main-control-watcher-cadence.md` | modified | +5 lines: freshness metadata clarification |

### Risk Assessment

- **Risk level:** LOW
- **Runtime impact:** Zero — documentation only
- **Mainline sensitivity:** Low — these are clarifications to existing docs, not behavioral changes
- **Reversibility:** Fully reversible via `git checkout -- docs/current/`

### Verification Commands

```bash
# Confirm review outcome mapping exists
rg 'promote.*保留|revise.*调整|park.*暂停|kill.*停用|pending.*待复盘' docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md

# Confirm gate class mappings exist
rg 'hard_safety_stop|review_only_warning' docs/current/AI_AGENT_CONSTRAINTS.md

# Confirm freshness note exists
rg 'Candidate Packet Freshness|watcher-side metadata' docs/current/strategy-group-handoffs/main-control-watcher-cadence.md
```

### Proposed Commit Title

```
docs(current): add review vocabulary mapping and gate class clarifications
```

---

## 5. Commit Candidate C: Token-Burn Evidence Artifacts

### Rationale

19 files in `output/claude-token-burn/` are audit evidence, task cards, and planning artifacts generated during the Claude token-burn session. These are read-only reference materials that document findings, decisions, and next-step queues. They have zero runtime impact and serve as provenance for future task distribution.

### Files (19, all untracked)

| File | Type |
|------|------|
| `output/claude-token-burn/INDEX.md` | index |
| `output/claude-token-burn/NEXT_QUEUE.md` | queue |
| `output/claude-token-burn/CLAUDE-AUDIT-001-owner-language-leakage.md` | audit |
| `output/claude-token-burn/CLAUDE-AUDIT-002-runtime-safety-redteam.md` | audit |
| `output/claude-token-burn/CLAUDE-CLEANUP-PLAN-001-agent-config-wave1-rewrite-plan.md` | cleanup-plan |
| `output/claude-token-burn/CLAUDE-DEBT-001-deletion-consolidation-map.md` | audit |
| `output/claude-token-burn/CLAUDE-DOC-DEBT-001-doc-authority-conflict-map.md` | docs-fix |
| `output/claude-token-burn/CLAUDE-FINAL-CODETRACE-008-handoff-runtime-consumption-audit.md` | code-trace |
| `output/claude-token-burn/CLAUDE-FINAL-DECISIONPACK-009-runtime-semantics-adr-options.md` | decision-pack |
| `output/claude-token-burn/CLAUDE-FINAL-DOCFIX-010-docs-semantic-cleanup-report.md` | docs-fix |
| `output/claude-token-burn/CLAUDE-FINAL-HANDOFFCARDS-006-strategygroup-handoff-quality-cards.md` | task-cards |
| `output/claude-token-burn/CLAUDE-FINAL-HANDOFFQA-007-strategygroup-handoff-readonly-audit.md` | audit |
| `output/claude-token-burn/CLAUDE-FINAL-REVIEW-002-agent-config-cleanup-safety-review.md` | review |
| `output/claude-token-burn/CLAUDE-FINAL-TASKPACK-003-post-acceptance-task-cards.md` | task-cards |
| `output/claude-token-burn/CLAUDE-FINAL-TESTCARDS-004-runtime-safety-test-cards.md` | task-cards |
| `output/claude-token-burn/CLAUDE-FINAL-UICARDS-005-owner-console-surface-governance-cards.md` | task-cards |
| `output/claude-token-burn/CLAUDE-SCHEMA-DEBT-001-personal-campaign-schema-usage.md` | audit |
| `output/claude-token-burn/CLAUDE-TEST-MAP-001-runtime-path-test-coverage.md` | audit |
| `output/claude-token-burn/CODEX-CLEANUP-REVIEW-001-mainline-safe-cleanup-notes.md` | review |

### Risk Assessment

- **Risk level:** NONE
- **Runtime impact:** Zero — output artifacts only
- **Mainline sensitivity:** None — `output/` is not imported by any source code
- **Reversibility:** Fully reversible by deleting the directory

### Verification Command

```bash
# Confirm file count
ls output/claude-token-burn/*.md | wc -l
# Expected: 19

# Confirm INDEX.md and NEXT_QUEUE.md exist
ls output/claude-token-burn/INDEX.md output/claude-token-burn/NEXT_QUEUE.md
```

### Proposed Commit Title

```
docs(output): add Claude token-burn audit reports and task queue
```

### Note on output/ scope

Only `output/claude-token-burn/` should be staged. The `output/` directory also contains other subdirectories (tokyo-*, playwright, brc-runtime-governance-*, strategygroup-runtime-pilot, unit-active-monitor) and loose JSON files that are pre-existing and should not be included in this commit.

---

## 6. Explicit Exclusions / Do Not Stage Now

### 6.1 scripts/ (3 modified files) — MAINLINE-SENSITIVE

| File | Status | Change Summary |
|------|--------|----------------|
| `scripts/build_tokyo_runtime_governance_git_owner_deploy_packet.py` | modified | +1 line: pass `allow_tracked_dirty_for_remote_git_export=True` |
| `scripts/plan_tokyo_runtime_governance_git_deploy.py` | modified | +5/-1 lines: downgrade dirty-blocker to warning for remote git export |
| `scripts/prepare_tokyo_runtime_governance_release.py` | modified | +16/-1 lines: add `--allow-tracked-dirty-for-remote-git-export` flag |

**Why excluded:** These files modify Tokyo deploy behavior — downgrading a `tracked_worktree_dirty` blocker to a warning when deploying via remote git export. This is a mainline-sensitive behavioral change to deployment scripts. Per AGENTS.md and INDEX.md Section 4, `scripts/**` is in the "do not touch during mainline acceptance" category.

**Risk:** MEDIUM — changes deploy safety gate behavior. While the change is intentional (dirty worktree is acceptable when deploying from a pushed remote commit), it should be reviewed and committed as part of mainline acceptance, not as a side cleanup.

### 6.2 tests/ (2 modified files) — COUPLED TO scripts/

| File | Status | Change Summary |
|------|--------|----------------|
| `tests/unit/test_tokyo_runtime_governance_git_deploy.py` | modified | +58 lines: test for dirty-worktree-allowed-for-remote-export |
| `tests/unit/test_tokyo_runtime_governance_release_prep.py` | modified | +29 lines: test for warn-on-dirty-remote-export |

**Why excluded:** These test changes are **directly coupled** to the scripts/ changes — they test the `allow_tracked_dirty_for_remote_git_export` flag behavior. Committing them without the scripts/ changes would leave tests referencing functionality that doesn't exist. Committing scripts/ without tests would leave the behavioral change untested. They must be committed together or not at all.

**Dependency chain:**
```
scripts/prepare_tokyo_runtime_governance_release.py  (adds flag)
  ← scripts/plan_tokyo_runtime_governance_git_deploy.py  (passes flag)
    ← scripts/build_tokyo_runtime_governance_git_owner_deploy_packet.py  (passes flag)
      ← tests/unit/test_tokyo_runtime_governance_git_deploy.py  (tests flag)
      ← tests/unit/test_tokyo_runtime_governance_release_prep.py  (tests flag)
```

### 6.3 Untracked non-token-burn entries

| Entry | Type | Action |
|-------|------|--------|
| `live-config.env` | Config/secrets | **DO NOT STAGE** — may contain secrets; per task Hard Stop |
| `local-archives/` | Workspace archives | **DO NOT STAGE** — local workspace artifact |
| `.playwright-cli/` | Playwright logs | **DO NOT STAGE** — test tooling output, 200+ files |

### 6.4 Other output/ subdirectories

The `output/` directory contains many pre-existing subdirectories and JSON files beyond `output/claude-token-burn/`. Only `output/claude-token-burn/` should be staged if committing Candidate C. The rest are pre-existing artifacts from prior Tokyo deploy runs and should not be touched.

---

## 7. Mixed Concern Assessment

### Concern Separation

The dirty tree contains **3 distinct concern types** that should be separate commits:

| Concern | Files | Commit? |
|---------|-------|---------|
| Agent instruction authority cleanup | 27 `.agents/` + `.claude/` | Yes — Candidate A |
| Docs semantic cleanup | 4 `docs/current/` | Yes — Candidate B |
| Token-burn artifacts | 19 `output/claude-token-burn/` | Optional — Candidate C |
| Deploy script behavior change | 3 `scripts/` + 2 `tests/` | No — wait for mainline |

**Why not a single commit:** Mixing agent cleanup with docs cleanup conflates two independent improvements. If a rollback is needed on one, the other would be unnecessarily reverted. The token-burn artifacts are a third, purely evidentiary concern.

**Recommended commit sequence:**
1. Candidate A first (agent cleanup) — largest diff, lowest risk
2. Candidate B second (docs cleanup) — small, semantic
3. Candidate C optional (token-burn artifacts) — evidentiary, can wait

---

## 8. Verification Commands

### Pre-commit verification (run before staging)

```bash
# 1. Confirm no src/ or deploy/ changes exist
git diff --stat -- src/ deploy/ owner-runtime-console/
# Expected: empty

# 2. Confirm tests/ changes exist (and are coupled to scripts/)
git diff --stat -- tests/
# Expected: 2 files, 87 insertions (coupled to scripts/)

# 3. Confirm scripts/ changes exist
git diff --stat -- scripts/
# Expected: 3 files (mainline-sensitive)

# 4. Confirm agent cleanup files have no dead paths
grep -rn "docs/ops/\|docs/canon/" .agents/skills/ .claude/commands/ .claude/team/ --include="*.md" | grep -v "Do not recreate"
# Expected: zero matches

# 5. Confirm docs semantic changes are present
rg 'promote.*保留|revise.*调整' docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md
rg 'hard_safety_stop|review_only_warning' docs/current/AI_AGENT_CONSTRAINTS.md

# 6. Confirm token-burn file count
ls output/claude-token-burn/*.md | wc -l
# Expected: 19

# 7. Confirm no secrets are staged
git diff --cached -- live-config.env
# Expected: empty (never stage this file)
```

### Post-commit verification (run after each commit)

```bash
# After Candidate A commit:
git log --oneline -1
grep -rn "docs/ops/" .agents/skills/ .claude/commands/ .claude/team/ --include="*.md" | wc -l
# Expected: 0

# After Candidate B commit:
git log --oneline -1
rg 'Review Outcome Vocabulary Mapping' docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md
# Expected: match found

# After Candidate C commit (if done):
git log --oneline -1
ls output/claude-token-burn/INDEX.md
# Expected: file exists and is tracked
```

---

## 9. Future Staging Recipe (Do Not Execute)

### Step 1: Stage and commit Candidate A

```bash
git add \
  .agents/skills/architect/SKILL.md \
  .agents/skills/backend/SKILL.md \
  .agents/skills/kaigong/SKILL.md \
  .agents/skills/pm/SKILL.md \
  .agents/skills/pua-skill/SKILL.md \
  .agents/skills/qa/SKILL.md \
  .agents/skills/reviewer/SKILL.md \
  .agents/skills/shougong/SKILL.md \
  .claude/commands/architect.md \
  .claude/commands/backend.md \
  .claude/commands/diagnostic.md \
  .claude/commands/frontend.md \
  .claude/commands/kaigong.md \
  .claude/commands/pm.md \
  .claude/commands/product-manager.md \
  .claude/commands/qa.md \
  .claude/commands/reviewer.md \
  .claude/commands/shougong.md \
  .claude/team/README.md \
  .claude/team/WORKFLOW.md \
  .claude/team/architect/SKILL.md \
  .claude/team/backend-dev/SKILL.md \
  .claude/team/code-reviewer/SKILL.md \
  .claude/team/diagnostic-analyst/SKILL.md \
  .claude/team/frontend-dev/SKILL.md \
  .claude/team/product-manager/SKILL.md \
  .claude/team/project-manager/SKILL.md

git commit -m "fix(agent): rewrite dead authority paths to docs/current chain

Wave 1 of agent instruction cleanup per CLAUDE-CLEANUP-PLAN-001.
27 files: 8 .agents/skills, 10 .claude/commands, 9 .claude/team.
Replaces docs/ops/ and docs/canon/ references with docs/current/* authority chain.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Step 2: Stage and commit Candidate B

```bash
git add \
  docs/current/AI_AGENT_CONSTRAINTS.md \
  docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md \
  docs/current/strategy-group-handoffs/main-control-conflict-policy.md \
  docs/current/strategy-group-handoffs/main-control-watcher-cadence.md

git commit -m "docs(current): add review vocabulary mapping and gate class clarifications

Per CLAUDE-FINAL-DOCFIX-010:
- Review Outcome Vocabulary Mapping (backend English → Owner Chinese)
- Gate class → Owner-facing sentence mappings
- Candidate Packet Freshness watcher metadata note
- Stale facts upstream status/enum clarification

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Step 3 (Optional): Stage and commit Candidate C

```bash
git add output/claude-token-burn/

git commit -m "docs(output): add Claude token-burn audit reports and task queue

19 files: 17 audit/review/task-card reports + INDEX.md + NEXT_QUEUE.md.
Evidence artifacts from Claude token-burn session (CLAUDE-FINAL-INDEX-011).

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Step 4 (Future — after mainline acceptance): Stage and commit scripts/tests

```bash
# Only after mainline acceptance is complete:
git add \
  scripts/build_tokyo_runtime_governance_git_owner_deploy_packet.py \
  scripts/plan_tokyo_runtime_governance_git_deploy.py \
  scripts/prepare_tokyo_runtime_governance_release.py \
  tests/unit/test_tokyo_runtime_governance_git_deploy.py \
  tests/unit/test_tokyo_runtime_governance_release_prep.py

git commit -m "fix(deploy): allow dirty worktree warning for remote git export

Downgrades tracked_worktree_dirty from blocker to warning when deploying
via pushed remote git commit (not local archive).
Adds --allow-tracked-dirty-for-remote-git-export flag.
Includes coupled unit tests.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## 10. Non-Interference Confirmation

### What this audit does NOT touch

| Item | Status |
|------|--------|
| `src/**` | Zero changes confirmed |
| `deploy/**` | Zero changes confirmed |
| `owner-runtime-console/**` | Zero changes confirmed |
| `live-config.env` | Not read, not staged, not modified |
| `local-archives/` | Not touched |
| `.playwright-cli/` | Not touched |
| scripts/ behavior | Not modified — only classified |
| tests/ behavior | Not modified — only classified |
| Git state | No staging, commit, push, checkout, reset, restore, or clean performed |

### Rollback / Non-Revert Note

This audit does **not** revert any user or mainline changes. The scripts/ and tests/ changes are explicitly **excluded from staging** rather than reverted. They remain in the working tree as-is, ready for future inclusion after mainline acceptance.

If the user later decides the scripts/ changes should be committed alongside the cleanup candidates, the staging recipe in Section 9 Step 4 can be executed at that time.

---

## Summary

| Decision | Recommendation |
|----------|---------------|
| **Commit now?** | Yes — Candidates A and B are safe to commit immediately |
| **Candidate C?** | Optional — can commit now or defer |
| **scripts/tests?** | Wait — mainline-sensitive, commit after acceptance |
| **Mixed concerns?** | Yes — split into 2-3 separate commits |
| **Any blockers?** | None for Candidates A/B/C |

---

*End of audit. Report path: `output/claude-token-burn/CLAUDE-FINAL-COMMITAUDIT-012-worktree-commit-boundary-audit.md`*
