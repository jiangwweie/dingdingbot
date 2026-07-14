#!/usr/bin/env python3
"""Thin CLI wrapper for the StrategyGroup live-facts readiness read model."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.application.readmodels import strategy_group_live_facts_readiness as _impl  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    return _impl.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
