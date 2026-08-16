from __future__ import annotations

import pytest

from scripts.trading_kernel.certify_release_candidate import (
    CERTIFICATION_COMMANDS,
    ReleaseCertificationLevel,
    ReleaseCertificationManifest,
    build_certification_identity,
    validate_manifest_identity,
)

COMMIT = "a" * 40


def test_release_certification_command_set_has_no_pytest_overlap() -> None:
    pytest_targets = [
        argument
        for command in CERTIFICATION_COMMANDS
        if "pytest" in command
        for argument in command
        if argument.startswith("tests/trading_kernel")
    ]

    assert pytest_targets == [
        "tests/trading_kernel/unit",
        "tests/trading_kernel/architecture",
        "tests/trading_kernel/integration",
        "tests/trading_kernel/full_chain",
    ]
    assert "tests/trading_kernel" not in pytest_targets


def test_exact_release_certification_identity_is_reusable() -> None:
    identity = build_certification_identity(COMMIT, ReleaseCertificationLevel.R3)
    manifest = ReleaseCertificationManifest(
        **identity,
        status="pass",
        certified_at_ms=2_000,
        command_durations_ms=(1, 2, 3, 4, 5, 6),
    )

    validate_manifest_identity(manifest, COMMIT, ReleaseCertificationLevel.R3)


def test_release_certification_rejects_a_different_commit() -> None:
    identity = build_certification_identity(COMMIT, ReleaseCertificationLevel.R3)
    manifest = ReleaseCertificationManifest(
        **identity,
        status="pass",
        certified_at_ms=2_000,
        command_durations_ms=(1, 2, 3, 4, 5, 6),
    )

    with pytest.raises(ValueError, match="commit"):
        validate_manifest_identity(manifest, "b" * 40, ReleaseCertificationLevel.R3)


def test_release_certification_rejects_command_set_drift() -> None:
    identity = build_certification_identity(COMMIT, ReleaseCertificationLevel.R3)
    manifest = ReleaseCertificationManifest(
        **{**identity, "command_set_digest": "sha256:" + "0" * 64},
        status="pass",
        certified_at_ms=2_000,
        command_durations_ms=(1, 2, 3, 4, 5, 6),
    )

    with pytest.raises(ValueError, match="command set"):
        validate_manifest_identity(manifest, COMMIT, ReleaseCertificationLevel.R3)


def test_r4_manifest_cannot_satisfy_an_r3_certification_requirement() -> None:
    identity = build_certification_identity(COMMIT, ReleaseCertificationLevel.R4)
    manifest = ReleaseCertificationManifest(
        **identity,
        status="pass",
        certified_at_ms=2_000,
        command_durations_ms=(1, 2, 3, 4, 5, 6, 7),
    )

    with pytest.raises(ValueError, match="release level differs"):
        validate_manifest_identity(manifest, COMMIT, ReleaseCertificationLevel.R3)
