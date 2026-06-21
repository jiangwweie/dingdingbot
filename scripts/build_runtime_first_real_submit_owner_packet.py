#!/usr/bin/env python3
"""Read-only compatibility wrapper for the explicit Owner first-real-submit packet namespace.

This wrapper does not modify runtime state, create execution intent, or place orders.
"""

from __future__ import annotations

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.replay_recovery_history.compat_wrapper import install_compat_exports


install_compat_exports(
    globals(),
    "scripts.replay_recovery_history.first_real_submit."
    "build_runtime_first_real_submit_owner_packet",
)


if __name__ == "__main__":
    raise SystemExit(_main())
