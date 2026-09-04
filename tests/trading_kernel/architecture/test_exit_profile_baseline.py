from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_current_runtime_has_no_yaml_parser_or_exit_profile_yaml_catalog() -> None:
    violations: list[str] = []
    for root in ("src/trading_kernel", "scripts/trading_kernel"):
        for path in (REPO_ROOT / root).rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            for marker in ("import yaml", "from yaml", "yaml.safe_load", "yaml.load"):
                if marker in source:
                    violations.append(f"{path.relative_to(REPO_ROOT)}: {marker}")
    exit_yaml = tuple(
        path.relative_to(REPO_ROOT).as_posix()
        for pattern in ("*exit*.yaml", "*exit*.yml")
        for path in REPO_ROOT.rglob(pattern)
        if path.is_file()
    )

    assert violations == []
    assert exit_yaml == ()


def test_lifecycle_uses_ticket_profile_without_current_binding_or_legacy_event_policy() -> None:
    domain = (REPO_ROOT / "src/trading_kernel/domain/exit_policy.py").read_text(
        encoding="utf-8"
    )
    models = (REPO_ROOT / "src/trading_kernel/infrastructure/pg_models.py").read_text(
        encoding="utf-8"
    )
    lifecycle = (
        REPO_ROOT / "src/trading_kernel/application/maintain_ticket_lifecycle.py"
    ).read_text(encoding="utf-8")

    assert "registered_exit_profiles" in domain
    assert "_policy_for_contract" not in domain
    assert '_id("exit_policy_id")' in models
    assert 'sa.UniqueConstraint("event_spec_id")' not in models
    assert "uow.exit_profiles.get_profile(" in lifecycle
    assert "uow.strategy_registry.get_exit_policy(" not in lifecycle
    assert "get_current_binding(" not in lifecycle
    assert "profile.event_spec_id" not in lifecycle


def test_lifecycle_request_uses_entry_command_as_fill_window_lower_bound() -> None:
    worker = (
        REPO_ROOT / "src/trading_kernel/interfaces/lifecycle_worker.py"
    ).read_text(encoding="utf-8")

    assert "entry_order_reference.command_created_at_ms" in worker
    assert "entry_fill_window_started_at_ms" in worker
    assert "_earliest_nonzero_exposure_started_at_ms" not in worker


def test_exit_profile_authority_lock_is_absent_from_trading_hot_paths() -> None:
    for relative_path in (
        "src/trading_kernel/application/build_capacity_claim.py",
        "src/trading_kernel/application/issue_ready_signal.py",
        "src/trading_kernel/application/issue_ticket.py",
        "src/trading_kernel/application/maintain_ticket_lifecycle.py",
        "src/trading_kernel/application/reconcile_ticket.py",
    ):
        source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        assert "acquire_authority_write_lock" not in source
        assert "EXIT_PROFILE_AUTHORITY_WRITE_LOCK" not in source


def test_application_runtime_has_no_legacy_event_exit_policy_resolution() -> None:
    violations = []
    application_root = REPO_ROOT / "src/trading_kernel/application"
    for path in application_root.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        for marker in (
            "get_exit_policy(",
            "exit_policy_for(",
            ".event_spec_id != aggregate.ticket.identity.runtime.event_spec_id",
        ):
            if marker in source:
                violations.append(f"{path.relative_to(REPO_ROOT)}: {marker}")

    assert violations == []
