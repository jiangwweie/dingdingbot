from __future__ import annotations

import ast
from pathlib import Path

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
    assert migration_names == ("0001_trading_kernel_baseline_v2.py",)

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
    """Certification precedes routine work at the max-wait boundary, without a fifth worker."""

    worker = ast.parse(
        _read("src/trading_kernel/interfaces/reconciliation_worker.py")
    )
    function = next(
        node
        for node in worker.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "run_reconciliation_worker_once"
    )
    calls = [
        node.func.id
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]
    assert calls.count("_certify_one_due_instrument") == 2
    assert calls.count("_run_reconciliation_worker_once_core") == 3

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


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")
