"""Execute the real mobile request module against bounded network/IDB faults."""

import subprocess
from pathlib import Path


def test_unknown_mobile_write_keeps_key_and_recovers_readonly():
    root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        ["node", "tests/trading_kernel/unit/mobile_pending_write.cjs"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "readonly recovery passed" in result.stdout
