from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_requirements_pin_the_certified_ccxt_adapter_version() -> None:
    requirements = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
    ccxt_lines = [
        line.strip()
        for line in requirements.splitlines()
        if line.strip().startswith("ccxt")
    ]

    assert ccxt_lines == ["ccxt==4.5.56"]
