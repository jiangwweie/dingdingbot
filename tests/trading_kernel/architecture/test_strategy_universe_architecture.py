from __future__ import annotations

import ast
from pathlib import Path

from src.trading_kernel.domain.strategy_registry import (
    RegisteredStrategyContract,
)
from src.trading_kernel.infrastructure.pg_models import metadata

REPO_ROOT = Path(__file__).resolve().parents[3]
KERNEL_ROOT = REPO_ROOT / "src/trading_kernel"
UNIVERSE_APPLICATION_SOURCES = (
    KERNEL_ROOT / "application/install_strategy_universe.py",
    KERNEL_ROOT / "application/advance_strategy_universe.py",
    KERNEL_ROOT / "application/project_comparative_universe.py",
)


def test_universe_has_one_membership_authority_without_rank_or_legacy_table() -> None:
    """Registry is semantic-only; PostgreSQL Universe membership is unordered."""

    fields = set(RegisteredStrategyContract.model_fields)
    assert not {
        "candidate_instruments",
        "candidate_members",
        "candidate_scope_priority",
        "priority_rank",
    } & fields
    assert "brc_strategy_candidate_scopes" not in metadata.tables

    registry_source = _read(KERNEL_ROOT / "domain/strategy_registry.py")
    arbitration_source = _read(KERNEL_ROOT / "domain/arbitration.py")
    assert "candidate_scope_priority" not in registry_source
    assert "candidate_scope_priority" not in arbitration_source
    assert "priority_rank" not in arbitration_source


def test_universe_runtime_has_no_static_pool_priority_or_asset_scope_expansion() -> None:
    """The general crypto boundary cannot smuggle in selection or US-equity scope."""

    runtime_sources = _sources_under(
        KERNEL_ROOT / "application",
        KERNEL_ROOT / "infrastructure",
        KERNEL_ROOT / "interfaces",
        REPO_ROOT / "scripts/trading_kernel",
    )
    source = "\n".join(runtime_sources.values()).lower()
    assert "candidate_scope_priority" not in source
    assert "universe_member_priority" not in source
    assert "us_equity" not in source
    assert "us-equity" not in source
    assert "correlation" not in source
    assert "cluster" not in source
    assert "downsize" not in source


def test_universe_application_has_no_parallel_ticket_or_exchange_setting_path() -> None:
    """Install, certification and activation remain before the established chain."""

    forbidden_import_suffixes = {
        "dispatch_exchange_command",
        "issue_ticket",
        "revalidate_entry_dispatch",
        "venue_adapter",
    }
    forbidden_attributes = {
        "set_leverage",
        "set_margin_mode",
        "set_position_mode",
        "create_order",
        "cancel_order",
    }
    for path in UNIVERSE_APPLICATION_SOURCES:
        tree = ast.parse(_read(path), filename=str(path))
        imported_modules = {
            alias.name.rsplit(".", 1)[-1]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
            for alias in node.names
        }
        attributes = {
            node.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
        }
        assert not forbidden_import_suffixes & imported_modules, path
        assert not forbidden_attributes & attributes, path


def test_dynamic_adapter_requires_no_postgresql_lookup_per_request() -> None:
    """Canonical InstrumentCodec stays local to the venue adapter boundary."""

    adapter_source = _read(KERNEL_ROOT / "infrastructure/venue_adapter.py")
    forbidden_imports = {
        "sqlalchemy",
        "asyncpg",
        "pg_models",
        "pg_repositories",
        "pg_unit_of_work",
        "pg_universe_repository",
    }
    imported = _import_roots(ast.parse(adapter_source))
    assert not forbidden_imports & imported


def test_domain_stays_free_of_infrastructure_and_operating_system_imports() -> None:
    """Universe additions cannot weaken the pure-domain boundary."""

    forbidden_imports = {
        "sqlalchemy",
        "asyncpg",
        "ccxt",
        "subprocess",
        "pathlib",
        "logging",
        "requests",
        "httpx",
    }
    violations: list[str] = []
    for path, source in _sources_under(KERNEL_ROOT / "domain").items():
        imported = _import_roots(ast.parse(source))
        forbidden = sorted(forbidden_imports & imported)
        if forbidden:
            violations.append(f"{path}: {', '.join(forbidden)}")
    assert not violations, "domain infrastructure imports:\n" + "\n".join(violations)


def test_universe_does_not_add_a_fifth_worker_or_runtime_file_authority() -> None:
    """Universe work is orchestrated by the existing four persistent workers."""

    expected = {
        "brc-trading-kernel-observation-worker.service",
        "brc-trading-kernel-entry-worker.service",
        "brc-trading-kernel-lifecycle-worker.service",
        "brc-trading-kernel-reconciliation-worker.service",
        "brc-trading-kernel.slice",
    }
    actual = {
        path.name
        for path in (REPO_ROOT / "deploy/systemd").iterdir()
        if path.is_file()
    }
    assert actual == expected

    universe_runtime_source = "\n".join(
        _read(path) for path in UNIVERSE_APPLICATION_SOURCES
    )
    assert "write_text(" not in universe_runtime_source
    assert "write_bytes(" not in universe_runtime_source
    assert "open(" not in universe_runtime_source


def _sources_under(*roots: Path) -> dict[str, str]:
    return {
        path.relative_to(REPO_ROOT).as_posix(): _read(path)
        for root in roots
        for path in root.rglob("*.py")
    }


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _import_roots(tree: ast.AST) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            roots.add(node.module.split(".", 1)[0])
    return roots
