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
