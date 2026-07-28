from __future__ import annotations

import ast
import re
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
    KERNEL_ROOT / "application/certify_universe_instrument.py",
    KERNEL_ROOT / "application/project_comparative_universe.py",
    KERNEL_ROOT / "application/read_strategy_universe_status.py",
)
UNIVERSE_AUTHORITY_SOURCES = (
    *UNIVERSE_APPLICATION_SOURCES,
    KERNEL_ROOT / "domain/strategy_registry.py",
    KERNEL_ROOT / "infrastructure/pg_models.py",
    KERNEL_ROOT / "infrastructure/pg_signal_repository.py",
    KERNEL_ROOT / "infrastructure/pg_universe_repository.py",
    KERNEL_ROOT / "infrastructure/runtime_authority_seed.py",
    REPO_ROOT / "scripts/trading_kernel/configure_strategy_universe.py",
    REPO_ROOT / "scripts/trading_kernel/read_strategy_universe_status.py",
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
    """All Universe application boundaries remain before the established chain."""

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


def test_universe_authority_has_no_legacy_compatibility_or_dual_write_surface() -> None:
    """Universe authority is forward-only without an alternate old-state reader."""

    violations: list[str] = []
    for path in UNIVERSE_AUTHORITY_SOURCES:
        source = _read(path)
        tree = ast.parse(source, filename=str(path))
        markers = _legacy_authority_markers(tree)
        if "brc_strategy_candidate_scopes" in source:
            markers.add("retired candidate-scope table")
        if markers:
            violations.append(
                f"{path.relative_to(REPO_ROOT)}: {', '.join(sorted(markers))}"
            )
    assert not violations, (
        "Universe authority must not retain a legacy/compatibility/fallback/"
        "dual-write surface: "
        + ", ".join(violations)
    )


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


def _legacy_authority_markers(tree: ast.AST) -> set[str]:
    """Inspect executable identifiers, not comments or venue-parser text."""

    markers: set[str] = set()
    names = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
    }
    names.update(
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
    )
    names.update(
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    )
    names.update(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    )
    for name in names:
        words = _identifier_words(name)
        if {"legacy", "compat", "compatibility", "fallback"} & set(words):
            markers.add(name)
        if "dualwrite" in words or "dualread" in words:
            markers.add(name)
        if any(
            words[index : index + 2] in (["dual", "write"], ["dual", "read"])
            for index in range(len(words) - 1)
        ):
            markers.add(name)
    return markers


def _identifier_words(name: str) -> list[str]:
    return [
        word.lower()
        for word in re.findall(r"[A-Z]+(?=[A-Z][a-z]|$)|[A-Z]?[a-z]+", name)
    ]
