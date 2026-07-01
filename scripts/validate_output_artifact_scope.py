#!/usr/bin/env python3
"""Validate routine output artifact changes against the control snapshot list."""

from __future__ import annotations

import argparse
from fnmatch import fnmatch
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPO_ROOT / "config/output_control_snapshots.json"
SCHEMA = "brc.output_control_snapshots.v1"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument(
        "--path",
        action="append",
        dest="paths",
        default=[],
        help="Changed output path to validate. May be passed more than once.",
    )
    parser.add_argument(
        "--git-status",
        action="store_true",
        help="Validate changed output paths reported by git status --porcelain.",
    )
    args = parser.parse_args(argv)

    manifest_path = Path(args.manifest)
    manifest = _read_json(manifest_path)
    errors = validate_manifest(manifest)
    paths = list(args.paths)
    if args.git_status:
        paths.extend(_git_changed_output_paths(REPO_ROOT))
    errors.extend(validate_changed_output_paths(paths, manifest))
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "status": "output_artifact_scope_valid",
                "manifest": str(manifest_path),
                "checked_path_count": len(set(paths)),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if manifest.get("schema") != SCHEMA:
        errors.append(f"manifest.schema must be {SCHEMA}")
    if manifest.get("status") != "current":
        errors.append("manifest.status must be current")
    snapshots = _dict_rows(manifest.get("control_snapshots"))
    if not snapshots:
        errors.append("manifest.control_snapshots is required")
    seen: set[str] = set()
    for index, row in enumerate(snapshots):
        prefix = f"control_snapshots[{index}]"
        path = str(row.get("path") or "")
        paired_path = str(row.get("paired_path") or "")
        for key in ("path", "paired_path", "source_command", "validator", "consumed_by"):
            if not str(row.get(key) or ""):
                errors.append(f"{prefix}.{key} is required")
        for key, value in (("path", path), ("paired_path", paired_path)):
            if value and not value.startswith("output/"):
                errors.append(f"{prefix}.{key} must be under output/")
            if value and value in seen:
                errors.append(f"{prefix}.{key} duplicates another control path")
            if value:
                seen.add(value)
        if "*" in path or "*" in paired_path:
            errors.append(f"{prefix}.path must be exact, not a glob")
    boundary = _as_dict(manifest.get("authority_boundary"))
    for key in (
        "finalgate_called",
        "operation_layer_called",
        "exchange_write_called",
        "live_profile_changed",
        "order_sizing_changed",
    ):
        if boundary.get(key) is not False:
            errors.append(f"authority_boundary.{key} must be false")
    return errors


def validate_changed_output_paths(
    paths: list[str],
    manifest: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    allowed = control_snapshot_paths(manifest)
    volatile_globs = [
        str(item)
        for item in manifest.get("volatile_output_globs", [])
        if isinstance(item, str)
    ]
    for path in sorted(set(_normalize_path(path) for path in paths)):
        if not path or not path.startswith("output/"):
            continue
        if path in allowed:
            continue
        matched_glob = next((glob for glob in volatile_globs if _match(path, glob)), "")
        if matched_glob:
            errors.append(
                f"{path} is volatile output matched by {matched_glob}; do not include it in routine commits"
            )
        else:
            errors.append(
                f"{path} is not an approved control snapshot; add it to {DEFAULT_MANIFEST.relative_to(REPO_ROOT)} with a source command and validator before committing"
            )
    return errors


def control_snapshot_paths(manifest: dict[str, Any]) -> set[str]:
    paths: set[str] = set()
    for row in _dict_rows(manifest.get("control_snapshots")):
        for key in ("path", "paired_path"):
            value = str(row.get(key) or "")
            if value:
                paths.add(_normalize_path(value))
    return paths


def _git_changed_output_paths(repo_root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "status", "--porcelain", "--", "output"],
        cwd=repo_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git status failed")
    paths: list[str] = []
    for line in result.stdout.splitlines():
        if not line:
            continue
        raw_path = line[3:]
        if " -> " in raw_path:
            raw_path = raw_path.split(" -> ", 1)[1]
        paths.append(raw_path.strip())
    return paths


def _match(path: str, pattern: str) -> bool:
    if pattern.endswith("/**"):
        return path.startswith(pattern[:-3])
    return fnmatch(path, pattern)


def _normalize_path(path: str) -> str:
    normalized = path.strip().replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


if __name__ == "__main__":
    raise SystemExit(main())
