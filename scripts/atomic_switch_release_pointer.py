#!/usr/bin/env python3
"""Durably replace app/current with an exact release target symlink."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import sys
import uuid
from typing import Any


def switch_release_pointer(
    current: Path,
    target: Path,
    *,
    expected_sha: str,
) -> dict[str, Any]:
    current = Path(current)
    target = Path(target).resolve(strict=True)
    expected_sha = _runtime_head(expected_sha)
    if not stat.S_ISDIR(target.stat().st_mode):
        raise ValueError("release_target_not_directory")
    manifest_sha = _manifest_sha(target)
    if manifest_sha != expected_sha:
        raise ValueError("release_manifest_sha_mismatch")
    current.parent.mkdir(parents=True, exist_ok=True)
    if current.parent.stat().st_dev != target.stat().st_dev:
        raise ValueError("release_pointer_cross_filesystem")
    temp = current.with_name(f".{current.name}.{uuid.uuid4().hex}.tmp")
    try:
        os.symlink(str(target), temp)
        os.replace(temp, current)
        _fsync_dir(current.parent)
    finally:
        if os.path.lexists(temp):
            temp.unlink()
    resolved = current.resolve(strict=True)
    if resolved != target or _manifest_sha(resolved) != expected_sha:
        raise RuntimeError("release_pointer_post_switch_mismatch")
    return {
        "status": "release_pointer_switched",
        "release_pointer": str(current),
        "resolved_target": str(resolved),
        "target_runtime_head": expected_sha,
        "parent_fsynced": True,
    }


def _manifest_sha(target: Path) -> str:
    path = target / ".brc-release-manifest.json"
    if not path.is_file() or path.is_symlink():
        raise ValueError("release_manifest_missing_or_unsafe")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        value = str(payload["git_deploy"]["target_commit"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ValueError("release_manifest_invalid") from exc
    return _runtime_head(value)


def _runtime_head(value: str) -> str:
    text = str(value or "").strip()
    if len(text) != 40 or any(char not in "0123456789abcdef" for char in text):
        raise ValueError("target_runtime_head_invalid")
    return text


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--expected-sha", required=True)
    args = parser.parse_args(argv)
    try:
        result = switch_release_pointer(
            Path(args.current), Path(args.target), expected_sha=args.expected_sha
        )
    except (OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
