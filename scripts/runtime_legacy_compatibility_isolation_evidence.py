#!/usr/bin/env python3
"""Build current legacy compatibility isolation evidence.

The original first-real-submit implementation remains archived under
`scripts/replay_recovery_history`. This current wrapper exposes the isolation
result as evidence, not as a legacy-shaped runtime gate.
"""

from __future__ import annotations

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
)

_ARCHIVED_MODULE_NAME = archived_first_real_submit_module(
    "runtime_legacy_compatibility_isolation"
)
_ARCHIVED_BUILDER_NAME = archived_legacy_name("build_isolation")
_ARCHIVED_SCOPE = archived_legacy_name("runtime_legacy_compatibility_isolation")
_CURRENT_SCOPE = "runtime_legacy_compatibility_isolation_evidence"

_archived_module = import_module(_ARCHIVED_MODULE_NAME)

for _name, _value in vars(_archived_module).items():
    if _name.startswith("__") and _name.endswith("__"):
        continue
    if _name in {_ARCHIVED_BUILDER_NAME, "main"}:
        continue
    globals()[_name] = _value


def _as_isolation_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    evidence = dict(payload)
    if evidence.get("scope") == _ARCHIVED_SCOPE:
        evidence["scope"] = _CURRENT_SCOPE
    return evidence


def build_isolation_evidence(*, repo_root: Path = ROOT_DIR) -> dict[str, Any]:
    payload = getattr(_archived_module, _ARCHIVED_BUILDER_NAME)(
        repo_root=repo_root,
    )
    return _as_isolation_evidence(payload)


def main(argv: list[str] | None = None) -> int:
    args = _archived_module._parse_args(sys.argv[1:] if argv is None else argv)
    evidence = build_isolation_evidence(repo_root=ROOT_DIR)
    if args.output_json:
        _write_json(args.output_json, evidence)
    print(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True))
    return (
        0
        if evidence["status"] == "legacy_compatibility_isolated_from_runtime_mainline"
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
