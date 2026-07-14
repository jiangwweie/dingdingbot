from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import text


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
        repo_root
        / "migrations/versions/2026-07-14-122_create_account_risk_current_projections.py",
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
    conn.execute(
        text(
            "UPDATE brc_runtime_capabilities_current SET status = 'enabled', "
            "certification_ref = :ref, updated_at_ms = :now_ms "
            "WHERE capability_id = 'ticket_lifecycle_durable_mutation'"
        ),
        {"ref": f"test:{module_prefix}", "now_ms": now_ms},
    )
