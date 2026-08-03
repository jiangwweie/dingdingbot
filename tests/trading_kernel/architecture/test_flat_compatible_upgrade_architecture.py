from __future__ import annotations

from pathlib import Path

from scripts.trading_kernel.deploy_tokyo_release import (
    COMPATIBLE_SOURCE_SCHEMA_REVISION,
    SCHEMA_REVISION,
)
from scripts.trading_kernel.verify_schema import COMPATIBLE_SOURCE_REVISION

REPO_ROOT = Path(__file__).resolve().parents[3]
PRODUCTION_ROOTS = (
    REPO_ROOT / "src/trading_kernel",
    REPO_ROOT / "scripts/trading_kernel",
)
DEPLOYMENT_AUTHORITY_SOURCES = (
    "scripts/trading_kernel/certify_readonly.py",
    "scripts/trading_kernel/deploy_tokyo_release.py",
    "scripts/trading_kernel/probe_production_runtime.py",
    "scripts/trading_kernel/promote_entry.py",
    "scripts/trading_kernel/seed_runtime_authority.py",
    "src/trading_kernel/infrastructure/runtime_authority_seed.py",
)


def test_deployment_has_no_tp1_replay_surface() -> None:
    violations = [
        relative_path
        for relative_path in DEPLOYMENT_AUTHORITY_SOURCES
        if "tp1_replay_ticket" in (
            REPO_ROOT / relative_path
        ).read_text(encoding="utf-8")
    ]

    assert not violations, (
        "historical TP1 replay remains a reusable deployment surface: "
        + ", ".join(violations)
    )


def test_active_position_handover_is_not_a_deployment_surface() -> None:
    forbidden = (
        "--protected-ticket-json",
        "ProtectedHandoverTicketProbe",
        "deploy-protected-identity",
        "deploy_protected_identity",
        "protected_promotion_pass",
        "protected_tickets",
    )
    violations = [
        f"{relative_path}:{marker}"
        for relative_path in DEPLOYMENT_AUTHORITY_SOURCES
        for marker in forbidden
        if marker in (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    ]

    assert not violations, (
        "active-position deployment handover remains: " + ", ".join(violations)
    )


def test_kernel_has_no_legacy_or_compatibility_module_surface() -> None:
    forbidden_module_tokens = {"legacy", "compat", "compatibility"}
    violations = [
        str(path.relative_to(REPO_ROOT))
        for root in PRODUCTION_ROOTS
        for path in root.rglob("*.py")
        if forbidden_module_tokens.intersection(path.relative_to(root).parts)
        or any(
            token in forbidden_module_tokens
            for token in path.stem.replace("-", "_").split("_")
        )
    ]

    assert not violations, (
        "legacy or compatibility module would create a parallel kernel surface: "
        + ", ".join(violations)
    )


def test_flat_upgrade_has_one_exact_0002_to_0003_authority() -> None:
    assert COMPATIBLE_SOURCE_SCHEMA_REVISION == (
        "0002_sor_v3_strategy_group_capacity"
    )
    assert COMPATIBLE_SOURCE_REVISION == COMPATIBLE_SOURCE_SCHEMA_REVISION
    assert SCHEMA_REVISION == "0003_portfolio_admission_observability"


def test_retired_0001_source_is_not_a_regular_deployment_compatibility_path() -> None:
    retired_source = "0001_trading_kernel_baseline_v4"
    violations = [
        relative_path
        for relative_path in (
            "scripts/trading_kernel/deploy_tokyo_release.py",
            "scripts/trading_kernel/verify_schema.py",
            "scripts/trading_kernel/certify_readonly.py",
        )
        if retired_source in (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    ]

    assert not violations, (
        "retired 0001 source remains in the current deployment path: "
        + ", ".join(violations)
    )
