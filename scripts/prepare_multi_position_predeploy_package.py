#!/usr/bin/env python3
"""Print a stdout-only, non-mutating R9 multi-position predeploy manifest.

The manifest deliberately distinguishes facts this command can prove locally
from deployment evidence that must be collected in a shadow or Tokyo readonly
surface.  It never writes a manifest, initiates SSH, invokes Alembic, or
changes a database.  Supplied PostgreSQL DSNs are used only in explicit
read-only transactions for the schema fingerprint and role-topology audit.
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Iterable, Mapping

import sqlalchemy as sa


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.audit_postgres_role_topology import audit_role_topology


SCHEMA_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
STATUS_VALUES = frozenset({"passed", "blocked", "not_run"})


class PredeployPackageError(RuntimeError):
    """Raised when an immutable predeploy fact cannot be derived."""


@dataclass(frozen=True)
class CommandResult:
    stdout: str
    returncode: int


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        report = build_predeploy_manifest(
            repo_root=_repo_root(),
            postgres_dsn=args.postgres_dsn or None,
            schema=args.schema or None,
            shadow_restore_status=args.shadow_restore_status,
            previous_entry_status=args.previous_entry_status,
            previous_lifecycle_status=args.previous_lifecycle_status,
            previous_projection_status=args.previous_projection_status,
            previous_monitor_status=args.previous_monitor_status,
            role_topology_database_url=args.role_topology_database_url or None,
            role_topology_migration_role=args.role_topology_migration_role or None,
            role_topology_schema=args.role_topology_schema,
            role_topology_audit=_parse_role_topology_audit(args.role_topology_audit_json),
        )
    except (PredeployPackageError, sa.exc.SQLAlchemyError, ValueError) as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "ready_for_owner_deploy_confirmation" else 2


def build_predeploy_manifest(
    *,
    repo_root: Path,
    postgres_dsn: str | None = None,
    schema: str | None = None,
    shadow_restore_status: str = "not_run",
    previous_entry_status: str = "not_run",
    previous_lifecycle_status: str = "not_run",
    previous_projection_status: str = "not_run",
    previous_monitor_status: str = "not_run",
    role_topology_database_url: str | None = None,
    role_topology_migration_role: str | None = None,
    role_topology_schema: str = "public",
    role_topology_audit: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the R9 gate without accepting unverified evidence as success."""

    _validate_statuses(
        shadow_restore_status,
        previous_entry_status,
        previous_lifecycle_status,
        previous_projection_status,
        previous_monitor_status,
    )
    commit = _git(repo_root, "rev-parse", "HEAD").stdout
    branch = _git(repo_root, "branch", "--show-current").stdout or "DETACHED"
    source_tree = _git(repo_root, "rev-parse", "HEAD^{tree}").stdout
    tracked_dirty = _tracked_dirty(repo_root)
    migration_graph = migration_graph_fingerprint(repo_root / "migrations" / "versions")
    schema_fingerprint = schema_fingerprint_from_postgres(postgres_dsn, schema)
    role_topology = _role_topology_from_audit(
        role_topology_database_url,
        migration_role=role_topology_migration_role,
        target_schema=role_topology_schema,
        audit_receipt=role_topology_audit,
    )

    previous = {
        "entry": previous_entry_status,
        "lifecycle": previous_lifecycle_status,
        "projection": previous_projection_status,
        "monitor": previous_monitor_status,
    }
    blockers: list[str] = []
    if tracked_dirty:
        blockers.append("tracked_worktree_dirty")
    if schema_fingerprint["status"] != "passed":
        blockers.append("candidate_schema_fingerprint_missing")
    if shadow_restore_status != "passed":
        blockers.append("production_backup_shadow_restore_not_verified")
    if role_topology["status"] != "passed":
        blockers.append(str(role_topology["blocker"]))
    failed_previous = [surface for surface, status in previous.items() if status != "passed"]
    if failed_previous:
        blockers.append("previous_writer_compatibility_not_verified")

    status = "ready_for_owner_deploy_confirmation" if not blockers else "blocked"
    return {
        "schema": "brc.multi_position_predeploy_package.v1",
        "status": status,
        "exact_commit": commit,
        "branch": branch,
        "source_digest": {
            "algorithm": "git-tree-sha1",
            "value": source_tree,
            "tracked_worktree_dirty": tracked_dirty,
        },
        "migration_head": migration_graph["head"],
        "migration_graph": migration_graph,
        "schema_fingerprint": schema_fingerprint,
        "shadow_restore": {
            "status": shadow_restore_status,
            "required_evidence": "production_backup_to_shadow_then_candidate_upgrade_and_full_chain",
        },
        "previous_writer_compatibility": {
            "classification": (
                "previous_code_write_compatible"
                if not failed_previous
                else "not_verified"
            ),
            "surfaces": previous,
            "required_mode": "writer_fence_enabled",
        },
        "role_topology": role_topology,
        "writer_fence_plan": _writer_fence_plan(commit),
        "postdeploy_no_write_canary": {
            "status": "planned_not_executed",
            "required_checks": [
                "release_head_matches_exact_commit",
                "schema_at_candidate_head",
                "read_only_role_preflight",
                "no_entry_mutation",
                "no_exchange_write",
            ],
        },
        "blockers": blockers,
        "forbidden_effects": {
            "tokyo_ssh_called": False,
            "production_migration_run": False,
            "production_role_changed": False,
            "writer_fence_changed": False,
            "exchange_write_called": False,
            "report_file_written": False,
        },
    }


def _role_topology_from_audit(
    database_url: str | None,
    *,
    migration_role: str | None,
    target_schema: str,
    audit_receipt: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    required_fields = [
        "application_identity",
        "migration_identity",
        "schema_owner",
        "membership",
        "ddl_capability",
    ]
    if audit_receipt is not None and database_url:
        raise ValueError("role_topology_audit_receipt_and_database_url_conflict")
    if audit_receipt is not None:
        audit = _validated_role_topology_audit(audit_receipt)
    elif database_url:
        audit = audit_role_topology(
            database_url,
            migration_role=migration_role,
            target_schema=target_schema,
        )
    else:
        return {
            "status": "not_run",
            "blocker": "tokyo_role_topology_not_verified",
            "required_fields": required_fields,
        }
    decision = str(audit["role_topology_decision"])
    if decision == "existing_roles_sufficient":
        status, blocker = "passed", None
    elif decision == "grant_owner_convergence_without_secret_change":
        status, blocker = "blocked", "tokyo_role_topology_convergence_not_applied"
    elif decision == "credential_or_secret_change_required":
        status, blocker = "blocked", "tokyo_role_topology_credential_change_required"
    else:
        status, blocker = "blocked", "tokyo_role_topology_unknown"
    return {
        "status": status,
        "blocker": blocker,
        "required_fields": required_fields,
        "audit": audit,
    }


def _validated_role_topology_audit(receipt: Mapping[str, Any]) -> dict[str, Any]:
    audit = dict(receipt)
    required = {
        "status": "role_topology_audited",
        "application_role_id": "brc_runtime_app",
        "migration_role_id": "brc_runtime_migrator",
        "credential_or_secret_change_required": False,
        "role_topology_decision": "existing_roles_sufficient",
        "application_can_create": False,
        "application_can_alter": False,
        "application_can_drop": False,
    }
    if any(audit.get(key) != value for key, value in required.items()):
        raise ValueError("role_topology_audit_receipt_invalid")
    forbidden = audit.get("forbidden_effects")
    if not isinstance(forbidden, Mapping) or any(value is not False for value in forbidden.values()):
        raise ValueError("role_topology_audit_receipt_forbidden_effect_invalid")
    return audit


def _parse_role_topology_audit(value: str) -> Mapping[str, Any] | None:
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("role_topology_audit_receipt_json_invalid") from exc
    if not isinstance(parsed, Mapping):
        raise ValueError("role_topology_audit_receipt_json_invalid")
    return parsed


def migration_graph_fingerprint(migrations_dir: Path) -> dict[str, Any]:
    if not migrations_dir.is_dir():
        raise PredeployPackageError("migration_directory_missing")
    revisions: dict[str, dict[str, Any]] = {}
    digest = hashlib.sha256()
    for path in sorted(migrations_dir.glob("*.py")):
        if path.name == "__init__.py":
            continue
        content = path.read_bytes()
        revision, down_revision = _migration_identifiers(path, content)
        if revision in revisions:
            raise PredeployPackageError("duplicate_migration_revision")
        file_digest = hashlib.sha256(content).hexdigest()
        revisions[revision] = {
            "file": path.name,
            "down_revision": down_revision,
            "sha256": file_digest,
        }
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(content)
        digest.update(b"\0")
    if not revisions:
        raise PredeployPackageError("migration_files_missing")
    parents = {value["down_revision"] for value in revisions.values() if value["down_revision"]}
    heads = sorted(set(revisions) - parents)
    if len(heads) != 1:
        raise PredeployPackageError("migration_graph_not_single_head")
    _validate_linear_graph(revisions, heads[0])
    return {
        "algorithm": "sha256(filename-nul-content-nul)",
        "checksum": digest.hexdigest(),
        "revision_count": len(revisions),
        "head": heads[0],
    }


def schema_fingerprint_from_postgres(
    postgres_dsn: str | None, schema: str | None
) -> dict[str, Any]:
    if not postgres_dsn or not schema:
        return {"status": "not_run", "reason": "postgres_dsn_and_schema_required"}
    if not SCHEMA_NAME.fullmatch(schema):
        raise ValueError("schema_name_invalid")
    engine = sa.create_engine(postgres_dsn)
    try:
        with engine.connect() as connection:
            with connection.begin():
                connection.execute(sa.text("SET TRANSACTION READ ONLY"))
                objects = _schema_objects(connection, schema)
    finally:
        engine.dispose()
    if not objects["columns"]:
        return {
            "status": "not_run",
            "schema": schema,
            "reason": "schema_has_no_tables",
        }
    canonical = json.dumps(objects, sort_keys=True, separators=(",", ":"))
    return {
        "status": "passed",
        "schema": schema,
        "algorithm": "sha256(canonical-pg-catalog-json)",
        "value": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "object_counts": {key: len(value) for key, value in objects.items()},
    }


def _schema_objects(connection: sa.Connection, schema: str) -> dict[str, list[dict[str, Any]]]:
    columns = connection.execute(
        sa.text(
            "SELECT table_name, column_name, data_type, udt_name, is_nullable, "
            "column_default, ordinal_position FROM information_schema.columns "
            "WHERE table_schema = :schema ORDER BY table_name, ordinal_position"
        ),
        {"schema": schema},
    ).mappings().all()
    constraints = connection.execute(
        sa.text(
            "SELECT c.relname AS table_name, con.conname AS constraint_name, "
            "con.contype AS constraint_type, pg_get_constraintdef(con.oid, true) "
            "AS definition FROM pg_constraint con JOIN pg_class c ON c.oid = con.conrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = :schema "
            "ORDER BY c.relname, con.conname"
        ),
        {"schema": schema},
    ).mappings().all()
    indexes = connection.execute(
        sa.text(
            "SELECT c.relname AS table_name, i.relname AS index_name, "
            "pg_get_indexdef(i.oid) AS definition FROM pg_index x "
            "JOIN pg_class c ON c.oid = x.indrelid JOIN pg_class i ON i.oid = x.indexrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = :schema "
            "ORDER BY c.relname, i.relname"
        ),
        {"schema": schema},
    ).mappings().all()
    return {
        "columns": [dict(row) for row in columns],
        "constraints": [dict(row) for row in constraints],
        "indexes": [dict(row) for row in indexes],
    }


def _migration_identifiers(path: Path, content: bytes) -> tuple[str, str | None]:
    try:
        tree = ast.parse(content, filename=str(path))
    except SyntaxError as exc:
        raise PredeployPackageError("migration_syntax_invalid") from exc
    values: dict[str, Any] = {}
    for node in tree.body:
        target: ast.expr | None = None
        value: ast.expr | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign):
            target, value = node.target, node.value
        if isinstance(target, ast.Name) and target.id in {"revision", "down_revision"} and value:
            values[target.id] = ast.literal_eval(value)
    revision = values.get("revision")
    down_revision = values.get("down_revision")
    if not isinstance(revision, str) or not revision:
        raise PredeployPackageError("migration_revision_missing")
    if down_revision is not None and not isinstance(down_revision, str):
        raise PredeployPackageError("migration_down_revision_not_linear")
    return revision, down_revision


def _validate_linear_graph(revisions: dict[str, dict[str, Any]], head: str) -> None:
    seen: set[str] = set()
    current: str | None = head
    while current is not None:
        if current in seen or current not in revisions:
            raise PredeployPackageError("migration_graph_not_linear")
        seen.add(current)
        current = revisions[current]["down_revision"]
    if len(seen) != len(revisions):
        raise PredeployPackageError("migration_graph_disconnected")


def _writer_fence_plan(commit: str) -> dict[str, Any]:
    return {
        "status": "planned_not_executed",
        "must_remain_engaged_until": "postdeploy_no_write_canary_passed",
        "engage_command_template": (
            "python3 scripts/set_production_writer_fence.py --engage "
            "--deploy-transaction-id <transaction-id> --deploy-nonce <nonce> "
            f"--target-runtime-head {commit}"
        ),
        "release_forbidden_in_r9": True,
        "rollback_class": "writer_fence_plus_forward_fix",
    }


def _validate_statuses(*statuses: str) -> None:
    invalid = [status for status in statuses if status not in STATUS_VALUES]
    if invalid:
        raise ValueError("predeploy_status_invalid")


def _repo_root() -> Path:
    result = _run(("git", "rev-parse", "--show-toplevel"), Path.cwd())
    if result.returncode != 0 or not result.stdout:
        raise PredeployPackageError("not_inside_git_repository")
    return Path(result.stdout)


def _git(repo_root: Path, *args: str) -> CommandResult:
    result = _run(("git", *args), repo_root)
    if result.returncode != 0:
        raise PredeployPackageError("git_command_failed")
    return result


def _tracked_dirty(repo_root: Path) -> bool:
    return (
        _run(("git", "diff", "--quiet"), repo_root).returncode != 0
        or _run(("git", "diff", "--cached", "--quiet"), repo_root).returncode != 0
    )


def _run(command: Iterable[str], cwd: Path) -> CommandResult:
    completed = subprocess.run(
        tuple(command), cwd=str(cwd), check=False, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    return CommandResult(stdout=completed.stdout.strip(), returncode=completed.returncode)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--postgres-dsn", default="")
    parser.add_argument("--schema", default="")
    parser.add_argument("--shadow-restore-status", choices=sorted(STATUS_VALUES), default="not_run")
    parser.add_argument("--previous-entry-status", choices=sorted(STATUS_VALUES), default="not_run")
    parser.add_argument("--previous-lifecycle-status", choices=sorted(STATUS_VALUES), default="not_run")
    parser.add_argument("--previous-projection-status", choices=sorted(STATUS_VALUES), default="not_run")
    parser.add_argument("--previous-monitor-status", choices=sorted(STATUS_VALUES), default="not_run")
    parser.add_argument("--role-topology-database-url", default="")
    parser.add_argument("--role-topology-migration-role", default="")
    parser.add_argument("--role-topology-schema", default="public")
    parser.add_argument("--role-topology-audit-json", default="")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
