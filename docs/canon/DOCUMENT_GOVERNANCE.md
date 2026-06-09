---
title: DOCUMENT_GOVERNANCE
status: CURRENT_CANON
authority: owner-instruction + docs-governance-pass
last_verified: 2026-06-09
source_of_truth:
  - docs/ops/knowledge-pack/DOCUMENT_GOVERNANCE.md
  - owner instruction 2026-06-09
---

# Document Governance

This document defines how project documents should be read, trusted, and
classified.

---

## 1. Authority Order

When documents conflict, resolve by this priority:

```text
Owner explicit decision
  > tracked code fact
  > docs/canon/*
  > ADR
  > docs/evidence/*
  > docs/ops/*
  > docs/archive/*
```

Canon files (`docs/canon/`) are the primary agent reading source. They
distill verified facts from knowledge-pack and code. If canon and knowledge-pack
disagree, canon wins unless a newer Owner decision or code change supersedes it.

---

## 2. Canon Rules

Canon files must be:

- Short and focused
- Fact-based, not narrative
- Free of sprint logs, research results, or historical storytelling
- Free of duplicate truth (one fact, one location)
- Updated when code or Owner decisions change
- Never sourced from archived documents as current fact

Canon files must not contain:

- Sprint progress logs
- Research analysis reports
- Historical narrative
- Copy-pasted full text from knowledge-pack

---

## 3. Archive Rules

- Archive can be read as history only.
- Archive cannot override canon.
- Archived agent instructions must not be used as current instructions.
- Archive files are preserved as historical evidence, not current capability.

---

## 4. Evidence Rules

- Research and live trial reports are evidence, not current constraint.
- Evidence must not be promoted to current fact without code verification.
- Evidence grade: code fact > verified report > historical evidence >
  static inference > unknown.

---

## 5. Banner Types

The following banner types are defined for future use:

| Banner | Meaning | When to apply |
| ------ | ------- | ------------- |
| `SUPERSEDED` | Replaced by a newer document | When a canon or knowledge-pack file replaces an older one |
| `HISTORICAL_EVIDENCE` | Contains useful historical context but is not current fact | When a document has value as history but should not guide current work |
| `QUARANTINED_AGENT_INSTRUCTION` | Contains agent instructions that are outdated or misleading | When agent instruction docs are superseded by canon |

Do not apply banners in the current phase. Banners will be applied in a future
cleanup phase.

---

## 6. Reading Order for Agents

Agents should read `docs/canon/` first, then consult `docs/ops/` for
detailed evidence. If an `docs/ops/` document conflicts with a canon file,
the canon file takes precedence.

Older `docs/ops/` documents that lack a canon equivalent should be read with
caution and treated as historical evidence unless explicitly verified against
current code.
