#!/usr/bin/env python3
"""Validate server-backed candidate universe coverage before refreshing snapshots."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


AUTHORITY_BOUNDARY = (
    "runtime_candidate_universe_coverage_validator_is_read_only; "
    "no_finalgate_no_operation_layer_no_exchange_write"
)
READY_STATUS = "runtime_candidate_universe_coverage_valid"
BLOCKED_STATUS = "runtime_candidate_universe_coverage_invalid"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact_json")
    args = parser.parse_args(argv)

    artifact = _read_json(Path(args.artifact_json))
    errors = validate_runtime_candidate_universe_coverage(artifact)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(
            json.dumps(
                {
                    "status": BLOCKED_STATUS,
                    "error_count": len(errors),
                    "authority_boundary": AUTHORITY_BOUNDARY,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 1
    print(
        json.dumps(
            {
                "status": READY_STATUS,
                "expected_row_count": _coverage_expected_row_count(
                    _coverage(artifact)
                ),
                "authority_boundary": AUTHORITY_BOUNDARY,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def validate_runtime_candidate_universe_coverage(
    artifact: dict[str, Any],
) -> list[str]:
    coverage = _coverage(artifact)
    errors: list[str] = []
    if not coverage:
        return ["candidate_universe_coverage is required"]
    rows = _dict_rows(coverage.get("rows"))
    expected_count = _coverage_expected_row_count(coverage)
    if expected_count <= 0:
        errors.append("candidate_universe_coverage.expected_row_count must be positive")
    if len(rows) != expected_count:
        errors.append(
            "candidate_universe_coverage.rows length must equal expected_row_count"
        )
    if coverage.get("status") != "complete":
        errors.append("candidate_universe_coverage.status must be complete")
    for key in ("expected_row_count", "active_matched_row_count"):
        if coverage.get(key) != expected_count:
            errors.append(f"candidate_universe_coverage.{key} must be {expected_count}")
    if coverage.get("missing_row_count") != 0:
        errors.append("candidate_universe_coverage.missing_row_count must be 0")

    by_pair = {
        (
            str(row.get("strategy_group_id") or ""),
            str(row.get("symbol") or ""),
            str(row.get("side") or row.get("expected_side") or ""),
        ): row
        for row in rows
    }
    row_pairs = set(by_pair)
    if len(row_pairs) != len(rows):
        errors.append(
            "candidate_universe_coverage rows must be unique by strategy/symbol/side"
        )
    for pair in sorted(row_pairs):
        if not all(pair):
            errors.append(
                "candidate_universe_coverage rows require strategy_group_id/symbol/side"
            )
            continue
        if pair[2] not in {"long", "short"}:
            errors.append(
                "candidate_universe_coverage row side must be long or short "
                f"for {pair[0]}/{pair[1]}/{pair[2]}"
            )
        row = by_pair[pair]
        prefix = f"candidate_universe_coverage {pair[0]}/{pair[1]}/{pair[2]}"
        if row.get("state") != "active_watcher_scope":
            errors.append(f"{prefix} state must be active_watcher_scope")
        if row.get("blocker_class") not in {"", None, "none"}:
            errors.append(f"{prefix} blocker_class must be none")
        if not row.get("active_runtime_instance_ids"):
            errors.append(f"{prefix} active_runtime_instance_ids must be non-empty")
        if not row.get("selected_runtime_instance_ids"):
            errors.append(f"{prefix} selected_runtime_instance_ids must be non-empty")
        boundary = str(row.get("authority_boundary") or "")
        for token in ("no_finalgate", "no_operation_layer", "no_exchange_write"):
            if token not in boundary:
                errors.append(f"{prefix} authority_boundary missing {token}")
    return errors


def _coverage(artifact: dict[str, Any]) -> dict[str, Any]:
    coverage = artifact.get("candidate_universe_coverage")
    if isinstance(coverage, dict):
        return coverage
    latest = artifact.get("latest_summary")
    if isinstance(latest, dict) and isinstance(latest.get("candidate_universe_coverage"), dict):
        return latest["candidate_universe_coverage"]
    return {}


def _coverage_expected_row_count(coverage: dict[str, Any]) -> int:
    value = coverage.get("expected_row_count")
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    return 0


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


if __name__ == "__main__":
    raise SystemExit(main())
