from __future__ import annotations

import inspect
from pathlib import Path

from src.trading_kernel.interfaces.reconciliation_worker import (
    ReconciliationWorkerRequest,
    ReconciliationWorkerResult,
    run_reconciliation_worker_once,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_operability_repair_removes_the_retired_time_and_migration_generations() -> None:
    """The v2 rebuild has one semantic time model and one schema baseline."""

    migration_names = tuple(
        sorted(
            path.name
            for path in (REPO_ROOT / "migrations/trading_kernel/versions").glob("*.py")
            if path.name != "__init__.py"
        )
    )
    assert migration_names == ("0001_trading_kernel_baseline_v4.py",)

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
    """The approved PostgreSQL-derived seven-instrument manifest is non-optional."""

    bootstrap_source = _read("scripts/trading_kernel/bootstrap_strategy_universes.py")
    promotion_source = _read("scripts/trading_kernel/promote_entry.py")
    deployment_source = _read("scripts/trading_kernel/deploy_tokyo_release.py")

    assert "--instrument" not in bootstrap_source
    assert "--exchange-instrument-id" not in deployment_source
    assert "len(manifest) == 7" in promotion_source
    assert "binance-usdm:AVAXUSDT:perpetual" not in bootstrap_source


def test_reconciliation_certification_is_a_bounded_safety_worker_concern() -> None:
    """Certification remains bounded Housekeeping inside the four-worker runtime."""

    request = ReconciliationWorkerRequest(
        worker_id="architecture-check",
        runtime_commit="commit-check",
        schema_revision="0001_trading_kernel_baseline_v4",
        now_ms=1,
        timeout_seconds=1,
        unknown_visibility_grace_ms=1,
        idle_poll_interval_ms=1,
    )
    assert request.certification_max_wait_ms == 120_000
    assert request.certification_valid_for_ms == 600_000
    assert request.certification_eligible_check_interval_ms == 300_000
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
