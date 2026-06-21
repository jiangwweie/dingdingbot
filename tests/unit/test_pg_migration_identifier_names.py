from __future__ import annotations

import ast
from pathlib import Path


POSTGRES_IDENTIFIER_LIMIT = 63
MIGRATION_IDENTIFIER_PREFIXES = ("ck_", "idx_", "fk_", "uq_", "check_")


def _migration_revision_values(path: Path) -> dict[str, object]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    values: dict[str, object] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = node.targets
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
            value = node.value
        else:
            continue
        if value is None:
            continue
        for target in targets:
            if isinstance(target, ast.Name) and target.id in {
                "revision",
                "down_revision",
            }:
                values[target.id] = ast.literal_eval(value)
    return values


def test_migration_identifiers_fit_postgres_name_limit():
    bad_identifiers: list[tuple[str, int, str]] = []
    for path in Path("migrations/versions").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            value = node.value
            if not value.startswith(MIGRATION_IDENTIFIER_PREFIXES):
                continue
            if len(value) > POSTGRES_IDENTIFIER_LIMIT:
                bad_identifiers.append((path.name, len(value), value))

    assert bad_identifiers == []


def test_migration_revision_chain_is_single_head_after_slimming():
    revisions: dict[str, str] = {}
    down_revisions: dict[str, object] = {}
    for path in Path("migrations/versions").glob("*.py"):
        values = _migration_revision_values(path)
        revision = values.get("revision")
        if not isinstance(revision, str):
            continue
        revisions[revision] = path.name
        down_revisions[revision] = values.get("down_revision")

    missing_down_revisions = {
        revision: down_revision
        for revision, down_revision in down_revisions.items()
        if isinstance(down_revision, str) and down_revision not in revisions
    }
    heads = sorted(
        set(revisions)
        - {
            down_revision
            for down_revision in down_revisions.values()
            if isinstance(down_revision, str)
        }
    )
    roots = sorted(
        revision
        for revision, down_revision in down_revisions.items()
        if down_revision is None
    )

    assert len(revisions) == 84
    assert roots == ["001"]
    assert heads == ["084"]
    assert missing_down_revisions == {}
