from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
KERNEL_ROOT = REPO_ROOT / "src/trading_kernel"
STRESS_MODULE = KERNEL_ROOT / "domain/cross_margin_stress.py"
VENUE_ADAPTER = KERNEL_ROOT / "infrastructure/venue_adapter.py"


def test_retired_liquidation_command_authority_is_absent() -> None:
    """Executable code and fixtures must use the Stop-stress authority only."""

    forbidden = {
        "projected_liquidation",
        "actual_liquidation",
        "min_liquidation_distance",
        "safe_liquidation",
        "_project_cross_margin_liquidation",
    }
    violations: list[str] = []
    roots = (
        KERNEL_ROOT,
        REPO_ROOT / "scripts/trading_kernel",
        REPO_ROOT / "tests/trading_kernel/unit",
        REPO_ROOT / "tests/trading_kernel/integration",
        REPO_ROOT / "tests/trading_kernel/full_chain",
    )
    explicit_retirement_assertions = {
        REPO_ROOT
        / "tests/trading_kernel/integration/test_schema_baseline.py",
        REPO_ROOT
        / "tests/trading_kernel/integration/test_schema_migration_postgres.py",
    }
    for root in roots:
        for path in root.rglob("*.py"):
            if path in explicit_retirement_assertions:
                continue
            source = path.read_text(encoding="utf-8").lower()
            matched = sorted(token for token in forbidden if token in source)
            if matched:
                violations.append(
                    f"{path.relative_to(REPO_ROOT)}: {', '.join(matched)}"
                )

    assert not violations, "retired liquidation authority remains:\n" + "\n".join(
        violations
    )


def test_stress_financial_formula_has_one_domain_home() -> None:
    """No Application or infrastructure copy of the financial formula exists."""

    formula_markers = {
        "base_margin_balance",
        "stress_boundary_clamped_to_zero",
        "projected_maintenance",
    }
    homes: dict[str, list[str]] = {marker: [] for marker in formula_markers}
    for path in KERNEL_ROOT.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        for marker in formula_markers:
            if marker in source:
                homes[marker].append(path.relative_to(REPO_ROOT).as_posix())

    expected = STRESS_MODULE.relative_to(REPO_ROOT).as_posix()
    assert homes == {marker: [expected] for marker in formula_markers}


def test_account_risk_snapshot_has_one_type_and_one_parser() -> None:
    """Entry and post-fill share one typed account snapshot parser."""

    type_definitions: list[str] = []
    parser_definitions: list[str] = []
    for path in KERNEL_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "AccountRiskSnapshot":
                type_definitions.append(path.relative_to(REPO_ROOT).as_posix())
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "_read_account_risk_snapshot"
            ):
                parser_definitions.append(path.relative_to(REPO_ROOT).as_posix())

    assert type_definitions == [
        "src/trading_kernel/domain/cross_margin_stress.py"
    ]
    assert parser_definitions == [
        "src/trading_kernel/infrastructure/venue_adapter.py"
    ]

    adapter_tree = ast.parse(
        VENUE_ADAPTER.read_text(encoding="utf-8"),
        filename=str(VENUE_ADAPTER),
    )
    parser_calls = [
        node
        for node in ast.walk(adapter_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "_read_account_risk_snapshot"
    ]
    assert len(parser_calls) == 2


def test_raw_venue_liquidation_observation_has_no_decision_path() -> None:
    """The venue value is audit evidence, never a risk or command input."""

    decision_paths = (
        KERNEL_ROOT / "domain/cross_margin_stress.py",
        KERNEL_ROOT / "domain/capacity_sizing.py",
        KERNEL_ROOT / "domain/post_fill_risk.py",
        KERNEL_ROOT / "application/build_capacity_claim.py",
        KERNEL_ROOT / "application/revalidate_entry_dispatch.py",
    )
    for path in decision_paths:
        assert "venue_reported_liquidation_price" not in path.read_text(
            encoding="utf-8"
        ), path


def test_cross_margin_stress_domain_is_pure_and_decimal_only() -> None:
    """The financial authority cannot depend on I/O or binary floats."""

    tree = ast.parse(
        STRESS_MODULE.read_text(encoding="utf-8"),
        filename=str(STRESS_MODULE),
    )
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    imported_modules.update(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    forbidden_fragments = (
        "application",
        "infrastructure",
        "sqlalchemy",
        "asyncpg",
        "ccxt",
        "subprocess",
        "pathlib",
        "requests",
        "httpx",
    )
    assert not {
        module
        for module in imported_modules
        if any(fragment in module for fragment in forbidden_fragments)
    }
    assert not [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, float)
    ]


def test_stop_stress_uses_existing_reconciliation_topology() -> None:
    """No fifth worker, post-fill queue, or parallel selector is allowed."""

    worker_files = {
        path.name
        for path in (KERNEL_ROOT / "interfaces").glob("*_worker.py")
    }
    assert worker_files == {
        "entry_worker.py",
        "lifecycle_worker.py",
        "observation_worker.py",
        "reconciliation_worker.py",
    }
    reconciliation_source = (
        KERNEL_ROOT / "interfaces/reconciliation_worker.py"
    ).read_text(encoding="utf-8")
    assert "AggregateStatus.POST_FILL_RISK_PENDING" in reconciliation_source
    assert "get_next_reconciliation_work" in reconciliation_source
    assert "post_fill_queue" not in reconciliation_source
    assert "post_fill_selector" not in reconciliation_source
