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


def test_exit_policy_catalog_remains_event_generated_until_ex03() -> None:
    domain = (
        REPO_ROOT / "src/trading_kernel/domain/exit_policy.py"
    ).read_text(encoding="utf-8")
    models = (
        REPO_ROOT / "src/trading_kernel/infrastructure/pg_models.py"
    ).read_text(encoding="utf-8")
    lifecycle = (
        REPO_ROOT / "src/trading_kernel/application/maintain_ticket_lifecycle.py"
    ).read_text(encoding="utf-8")

    assert "_policy_for_contract(item)" in domain
    assert '_id("exit_policy_id")' in models
    assert 'sa.UniqueConstraint("event_spec_id")' not in models
    assert "policy.event_spec_id != aggregate.ticket.identity.runtime.event_spec_id" in lifecycle


def test_current_lifecycle_request_uses_ticket_creation_as_exposure_start() -> None:
    worker = (
        REPO_ROOT / "src/trading_kernel/interfaces/lifecycle_worker.py"
    ).read_text(encoding="utf-8")

    assert "exposure_started_at_ms=aggregate.ticket.created_at_ms" in worker
