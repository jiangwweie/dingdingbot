#!/usr/bin/env python3
"""Current artifact wrapper for archived first-real-submit final review.

This read-only wrapper adapts replay-recovery legacy vocabulary into current
evidence/artifact vocabulary. It does not modify runtime state, create orders,
call exchange APIs, or call OrderLifecycle.
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
    archived_first_real_submit_final_review_inputs,
    normalize_first_real_submit_final_review_artifact,
)

_ARCHIVED_MODULE_NAME = archived_first_real_submit_module(
    "build_runtime_first_real_submit_final_review"
)
_ARCHIVED_BUILDER_NAME = archived_legacy_name("build_first_real_submit_final_review")
_archived_module = import_module(_ARCHIVED_MODULE_NAME)


def build_first_real_submit_final_review_artifact(
    *,
    postdeploy_acceptance_evidence: dict[str, Any],
    first_real_submit_owner_evidence: dict[str, Any],
    **kwargs: Any,
) -> dict[str, Any]:
    archived_kwargs = dict(kwargs)
    artifact = getattr(_archived_module, _ARCHIVED_BUILDER_NAME)(
        **archived_first_real_submit_final_review_inputs(
            postdeploy_acceptance_evidence=postdeploy_acceptance_evidence,
            first_real_submit_owner_evidence=first_real_submit_owner_evidence,
        ),
        **archived_kwargs,
    )
    return _normalize_current_artifact(artifact)


def _normalize_current_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    """Remove current-surface legacy wording from archived review output."""

    return normalize_first_real_submit_final_review_artifact(artifact)


def _main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    artifact = build_first_real_submit_final_review_artifact(
        postdeploy_acceptance_evidence=_load_json_object(
            Path(args.postdeploy_acceptance_artifact_path)
        ),
        first_real_submit_owner_evidence=_load_json_object(
            Path(args.first_real_submit_owner_evidence_path)
        ),
        expected_current_head=args.expected_current_head,
    )
    if args.json:
        print(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_human(artifact)
    return 0 if artifact["checks"]["ready_for_owner_action_review"] else 2


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"artifact must be a JSON object: {path}")
    return payload


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a current first-real-submit final review artifact."
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    parser.add_argument(
        "--postdeploy-acceptance-artifact-path",
        dest="postdeploy_acceptance_artifact_path",
        required=True,
    )
    parser.add_argument(
        "--first-real-submit-owner-evidence-path",
        dest="first_real_submit_owner_evidence_path",
        required=True,
    )
    parser.add_argument("--expected-current-head", default=None)
    return parser.parse_args(argv)


def _print_human(artifact: dict[str, Any]) -> None:
    checks = artifact["checks"]
    print(f"status={artifact['status']}")
    print(
        "ready_for_owner_action_review="
        + str(checks["ready_for_owner_action_review"]).lower()
    )
    print(f"target_head={artifact['target_head']}")
    if checks["blockers"]:
        print("blockers=" + ",".join(checks["blockers"]))
    if checks["warnings"]:
        print("warnings=" + ",".join(checks["warnings"]))


main = _main


if __name__ == "__main__":
    raise SystemExit(_main())
