from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "audit_tokyo_runtime_governance_migration_gap.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "audit_tokyo_runtime_governance_migration_gap",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_current_tokyo_runtime_governance_gap_is_linear_and_reviewable():
    module = _load_module()

    report = module.build_migration_gap_report(
        repo_root=REPO_ROOT,
        base_revision="044",
        head_revision="064",
        expected_revision_count=20,
    )

    checks = report["checks"]
    assert report["status"] == "ready_for_controlled_migration_preflight"
    assert checks["ready_for_controlled_migration_preflight"] is True
    assert checks["blockers"] == []
    assert checks["chain_length"] == 20
    assert checks["first_revision"] == "045"
    assert checks["last_revision"] == "064"
    assert "data_destructive_upgrade_ops_present" not in checks["blockers"]
    assert "non_additive_schema_ops_present" in checks["warnings"]
    assert "data_touching_upgrade_ops_present" in checks["warnings"]
    assert "not_null_columns_added_to_existing_table" in checks["warnings"]

    revisions = [item["revision"] for item in report["chain"]]
    assert revisions == [f"{number:03d}" for number in range(45, 65)]
    notes = report["deployment_notes"]
    assert notes["requires_remote_db_backup"] is True
    assert notes["requires_backend_stopped_or_write_quiesced"] is True
    assert notes["positions_table_is_data_touched_by_revision_062"] is True
    assert (
        notes[
            "controlled_submit_results_not_null_adds_require_empty_or_quiesced_table"
        ]
        is True
    )
    assert all(value is False for value in report["safety_invariants"].values())


def test_current_gap_evidence_names_revision_053_and_062_review_items():
    module = _load_module()

    report = module.build_migration_gap_report(
        repo_root=REPO_ROOT,
        base_revision="044",
        head_revision="064",
        expected_revision_count=20,
    )

    not_null = report["review_evidence"]["not_null_existing_table_adds"]
    assert {item["revision"] for item in not_null} == {"053"}
    assert {item["column"] for item in not_null} == {
        "preflight_id",
        "preflight_status",
        "final_gate_verdict",
    }

    data_touching = report["review_evidence"]["data_touching_upgrade_ops"]
    assert any(item["revision"] == "062" for item in data_touching)
    assert all(item["operation"] == "execute" for item in data_touching)


def test_incremental_live_enablement_and_order_created_status_gap_is_reviewable_from_064_to_067():
    module = _load_module()

    report = module.build_migration_gap_report(
        repo_root=REPO_ROOT,
        base_revision="064",
        head_revision="067",
        expected_revision_count=3,
    )

    checks = report["checks"]
    assert report["status"] == "ready_for_controlled_migration_preflight"
    assert checks["ready_for_controlled_migration_preflight"] is True
    assert checks["blockers"] == []
    assert checks["chain_length"] == 3
    assert checks["first_revision"] == "065"
    assert checks["last_revision"] == "067"
    assert "non_additive_schema_ops_present" in checks["warnings"]
    assert [item["filename"] for item in report["chain"]] == [
        "2026-06-10-065_relax_strategy_runtime_live_enablement_constraints.py",
        "2026-06-10-066_add_order_lifecycle_adapter_disabled_submit_status.py",
        "2026-06-10-067_allow_created_order_status.py",
    ]
    non_additive = report["review_evidence"]["non_additive_schema_ops"]
    assert {item["operation"] for item in non_additive} == {"drop_constraint"}
    assert {
        "strategy_runtime_instances",
        "runtime_execution_controlled_submit_results",
        "orders",
    } <= {
        item["table"] for item in non_additive
    }
    assert all(value is False for value in report["safety_invariants"].values())


def test_gap_audit_blocks_missing_chain_base():
    module = _load_module()

    report = module.build_migration_gap_report(
        repo_root=REPO_ROOT,
        base_revision="999",
        head_revision="064",
        expected_revision_count=20,
    )

    assert report["status"] == "blocked"
    assert report["checks"]["ready_for_controlled_migration_preflight"] is False
    assert "base_revision_missing" in report["checks"]["blockers"]
    assert "migration_chain_does_not_reach_base" in report["checks"]["blockers"]
