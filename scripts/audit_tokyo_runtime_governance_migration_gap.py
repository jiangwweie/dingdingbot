#!/usr/bin/env python3
"""Read-only audit for the Tokyo runtime-governance migration gap.

The script statically inspects local Alembic migration source files between the
currently deployed Tokyo revision and the local runtime-governance head. It does
not connect to a database, run migrations, SSH, read secrets, restart services,
create execution records, create orders, call OrderLifecycle, or call exchange
APIs.
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_BASE_REVISION = "064"
DEFAULT_HEAD_REVISION = "069"
DEFAULT_EXPECTED_REVISION_COUNT = 5

DATA_DESTRUCTIVE_UPGRADE_OPS = {
    "drop_table",
    "drop_column",
    "delete",
    "truncate",
}
NON_ADDITIVE_SCHEMA_OPS = {
    "alter_column",
    "drop_constraint",
    "drop_index",
    "execute",
}
DATA_TOUCHING_OPS = {
    "execute",
    "bulk_insert",
}
IGNORED_OP_CALLS = {
    "get_bind",
}


class MigrationGapAuditError(RuntimeError):
    """Raised when local migration-gap inspection cannot proceed."""


@dataclass(frozen=True)
class CommandResult:
    stdout: str
    returncode: int


@dataclass(frozen=True)
class MigrationOp:
    name: str
    line_number: int
    table: str | None = None
    column: str | None = None
    nullable: bool | None = None
    has_server_default: bool = False


@dataclass(frozen=True)
class MigrationInfo:
    revision: str
    down_revision: str | None
    filename: str
    path: Path
    upgrade_ops: tuple[MigrationOp, ...]


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    repo_root = _repo_root()
    report = build_migration_gap_report(
        repo_root=repo_root,
        base_revision=args.base_revision,
        head_revision=args.head_revision,
        expected_revision_count=args.expected_revision_count,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_human_report(report)
    return 0 if report["checks"]["ready_for_controlled_migration_preflight"] else 2


def build_migration_gap_report(
    *,
    repo_root: Path,
    base_revision: str,
    head_revision: str,
    expected_revision_count: int | None,
) -> dict[str, Any]:
    """Build a static report for the local migration gap."""

    versions_dir = repo_root / "migrations" / "versions"
    migrations = _load_migrations(versions_dir)
    chain, chain_blockers = _migration_chain(
        migrations=migrations,
        base_revision=base_revision,
        head_revision=head_revision,
    )
    destructive_ops = _op_evidence(
        chain,
        lambda op: op.name in DATA_DESTRUCTIVE_UPGRADE_OPS,
    )
    non_additive_ops = _op_evidence(
        chain,
        lambda op: op.name in NON_ADDITIVE_SCHEMA_OPS,
    )
    data_touching_ops = _op_evidence(
        chain,
        lambda op: op.name in DATA_TOUCHING_OPS,
    )
    not_null_existing_table_adds = _op_evidence(
        chain,
        lambda op: (
            op.name == "add_column"
            and op.nullable is False
            and not op.has_server_default
        ),
    )

    blockers = list(chain_blockers)
    warnings: list[str] = []
    if expected_revision_count is not None and len(chain) != expected_revision_count:
        blockers.append("migration_gap_revision_count_mismatch")
    if destructive_ops:
        blockers.append("data_destructive_upgrade_ops_present")
    if non_additive_ops:
        warnings.append("non_additive_schema_ops_present")
    if data_touching_ops:
        warnings.append("data_touching_upgrade_ops_present")
    if not_null_existing_table_adds:
        warnings.append("not_null_columns_added_to_existing_table")

    return {
        "status": "ready_for_controlled_migration_preflight" if not blockers else "blocked",
        "scope": "tokyo_runtime_governance_migration_gap_audit",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(repo_root),
        "inputs": {
            "base_revision": base_revision,
            "head_revision": head_revision,
            "expected_revision_count": expected_revision_count,
        },
        "chain": [_migration_summary(item) for item in chain],
        "operation_summary": _operation_summary(chain),
        "review_evidence": {
            "data_destructive_upgrade_ops": destructive_ops,
            "non_additive_schema_ops": non_additive_ops,
            "data_touching_upgrade_ops": data_touching_ops,
            "not_null_existing_table_adds": not_null_existing_table_adds,
        },
        "checks": {
            "ready_for_controlled_migration_preflight": not blockers,
            "blockers": blockers,
            "warnings": warnings,
            "chain_length": len(chain),
            "expected_revision_count": expected_revision_count,
            "first_revision": chain[0].revision if chain else None,
            "last_revision": chain[-1].revision if chain else None,
        },
        "deployment_notes": {
            "requires_remote_db_backup": True,
            "requires_backend_stopped_or_write_quiesced": bool(
                data_touching_ops or not_null_existing_table_adds
            ),
            "positions_table_is_data_touched_by_revision_062": any(
                item["revision"] == "062" for item in data_touching_ops
            ),
            "controlled_submit_results_not_null_adds_require_empty_or_quiesced_table": any(
                item["revision"] == "053" for item in not_null_existing_table_adds
            ),
        },
        "safety_invariants": {
            "ssh_called": False,
            "database_connected": False,
            "migrations_run": False,
            "remote_files_modified": False,
            "services_restarted": False,
            "execution_intent_created": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "exchange_called": False,
            "secrets_read": False,
        },
    }


def _load_migrations(versions_dir: Path) -> dict[str, MigrationInfo]:
    if not versions_dir.is_dir():
        raise MigrationGapAuditError(f"migration versions dir missing: {versions_dir}")
    migrations: dict[str, MigrationInfo] = {}
    for path in sorted(versions_dir.glob("*.py")):
        info = _parse_migration(path)
        if info.revision in migrations:
            raise MigrationGapAuditError(f"duplicate migration revision: {info.revision}")
        migrations[info.revision] = info
    return migrations


def _parse_migration(path: Path) -> MigrationInfo:
    text = path.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(text, filename=str(path))
    revision = _module_assignment(tree, "revision")
    down_revision = _module_assignment(tree, "down_revision")
    if not revision:
        raise MigrationGapAuditError(f"migration revision missing: {path}")
    return MigrationInfo(
        revision=revision,
        down_revision=down_revision,
        filename=path.name,
        path=path,
        upgrade_ops=tuple(
            _UpgradeOpVisitor(constants=_module_string_constants(tree)).collect(tree)
        ),
    )


def _module_assignment(tree: ast.Module, name: str) -> str | None:
    for node in tree.body:
        target_name = None
        value = None
        if isinstance(node, ast.Assign) and node.targets:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                target_name = target.id
                value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target_name = node.target.id
            value = node.value
        if target_name == name:
            return _literal_string_or_none(value)
    return None


def _literal_string_or_none(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant):
        if node.value is None:
            return None
        if isinstance(node.value, str):
            return node.value
    return None


def _literal_or_constant_string(
    node: ast.AST | None,
    constants: dict[str, str],
) -> str | None:
    value = _literal_string_or_none(node)
    if value is not None:
        return value
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    return None


def _module_string_constants(tree: ast.Module) -> dict[str, str]:
    constants: dict[str, str] = {}
    for node in tree.body:
        target_name = None
        value = None
        if isinstance(node, ast.Assign) and node.targets:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                target_name = target.id
                value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target_name = node.target.id
            value = node.value
        if target_name:
            literal_value = _literal_string_or_none(value)
            if literal_value is not None:
                constants[target_name] = literal_value
    return constants


def _literal_bool_or_none(node: ast.AST | None) -> bool | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, bool):
        return node.value
    return None


class _UpgradeOpVisitor(ast.NodeVisitor):
    def __init__(self, *, constants: dict[str, str]) -> None:
        self._ops: list[MigrationOp] = []
        self._functions: dict[str, ast.FunctionDef] = {}
        self._visiting: set[str] = set()
        self._constants = constants

    def collect(self, tree: ast.Module) -> list[MigrationOp]:
        self._functions = {
            node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)
        }
        self._visit_function_body("upgrade")
        return self._ops

    def _visit_function_body(self, name: str) -> None:
        node = self._functions.get(name)
        if node is None or name in self._visiting:
            return
        self._visiting.add(name)
        for child in node.body:
            self.visit(child)
        self._visiting.remove(name)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        return None

    def visit_Call(self, node: ast.Call) -> Any:
        op_name = _op_call_name(node)
        if op_name and op_name not in IGNORED_OP_CALLS:
            self._ops.append(_migration_op_from_call(op_name, node, self._constants))
        elif isinstance(node.func, ast.Name) and node.func.id in self._functions:
            self._visit_function_body(node.func.id)
        self.generic_visit(node)


def _op_call_name(node: ast.Call) -> str | None:
    func = node.func
    if not isinstance(func, ast.Attribute):
        return None
    receiver = func.value
    if isinstance(receiver, ast.Name) and (receiver.id == "op" or receiver.id.endswith("_op")):
        return func.attr
    return None


def _migration_op_from_call(
    name: str,
    node: ast.Call,
    constants: dict[str, str],
) -> MigrationOp:
    table_arg_index = 0
    if name in {"create_check_constraint", "drop_constraint"}:
        table_arg_index = 1
    table = (
        _literal_or_constant_string(node.args[table_arg_index], constants)
        if len(node.args) > table_arg_index
        else None
    )
    column = None
    nullable = None
    has_server_default = False
    if name == "add_column" and len(node.args) >= 2:
        column_call = node.args[1]
        if isinstance(column_call, ast.Call):
            column = (
                _literal_or_constant_string(column_call.args[0], constants)
                if column_call.args
                else None
            )
            nullable = _keyword_bool(column_call, "nullable")
            has_server_default = _has_keyword(column_call, "server_default")
    return MigrationOp(
        name=name,
        line_number=node.lineno,
        table=table,
        column=column,
        nullable=nullable,
        has_server_default=has_server_default,
    )


def _keyword_bool(node: ast.Call, keyword_name: str) -> bool | None:
    for keyword in node.keywords:
        if keyword.arg == keyword_name:
            return _literal_bool_or_none(keyword.value)
    return None


def _has_keyword(node: ast.Call, keyword_name: str) -> bool:
    return any(keyword.arg == keyword_name for keyword in node.keywords)


def _migration_chain(
    *,
    migrations: dict[str, MigrationInfo],
    base_revision: str,
    head_revision: str,
) -> tuple[list[MigrationInfo], list[str]]:
    blockers: list[str] = []
    if base_revision not in migrations:
        blockers.append("base_revision_missing")
    if head_revision not in migrations:
        blockers.append("head_revision_missing")
        return [], blockers

    chain_reversed: list[MigrationInfo] = []
    seen: set[str] = set()
    current_revision: str | None = head_revision
    while current_revision and current_revision != base_revision:
        if current_revision in seen:
            blockers.append("migration_chain_cycle_detected")
            break
        seen.add(current_revision)
        current = migrations.get(current_revision)
        if current is None:
            blockers.append("migration_chain_link_missing")
            break
        chain_reversed.append(current)
        current_revision = current.down_revision

    if current_revision != base_revision:
        blockers.append("migration_chain_does_not_reach_base")
    chain = list(reversed(chain_reversed))
    for previous, current in zip(chain, chain[1:]):
        if current.down_revision != previous.revision:
            blockers.append("migration_chain_not_linear")
            break
    return chain, blockers


def _migration_summary(info: MigrationInfo) -> dict[str, Any]:
    return {
        "revision": info.revision,
        "down_revision": info.down_revision,
        "filename": info.filename,
        "upgrade_operation_counts": _counts(op.name for op in info.upgrade_ops),
    }


def _operation_summary(chain: list[MigrationInfo]) -> dict[str, int]:
    return _counts(op.name for info in chain for op in info.upgrade_ops)


def _op_evidence(
    chain: list[MigrationInfo],
    predicate: Any,
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for info in chain:
        for op in info.upgrade_ops:
            if predicate(op):
                evidence.append(
                    {
                        "revision": info.revision,
                        "filename": info.filename,
                        "operation": op.name,
                        "line": op.line_number,
                        "table": op.table,
                        "column": op.column,
                        "nullable": op.nullable,
                        "has_server_default": op.has_server_default,
                    }
                )
    return evidence


def _counts(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Statically inspect the local Alembic migration gap before a future "
            "Tokyo runtime-governance deployment."
        )
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    parser.add_argument(
        "--base-revision",
        default=DEFAULT_BASE_REVISION,
        help="Currently deployed Tokyo migration revision.",
    )
    parser.add_argument(
        "--head-revision",
        default=DEFAULT_HEAD_REVISION,
        help="Local migration head expected for this release stage.",
    )
    parser.add_argument(
        "--expected-revision-count",
        type=int,
        default=DEFAULT_EXPECTED_REVISION_COUNT,
        help="Expected number of migrations after base through head.",
    )
    return parser.parse_args(argv)


def _repo_root() -> Path:
    result = _run(("git", "rev-parse", "--show-toplevel"), cwd=Path.cwd())
    if result.returncode != 0 or not result.stdout:
        raise MigrationGapAuditError("not inside a git repository")
    return Path(result.stdout.strip())


def _run(command: tuple[str, ...], *, cwd: Path) -> CommandResult:
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return CommandResult(stdout=completed.stdout.strip(), returncode=completed.returncode)


def _print_human_report(report: dict[str, Any]) -> None:
    checks = report["checks"]
    print(f"status={report['status']}")
    print(f"base_revision={report['inputs']['base_revision']}")
    print(f"head_revision={report['inputs']['head_revision']}")
    print(f"chain_length={checks['chain_length']}")
    print(
        "ready_for_controlled_migration_preflight="
        + str(checks["ready_for_controlled_migration_preflight"]).lower()
    )
    if checks["blockers"]:
        print("blockers=" + ",".join(checks["blockers"]))
    if checks["warnings"]:
        print("warnings=" + ",".join(checks["warnings"]))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except MigrationGapAuditError as exc:
        print(f"migration_gap_audit_error={exc}", file=sys.stderr)
        raise SystemExit(2)
