"""Operation explanations cannot submit orders or bypass existing preview gates."""
import subprocess
from pathlib import Path


def test_mobile_operation_guide_is_readonly_until_explicit_form_action():
    result = subprocess.run(['node', 'tests/trading_kernel/unit/mobile_operation_guide.cjs'],
        cwd=Path(__file__).resolve().parents[3], capture_output=True, text=True, timeout=20, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
