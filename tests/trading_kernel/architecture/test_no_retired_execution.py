from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

RETIRED_PATH_PATTERNS = (
    "src/application/action_time/**/*.py",
    "src/application/runtime_execution*.py",
    "src/domain/runtime_execution*.py",
    "src/infrastructure/pg_runtime_execution*.py",
    "migrations/versions/*.py",
)

RETIRED_EXPLICIT_PATHS = (
    "src/application/execution_orchestrator.py",
    "src/application/order_lifecycle_service.py",
    "src/application/position_projection_service.py",
    "src/application/capital_protection.py",
    "src/application/reconciliation.py",
    "src/application/startup_reconciliation_service.py",
    "src/infrastructure/exchange_gateway.py",
    "src/trading_kernel/interfaces/worker.py",
    "scripts/trading_kernel/run_worker_once.py",
)

RETIRED_IMPORT_MARKERS = (
    "src.application.action_time",
    "src.application.runtime_execution",
    "src.domain.runtime_execution",
    "src.infrastructure.pg_runtime_execution",
    "src.application.execution_orchestrator",
    "src.application.order_lifecycle_service",
    "src.application.position_projection_service",
    "src.application.capital_protection",
    "src.application.reconciliation",
    "src.application.startup_reconciliation_service",
    "src.infrastructure.exchange_gateway",
)


def test_retired_execution_files_are_absent() -> None:
    remaining: set[str] = set()
    for pattern in RETIRED_PATH_PATTERNS:
        remaining.update(
            path.relative_to(REPO_ROOT).as_posix()
            for path in REPO_ROOT.glob(pattern)
            if path.is_file()
        )
    remaining.update(
        relative_path
        for relative_path in RETIRED_EXPLICIT_PATHS
        if (REPO_ROOT / relative_path).is_file()
    )

    assert not remaining, "retired execution files remain:\n" + "\n".join(
        sorted(remaining)
    )


def test_production_code_does_not_import_retired_execution_modules() -> None:
    remaining: list[str] = []
    for root_name in ("src", "scripts"):
        for path in (REPO_ROOT / root_name).rglob("*.py"):
            relative_path = path.relative_to(REPO_ROOT).as_posix()
            source = path.read_text(encoding="utf-8")
            for marker in RETIRED_IMPORT_MARKERS:
                if marker in source:
                    remaining.append(f"{relative_path}: {marker}")

    assert not remaining, "retired execution imports remain:\n" + "\n".join(
        sorted(remaining)
    )


def test_systemd_contains_only_four_persistent_workers_and_resource_slice() -> None:
    expected = {
        f"brc-trading-kernel-{worker}.service"
        for worker in (
            "observation-worker",
            "entry-worker",
            "lifecycle-worker",
            "reconciliation-worker",
        )
    } | {"brc-trading-kernel.slice"}
    actual = {
        path.name
        for path in (REPO_ROOT / "deploy" / "systemd").iterdir()
        if path.is_file()
    }

    assert actual == expected


def test_shadow_outcome_cannot_import_ticket_command_or_venue_write_authority() -> None:
    forbidden_imports = (
        "domain.ticket",
        "application.issue_ticket",
        "application.dispatch_exchange_command",
        "interfaces.entry_worker",
        "infrastructure.binance_usdm_venue",
    )
    violations: list[str] = []

    for path in (REPO_ROOT / "src" / "trading_kernel").rglob("*shadow*.py"):
        source = path.read_text(encoding="utf-8")
        for marker in forbidden_imports:
            if marker in source:
                violations.append(
                    f"{path.relative_to(REPO_ROOT).as_posix()}: {marker}"
                )

    assert not violations, "Shadow Outcome gained exchange-write authority:\n" + "\n".join(
        sorted(violations)
    )
