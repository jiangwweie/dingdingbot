from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PRODUCTION_ROOTS = (
    REPO_ROOT / "src/trading_kernel",
    REPO_ROOT / "scripts/trading_kernel",
)


def test_protected_handover_has_no_tp1_replay_deployment_surface() -> None:
    production_sources = (
        "scripts/trading_kernel/deploy_tokyo_release.py",
        "scripts/trading_kernel/seed_runtime_authority.py",
        "src/trading_kernel/infrastructure/runtime_authority_seed.py",
    )
    violations = [
        relative_path
        for relative_path in production_sources
        if "tp1_replay_ticket" in (
            REPO_ROOT / relative_path
        ).read_text(encoding="utf-8")
    ]

    assert not violations, (
        "historical TP1 replay remains a reusable deployment surface: "
        + ", ".join(violations)
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
