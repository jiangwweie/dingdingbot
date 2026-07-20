from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "prepare_multi_position_predeploy_package.py"


def _module():
    spec = importlib.util.spec_from_file_location("multi_position_predeploy", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(("git", *args), cwd=repo, check=True, text=True,
                          stdout=subprocess.PIPE).stdout.strip()


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "migrations" / "versions").mkdir(parents=True)
    _git(tmp_path, "init", str(repo))
    _git(repo, "config", "user.email", "codex@example.test")
    _git(repo, "config", "user.name", "Codex Test")
    (repo / "migrations" / "versions" / "001.py").write_text(
        "revision = '001'\ndown_revision = None\n", encoding="utf-8"
    )
    (repo / "migrations" / "versions" / "002.py").write_text(
        "revision: str = '002'\ndown_revision: str = '001'\n", encoding="utf-8"
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "test migrations")
    return repo


def test_manifest_fails_closed_without_shadow_topology_and_previous_evidence(tmp_path: Path):
    module = _module()
    report = module.build_predeploy_manifest(repo_root=_repo(tmp_path))

    assert report["status"] == "blocked"
    assert report["migration_head"] == "002"
    assert report["schema_fingerprint"]["status"] == "not_run"
    assert report["forbidden_effects"]["writer_fence_changed"] is False
    assert set(report["blockers"]) == {
        "candidate_schema_fingerprint_missing",
        "production_backup_shadow_restore_not_verified",
        "tokyo_role_topology_not_verified",
        "previous_writer_compatibility_not_verified",
    }


def test_manifest_is_ready_only_with_all_explicit_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    module = _module()
    monkeypatch.setattr(
        module,
        "schema_fingerprint_from_postgres",
        lambda _dsn, _schema: {"status": "passed", "value": "fingerprint"},
    )
    monkeypatch.setattr(
        module,
        "audit_role_topology",
        lambda *_args, **_kwargs: {"role_topology_decision": "existing_roles_sufficient"},
    )
    report = module.build_predeploy_manifest(
        repo_root=_repo(tmp_path),
        shadow_restore_status="passed",
        previous_entry_status="passed",
        previous_lifecycle_status="passed",
        previous_projection_status="passed",
        previous_monitor_status="passed",
        role_topology_database_url="postgresql://role-audit",
    )

    assert report["status"] == "ready_for_owner_deploy_confirmation"
    assert report["previous_writer_compatibility"]["classification"] == (
        "previous_code_write_compatible"
    )
    assert report["writer_fence_plan"]["release_forbidden_in_r9"] is True


def test_manifest_refuses_manual_pass_when_catalog_requires_credential_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _module()
    monkeypatch.setattr(
        module,
        "audit_role_topology",
        lambda *_args, **_kwargs: {
            "role_topology_decision": "credential_or_secret_change_required"
        },
    )
    report = module.build_predeploy_manifest(
        repo_root=_repo(tmp_path),
        role_topology_database_url="postgresql://role-audit",
    )

    assert report["role_topology"]["status"] == "blocked"
    assert report["role_topology"]["blocker"] == (
        "tokyo_role_topology_credential_change_required"
    )
    assert "tokyo_role_topology_credential_change_required" in report["blockers"]


def test_manifest_accepts_only_structurally_valid_readonly_role_audit_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _module()
    monkeypatch.setattr(
        module,
        "schema_fingerprint_from_postgres",
        lambda _dsn, _schema: {"status": "passed", "value": "fingerprint"},
    )
    receipt = {
        "status": "role_topology_audited",
        "application_role_id": "brc_runtime_app",
        "migration_role_id": "brc_runtime_migrator",
        "credential_or_secret_change_required": False,
        "role_topology_decision": "existing_roles_sufficient",
        "application_can_create": False,
        "application_can_alter": False,
        "application_can_drop": False,
        "forbidden_effects": {"database_write_executed": False},
    }
    report = module.build_predeploy_manifest(
        repo_root=_repo(tmp_path),
        postgres_dsn="postgresql://shadow",
        schema="public",
        shadow_restore_status="passed",
        previous_entry_status="passed",
        previous_lifecycle_status="passed",
        previous_projection_status="passed",
        previous_monitor_status="passed",
        role_topology_audit=receipt,
    )

    assert report["status"] == "ready_for_owner_deploy_confirmation"
    assert report["role_topology"]["status"] == "passed"


def test_manifest_rejects_role_audit_receipt_with_nonzero_forbidden_effect(
    tmp_path: Path,
):
    module = _module()
    with pytest.raises(ValueError, match="forbidden_effect"):
        module.build_predeploy_manifest(
            repo_root=_repo(tmp_path),
            role_topology_audit={
                "status": "role_topology_audited",
                "application_role_id": "brc_runtime_app",
                "migration_role_id": "brc_runtime_migrator",
                "credential_or_secret_change_required": False,
                "role_topology_decision": "existing_roles_sufficient",
                "application_can_create": False,
                "application_can_alter": False,
                "application_can_drop": False,
                "forbidden_effects": {"database_write_executed": True},
            },
        )


def test_migration_graph_rejects_multiple_heads(tmp_path: Path):
    module = _module()
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "001.py").write_text("revision = '001'\ndown_revision = None\n")
    (migrations / "002.py").write_text("revision = '002'\ndown_revision = None\n")

    with pytest.raises(module.PredeployPackageError, match="single_head"):
        module.migration_graph_fingerprint(migrations)


def test_empty_schema_is_not_accepted_as_a_candidate_fingerprint(
    monkeypatch: pytest.MonkeyPatch,
):
    module = _module()

    class Connection:
        def execute(self, *_args, **_kwargs):
            class Result:
                def mappings(self):
                    return self

                def all(self):
                    return []

            return Result()

    class Transaction:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class EngineConnection(Connection):
        def begin(self):
            return Transaction()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class Engine:
        def connect(self):
            return EngineConnection()

        def dispose(self):
            return None

    monkeypatch.setattr(module.sa, "create_engine", lambda _dsn: Engine())
    result = module.schema_fingerprint_from_postgres("postgresql://example", "shadow")

    assert result == {
        "status": "not_run",
        "schema": "shadow",
        "reason": "schema_has_no_tables",
    }


def test_cli_runs_directly_from_the_scripts_path_without_import_error():
    completed = subprocess.run(
        (sys.executable, str(SCRIPT), "--help"),
        cwd=REPO_ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert completed.returncode == 0
    assert "--role-topology-database-url" in completed.stdout
