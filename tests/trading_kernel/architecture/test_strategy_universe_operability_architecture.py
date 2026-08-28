from __future__ import annotations

import ast
import inspect
from pathlib import Path

from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION
from src.trading_kernel.interfaces.reconciliation_worker import (
    ReconciliationWorkerRequest,
    ReconciliationWorkerResult,
    run_reconciliation_worker_once,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_operability_repair_uses_one_forward_only_schema_revision_chain() -> None:
    """The runtime owns one unbranched v4-to-head migration chain."""

    migration_paths = tuple(
        sorted(
            path
            for path in (REPO_ROOT / "migrations/trading_kernel/versions").glob("*.py")
            if path.name != "__init__.py"
        )
    )
    assert tuple(path.name for path in migration_paths) == (
        "0001_trading_kernel_baseline_v4.py",
        "0002_sor_v3_strategy_group_capacity.py",
        "0003_portfolio_admission_observability.py",
        "0004_owner_control_plane.py",
        "0005_tradfi_instrument_center.py",
        "0006_sor_dynamic_selection_v0.py",
        "0007_exit_profile_authority_v1.py",
    )

    revisions: dict[str, str | None] = {}
    for path in migration_paths:
        assignments = {
            node.target.id: ast.literal_eval(node.value)
            for node in ast.parse(path.read_text(encoding="utf-8")).body
            if isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id in {"revision", "down_revision"}
        }
        revisions[str(assignments["revision"])] = assignments["down_revision"]
    assert revisions == {
        "0001_trading_kernel_baseline_v4": None,
        "0002_sor_v3_strategy_group_capacity": (
            "0001_trading_kernel_baseline_v4"
        ),
        "0003_portfolio_admission_observability": (
            "0002_sor_v3_strategy_group_capacity"
        ),
        "0004_owner_control_plane": "0003_portfolio_admission_observability",
        "0005_tradfi_instrument_center": "0004_owner_control_plane",
        "0006_sor_dynamic_selection_v0": "0005_tradfi_instrument_center",
        "0007_exit_profile_authority_v1": "0006_sor_dynamic_selection_v0",
    }
    assert set(revisions.values()) - {None} == {
        "0001_trading_kernel_baseline_v4",
        "0002_sor_v3_strategy_group_capacity",
        "0003_portfolio_admission_observability",
        "0004_owner_control_plane",
        "0005_tradfi_instrument_center",
        "0006_sor_dynamic_selection_v0",
    }

    baseline_source = migration_paths[0].read_text(encoding="utf-8")
    assert "migrations.trading_kernel.v4_schema" in baseline_source
    assert "src.trading_kernel.infrastructure.pg_models" not in baseline_source

    production_sources = (
        REPO_ROOT / "src/trading_kernel",
        REPO_ROOT / "migrations/trading_kernel",
        REPO_ROOT / "scripts/trading_kernel",
    )
    matches = [
        path.relative_to(REPO_ROOT).as_posix()
        for root in production_sources
        for path in root.rglob("*.py")
        if "warm_ready_at_ms" in path.read_text(encoding="utf-8")
    ]
    assert matches == []


def test_bootstrap_and_promotion_have_no_operator_shrinkable_instrument_scope() -> None:
    """The approved Crypto and TradFi manifests are non-optional."""

    bootstrap_source = _read("scripts/trading_kernel/bootstrap_strategy_universes.py")
    promotion_source = _read("scripts/trading_kernel/promote_entry.py")
    deployment_source = _read("scripts/trading_kernel/deploy_tokyo_release.py")

    assert "--instrument" not in bootstrap_source
    assert "--exchange-instrument-id" not in deployment_source
    assert "APPROVED_ACTIVE_INSTRUMENT_COUNT = len(" in promotion_source
    assert "APPROVED_UNIVERSE_BATCHES.values()" in promotion_source
    assert "binance-usdm:AVAXUSDT:perpetual" not in bootstrap_source


def test_reconciliation_certification_is_a_bounded_safety_worker_concern() -> None:
    """Certification remains bounded Housekeeping inside the four-worker runtime."""

    request = ReconciliationWorkerRequest(
        worker_id="architecture-check",
        runtime_commit="commit-check",
        schema_revision=CURRENT_SCHEMA_REVISION,
        now_ms=1,
        timeout_seconds=1,
        unknown_visibility_grace_ms=1,
        idle_poll_interval_ms=1,
    )
    assert request.certification_max_wait_ms == 120_000
    assert request.certification_valid_for_ms == 600_000
    assert request.certification_eligible_check_interval_ms == 300_000
    assert request.schema_revision == CURRENT_SCHEMA_REVISION
    assert "housekeeping_status" in ReconciliationWorkerResult.model_fields
    assert (
        "instrument_certification_source"
        in inspect.signature(run_reconciliation_worker_once).parameters
    )

    services = {
        path.name
        for path in (REPO_ROOT / "deploy/systemd").glob("*.service")
    }
    assert services == {
        "brc-trading-kernel-observation-worker.service",
        "brc-trading-kernel-entry-worker.service",
        "brc-trading-kernel-lifecycle-worker.service",
        "brc-trading-kernel-reconciliation-worker.service",
    }
    assert list((REPO_ROOT / "deploy/systemd").glob("*.timer")) == []


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")
