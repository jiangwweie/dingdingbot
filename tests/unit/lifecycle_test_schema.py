from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
import sqlalchemy as sa

from src.application.action_time.lifecycle_mutation_capability import (
    set_lifecycle_mutation_capability,
)
from src.application.readmodels.lifecycle_mutation_enablement_proof import (
    ActionTimeCertificationReferenceV2,
    LaneSourceWatermarkV1,
    LifecycleMutationEnablementProof,
)


def apply_enabled_lifecycle_command_schema(
    conn,
    *,
    repo_root: Path,
    module_prefix: str,
    now_ms: int,
) -> None:
    paths = (
        repo_root
        / "migrations/versions/2026-07-10-105_create_ticket_bound_exchange_commands.py",
        repo_root
        / "migrations/versions/2026-07-11-113_create_exchange_account_mode_and_domain_holds.py",
        repo_root
        / "migrations/versions/2026-07-11-114_extend_exchange_commands_for_lifecycle.py",
    )
    for index, path in enumerate(paths):
        name = f"{module_prefix}_{index}_{path.stem.replace('-', '_')}"
        spec = importlib.util.spec_from_file_location(name, path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        old_op = module.op
        module.op = Operations(MigrationContext.configure(conn))
        try:
            module.upgrade()
        finally:
            module.op = old_op
    columns = {
        str(item["name"])
        for item in sa.inspect(conn).get_columns("brc_runtime_capabilities_current")
    }
    if "proof_schema" not in columns:
        conn.exec_driver_sql(
            "ALTER TABLE brc_runtime_capabilities_current "
            "ADD COLUMN proof_schema VARCHAR(128)"
        )
    if "proof_payload" not in columns:
        conn.exec_driver_sql(
            "ALTER TABLE brc_runtime_capabilities_current "
            "ADD COLUMN proof_payload JSON"
        )
    action_time = ActionTimeCertificationReferenceV2(
        stage="post_canary",
        target_runtime_head="a" * 40,
        certification_input_digest="sha256:" + "1" * 64,
        release_activation_outcome_id=f"process:{module_prefix}:release",
        release_activation_source_watermark=f"release:{module_prefix}:watermark",
        lane_source_watermarks=(
            LaneSourceWatermarkV1(
                lane_scope_key=f"lane:{module_prefix}",
                lane_identity_key=f"identity:{module_prefix}",
                source_watermark=f"watermark:{module_prefix}",
                process_outcome_id=f"process:{module_prefix}:lane",
            ),
        ),
        fact_snapshot_ids=(f"fact:{module_prefix}:one",),
        fact_set_digest="sha256:" + "2" * 64,
        fact_min_valid_until_ms=now_ms + 60_000,
        deploy_nonce=f"nonce:{module_prefix}",
    )
    proof = LifecycleMutationEnablementProof(
        target_runtime_head="a" * 40,
        lane_identity_digest="sha256:" + "3" * 64,
        action_time_certification_ref=action_time.certification_ref(),
        action_time_certification_payload=action_time,
        certification_projection_digest="sha256:" + "4" * 64,
    )
    enabled = set_lifecycle_mutation_capability(
        conn,
        enabled=True,
        certification_ref=proof.lifecycle_certification_ref(),
        now_ms=now_ms,
        proof=proof,
    )
    assert enabled["status"] == "ready"
