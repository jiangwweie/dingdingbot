"""Desktop freshness may not keep an old response labelled live indefinitely."""
import subprocess
from pathlib import Path


def test_desktop_polling_and_snapshot_freshness():
    result = subprocess.run(['node', 'tests/trading_kernel/unit/desktop_overview_freshness.cjs'],
        cwd=Path(__file__).resolve().parents[3], capture_output=True, text=True, timeout=20, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
