from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.trading_kernel.certify_release_candidate import (
    CERTIFICATION_COMMANDS,
    ReleaseCertificationLevel,
    ReleaseCertificationManifest,
    RuntimeCompatibilityClassification,
    build_certification_identity,
    build_runtime_release_compatibility_fact,
    certification_commands_for,
    validate_manifest_identity,
)


def test_certification_command_streams_output_before_process_exit(tmp_path: Path) -> None:
    from scripts.trading_kernel.certify_release_candidate import (
        run_certification_command,
    )

    marker = tmp_path / "ack"
    class LiveStream:
        def write(self, value: str) -> int:
            if "step_started" in value:
                marker.touch()
            return len(value)
        def flush(self) -> None:
            pass
    code = "import pathlib,time,sys; print('step_started',flush=True); p=pathlib.Path(sys.argv[1]); end=time.monotonic()+2; " \
        "\nwhile not p.exists() and time.monotonic()<end: time.sleep(.01)\nassert p.exists(),'output was buffered until exit'\nprint('step_complete',flush=True)"
    result = run_certification_command((sys.executable,"-c",code,str(marker)),cwd=tmp_path,stream=LiveStream())
    assert result.returncode == 0 and "step_complete" in result.stdout


def test_certification_command_keeps_bounded_failure_tail(tmp_path: Path) -> None:
    import io

    from scripts.trading_kernel.certify_release_candidate import (
        run_certification_command,
    )
    result = run_certification_command((sys.executable,"-c","import sys; print('x'*100000); print('last_error'); sys.exit(2)"),cwd=tmp_path,stream=io.StringIO())
    assert isinstance(result, subprocess.CompletedProcess)
    assert result.returncode == 2 and len(result.stdout) <= 8000 and "last_error" in result.stdout


def test_r4_preservation_targets_are_not_executed_twice() -> None:
    from pathlib import PurePosixPath
    targets = [PurePosixPath(part) for command in certification_commands_for(ReleaseCertificationLevel.R4)
        if "pytest" in command for part in command if part.startswith("tests/")]
    assert not [(a,b) for i,a in enumerate(targets) for b in targets[i+1:] if a==b or a in b.parents or b in a.parents]

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
        command_durations_ms=tuple(
            range(
                1,
                len(certification_commands_for(ReleaseCertificationLevel.R4)) + 1,
            )
        ),
    )

    with pytest.raises(ValueError, match="release level differs"):
        validate_manifest_identity(manifest, COMMIT, ReleaseCertificationLevel.R3)


def test_release_compatibility_fact_is_bound_to_the_exact_certification_manifest() -> None:
    identity = build_certification_identity(COMMIT, ReleaseCertificationLevel.R4)
    manifest = ReleaseCertificationManifest(
        **identity,
        status="pass",
        certified_at_ms=2_000,
        command_durations_ms=tuple(
            range(
                1,
                len(certification_commands_for(ReleaseCertificationLevel.R4)) + 1,
            )
        ),
    )

    fact = build_runtime_release_compatibility_fact(
        manifest=manifest,
        from_commit="b" * 40,
        from_schema_revision="0005_tradfi_instrument_center",
        classification=RuntimeCompatibilityClassification.COMPATIBLE_RESTART,
        reason_codes=("PERSISTED_ACTIVE_UNIVERSE_CONTRACT_UNCHANGED",),
        created_at_ms=3_000,
    )

    assert fact.to_commit == COMMIT
    assert fact.to_schema_revision == identity["schema_revision"]
    assert fact.certification_manifest_digest.startswith("sha256:")
    assert fact.compatibility_basis_digest.startswith("sha256:")


def test_release_compatibility_rejects_a_manifest_that_is_not_r4() -> None:
    identity = build_certification_identity(COMMIT, ReleaseCertificationLevel.R3)
    manifest = ReleaseCertificationManifest(
        **identity,
        status="pass",
        certified_at_ms=2_000,
        command_durations_ms=(1, 2, 3, 4, 5, 6),
    )

    with pytest.raises(ValueError, match="R4 certification"):
        build_runtime_release_compatibility_fact(
            manifest=manifest,
            from_commit="b" * 40,
            from_schema_revision="0005_tradfi_instrument_center",
            classification=(
                RuntimeCompatibilityClassification.COMPATIBLE_RESTART
            ),
            reason_codes=("PERSISTED_ACTIVE_UNIVERSE_CONTRACT_UNCHANGED",),
            created_at_ms=3_000,
        )
