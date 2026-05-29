---
title: DOCUMENT_GOVERNANCE
status: CURRENT_CANON
authority: owner-correction + docs-governance-pass1
last_verified: 2026-05-29
source_of_truth:
  - docs/ops/knowledge-pack/DOCS_GOVERNANCE_EXPLORATION_REPORT.md
  - docs/ops/knowledge-pack/CURRENT_POSITION_REBUILD.md
---

# DOCUMENT_GOVERNANCE.md

This document defines how project documents should be read, trusted, created, and maintained.

---

## 1. Authority order

When documents conflict, resolve by this priority:

1. **Owner explicit correction / decision** (highest)
2. Current tracked code
3. Current git status
4. Current verified reports
5. ADR / decision records
6. Historical docs
7. Old knowledge-pack (lowest)

A later document does not automatically supersede an earlier one.
Only explicit Owner correction or tracked code state overrides.

---

## 2. Document statuses

| Status | Meaning | Who should read it |
|---|---|---|
| `CURRENT_CANON` | Highest-authority current facts; verified against code and Owner input | Everyone |
| `ACTIVE_WORKING` | Current working document; not final authority | Active developers |
| `DECISION_RECORD` | Accepted architectural decision | Everyone for context |
| `OPERATIONAL` | Current task/progress tracking | Active developers |
| `RESEARCH_ARCHIVE` | Historical research; does not represent current capability | Researchers only |
| `HISTORICAL_ARCHIVE` | Historical background; predates current architecture | Context-seekers only |
| `DEPRECATED` | Contains known errors; do not use as fact source | Nobody (unless auditing history) |
| `SUPERSEDED` | Replaced by a newer document | Nobody (redirect to replacement) |
| `DRAFT` | Unfinished; may contain errors | Authors only |
| `UNVERIFIED` | Content not verified against code or Owner input | Use with caution |
| `UNKNOWN` | Not yet classified | Requires classification before use |

---

## 3. Tracked-only rule

**Untracked files must never be described as integrated capabilities.**

A file that exists in the working directory but is not committed to git:

- Has no presence in the tracked codebase
- Cannot be deployed
- Cannot be depended on by other tracked code
- Should be described as "untracked / not integrated"

When counting migrations, modules, or capabilities, only tracked files count for the integrated capability claim.

---

## 4. Capability wording rules

These distinctions must be maintained in all project documentation:

| Wrong | Correct |
|---|---|
| exists = integrated | exists != integrated |
| implemented = verified | implemented != verified |
| testnet verified = production-ready | testnet verified != production-ready |
| metadata operation = runtime execution | metadata operation != runtime execution |
| signal_evaluated = trade intent | signal_evaluated != trade intent |
| intent_recorded = order-capable | intent_recorded != order-capable |
| trial_candidate = strategy-ready | trial_candidate != strategy-ready |
| account facts read = account_equity available | account facts != account_equity |
| broad smoke score = deployment worthy | broad smoke score != deployment worthy |

---

## 5. Front matter policy

All new important documents should include YAML front matter:

```yaml
---
title: <document title>
status: CURRENT_CANON | ACTIVE_WORKING | DECISION_RECORD | OPERATIONAL |
        RESEARCH_ARCHIVE | HISTORICAL_ARCHIVE | DEPRECATED | SUPERSEDED | DRAFT | UNVERIFIED
authority: owner-confirmed | tracked-code | current-rebuild | historical-report | unverified
last_verified: YYYY-MM-DD
supersedes:
  - <path to superseded document>
superseded_by:
  - <path to replacement document>
source_of_truth:
  - <paths to authoritative sources>
notes: <optional notes>
---
```

Existing documents that lack front matter should be given a status banner at minimum when they are reviewed.

---

## 6. Archive policy

Documents should be archived (not deleted) when:

- They contain known factual errors that have been corrected elsewhere
- Their claims have been explicitly superseded by Owner correction
- They refer to an earlier project phase that no longer applies

Archived documents:

- Move to `docs/archive/` with a date prefix
- Keep a redirect README in the original location
- Are preserved as historical evidence
- Must never be interpreted as current capability

---

## 7. Deprecation policy

A document is deprecated when:

- It contains claims that are known to be wrong (e.g., "27 migrations")
- It uses a positioning that the Owner has explicitly rejected
- It describes untracked files as integrated capabilities

Deprecated documents:

- Receive a `> [!WARNING]` banner at the top
- Banner points to the replacement document
- Original content is preserved (not rewritten)
- Status in front matter is set to `DEPRECATED` or `SUPERSEDED`

---

## 8. Safe update policy

When updating project documentation:

1. **Never delete historical evidence.** Archive, don't delete.
2. **Never rewrite old documents to match new facts.** Add deprecation banners instead.
3. **Never describe untracked files as integrated capabilities.**
4. **Never describe testnet verification as production readiness.**
5. **Never describe metadata operations as runtime execution.**
6. **Always cite evidence** (file path, commit hash, report path, or Owner statement).
7. **Always date your updates.**
8. **When in doubt, create a new document rather than editing an old one.**
