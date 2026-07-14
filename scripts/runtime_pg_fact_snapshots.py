"""Thin compatibility wrapper for PG runtime fact snapshot helpers."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.application.action_time.runtime_pg_fact_snapshots import *  # noqa: F401,F403,E402
