from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_selection_runner_has_no_runtime_materialization_dependency() -> None:
    source = REPO_ROOT / "src/trading_kernel/application/run_instrument_selection.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        str(node.module or "")
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }

    assert not any(
        forbidden in imported
        for imported in imports
        for forbidden in (
            "coordinate_selection_materialization",
            "strategy_entry_vacuum",
            "strategy_universe",
            "selection_authority",
        )
    )


def test_selection_once_cli_is_a_thin_application_wrapper() -> None:
    source = REPO_ROOT / "scripts/trading_kernel/run_instrument_selection_once.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imports = {
        str(node.module or "")
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }

    assert "src.trading_kernel.application.run_instrument_selection" in imports
    assert "src.trading_kernel.domain.instrument_selection" not in imports
    assert "src.trading_kernel.infrastructure.pg_models" not in imports


def test_production_selection_domain_has_no_research_or_artifact_import() -> None:
    source = (
        REPO_ROOT / "src/trading_kernel/domain/dynamic_selection_numeric.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        str(node.module or "")
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }

    assert "src.trading_kernel.domain.instrument_selection" in imports
    assert not any(
        imported == "research" or imported.startswith("research.")
        for imported in imports
    )
    assert not any(
        forbidden in source
        for forbidden in (
            "market_data_manifest.json",
            "stage3_1_member_decisions.parquet",
            "pyarrow",
            "pandas",
        )
    )
