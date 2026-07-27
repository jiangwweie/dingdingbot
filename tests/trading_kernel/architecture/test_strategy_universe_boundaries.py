from __future__ import annotations

import ast
from pathlib import Path

from src.trading_kernel.domain.strategy_plugin import strategy_plugins


REPO_ROOT = Path(__file__).resolve().parents[3]
DOMAIN_FILES = (
    "src/trading_kernel/domain/strategy_plugin.py",
    "src/trading_kernel/domain/strategy_universe.py",
    "src/trading_kernel/domain/universe_projection.py",
    "src/trading_kernel/domain/us_equity_session.py",
    "src/trading_kernel/domain/product_admission.py",
    "src/trading_kernel/domain/corporate_events.py",
    "src/trading_kernel/domain/detectors/rsr_vcb.py",
)


def test_new_strategy_domain_has_no_infrastructure_dependencies() -> None:
    forbidden_roots = {
        "sqlalchemy",
        "asyncpg",
        "ccxt",
        "pathlib",
        "subprocess",
        "requests",
        "aiohttp",
    }
    violations: list[str] = []
    for relative in DOMAIN_FILES:
        tree = ast.parse((REPO_ROOT / relative).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = {alias.name.split(".", 1)[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots = {node.module.split(".", 1)[0]}
            else:
                continue
            for root in roots & forbidden_roots:
                violations.append(f"{relative}: {root}")
    assert violations == []


def test_plugin_registry_is_static_and_declares_exactly_seven_events() -> None:
    plugin_source = (
        REPO_ROOT / "src/trading_kernel/domain/strategy_plugin.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(plugin_source)
    forbidden_calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        if node.func.id in {"eval", "exec", "__import__"}
    }
    plugins = strategy_plugins()

    assert forbidden_calls == set()
    assert len(plugins) == 7
    assert len({plugin.event_spec_id for plugin in plugins}) == 7
    assert all(callable(plugin.detector_factory) for plugin in plugins)


def test_runtime_membership_comes_from_universe_not_registry_candidates() -> None:
    production_files = tuple(
        (REPO_ROOT / "src/trading_kernel").rglob("*.py")
    )
    violations = [
        path.relative_to(REPO_ROOT).as_posix()
        for path in production_files
        if "candidate_instruments" in path.read_text(encoding="utf-8")
    ]
    assert violations == []
