#!/usr/bin/env python3
"""Thin CLI wrapper for typed runtime strategy signal-input construction."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.application.readmodels import runtime_strategy_signal_input as _impl  # noqa: E402


def main() -> int:
    return _impl.main()


if __name__ == "__main__":
    raise SystemExit(main())
