from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_sor_v2_history_classification_cli_is_bounded_and_file_free(
    tmp_path: Path,
) -> None:
    """The retained offline CLI surface remains bounded and display-only."""

    result = subprocess.run(
        [
            sys.executable,
            str(
                REPO_ROOT
                / "scripts"
                / "trading_kernel"
                / "classify_sor_v2_history.py"
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
    assert "--ticket-id" in result.stdout
    assert "--classification" in result.stdout
    assert list(tmp_path.rglob("*")) == []
