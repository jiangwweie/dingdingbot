from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from src.trading_kernel.application import runtime
from src.trading_kernel.application.runtime import worker_ownership_map
from src.trading_kernel.interfaces import observation_worker


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_each_runtime_transition_has_one_worker_owner() -> None:
    assert worker_ownership_map() == {
        "observation": "observation_worker",
        "entry": "entry_worker",
        "lifecycle": "lifecycle_worker",
        "reconciliation": "reconciliation_worker",
    }


def test_combined_runtime_orchestrator_is_retired() -> None:
    assert not hasattr(runtime, "run_runtime_once")
    assert not (REPO_ROOT / "scripts/trading_kernel/run_worker_once.py").exists()
    assert not (REPO_ROOT / "src/trading_kernel/interfaces/worker.py").exists()
    assert not hasattr(observation_worker, "run_observation_once")


def test_command_worker_cli_requires_one_explicit_complete_worker_role(
    tmp_path: Path,
) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(
                REPO_ROOT
                / "scripts"
                / "trading_kernel"
                / "run_command_worker_once.py"
            ),
            "--help",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "--worker-role {entry,lifecycle}" in result.stdout
    assert "--runtime-commit" in result.stdout
    assert "--schema-revision" in result.stdout
    assert "--admission-snapshot-validity-ms" in result.stdout
    assert "--idle-poll-interval-ms" in result.stdout
    assert list(tmp_path.rglob("*")) == []


def test_observation_worker_cli_owns_pg_scope_selection_and_closed_bar_cadence(
    tmp_path: Path,
) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(
                REPO_ROOT
                / "scripts"
                / "trading_kernel"
                / "run_observation_worker_once.py"
            ),
            "--help",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "--market-source-factory" in result.stdout
    assert "--runtime-commit" in result.stdout
    assert "--schema-revision" in result.stdout
    assert "--timeout-seconds" in result.stdout
    assert "--retry-interval-ms" in result.stdout
    assert "--runtime-scope-id" not in result.stdout
    assert list(tmp_path.rglob("*")) == []


def test_reconciliation_worker_cli_owns_venue_truth_and_terminal_closure(
    tmp_path: Path,
) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(
                REPO_ROOT
                / "scripts"
                / "trading_kernel"
                / "run_reconciliation_worker_once.py"
            ),
            "--help",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "--venue-factory" in result.stdout
    assert "--unknown-visibility-grace-ms" in result.stdout
    assert "--idle-poll-interval-ms" in result.stdout
    assert list(tmp_path.rglob("*")) == []
