#!/usr/bin/env python3
"""Validate production runtime does not use JSON files as authority."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DISPATCHER_DROPIN = (
    REPO_ROOT
    / "deploy/systemd/brc-runtime-signal-watcher.service.d/"
    "90-resume-dispatcher-after-refresh.conf"
)
PRODUCT_STATE_DROPIN = (
    REPO_ROOT
    / "deploy/systemd/brc-runtime-signal-watcher.service.d/"
    "80-product-state-refresh.conf"
)


def validate_no_runtime_file_authority(*, repo_root: Path = REPO_ROOT) -> list[str]:
    errors: list[str] = []
    dispatcher = (repo_root / DISPATCHER_DROPIN.relative_to(REPO_ROOT)).read_text(
        encoding="utf-8"
    )
    product_state = (
        repo_root / PRODUCT_STATE_DROPIN.relative_to(REPO_ROOT)
    ).read_text(encoding="utf-8")
    if "--identity-source pg_ticket" not in dispatcher:
        errors.append("runtime dispatcher production drop-in must use pg_ticket identity")
    if "--mode watcher_tick_summary" not in product_state:
        errors.append("watcher product-state post-step must use watcher_tick_summary")
    forbidden_production_inputs = (
        "--candidate-pool-json",
        "--daily-table-json",
        "--goal-status-json",
        "--live-facts-json",
        "--runtime-active-monitor-json",
    )
    for token in forbidden_production_inputs:
        if token in dispatcher:
            errors.append(f"dispatcher drop-in contains file authority input: {token}")
        if token in product_state:
            errors.append(f"product-state drop-in contains file authority input: {token}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    errors = validate_no_runtime_file_authority(repo_root=args.repo_root)
    report: dict[str, Any] = {
        "status": "no_runtime_file_authority_valid" if not errors else "blocked",
        "errors": errors,
        "checked_files": [
            str(DISPATCHER_DROPIN.relative_to(REPO_ROOT)),
            str(PRODUCT_STATE_DROPIN.relative_to(REPO_ROOT)),
        ],
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    elif errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
    else:
        print(report["status"])
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
