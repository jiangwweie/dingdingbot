"""The actual phone shell must not round trading prices for display."""

import subprocess
from pathlib import Path


def test_mobile_price_precision_uses_exact_decimal_strings():
    root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        ["node", "tests/trading_kernel/unit/mobile_price_precision.cjs"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
