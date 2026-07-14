#!/usr/bin/env python3
"""Thin CLI wrapper for the PG-backed StrategyGroup runtime Goal Status read model."""

from __future__ import annotations

from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.application.readmodels import strategygroup_runtime_goal_status as _impl  # noqa: E402


globals().update(
    {name: value for name, value in vars(_impl).items() if not name.startswith("__")}
)


def main() -> int:
    previous = {
        "sa": _impl.sa,
        "PgBackedRuntimeControlStateRepository": (
            _impl.PgBackedRuntimeControlStateRepository
        ),
        "build_goal_status_artifact_from_control_state": (
            _impl.build_goal_status_artifact_from_control_state
        ),
    }
    try:
        _impl.sa = globals()["sa"]
        _impl.PgBackedRuntimeControlStateRepository = globals()[
            "PgBackedRuntimeControlStateRepository"
        ]
        _impl.build_goal_status_artifact_from_control_state = globals()[
            "build_goal_status_artifact_from_control_state"
        ]
        return _impl.main()
    finally:
        _impl.sa = previous["sa"]
        _impl.PgBackedRuntimeControlStateRepository = previous[
            "PgBackedRuntimeControlStateRepository"
        ]
        _impl.build_goal_status_artifact_from_control_state = previous[
            "build_goal_status_artifact_from_control_state"
        ]


if __name__ == "__main__":
    raise SystemExit(main())
