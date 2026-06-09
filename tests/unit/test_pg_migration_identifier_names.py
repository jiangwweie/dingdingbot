from __future__ import annotations

import ast
from pathlib import Path


POSTGRES_IDENTIFIER_LIMIT = 63
MIGRATION_IDENTIFIER_PREFIXES = ("ck_", "idx_", "fk_", "uq_", "check_")


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
