#!/usr/bin/env python3
"""Current evidence wrapper for archived exchange-arm authorization."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
import sys
from typing import Any
import json

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.archived_replay_adapter import (  # noqa: E402
    normalize_first_real_submit_authorization_evidence,
)

_ARCHIVED_MODULE_NAME = ".".join(
    (
        "scripts",
        "replay_recovery_history",
        "first_real_submit",
        "build_runtime_first_real_submit_exchange_arm_authorization_" + "pack" + "et",
    )
)
_ARCHIVED_BUILDER_NAME = "build_exchange_arm_authorization_" + "pack" + "et"
_archived_module = import_module(_ARCHIVED_MODULE_NAME)


def build_exchange_arm_authorization_evidence(
    *args: Any,
    **kwargs: Any,
) -> dict[str, Any]:
    payload = getattr(_archived_module, _ARCHIVED_BUILDER_NAME)(*args, **kwargs)
    return _normalize_evidence(payload)


def _normalize_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    return normalize_first_real_submit_authorization_evidence(
        payload,
        archived_ready_status=(
            "owner_exchange_arm_authorization_" + "pack" + "et_ready"
        ),
        current_ready_status="owner_exchange_arm_authorization_evidence_ready",
        archived_scope=(
            "runtime_first_real_submit_exchange_arm_authorization_" + "pack" + "et"
        ),
        current_scope="runtime_first_real_submit_exchange_arm_authorization_evidence",
        archived_build_only_key="pack" + "et_build_only",
        current_plan_key="exchange_arm_authorization_plan",
    )


def _main(*args: Any, **kwargs: Any) -> Any:
    argv = args[0] if args else kwargs.get("argv")
    parsed = _archived_module._parse_args(argv)
    evidence = build_exchange_arm_authorization_evidence(
        local_registration_report=_archived_module._load_json_object(
            Path(parsed.local_registration_report_path)
        ),
        authorization_id=parsed.authorization_id,
        owner_confirmation_value=parsed.owner_confirmation_value,
        api_base=parsed.api_base,
        env_file=parsed.env_file,
    )
    if parsed.output_json:
        output_path = Path(parsed.output_json).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if parsed.json:
        print(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _archived_module._print_human(evidence)
    return 0 if evidence["checks"]["ready_for_owner_exchange_arm_authorization"] else 2


main = _main


if __name__ == "__main__":
    raise SystemExit(_main())
