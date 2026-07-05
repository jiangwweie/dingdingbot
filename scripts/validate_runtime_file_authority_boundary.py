#!/usr/bin/env python3
"""Validate that PG cutover file-authority debt does not expand."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPO_ROOT / "config/runtime_file_authority_boundary.json"
SCHEMA = "brc.runtime_file_authority_boundary.v1"

PATTERNS: dict[str, re.Pattern[str]] = {
    "docs_current_json_literal": re.compile(r"docs/current/[^\"'\s)]+\.json"),
    "output_runtime_latest_literal": re.compile(
        r"output/runtime-monitor/latest-[^\"'\s)]+\.json"
    ),
    "default_candidate_universe": re.compile(r"\bDEFAULT_CANDIDATE_UNIVERSE\b"),
    "default_side_scope": re.compile(r"\bDEFAULT_SIDE_SCOPE\b"),
    "file_backed_runtime_repo": re.compile(
        r"\bFileBackedRuntimeControlStateRepository\b"
    ),
}

DISPOSITIONS = {
    "pre_pg_cutover_debt",
    "local_migration_comparison_only",
    "export_only_writer",
}

AUTHORITY_FALSE_KEYS = (
    "production_runtime_file_authority_allowed",
    "finalgate_called",
    "operation_layer_called",
    "exchange_write_called",
    "order_created",
    "live_profile_changed",
    "order_sizing_changed",
)

FORBIDDEN_PRODUCTION_TEXT_BY_PATH: dict[str, tuple[str, ...]] = {
    "scripts/refresh_strategygroup_runtime_product_state_artifacts.py": (
        "--collect-live-facts-before-refresh",
        "--live-facts-output",
        "--live-facts-base-url",
        "collect_live_facts_before_refresh",
        "live_facts_precollect",
        "DEFAULT_LIVE_FACTS_FILENAME",
    ),
    "scripts/run_server_product_state_refresh_sequence.py": (
        "--collect-live-facts-before-refresh",
        "--live-facts-output",
        "--live-facts-json",
        "strategy-group-live-facts-input.json",
    ),
    "scripts/build_strategy_group_live_facts_readiness_artifact.py": (
        "--live-facts-json",
    ),
    "src/application/readmodels/trading_console.py": (
        "BRC_STRATEGY_GROUP_LIVE_FACTS_PATH",
        "DEFAULT_STRATEGY_GROUP_LIVE_FACTS_PATH",
        "DEFAULT_STRATEGY_GROUP_LIVE_FACTS_GLOB",
        "strategy-group-live-facts-input.json",
    ),
}


@dataclass(frozen=True)
class Occurrence:
    path: str
    pattern_id: str
    matches: tuple[str, ...]
    occurrence_count: int


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root)
    manifest_path = Path(args.manifest)
    manifest = _read_json(manifest_path)
    errors = validate_manifest(manifest)
    if not errors:
        errors.extend(validate_occurrences(manifest, repo_root=repo_root))
    errors.extend(validate_forbidden_production_text(repo_root=repo_root))

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    report = {
        "status": "runtime_file_authority_boundary_valid",
        "manifest": str(manifest_path),
        "monitored_occurrence_count": len(manifest.get("monitored_occurrences", [])),
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        print(report["status"])
    return 0


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if manifest.get("schema") != SCHEMA:
        errors.append(f"manifest.schema must be {SCHEMA}")
    if manifest.get("status") != "current":
        errors.append("manifest.status must be current")

    boundary = _as_dict(manifest.get("authority_boundary"))
    for key in AUTHORITY_FALSE_KEYS:
        if boundary.get(key) is not False:
            errors.append(f"authority_boundary.{key} must be false")

    rows = _dict_rows(manifest.get("monitored_occurrences"))
    if not rows:
        errors.append("monitored_occurrences is required")

    seen_keys: set[tuple[str, str]] = set()
    for index, row in enumerate(rows):
        prefix = f"monitored_occurrences[{index}]"
        path = str(row.get("path") or "")
        pattern_id = str(row.get("pattern_id") or "")
        key = (path, pattern_id)
        if not path:
            errors.append(f"{prefix}.path is required")
        elif not path.endswith(".py"):
            errors.append(f"{prefix}.path must point to a Python file")
        if pattern_id not in PATTERNS:
            errors.append(f"{prefix}.pattern_id is unknown")
        if key in seen_keys:
            errors.append(f"{prefix} duplicates path/pattern_id {path}:{pattern_id}")
        seen_keys.add(key)

        occurrence_count = row.get("occurrence_count")
        if not isinstance(occurrence_count, int) or occurrence_count < 1:
            errors.append(f"{prefix}.occurrence_count must be a positive integer")
        matches = row.get("matches")
        if not isinstance(matches, list) or not all(
            isinstance(item, str) and item for item in matches
        ):
            errors.append(f"{prefix}.matches must be a non-empty string list")
        disposition = str(row.get("disposition") or "")
        if disposition not in DISPOSITIONS:
            errors.append(f"{prefix}.disposition is invalid")
        for field in ("replacement", "sunset_condition"):
            if not str(row.get(field) or "").strip():
                errors.append(f"{prefix}.{field} is required")
    return errors


def validate_occurrences(
    manifest: dict[str, Any],
    *,
    repo_root: Path,
) -> list[str]:
    errors: list[str] = []
    expected_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for row in _dict_rows(manifest.get("monitored_occurrences")):
        expected_by_key[(str(row["path"]), str(row["pattern_id"]))] = row

    for key, row in sorted(expected_by_key.items()):
        path, pattern_id = key
        source_path = repo_root / path
        if not source_path.exists():
            errors.append(f"{path} is missing; update the boundary manifest")
            continue
        observed = collect_occurrence(source_path, repo_root=repo_root, pattern_id=pattern_id)
        expected_matches = tuple(sorted(set(str(item) for item in row["matches"])))
        expected_count = int(row["occurrence_count"])
        if observed.matches != expected_matches:
            errors.append(
                f"{path}:{pattern_id} matches changed; expected "
                f"{list(expected_matches)}, observed {list(observed.matches)}"
            )
        if observed.occurrence_count != expected_count:
            errors.append(
                f"{path}:{pattern_id} occurrence_count changed; expected "
                f"{expected_count}, observed {observed.occurrence_count}"
            )
    return errors


def validate_forbidden_production_text(
    *,
    repo_root: Path,
    forbidden_by_path: dict[str, tuple[str, ...]] | None = None,
) -> list[str]:
    errors: list[str] = []
    paths = forbidden_by_path or FORBIDDEN_PRODUCTION_TEXT_BY_PATH
    for relative_path, forbidden_items in sorted(paths.items()):
        source_path = repo_root / relative_path
        if not source_path.exists():
            errors.append(f"{relative_path} is missing; update forbidden text guard")
            continue
        text = source_path.read_text(encoding="utf-8")
        for forbidden in forbidden_items:
            if forbidden in text:
                errors.append(
                    f"{relative_path} contains retired production file-authority "
                    f"text: {forbidden}"
                )
    return errors


def collect_occurrence(
    path: Path,
    *,
    repo_root: Path,
    pattern_id: str,
) -> Occurrence:
    pattern = PATTERNS[pattern_id]
    text = path.read_text(encoding="utf-8")
    found = [match.group(0) for match in pattern.finditer(text)]
    try:
        display_path = str(path.relative_to(repo_root))
    except ValueError:
        display_path = str(path)
    return Occurrence(
        path=display_path,
        pattern_id=pattern_id,
        matches=tuple(sorted(set(found))),
        occurrence_count=len(found),
    )


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_rows(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


if __name__ == "__main__":
    raise SystemExit(main())
