#!/usr/bin/env python3
"""Thin CLI wrapper for PG ticket-bound protected submit attempt materialization."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.application.action_time.protected_submit_attempt import *  # noqa: F401,F403,E402
from src.application.action_time import protected_submit_attempt as _impl  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(_impl.main())
