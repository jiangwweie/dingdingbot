#!/usr/bin/env python3
"""Read-only audit of the PostgreSQL application/migration role boundary.

This command never creates, alters, grants to, or revokes a database role.  It
uses one read-only transaction and prints a JSON document whose identity refs
are hashes, never connection URLs or credentials.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping

import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.pg_dsn import normalize_sync_postgres_dsn  # noqa: E402


ROLE_TOPOLOGY_DECISIONS = frozenset(
    {
        "existing_roles_sufficient",
        "grant_owner_convergence_without_secret_change",
        "credential_or_secret_change_required",
        "role_topology_unknown",
    }
)


def audit_role_topology(
    database_url: str,
    *,
    migration_role: str | None = None,
    target_schema: str = "public",
) -> dict[str, Any]:
    """Read catalog facts and return their fail-closed topology decision."""

    if not target_schema or not target_schema.replace("_", "a").isalnum():
        raise ValueError("target_schema_invalid")
    dsn = normalize_sync_postgres_dsn(database_url)
    if not dsn.startswith(("postgresql://", "postgresql+psycopg://")):
        raise ValueError("postgresql_database_url_required")
    engine = sa.create_engine(dsn)
    try:
        with engine.connect() as connection:
            with connection.begin():
                connection.execute(sa.text("SET TRANSACTION READ ONLY"))
                identity = connection.execute(
                    sa.text(
                        "SELECT current_database() AS database_name, "
                        "session_user AS session_user, current_user AS current_user"
                    )
                ).mappings().one()
                login_roles = connection.execute(
                    sa.text(
                        "SELECT rolname FROM pg_roles WHERE rolcanlogin "
                        "ORDER BY rolname"
                    )
                ).scalars().all()
                application_role = str(identity["session_user"])
                resolved_migration_role = migration_role or _infer_migration_role(
                    login_roles, application_role
                )
                facts = _read_catalog_facts(
                    connection,
                    application_role=application_role,
                    migration_role=resolved_migration_role,
                    target_schema=target_schema,
                    identity=dict(identity),
                    login_roles=[str(role) for role in login_roles],
                )
    finally:
        engine.dispose()
    return evaluate_role_topology(facts)


def evaluate_role_topology(facts: Mapping[str, Any]) -> dict[str, Any]:
    """Classify immutable catalog facts without performing a privilege change."""

    application_role = _required_text(facts.get("application_role"), "application_role")
    migration_role = facts.get("migration_role")
    role_attributes = dict(facts.get("role_attributes") or {})
    app_attributes = dict(role_attributes.get(application_role) or {})
    migration_attributes = dict(role_attributes.get(str(migration_role)) or {})
    known_roles = set(role_attributes)
    schema_create = bool(facts.get("schema_create_privilege"))
    object_owner = bool(facts.get("application_owns_managed_objects"))
    set_role_targets = set(facts.get("application_set_role_targets") or [])
    app_is_superuser = bool(app_attributes.get("rolsuper"))
    app_can_create_roles = bool(app_attributes.get("rolcreaterole"))
    app_can_create_databases = bool(app_attributes.get("rolcreatedb"))

    unknown = (
        not migration_role
        or application_role not in known_roles
        or str(migration_role) not in known_roles
        or not bool(app_attributes.get("rolcanlogin"))
        or not bool(migration_attributes)
    )
    application_can_create = app_is_superuser or schema_create
    application_can_alter = (
        app_is_superuser
        or object_owner
        or str(migration_role) in set_role_targets
    )
    application_can_drop = application_can_alter
    same_identity = application_role == migration_role
    only_one_login = len(set(facts.get("login_roles") or [])) <= 1

    if unknown:
        decision = "role_topology_unknown"
        credential_change_required = False
    elif same_identity or only_one_login:
        decision = "credential_or_secret_change_required"
        credential_change_required = True
    elif application_can_create or application_can_alter or application_can_drop:
        decision = "grant_owner_convergence_without_secret_change"
        credential_change_required = False
    else:
        decision = "existing_roles_sufficient"
        credential_change_required = False
    assert decision in ROLE_TOPOLOGY_DECISIONS

    database_name = _required_text(facts.get("database_name"), "database_name")
    session_user = _required_text(facts.get("application_session_user"), "session_user")
    current_user = _required_text(facts.get("application_current_user"), "current_user")
    return {
        "status": "role_topology_audited",
        "database_ref": _identity_ref(database_name),
        "migration_role_id": migration_role,
        "application_role_id": application_role,
        "application_session_user": session_user,
        "application_current_user": current_user,
        "application_connection_identity_ref": _identity_ref(
            f"{database_name}|{session_user}|{current_user}"
        ),
        "migration_connection_identity_ref": (
            _identity_ref(f"{database_name}|{migration_role}")
            if migration_role
            else None
        ),
        "database_owner": facts.get("database_owner"),
        "target_schema": facts.get("target_schema"),
        "target_schema_owner": facts.get("target_schema_owner"),
        "managed_table_and_sequence_owners": facts.get("managed_object_owners", []),
        "role_membership": facts.get("role_membership", []),
        "set_role_path": sorted(set_role_targets),
        "schema_create_privilege": schema_create,
        "object_owner_implicit_alter_drop_capability": object_owner,
        "default_privileges": facts.get("default_privileges", []),
        "application_can_create": application_can_create,
        "application_can_alter": application_can_alter,
        "application_can_drop": application_can_drop,
        "credential_or_secret_change_required": credential_change_required,
        "role_topology_decision": decision,
        "forbidden_effects": {
            "role_created": False,
            "role_altered": False,
            "grant_or_revoke_executed": False,
            "credential_read": False,
            "credential_changed": False,
            "database_write_executed": False,
            "exchange_write_called": False,
        },
    }


def _read_catalog_facts(
    connection: sa.Connection,
    *,
    application_role: str,
    migration_role: str | None,
    target_schema: str,
    identity: Mapping[str, Any],
    login_roles: list[str],
) -> dict[str, Any]:
    role_names = [application_role] + ([migration_role] if migration_role else [])
    attributes = connection.execute(
        sa.text(
            "SELECT rolname, rolsuper, rolcreaterole, rolcreatedb, rolcanlogin "
            "FROM pg_roles WHERE rolname = ANY(:role_names) ORDER BY rolname"
        ),
        {"role_names": role_names},
    ).mappings().all()
    membership = connection.execute(
        sa.text(
            "SELECT member_role.rolname AS member, granted_role.rolname AS role "
            "FROM pg_auth_members m JOIN pg_roles member_role ON member_role.oid=m.member "
            "JOIN pg_roles granted_role ON granted_role.oid=m.roleid "
            "WHERE member_role.rolname = :application_role "
            "ORDER BY granted_role.rolname"
        ),
        {"application_role": application_role},
    ).mappings().all()
    schema_row = connection.execute(
        sa.text(
            "SELECT n.nspname AS schema_name, pg_get_userbyid(n.nspowner) AS owner, "
            "has_schema_privilege(:application_role,n.oid,'CREATE') AS can_create "
            "FROM pg_namespace n WHERE n.nspname=:target_schema"
        ),
        {"application_role": application_role, "target_schema": target_schema},
    ).mappings().one_or_none()
    database_owner = connection.execute(
        sa.text("SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=current_database()")
    ).scalar_one()
    object_owners = connection.execute(
        sa.text(
            "SELECT DISTINCT pg_get_userbyid(c.relowner) AS owner FROM pg_class c "
            "JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname=:target_schema AND c.relkind IN ('r','p','S') ORDER BY owner"
        ),
        {"target_schema": target_schema},
    ).scalars().all()
    owned_object_count = connection.execute(
        sa.text(
            "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname=:target_schema AND c.relkind IN ('r','p','S') "
            "AND c.relowner=(SELECT oid FROM pg_roles WHERE rolname=:application_role)"
        ),
        {"target_schema": target_schema, "application_role": application_role},
    ).scalar_one()
    defaults = connection.execute(
        sa.text(
            "SELECT coalesce(pg_get_userbyid(defaclrole),'') AS owner, defaclnamespace::regnamespace::text AS schema "
            "FROM pg_default_acl ORDER BY 1,2"
        )
    ).mappings().all()
    return {
        "database_name": identity["database_name"],
        "application_role": application_role,
        "migration_role": migration_role,
        "application_session_user": identity["session_user"],
        "application_current_user": identity["current_user"],
        "login_roles": login_roles,
        "role_attributes": {str(row["rolname"]): dict(row) for row in attributes},
        "database_owner": database_owner,
        "target_schema": target_schema,
        "target_schema_owner": schema_row["owner"] if schema_row else None,
        "schema_create_privilege": bool(schema_row and schema_row["can_create"]),
        "managed_object_owners": [str(owner) for owner in object_owners],
        "application_owns_managed_objects": bool(owned_object_count),
        "role_membership": [dict(row) for row in membership],
        "application_set_role_targets": [str(row["role"]) for row in membership],
        "default_privileges": [dict(row) for row in defaults],
    }


def _infer_migration_role(login_roles: list[str], application_role: str) -> str | None:
    distinct = [role for role in login_roles if role != application_role]
    return distinct[0] if len(distinct) == 1 else application_role if len(login_roles) == 1 else None


def _required_text(value: object, name: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise ValueError(f"{name}_required")
    return result


def _identity_ref(value: str) -> str:
    return "sha256:" + sha256(value.encode("utf-8")).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("PG_DATABASE_URL", ""))
    parser.add_argument("--migration-role", default="")
    parser.add_argument("--target-schema", default="public")
    args = parser.parse_args(argv)
    if not args.database_url:
        parser.error("--database-url or PG_DATABASE_URL is required")
    try:
        report = audit_role_topology(
            args.database_url,
            migration_role=args.migration_role or None,
            target_schema=args.target_schema,
        )
    except (SQLAlchemyError, ValueError) as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0 if report["role_topology_decision"] != "role_topology_unknown" else 2


if __name__ == "__main__":
    raise SystemExit(main())
