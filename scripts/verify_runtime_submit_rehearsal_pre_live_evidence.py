#!/usr/bin/env python3
"""Build current pre-live submit rehearsal evidence.

The underlying first-real-submit replay implementation remains archived under
`scripts/replay_recovery_history`. This current wrapper exposes that rehearsal
as Runtime Safety evidence instead of a legacy-shaped judgment source.
"""

from __future__ import annotations

import asyncio
import json
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
    replace_strings,
)

_ARCHIVED_MODULE_NAME = archived_first_real_submit_module(
    "verify_runtime_submit_rehearsal_pre_live"
)
_ARCHIVED_BUILDER_NAME = archived_legacy_name("build_pre_live")
_ARCHIVED_SCOPE = archived_legacy_name("runtime_submit_rehearsal_pre_live")
_CURRENT_SCOPE = "runtime_submit_rehearsal_pre_live_evidence"

_archived_module = import_module(_ARCHIVED_MODULE_NAME)

for _name, _value in vars(_archived_module).items():
    if _name.startswith("__") and _name.endswith("__"):
        continue
    if _name in {_ARCHIVED_BUILDER_NAME, "_amain", "main"}:
        continue
    globals()[_name] = _value


def _as_pre_live_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    evidence = replace_strings(
        payload,
        {
            archived_legacy_name("runtime_submit_rehearsal_pre_live"): (
                "runtime_submit_rehearsal_pre_live_evidence"
            ),
            archived_legacy_name("first_real_submit"): "first_real_submit_evidence",
            archived_legacy_name("first_real_submit") + "_not_available": (
                "first_real_submit_evidence_not_available"
            ),
        },
    )
    if evidence.get("scope") == _ARCHIVED_SCOPE:
        evidence["scope"] = _CURRENT_SCOPE
    return evidence


async def build_pre_live_evidence(*args: Any, **kwargs: Any) -> dict[str, Any]:
    payload = await getattr(_archived_module, _ARCHIVED_BUILDER_NAME)(
        *args,
        **kwargs,
    )
    return _as_pre_live_evidence(payload)


async def _amain(argv: list[str] | None = None) -> int:
    args = _archived_module._parse_args(argv)
    report = await build_pre_live_evidence(
        deployed_head=args.deployed_head,
        owner_real_submit_authorized=args.owner_real_submit_authorized,
        owner_live_runtime_enablement_authorized=(
            args.owner_live_runtime_enable_authorized
        ),
        require_current_head_deployed=not args.skip_current_head_deployed_check,
        active_positions=args.active_positions,
        exercise_local_registration_pre_exchange=(
            args.exercise_local_registration_pre_exchange
        ),
        exercise_exchange_submit_adapter_pre_execution=(
            args.exercise_exchange_submit_adapter_pre_execution
        ),
        exercise_in_memory_exchange_execution_simulation=(
            args.exercise_in_memory_exchange_execution_simulation
        ),
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _archived_module._print_human(report)
    return 0 if report["checks"]["technical_rehearsal_passed"] else 2


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_amain(argv))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"pre_live_evidence_error={exc}", file=sys.stderr)
        raise SystemExit(2)
