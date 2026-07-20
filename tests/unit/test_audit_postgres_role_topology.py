from __future__ import annotations

from scripts.audit_postgres_role_topology import evaluate_role_topology


def _facts(*, application: str = "runtime_app", migration: str | None = "migrator", login_roles: list[str] | None = None, app_attributes: dict[str, bool] | None = None, schema_create: bool = False, object_owner: bool = False, set_role_targets: list[str] | None = None):
    return {
        "database_name": "brc",
        "application_role": application,
        "migration_role": migration,
        "application_session_user": application,
        "application_current_user": application,
        "login_roles": login_roles or [application, migration],
        "role_attributes": {
            application: {
                "rolsuper": False,
                "rolcreaterole": False,
                "rolcreatedb": False,
                "rolcanlogin": True,
                **(app_attributes or {}),
            },
            **({migration: {"rolsuper": True, "rolcreaterole": True, "rolcreatedb": True, "rolcanlogin": True}} if migration else {}),
        },
        "database_owner": migration,
        "target_schema": "public",
        "target_schema_owner": migration,
        "schema_create_privilege": schema_create,
        "managed_object_owners": [migration],
        "application_owns_managed_objects": object_owner,
        "role_membership": [],
        "application_set_role_targets": set_role_targets or [],
        "default_privileges": [],
    }


def test_separate_least_privilege_roles_are_sufficient():
    result = evaluate_role_topology(_facts())

    assert result["role_topology_decision"] == "existing_roles_sufficient"
    assert result["credential_or_secret_change_required"] is False
    assert result["application_can_create"] is False
    assert result["application_can_alter"] is False


def test_shared_superuser_identity_requires_new_credential_boundary():
    result = evaluate_role_topology(
        _facts(
            application="brc_dryrun",
            migration="brc_dryrun",
            login_roles=["brc_dryrun"],
            app_attributes={"rolsuper": True, "rolcreaterole": True, "rolcreatedb": True},
        )
    )

    assert result["role_topology_decision"] == "credential_or_secret_change_required"
    assert result["credential_or_secret_change_required"] is True
    assert result["application_can_create"] is True


def test_existing_separate_roles_with_ddl_are_grant_convergence_not_new_secret():
    result = evaluate_role_topology(_facts(schema_create=True))

    assert result["role_topology_decision"] == "grant_owner_convergence_without_secret_change"
    assert result["credential_or_secret_change_required"] is False


def test_unproven_migration_identity_fails_closed():
    result = evaluate_role_topology(_facts(migration=None, login_roles=["runtime_app", "other"]))

    assert result["role_topology_decision"] == "role_topology_unknown"


def test_auditor_is_catalog_readonly_and_never_handles_role_credentials():
    source = (
        __import__("pathlib").Path(__file__).resolve().parents[2]
        / "scripts/audit_postgres_role_topology.py"
    ).read_text(encoding="utf-8")

    assert "SET TRANSACTION READ ONLY" in source
    for forbidden in ("CREATE ROLE", "ALTER ROLE", "GRANT ", "REVOKE ", "PASSWORD"):
        assert forbidden not in source
