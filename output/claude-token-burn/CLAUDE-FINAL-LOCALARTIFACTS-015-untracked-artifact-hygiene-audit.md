# Untracked Artifact Hygiene Audit

Generated: 2026-06-17
Task ID: CLAUDE-FINAL-LOCALARTIFACTS-015
Mode: read-only metadata-only audit — no files read, modified, deleted, or staged

---

## 1. Summary

The workspace at `/Users/jiangwei/Documents/final` contains **~648 MB** of untracked artifacts across **717 files** in three directory groups plus 21 standalone entries. None are covered by `.gitignore`. The largest contributor is `local-archives/` (469 MB, a single pre-delete tarball), followed by `output/strategygroup-runtime-pilot/` (146 MB, 34 deploy snapshots) and `output/playwright/` (13 MB, screenshot evidence). The `output/claude-token-burn/` directory (472 KB, 23 reports) is the current mainline acceptance evidence and must be preserved. `live-config.env` is an untracked secret file at the repo root — it was **not read** and must **never** be committed.

Total untracked surface: **~648 MB, 717 files, 0 gitignored**.

---

## 2. Current Untracked Inventory

### 2.1 Top-Level Standalone Entries

| Path | Size | Type | Purpose |
|------|------|------|---------|
| `live-config.env` | unknown (not read) | env/secret | Live configuration with credentials |
| `.playwright-cli/` | 5.6 MB, 210 files | tooling cache | Playwright CLI logs, YML configs (124 yml), screenshots (15 png), logs (71 log) |
| `local-archives/` | 469 MB, 2 files | archive | Pre-deletion tarball + small integration archive |

### 2.2 output/ Directory Groups

| Path | Size | Files | Purpose |
|------|------|-------|---------|
| `output/claude-token-burn/` | 472 KB | 23 | Claude audit/review/task-card reports + INDEX + NEXT_QUEUE (mainline acceptance evidence) |
| `output/strategygroup-runtime-pilot/` | 146 MB | 263 | 34 deploy snapshot dirs + 1 dry-run audit + current-evidence dirs; each deploy dir ~15-17 MB |
| `output/playwright/` | 13 MB | 59 | UI screenshot evidence (59 png files, theme/mobile/incident captures) |
| `output/brc-runtime-governance-c71d8a73-20260613-full-chain/` | 844 KB | 61 | Full-chain governance test run artifacts (json, stdout, stderr) |
| `output/brc-runtime-governance-c71d8a73-20260613-next-free-live-path/` | 160 KB | 20 | Next-free-live-path test artifacts |
| `output/tokyo-runtime-governance-release/` | 15 MB | 20 | Tokyo governance release: deploy-apply/dry-run/owner-deploy/postdeploy JSONs |
| `output/tokyo-runtime-governance-{hash}/` (×9) | 36-56 KB each | 3-6 each | Per-commit Tokyo governance snapshots (deploy apply/dry-run/acceptance) |
| `output/tokyo-account-wide-position-open-order-readonly-refresh-*.json` (×6) | 4-16 KB each | 1 each | Tokyo readonly refresh snapshots (2026-06-14) |
| `output/tokyo-*.json` (14 standalone) | 4-28 KB each | 1 each | Tokyo deploy/verify/probe decision packets |
| `output/runtime-signal-watcher-pack-smoke/` | 8 KB | 2 | Watcher smoke test packets |
| `output/unit-active-monitor/` | 4 KB | 1 | Single runtime-active monitoring snapshot |

### 2.3 local-archives/ Breakdown

| Path | Size | Purpose |
|------|------|---------|
| `local-archives/worktree-cleanup-20260613/final-sprint6-integration-untracked-20260613.tar.gz` | 469 MB | Full pre-deletion archive of sprint 6 integration artifacts |
| `local-archives/final-sprint6-integration-20260615-pre-delete.tar.gz` | 4 KB | Small pre-delete marker/archive |

---

## 3. Classification Matrix

| Artifact Group | Keep Tracked? | Keep Local (ignored)? | Archive Outside Repo? | Candidate for Deletion? | Never Inspect Contents? |
|---|---|---|---|---|---|
| `live-config.env` | **no** — never commit | yes (must stay local) | no | no | **yes** — contains secrets |
| `.playwright-cli/` | no | no | no | **yes** (after Owner confirmation) | no |
| `local-archives/` | no | maybe (if Owner wants backup) | **yes** — move to external backup | yes (469 MB tarball after backup confirmed) | no |
| `output/claude-token-burn/` | **maybe** — current evidence | yes | no | **no** — preserve during mainline acceptance | no |
| `output/strategygroup-runtime-pilot/` | no | maybe (latest deploy only) | yes (older deploys) | **yes** — 33 of 34 deploys are stale, keep latest | no |
| `output/playwright/` | no | maybe | yes | maybe — UI evidence, keep until sprint 6 sign-off | no |
| `output/brc-runtime-governance-*` | no | no | yes | yes (after acceptance) | no |
| `output/tokyo-runtime-governance-*` | no | maybe (release dir) | yes | yes (older snapshots) | no |
| `output/tokyo-*.json` (standalone) | no | no | no | yes (after acceptance) | no |
| `output/runtime-signal-watcher-pack-smoke/` | no | no | no | yes | no |
| `output/unit-active-monitor/` | no | no | no | yes | no |

---

## 4. Mainline Acceptance Evidence To Preserve

The following artifacts are current mainline acceptance evidence and **must not be deleted** during the active acceptance phase:

1. **`output/claude-token-burn/`** (23 files, 472 KB) — All 17 audit/review/task-card reports, INDEX.md, NEXT_QUEUE.md. These are the Codex-referenced evidence chain for the runtime-governance pilot.

2. **`output/strategygroup-runtime-pilot/current-evidence/`** and **`current-evidence-ccb78a8c/`** — Current acceptance evidence snapshots.

3. **`output/tokyo-runtime-governance-release/`** (15 MB, 20 files) — The most recent Tokyo governance release artifacts; contains the latest deploy-apply, dry-run, owner-deploy-packet, and postdeploy-verify records.

4. **`output/playwright/`** (13 MB, 59 files) — UI screenshot evidence for sprint 6 theme/mobile work. Preserve until sprint 6 sign-off.

---

## 5. Likely Stale / Tooling Noise

| Artifact Group | Staleness Indicator | Recommended Action |
|---|---|---|
| `.playwright-cli/` | 210 files of CLI logs/configs/screenshots; tooling cache, not evidence | Delete after Owner confirmation |
| `output/strategygroup-runtime-pilot/deploy-*` (33 older dirs) | 34 deploy snapshots; only latest is current | Archive or delete 33 older deploys; keep most recent |
| `output/brc-runtime-governance-c71d8a73-20260613-*` | Dated 2026-06-13; full-chain and next-free-live-path test runs | Archive or delete after acceptance |
| `output/tokyo-runtime-governance-{hash}/` (×9) | Per-commit snapshots from 2026-06-15; superseded by release dir | Delete after acceptance |
| `output/tokyo-account-wide-position-open-order-readonly-refresh-*` (×6) | Dated 2026-06-14; readonly refresh snapshots | Delete after acceptance |
| `output/tokyo-*.json` (14 standalone) | Deploy decision/verify packets from various commits | Delete after acceptance |
| `output/runtime-signal-watcher-pack-smoke/` | 2-file smoke test output | Delete now |
| `output/unit-active-monitor/` | 1-file monitoring snapshot | Delete now |
| `local-archives/final-sprint6-integration-20260615-pre-delete.tar.gz` | 4 KB marker file | Delete now (negligible) |

---

## 6. .gitignore Recommendation Candidates

The following entries should be added to `.gitignore` to prevent future accidental commits. **These are recommendations only — `.gitignore` was not modified.**

```gitignore
# === Recommended additions ===

# Live secrets — NEVER commit
live-config.env

# Playwright CLI tooling cache
.playwright-cli/

# Local archives (large, non-source)
local-archives/

# Runtime output artifacts (generated, not source)
output/

# Or more granularly, if output/ is sometimes committed:
# output/strategygroup-runtime-pilot/
# output/playwright/
# output/brc-runtime-governance-*
# output/tokyo-runtime-governance-*
# output/tokyo-account-wide-*
# output/tokyo-git-deploy-*
# output/tokyo-owner-deploy-*
# output/tokyo-postdeploy-*
# output/tokyo-readonly-*
# output/tokyo-strategy-group-*
# output/runtime-signal-watcher-pack-smoke/
# output/unit-active-monitor/
```

**Note:** `output/claude-token-burn/` may be intentionally kept tracked for mainline acceptance evidence. If so, use `output/*` + `!output/claude-token-burn/` pattern, or keep the whole `output/` ignored and selectively add committed reports.

---

## 7. Future Cleanup Plan With Approval Gates

### Gate 0: Verify — No Deletion Without Owner Confirmation
Every step below requires explicit Owner approval before execution.

### Step 1: Immediate Safe Deletions (LOW risk, ~8 KB)
```bash
# Delete stale tooling noise
rm output/runtime-signal-watcher-pack-smoke/deployment-readiness-packet.json
rm output/runtime-signal-watcher-pack-smoke/post-signal-resume-pack.json
rmdir output/runtime-signal-watcher-pack-smoke/
rm output/unit-active-monitor/runtime-active-1/*.{json,...}
rmdir output/unit-active-monitor/runtime-active-1/
rmdir output/unit-active-monitor/
rm local-archives/final-sprint6-integration-20260615-pre-delete.tar.gz
```
**Gate 1:** Owner confirms these are safe to delete.

### Step 2: Archive Large Artifacts Outside Repo (~469 MB)
```bash
# Move the 469 MB tarball to external backup location
mv local-archives/worktree-cleanup-20260613/final-sprint6-integration-untracked-20260613.tar.gz ~/Desktop/backup/  # or Owner-chosen path
rmdir local-archives/worktree-cleanup-20260613/
rmdir local-archives/
```
**Gate 2:** Owner confirms backup destination and that the tarball is no longer needed locally.

### Step 3: Clean Stale Deploy Snapshots (~130 MB)
```bash
# Keep only the latest deploy dir in strategygroup-runtime-pilot
# Identify latest: ls -lt output/strategygroup-runtime-pilot/deploy-*/ | head
# Delete all but the latest
rm -rf output/strategygroup-runtime-pilot/deploy-<older-hashes>/
```
**Gate 3:** Owner confirms which deploy snapshot is the current one and approves deletion of the rest.

### Step 4: Archive/Clean Tokyo Governance Snapshots (~15 MB)
```bash
# Archive or delete per-commit governance dirs
rm -rf output/tokyo-runtime-governance-02854861/
# ... repeat for 2fca2ba4, 33bc3edc, 3dd07f63, 66492f2f, 76534a88, 7adf19e9, c10aaf0a, ccb78a8c, e9c060dd
# Delete standalone tokyo-*.json files
rm output/tokyo-account-wide-position-open-order-readonly-refresh-*.json
rm output/tokyo-git-deploy-*.json
rm output/tokyo-owner-deploy-decision-*.json
rm output/tokyo-postdeploy-*.json
rm output/tokyo-readonly-probe-*.json
rm output/tokyo-strategy-group-live-facts-*.json
```
**Gate 4:** Owner confirms Tokyo governance acceptance is complete and snapshots are no longer needed.

### Step 5: Clean Playwright Tooling Cache (~5.6 MB)
```bash
rm -rf .playwright-cli/
```
**Gate 5:** Owner confirms Playwright CLI logs are not needed for debugging.

### Step 6: Clean BRC Governance Test Artifacts (~1 MB)
```bash
rm -rf output/brc-runtime-governance-c71d8a73-20260613-full-chain/
rm -rf output/brc-runtime-governance-c71d8a73-20260613-next-free-live-path/
```
**Gate 6:** Owner confirms governance test runs are no longer needed as evidence.

### Step 7: Update .gitignore
Add entries from Section 6 above.
**Gate 7:** Owner approves .gitignore additions.

### Step 8: Preserve Token-Burn Evidence
`output/claude-token-burn/` stays intact until Owner decides to archive or commit it.

---

## 8. Verification Commands

All commands below are **read-only metadata verification**. None modify, delete, or stage files.

```bash
# Total untracked file count
git ls-files --others --exclude-standard | wc -l

# Total untracked size
du -sh $(git ls-files --others --exclude-standard --directory | head -5) 2>/dev/null

# Size per top-level untracked group
du -sh .playwright-cli/ local-archives/ output/ live-config.env 2>/dev/null

# File count per group
for d in .playwright-cli local-archives output; do echo "$d: $(find $d -type f | wc -l) files"; done

# Extension breakdown in output/
find output/ -type f | sed 's/.*\.//' | sort | uniq -c | sort -rn

# Confirm live-config.env exists and is untracked (do NOT read)
git ls-files --others --exclude-standard -- live-config.env

# Confirm .gitignore does NOT cover output/ or local-archives/
git check-ignore -v output/ local-archives/ .playwright-cli/ live-config.env 2>/dev/null; echo "exit: $?"

# List stale deploy snapshots (sorted by date, newest first)
ls -lt output/strategygroup-runtime-pilot/deploy-*/ 2>/dev/null | head -40

# Verify token-burn reports still present
ls output/claude-token-burn/*.md | wc -l

# Verify no source files were touched
git diff --stat HEAD -- src/ tests/ scripts/ deploy/
```

---

## 9. Non-Interference Confirmation

This audit confirms the following:

| Check | Status |
|-------|--------|
| `live-config.env` was **not read** | ✅ Confirmed — metadata existence check only |
| No `.env*` files were read | ✅ Confirmed |
| No artifact **contents** were read (JSON, TXT, PNG, YML) | ✅ Confirmed — only `git status`, `du`, `find`, `wc`, `ls`, `cat .gitignore` |
| No files were modified, deleted, moved, staged, committed, or pushed | ✅ Confirmed |
| No tests, deploys, watchers, or external commands were run | ✅ Confirmed |
| No source code directories (`src/`, `tests/`, `scripts/`, `deploy/`) were inspected | ✅ Confirmed |
| `live-config.env` must **never** be committed | ✅ Noted — it contains live credentials |
| `.gitignore` was **not** modified | ✅ Confirmed — recommendations only |
| Report written to designated path only | ✅ Confirmed |

---

*End of audit. Result: **PASS** — metadata-only audit completed without reading any secret or artifact contents.*
