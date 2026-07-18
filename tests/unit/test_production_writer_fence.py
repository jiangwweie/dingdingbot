from __future__ import annotations

import json
import os

import pytest

from scripts.set_production_writer_fence import (
    create_fence,
    remove_fence,
    supersede_fence,
)


def _receipt(marker_inode: int) -> dict:
    return {
        "schema": "brc.runtime_activation_commit.v1",
        "status": "runtime_activation_committed",
        "deploy_transaction_id": "tx-1",
        "deploy_nonce": "nonce-1",
        "target_runtime_head": "a" * 40,
        "fence_inode": marker_inode,
        "lifecycle_policy_enabled": True,
        "lifecycle_proof_ref": "lifecycle-cert:v2:" + "b" * 64,
        "release_pointer": "/deploy/releases/new",
    }


def test_create_fence_is_atomic_durable_and_mode_0600(tmp_path):
    marker = tmp_path / "production-writers.blocked"
    result = create_fence(
        marker,
        deploy_transaction_id="tx-1",
        deploy_nonce="nonce-1",
        target_runtime_head="a" * 40,
    )

    assert result["status"] == "fence_engaged"
    assert marker.exists()
    assert marker.stat().st_mode & 0o777 == 0o600
    payload = json.loads(marker.read_text(encoding="utf-8"))
    assert payload["deploy_transaction_id"] == "tx-1"


def test_remove_requires_matching_committed_receipt(tmp_path):
    marker = tmp_path / "production-writers.blocked"
    create_fence(
        marker,
        deploy_transaction_id="tx-1",
        deploy_nonce="nonce-1",
        target_runtime_head="a" * 40,
    )
    receipt = _receipt(marker.stat().st_ino)

    result = remove_fence(marker, activation_commit=receipt)

    assert result["status"] == "fence_removed"
    assert not marker.exists()


def test_remove_rejects_wrong_nonce_without_mutation(tmp_path):
    marker = tmp_path / "production-writers.blocked"
    create_fence(
        marker,
        deploy_transaction_id="tx-1",
        deploy_nonce="nonce-1",
        target_runtime_head="a" * 40,
    )
    receipt = _receipt(marker.stat().st_ino)
    receipt["deploy_nonce"] = "wrong"

    with pytest.raises(ValueError, match="activation_commit_fence_mismatch"):
        remove_fence(marker, activation_commit=receipt)

    assert marker.exists()


def test_supersede_replaces_only_exact_predecessor_without_fence_gap(tmp_path):
    marker = tmp_path / "production-writers.blocked"
    create_fence(
        marker,
        deploy_transaction_id="old-tx",
        deploy_nonce="old-nonce",
        target_runtime_head="a" * 40,
    )
    predecessor = json.loads(marker.read_text(encoding="utf-8"))

    result = supersede_fence(
        marker,
        predecessor_fence=predecessor,
        deploy_transaction_id="new-tx",
        deploy_nonce="new-nonce",
        target_runtime_head="b" * 40,
    )

    successor = json.loads(marker.read_text(encoding="utf-8"))
    assert result["status"] == "fence_superseded"
    assert result["predecessor_inode"] != result["inode"]
    assert successor == {
        "schema": "brc.production_writer_fence.v1",
        "deploy_transaction_id": "new-tx",
        "deploy_nonce": "new-nonce",
        "target_runtime_head": "b" * 40,
    }


def test_supersede_rejects_changed_predecessor_without_mutation(tmp_path):
    marker = tmp_path / "production-writers.blocked"
    create_fence(
        marker,
        deploy_transaction_id="old-tx",
        deploy_nonce="old-nonce",
        target_runtime_head="a" * 40,
    )
    predecessor = json.loads(marker.read_text(encoding="utf-8"))
    predecessor["deploy_nonce"] = "wrong"

    with pytest.raises(ValueError, match="fence_predecessor_lineage_mismatch"):
        supersede_fence(
            marker,
            predecessor_fence=predecessor,
            deploy_transaction_id="new-tx",
            deploy_nonce="new-nonce",
            target_runtime_head="b" * 40,
        )

    assert json.loads(marker.read_text(encoding="utf-8"))["deploy_transaction_id"] == "old-tx"


def test_create_rejects_symlink_marker(tmp_path):
    target = tmp_path / "target"
    target.write_text("x", encoding="utf-8")
    marker = tmp_path / "production-writers.blocked"
    os.symlink(target, marker)
    with pytest.raises(ValueError, match="fence_path_unsafe"):
        create_fence(
            marker,
            deploy_transaction_id="tx-1",
            deploy_nonce="nonce-1",
            target_runtime_head="a" * 40,
        )


def test_remove_accepts_explicitly_disabled_lifecycle_without_proof(tmp_path):
    marker = tmp_path / "production-writers.blocked"
    create_fence(
        marker,
        deploy_transaction_id="tx-1",
        deploy_nonce="nonce-1",
        target_runtime_head="a" * 40,
    )
    receipt = _receipt(marker.stat().st_ino)
    receipt["lifecycle_policy_enabled"] = False
    receipt["lifecycle_proof_ref"] = None

    result = remove_fence(marker, activation_commit=receipt)

    assert result["status"] == "fence_removed"
