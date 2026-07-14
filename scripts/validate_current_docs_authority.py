#!/usr/bin/env python3
"""Validate docs/current remains the active authority surface."""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]

ARCHIVED_CURRENT_DOC_FILENAMES = (
    "ACTIVE_STRATEGYGROUP_SEMANTICS_REVIEW_AND_OPTIMIZATION_PLAN.md",
    "L1_L9_OPTIMIZATION_EXECUTION_PLAN.md",
    "L1_L9_SYSTEM_REVIEW_AND_OPTIMIZATION_AUDIT.md",
    "MAINLINE_P0_P1_CHAIN_AUDIT_REGISTER.md",
    "MULTI_STRATEGY_MULTI_SYMBOL_MULTI_SIDE_ACTION_TIME_EVOLUTION_DESIGN.md",
    "OPERATION_LAYER_EXCHANGE_CAPABILITY_AUDIT.md",
    "PG_CURRENT_PROJECTION_AUTHORITY_CLOSURE_DESIGN.md",
    "REPO_FILE_SOURCE_ELIMINATION_GOVERNANCE_PLAN.md",
    "RUNTIME_CONTROL_STATE_MAINLINE_FILE_IO_MAP.md",
)

DOC_CURRENT_REF_RE = re.compile(r"docs/current/[A-Za-z0-9_./-]+\.md")


def main() -> int:
    errors = validate_current_docs_authority(REPO_ROOT)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "status": "current_docs_authority_valid",
                "current_doc_count": len(_current_docs(REPO_ROOT)),
                "archived_current_doc_count": len(ARCHIVED_CURRENT_DOC_FILENAMES),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def validate_current_docs_authority(repo_root: Path) -> list[str]:
    errors: list[str] = []
    errors.extend(_validate_current_doc_front_matter(repo_root))
    errors.extend(_validate_current_refs_exist(repo_root))
    errors.extend(_validate_archived_docs_not_reintroduced(repo_root))
    return errors


def _validate_current_doc_front_matter(repo_root: Path) -> list[str]:
    errors: list[str] = []
    for path in _current_docs(repo_root):
        rel = path.relative_to(repo_root).as_posix()
        lines = path.read_text(encoding="utf-8").splitlines()
        if not lines or lines[0].strip() != "---":
            errors.append(f"{rel} must start with YAML front matter")
            continue
        try:
            end = lines[1:].index("---") + 1
        except ValueError:
            errors.append(f"{rel} front matter is not closed")
            continue
        front_matter = lines[1:end]
        if not any(line.startswith("status:") for line in front_matter):
            errors.append(f"{rel} front matter must include status:")
    return errors


def _validate_current_refs_exist(repo_root: Path) -> list[str]:
    scan_paths = [repo_root / "AGENTS.md", *_current_docs(repo_root)]
    if not (repo_root / "AGENTS.md").exists():
        return ["AGENTS.md is missing"]
    errors: list[str] = []
    for path in scan_paths:
        rel = path.relative_to(repo_root).as_posix()
        text = path.read_text(encoding="utf-8")
        for ref in sorted(set(DOC_CURRENT_REF_RE.findall(text))):
            if not (repo_root / ref).exists():
                errors.append(f"{rel} references missing current doc: {ref}")
    return errors


def _validate_archived_docs_not_reintroduced(repo_root: Path) -> list[str]:
    errors: list[str] = []
    forbidden_refs = {
        f"docs/current/{filename}" for filename in ARCHIVED_CURRENT_DOC_FILENAMES
    }
    scan_paths = [repo_root / "AGENTS.md", *_current_docs(repo_root)]
    for path in scan_paths:
        if not path.exists():
            continue
        rel = path.relative_to(repo_root).as_posix()
        text = path.read_text(encoding="utf-8")
        for forbidden_ref in sorted(forbidden_refs):
            if forbidden_ref in text:
                errors.append(
                    f"{rel} reintroduces archived current doc reference: {forbidden_ref}"
                )
    return errors


def _current_docs(repo_root: Path) -> list[Path]:
    return sorted((repo_root / "docs" / "current").rglob("*.md"))


if __name__ == "__main__":
    raise SystemExit(main())
