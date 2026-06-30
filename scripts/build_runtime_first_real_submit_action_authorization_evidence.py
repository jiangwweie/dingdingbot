#!/usr/bin/env python3
"""Current evidence wrapper for archived first-real-submit action authorization.

This read-only evidence builder records explicit Owner review state only. It
does not modify runtime state, create orders, call exchange APIs, or call
OrderLifecycle.
"""

from __future__ import annotations

import argparse
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
    archived_first_real_submit_action_authorization_inputs,
    normalize_first_real_submit_action_authorization_evidence,
)

_ARCHIVED_MODULE_NAME = archived_first_real_submit_module(
    "build_runtime_first_real_submit_action_authorization"
)
_ARCHIVED_BUILDER_NAME = archived_legacy_name(
    "build_first_real_submit_action_authorization"
)
_archived_module = import_module(_ARCHIVED_MODULE_NAME)


def build_first_real_submit_action_authorization_evidence(
    *,
    final_review_artifact: dict[str, Any],
    **kwargs: Any,
) -> dict[str, Any]:
    evidence = getattr(_archived_module, _ARCHIVED_BUILDER_NAME)(
        **archived_first_real_submit_action_authorization_inputs(
            final_review_artifact=final_review_artifact,
        ),
        **kwargs,
    )
    return _normalize_current_evidence(evidence)


def _normalize_current_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    return normalize_first_real_submit_action_authorization_evidence(evidence)


def _main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    evidence = build_first_real_submit_action_authorization_evidence(
        final_review_artifact=_load_json_object(Path(args.final_review_artifact_path)),
        authorization_id=args.authorization_id,
        owner_confirmation_value=args.owner_confirmation_value,
        standing_authorized_first_real_submit=(
            args.standing_authorized_first_real_submit
        ),
        api_base=args.api_base,
        env_file=args.env_file,
    )
    if args.output_json:
        output_path = Path(args.output_json).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.json:
        print(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_human(evidence)
    return 0 if evidence["checks"]["ready_for_owner_action_authorization"] else 2


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"artifact must be a JSON object: {path}")
    return payload


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a non-executing first-real-submit action authorization evidence."
        )
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    parser.add_argument("--final-review-artifact-path", required=True)
    parser.add_argument("--authorization-id")
    parser.add_argument("--owner-confirmation-value")
    parser.add_argument("--standing-authorized-first-real-submit", action="store_true")
    parser.add_argument(
        "--api-base",
        default=getattr(_archived_module, "DEFAULT_API_BASE", "http://127.0.0.1:8000"),
    )
    parser.add_argument("--env-file")
    parser.add_argument("--output-json")
    return parser.parse_args(argv)


def _print_human(evidence: dict[str, Any]) -> None:
    checks = evidence["checks"]
    print(f"status={evidence['status']}")
    print(
        "ready_for_owner_action_authorization="
        + str(checks["ready_for_owner_action_authorization"]).lower()
    )
    print("action_authorized=" + str(checks["action_authorized"]).lower())
    print(f"target_head={evidence['target_head']}")
    print(f"authorization_id={evidence['authorization_id']}")
    if checks["blockers"]:
        print("blockers=" + ",".join(checks["blockers"]))
    if checks["warnings"]:
        print("warnings=" + ",".join(checks["warnings"]))


main = _main


if __name__ == "__main__":
    raise SystemExit(_main())
