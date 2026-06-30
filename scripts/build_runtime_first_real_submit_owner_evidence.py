#!/usr/bin/env python3
"""Current evidence wrapper for archived first-real-submit Owner review.

This read-only evidence builder is for explicit Owner review only. It does not
modify runtime state, create orders, call exchange APIs, or call OrderLifecycle.
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
import sys
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.archived_replay_adapter import (  # noqa: E402
    archived_first_real_submit_module,
    archived_legacy_name,
    normalize_first_real_submit_owner_evidence,
    to_archived_pre_live_submit_rehearsal_input,
)

_ARCHIVED_MODULE_NAME = archived_first_real_submit_module(
    "build_runtime_first_real_submit_owner"
)
_ARCHIVED_BUILDER_NAME = archived_legacy_name("build_first_real_submit_owner")
_archived_module = import_module(_ARCHIVED_MODULE_NAME)


def build_first_real_submit_owner_evidence(*args: Any, **kwargs: Any) -> dict[str, Any]:
    archived_kwargs = dict(kwargs)
    if "pre_live_evidence" in archived_kwargs:
        archived_kwargs["pre_live_evidence"] = _to_archived_pre_live_submit_rehearsal(
            archived_kwargs["pre_live_evidence"]
        )
    archived_output = getattr(_archived_module, _ARCHIVED_BUILDER_NAME)(
        *args,
        **archived_kwargs,
    )
    return _normalize_current_evidence(archived_output)


def _to_archived_pre_live_submit_rehearsal(
    evidence: dict[str, Any],
) -> dict[str, Any]:
    return to_archived_pre_live_submit_rehearsal_input(evidence)


def _normalize_current_evidence(archived_output: dict[str, Any]) -> dict[str, Any]:
    return normalize_first_real_submit_owner_evidence(archived_output)


def _main(*args: Any, **kwargs: Any) -> Any:
    return _archived_module.main(*args, **kwargs)


main = _main


if __name__ == "__main__":
    raise SystemExit(_main())
