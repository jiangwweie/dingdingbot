#!/usr/bin/env python3
"""Atomically engage or release the boot-persistent production writer fence."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import sys
import uuid
from typing import Any, Mapping


DEFAULT_MARKER = Path(
    "/home/ubuntu/brc-deploy/control-plane/production-writers.blocked"
)


def create_fence(
    marker: Path,
    *,
    deploy_transaction_id: str,
    deploy_nonce: str,
    target_runtime_head: str,
) -> dict[str, Any]:
    marker = Path(marker)
    payload = {
        "schema": "brc.production_writer_fence.v1",
        "deploy_transaction_id": _required(deploy_transaction_id, "transaction_id"),
        "deploy_nonce": _required(deploy_nonce, "deploy_nonce"),
        "target_runtime_head": _runtime_head(target_runtime_head),
    }
    marker.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.path.lexists(marker):
        _validate_existing_marker(marker, payload)
        return {
            "status": "fence_engaged",
            "marker": str(marker),
            "inode": marker.stat().st_ino,
            "idempotent": True,
        }
    tmp = marker.with_name(f".{marker.name}.{uuid.uuid4().hex}.tmp")
    raw = _canonical_bytes(payload)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb", closefd=False) as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.close(fd)
        fd = -1
        os.replace(tmp, marker)
        _fsync_dir(marker.parent)
    finally:
        if fd >= 0:
            os.close(fd)
        if tmp.exists():
            tmp.unlink()
    _validate_existing_marker(marker, payload)
    return {
        "status": "fence_engaged",
        "marker": str(marker),
        "inode": marker.stat().st_ino,
        "idempotent": False,
    }


def remove_fence(
    marker: Path,
    *,
    activation_commit: Mapping[str, Any],
) -> dict[str, Any]:
    marker = Path(marker)
    if not os.path.lexists(marker):
        raise ValueError("fence_marker_missing_storage_integrity_incident")
    marker_payload = _read_safe_marker(marker)
    receipt = dict(activation_commit)
    required = {
        "schema": "brc.runtime_activation_commit.v1",
        "status": "runtime_activation_committed",
        "deploy_transaction_id": marker_payload["deploy_transaction_id"],
        "deploy_nonce": marker_payload["deploy_nonce"],
        "target_runtime_head": marker_payload["target_runtime_head"],
        "fence_inode": marker.stat().st_ino,
    }
    if any(receipt.get(key) != value for key, value in required.items()):
        raise ValueError("activation_commit_fence_mismatch")
    lifecycle_enabled = receipt.get("lifecycle_policy_enabled")
    lifecycle_ref = receipt.get("lifecycle_proof_ref")
    if lifecycle_enabled is True:
        if not str(lifecycle_ref or "").startswith("lifecycle-cert:v2:"):
            raise ValueError("activation_commit_lifecycle_proof_missing")
    elif lifecycle_enabled is False:
        if lifecycle_ref is not None:
            raise ValueError("activation_commit_disabled_lifecycle_proof_present")
    else:
        raise ValueError("activation_commit_lifecycle_policy_missing")
    if not str(receipt.get("release_pointer") or "").strip():
        raise ValueError("activation_commit_release_pointer_missing")
    marker.unlink()
    _fsync_dir(marker.parent)
    return {"status": "fence_removed", "marker": str(marker)}


def _validate_existing_marker(marker: Path, expected: Mapping[str, Any]) -> None:
    if _read_safe_marker(marker) != dict(expected):
        raise ValueError("fence_existing_lineage_mismatch")


def _read_safe_marker(marker: Path) -> dict[str, Any]:
    info = marker.lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
        raise ValueError("fence_path_unsafe")
    if info.st_uid != os.geteuid():
        raise ValueError("fence_owner_mismatch")
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("fence_payload_invalid") from exc
    if not isinstance(payload, dict):
        raise ValueError("fence_payload_invalid")
    return payload


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _required(value: str, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{name}_required")
    return text


def _runtime_head(value: str) -> str:
    text = _required(value, "target_runtime_head")
    if len(text) != 40 or any(char not in "0123456789abcdef" for char in text):
        raise ValueError("target_runtime_head_invalid")
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--marker", default=str(DEFAULT_MARKER))
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--engage", action="store_true")
    mode.add_argument("--remove", action="store_true")
    parser.add_argument("--deploy-transaction-id", default="")
    parser.add_argument("--deploy-nonce", default="")
    parser.add_argument("--target-runtime-head", default="")
    parser.add_argument("--activation-commit-json", default="")
    args = parser.parse_args(argv)
    try:
        result = (
            create_fence(
                Path(args.marker),
                deploy_transaction_id=args.deploy_transaction_id,
                deploy_nonce=args.deploy_nonce,
                target_runtime_head=args.target_runtime_head,
            )
            if args.engage
            else remove_fence(
                Path(args.marker),
                activation_commit=json.loads(args.activation_commit_json),
            )
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
