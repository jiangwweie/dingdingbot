#!/usr/bin/env python3
"""Validate server-backed candidate universe coverage before refreshing snapshots."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.build_strategy_live_candidate_pool import (  # noqa: E402
    AUTHORITY_BOUNDARY,
    DEFAULT_CANDIDATE_UNIVERSE,
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
                "expected_row_count": _expected_row_count(),
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
    expected_pairs = _expected_pairs()
    expected_count = len(expected_pairs)
    if not coverage:
        return ["candidate_universe_coverage is required"]
    if coverage.get("status") != "complete":
        errors.append("candidate_universe_coverage.status must be complete")
    for key in ("expected_row_count", "active_matched_row_count"):
        if coverage.get(key) != expected_count:
            errors.append(f"candidate_universe_coverage.{key} must be {expected_count}")
    if coverage.get("missing_row_count") != 0:
        errors.append("candidate_universe_coverage.missing_row_count must be 0")

    rows = _dict_rows(coverage.get("rows"))
    by_pair = {
        (
            str(row.get("strategy_group_id") or ""),
            str(row.get("symbol") or ""),
        ): row
        for row in rows
    }
    row_pairs = set(by_pair)
    for pair in sorted(expected_pairs - row_pairs):
        errors.append(f"candidate_universe_coverage missing row {pair[0]}/{pair[1]}")
    for pair in sorted(row_pairs - expected_pairs):
        errors.append(f"candidate_universe_coverage unexpected row {pair[0]}/{pair[1]}")
    for pair in sorted(expected_pairs & row_pairs):
        row = by_pair[pair]
        prefix = f"candidate_universe_coverage {pair[0]}/{pair[1]}"
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


def _expected_pairs() -> set[tuple[str, str]]:
    return {
        (strategy_group_id, symbol)
        for strategy_group_id, symbols in DEFAULT_CANDIDATE_UNIVERSE.items()
        for symbol in symbols
    }


def _expected_row_count() -> int:
    return len(_expected_pairs())


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
