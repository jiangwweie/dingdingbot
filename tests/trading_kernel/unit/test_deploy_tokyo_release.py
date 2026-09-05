from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest

from scripts.trading_kernel.deploy_tokyo_release import (
    ALL_SERVICES,
    ENTRY_SERVICE,
    SAFETY_SERVICES,
    DeploymentBlocked,
    DeploymentMode,
    DeploymentPlan,
    SshTokyoReleaseBackend,
    deploy_tokyo_release,
)
from scripts.trading_kernel.deploy_tokyo_release import (
    CURRENT_RELEASE as CURRENT_RELEASE_SYMLINK,
)
from scripts.trading_kernel.deploy_tokyo_release import _parser as deployment_parser
from src.trading_kernel.application.runtime import (
    RuntimeCompatibilityClassification,
    RuntimeReleaseCompatibilityFact,
)
from src.trading_kernel.domain.exit_policy import build_exit_profile_catalog_digest

TARGET_COMMIT = "a" * 40
CURRENT_COMMIT = "b" * 40
CURRENT_RELEASE = "/opt/brc/releases/brc-trading-kernel-bbbbbbbbbbbb"
TARGET_RELEASE = "/opt/brc/releases/brc-trading-kernel-aaaaaaaaaaaa"
RECOVERY_RELEASE = "/opt/brc/releases/brc-trading-kernel-cccccccccccc"
SOURCE_SCHEMA_REVISION = "0006_sor_dynamic_selection_v0"
TARGET_SCHEMA_REVISION = "0007_exit_profile_authority_v1"
RELEASE_COMPATIBILITY_ID = (
    f"release-compatibility:{CURRENT_COMMIT}:{TARGET_COMMIT}"
)
SEED_IDENTITY = "sha256:" + "c" * 64
PRESERVATION_DIGEST = "sha256:" + "d" * 64
REGISTRY_DIGEST = "sha256:" + "f" * 64
SOURCE_REGISTRY_DIGEST = "sha256:" + "1" * 64
TARGET_EXCHANGE_INSTRUMENT_IDS = (
    "binance-usdm:ADAUSDT:perpetual",
    "binance-usdm:BNBUSDT:perpetual",
    "binance-usdm:BTCUSDT:perpetual",
    "binance-usdm:DOGEUSDT:perpetual",
    "binance-usdm:ETHUSDT:perpetual",
    "binance-usdm:SOLUSDT:perpetual",
    "binance-usdm:XRPUSDT:perpetual",
)


def test_regular_plan_freezes_current_schema_without_operator_probe_scope() -> None:
    plan = DeploymentPlan(
        target_commit=TARGET_COMMIT,
        target_release=TARGET_RELEASE,
        schema_revision=TARGET_SCHEMA_REVISION,
        expected_configured_leverage=5,
        enable_entry=False,
    )

    assert plan.schema_revision == TARGET_SCHEMA_REVISION
    assert "exchange_instrument_ids" not in plan.__dataclass_fields__


def test_regular_plan_rejects_a_schema_change() -> None:
    with pytest.raises(ValueError, match="regular deployment cannot change schema"):
        DeploymentPlan(
            target_commit=TARGET_COMMIT,
            target_release=TARGET_RELEASE,
            schema_revision=TARGET_SCHEMA_REVISION,
            source_schema_revision=SOURCE_SCHEMA_REVISION,
            expected_configured_leverage=5,
            enable_entry=False,
        )


def test_dep_002_compatible_upgrade_accepts_only_exact_source_to_current_head() -> None:
    plan = DeploymentPlan(
        target_commit=TARGET_COMMIT,
        target_release=TARGET_RELEASE,
        schema_revision=TARGET_SCHEMA_REVISION,
        source_schema_revision=SOURCE_SCHEMA_REVISION,
        mode=DeploymentMode.COMPATIBLE_UPGRADE,
        expected_configured_leverage=5,
        enable_entry=False,
        runtime_release_compatibility_fact=_compatible_fact(),
    )

    assert plan.mode is DeploymentMode.COMPATIBLE_UPGRADE
    assert plan.source_schema_revision == SOURCE_SCHEMA_REVISION

    with pytest.raises(ValueError, match="exact compatible source"):
        DeploymentPlan(
            target_commit=TARGET_COMMIT,
            target_release=TARGET_RELEASE,
            schema_revision=TARGET_SCHEMA_REVISION,
            source_schema_revision="0000_unknown",
            mode=DeploymentMode.COMPATIBLE_UPGRADE,
            expected_configured_leverage=5,
            enable_entry=False,
            runtime_release_compatibility_fact=_compatible_fact(),
        )


def test_compatible_upgrade_requires_one_exact_release_compatibility_fact() -> None:
    with pytest.raises(ValueError, match="release compatibility fact"):
        DeploymentPlan(
            target_commit=TARGET_COMMIT,
            target_release=TARGET_RELEASE,
            schema_revision=TARGET_SCHEMA_REVISION,
            source_schema_revision=SOURCE_SCHEMA_REVISION,
            mode=DeploymentMode.COMPATIBLE_UPGRADE,
            expected_configured_leverage=5,
            enable_entry=False,
        )


def test_release_compatibility_fact_must_match_the_exact_upgrade_identity() -> None:
    with pytest.raises(ValueError, match="target commit"):
        _compatible_plan(
            enable_entry=False,
            runtime_release_compatibility_fact=_compatible_fact(
                to_commit="c" * 40,
            ),
        )


def test_runtime_rematerialization_classification_fails_closed_without_release_fence() -> None:
    with pytest.raises(ValueError, match="durable release fence"):
        _compatible_plan(
            enable_entry=False,
            runtime_release_compatibility_fact=_compatible_fact(
                classification=(
                    RuntimeCompatibilityClassification.REQUIRES_RUNTIME_REMATERIALIZATION
                ),
                reason_codes=("STRATEGY_SEMANTICS_CHANGED",),
            ),
        )


def test_release_compatibility_persistence_failure_keeps_target_workers_stopped() -> None:
    backend = FakeDeploymentBackend(
        source_schema_revision=SOURCE_SCHEMA_REVISION,
        fail_at="persist_runtime_release_compatibility_fact",
    )

    with pytest.raises(RuntimeError, match="compatibility persistence"):
        deploy_tokyo_release(backend, _compatible_plan(enable_entry=False))

    assert backend.active_services == set()
    assert backend.entry_is_inactive_disabled_and_fenced()
    assert not any(call[0] == "activate_release" for call in backend.calls)


def test_unknown_release_compatibility_write_is_resolved_by_exact_read() -> None:
    backend = FakeDeploymentBackend(
        source_schema_revision=SOURCE_SCHEMA_REVISION,
        fail_at="persist_runtime_release_compatibility_fact_unknown_committed",
    )

    result = deploy_tokyo_release(backend, _compatible_plan(enable_entry=False))

    assert result.status == "pass"
    assert backend.active_services == set(SAFETY_SERVICES)
    assert sum(
        call[0] == "persist_runtime_release_compatibility_fact"
        for call in backend.calls
    ) == 1


def test_release_compatibility_postflight_requires_the_exact_persisted_fact() -> None:
    backend = FakeDeploymentBackend(
        source_schema_revision=SOURCE_SCHEMA_REVISION,
        postflight_drift="release_compatibility",
    )

    with pytest.raises(DeploymentBlocked, match="exact release compatibility"):
        deploy_tokyo_release(backend, _compatible_plan(enable_entry=False))

    assert backend.entry_is_inactive_disabled_and_fenced()


def test_dep_003_portfolio_admission_upgrade_rejects_enable_entry() -> None:
    with pytest.raises(ValueError, match="keep ENTRY disabled"):
        _compatible_plan(enable_entry=True)


def test_deployment_drain_requires_one_immutable_authorization() -> None:
    with pytest.raises(ValueError, match="authorization"):
        _compatible_plan(enable_entry=False, drain_active_tickets=True)

    with pytest.raises(ValueError, match="requires drain"):
        _compatible_plan(
            enable_entry=False,
            drain_authorization_id="deploy-20260804-01",
        )


def test_deployment_drain_rejects_entry_enablement() -> None:
    with pytest.raises(ValueError, match="keep ENTRY disabled"):
        _compatible_plan(
            enable_entry=True,
            drain_active_tickets=True,
            drain_authorization_id="deploy-20260804-01",
        )


def test_compatible_upgrade_drains_before_the_unchanged_flat_cutover() -> None:
    backend = FakeDeploymentBackend(
        source_schema_revision=SOURCE_SCHEMA_REVISION,
        active_ticket_count=1,
        drain_status="eligible",
    )

    result = deploy_tokyo_release(
        backend,
        _compatible_plan(
            enable_entry=False,
            drain_active_tickets=True,
            drain_authorization_id="deploy-20260804-01",
        ),
    )

    assert result.status == "pass"
    request_index = backend.calls.index(
        (
            "request_deployment_drain",
            CURRENT_RELEASE_SYMLINK,
            SOURCE_SCHEMA_REVISION,
            "deploy-20260804-01",
            TARGET_COMMIT,
        )
    )
    inspect_index = backend.calls.index(
        (
            "inspect_deployment_drain",
            CURRENT_RELEASE_SYMLINK,
            SOURCE_SCHEMA_REVISION,
            TARGET_COMMIT,
        )
    )
    source_certification_index = backend.calls.index(
        (
            "certify_compatible_source",
            TARGET_RELEASE,
            SOURCE_SCHEMA_REVISION,
        )
    )
    service_stop_index = backend.calls.index(("stop_services", SAFETY_SERVICES))
    assert inspect_index < request_index < source_certification_index < service_stop_index


def test_active_source_without_explicit_drain_remains_blocked() -> None:
    backend = FakeDeploymentBackend(
        source_schema_revision=SOURCE_SCHEMA_REVISION,
        active_ticket_count=1,
    )

    with pytest.raises(DeploymentBlocked, match="active Ticket"):
        deploy_tokyo_release(backend, _compatible_plan(enable_entry=False))

    assert not any(call[0] == "request_deployment_drain" for call in backend.calls)
    assert not any(call[0] == "migrate_schema" for call in backend.calls)


def test_compatible_upgrade_requires_operational_entry_gate_before_target_install() -> None:
    backend = FakeDeploymentBackend(
        source_schema_revision=SOURCE_SCHEMA_REVISION,
        entry_gate_ready=False,
    )

    with pytest.raises(DeploymentBlocked, match="inactive disabled and fenced"):
        deploy_tokyo_release(backend, _compatible_plan(enable_entry=False))

    assert not any(call[0] == "install_release" for call in backend.calls)
    assert not any(call[0] == "migrate_schema" for call in backend.calls)


def test_compatible_upgrade_cannot_reuse_active_position_handover() -> None:
    with pytest.raises(TypeError, match="protected_ticket_ids"):
        DeploymentPlan(
            target_commit=TARGET_COMMIT,
            target_release=TARGET_RELEASE,
            schema_revision=TARGET_SCHEMA_REVISION,
            source_schema_revision=SOURCE_SCHEMA_REVISION,
            mode=DeploymentMode.COMPATIBLE_UPGRADE,
            expected_configured_leverage=5,
            enable_entry=False,
            protected_ticket_ids=("ticket:btc",),
        )


def test_mig_007_compatible_upgrade_migrates_only_after_final_flat_recheck() -> None:
    backend = FakeDeploymentBackend(source_schema_revision=SOURCE_SCHEMA_REVISION)
    plan = _compatible_plan(enable_entry=False)

    result = deploy_tokyo_release(backend, plan)

    assert result.status == "pass"
    assert result.entry_enabled is False
    assert backend.calls.index(("fence_entry",)) < backend.calls.index(
        ("migrate_schema", TARGET_RELEASE, SOURCE_SCHEMA_REVISION, TARGET_SCHEMA_REVISION)
    )
    assert backend.calls.index(("stop_services", SAFETY_SERVICES)) < (
        backend.calls.index(("migration_writers_stopped_and_entry_fenced",))
    )
    assert backend.calls.index(("migration_writers_stopped_and_entry_fenced",)) < (
        backend.calls.index(
            ("migrate_schema", TARGET_RELEASE, SOURCE_SCHEMA_REVISION, TARGET_SCHEMA_REVISION)
        )
    )
    final_source_check = max(
        index
        for index, call in enumerate(backend.calls)
        if call == (
            "certify_compatible_source",
            TARGET_RELEASE,
            SOURCE_SCHEMA_REVISION,
        )
    )
    assert final_source_check < backend.calls.index(
        ("migrate_schema", TARGET_RELEASE, SOURCE_SCHEMA_REVISION, TARGET_SCHEMA_REVISION)
    )
    assert (
        "certify_r4_recovery",
        TARGET_RELEASE,
        "sha256:830ed497a82630805504e9f34ba72dcafcad9164a6fc65aa2a70ae1e3c21ec34",
    ) in backend.calls
    assert sum(call[0] == "certify_r4_recovery" for call in backend.calls) == 1
    preservation_index = backend.calls.index(
        (
            "verify_preservation",
            TARGET_RELEASE,
            SOURCE_SCHEMA_REVISION,
            PRESERVATION_DIGEST,
        )
    )
    target_postflight_index = max(
        index
        for index, call in enumerate(backend.calls)
        if call == ("certify_flat", TARGET_RELEASE)
    )
    safety_start_index = backend.calls.index(("start_services", SAFETY_SERVICES))
    persist_compatibility_index = backend.calls.index(
        ("persist_runtime_release_compatibility_fact", TARGET_RELEASE, RELEASE_COMPATIBILITY_ID)
    )
    migration_index = backend.calls.index(
        ("migrate_schema", TARGET_RELEASE, SOURCE_SCHEMA_REVISION, TARGET_SCHEMA_REVISION)
    )
    exact_postflight_index = backend.calls.index(
        ("read_runtime_release_compatibility_fact", TARGET_RELEASE, RELEASE_COMPATIBILITY_ID)
    )
    assert (
        migration_index
        < preservation_index
        < persist_compatibility_index
        < safety_start_index
        < exact_postflight_index
        < target_postflight_index
    )
    assert ("start_services", (ENTRY_SERVICE,)) not in backend.calls
    assert backend.active_services == set(SAFETY_SERVICES)
    assert backend.entry_is_inactive_disabled_and_fenced()


def test_compatible_upgrade_certifies_recovery_only_after_writer_stop() -> None:
    backend = FakeDeploymentBackend(
        source_schema_revision=SOURCE_SCHEMA_REVISION,
        source_preservation_changes_before_stop=True,
    )

    result = deploy_tokyo_release(backend, _compatible_plan(enable_entry=False))

    assert result.status == "pass"
    service_stop = backend.calls.index(("stop_services", SAFETY_SERVICES))
    certified = backend.calls.index(
        (
            "certify_r4_recovery",
            TARGET_RELEASE,
            "sha256:830ed497a82630805504e9f34ba72dcafcad9164a6fc65aa2a70ae1e3c21ec34",
        )
    )
    assert service_stop < certified


def test_compatible_upgrade_recovers_target_without_copying_a_stale_manifest() -> None:
    backend = FakeDeploymentBackend(
        source_schema_revision=TARGET_SCHEMA_REVISION,
        current_release=CURRENT_RELEASE,
        current_release_schema_marker=SOURCE_SCHEMA_REVISION,
        entry_gate_ready=True,
    )

    result = deploy_tokyo_release(backend, _compatible_plan(enable_entry=False))

    assert result.status == "pass"
    install_index = backend.calls.index(
        ("install_release", TARGET_COMMIT, TARGET_RELEASE)
    )
    certified_index = backend.calls.index(
        (
            "certify_r4_recovery",
            TARGET_RELEASE,
            "sha256:830ed497a82630805504e9f34ba72dcafcad9164a6fc65aa2a70ae1e3c21ec34",
        )
    )
    assert install_index < certified_index


def test_pre_migration_failure_restores_exact_source_safety_workers() -> None:
    backend = FakeDeploymentBackend(
        source_schema_revision=SOURCE_SCHEMA_REVISION,
        source_gate_after_stop="active_tickets",
    )

    with pytest.raises(DeploymentBlocked, match="active Ticket"):
        deploy_tokyo_release(backend, _compatible_plan(enable_entry=False))

    assert not any(call[0] == "migrate_schema" for call in backend.calls)
    assert backend.current_release == CURRENT_RELEASE
    assert backend.active_services == set(SAFETY_SERVICES)
    assert backend.entry_is_inactive_disabled_and_fenced()


def test_default_ssh_timeout_covers_bounded_preservation_scan() -> None:
    args = deployment_parser().parse_args([])

    assert args.timeout_seconds == 600.0


def test_ssh_deployment_requests_only_bounded_r4_recovery_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = SshTokyoReleaseBackend(
        target="tokyo",
        repo_root=Path("/repo"),
        timeout_seconds=600,
    )
    commands: list[tuple[str, ...]] = []

    def fake_remote(
        argv: tuple[str, ...],
        *,
        check: bool = True,
    ) -> object:
        del check
        commands.append(argv)
        return type(
            "Result",
            (),
            {
                "returncode": 0,
                "stdout": '{"status":"pass","preservation_manifest":{"digest":"sha256:'
                + "d" * 64
                + '"}}',
                "stderr": "",
            },
        )()

    monkeypatch.setattr(backend, "_remote", fake_remote)
    backend.certify_r4_recovery(
        TARGET_RELEASE,
        PRESERVATION_DIGEST,
    )

    assert "--summary-only" in commands[-1][-1]
    assert "--certify-r4-recovery" in commands[-1][-1]


@pytest.mark.parametrize(
    ("source_gate", "expected_message"),
    [
        ("active_tickets", "active Ticket"),
        ("active_reservations", "Budget Reservation"),
        ("active_domains", "Netting Domain"),
        ("unreviewed_terminal_tickets", "terminal Ticket Review"),
        ("unresolved_commands", "unresolved Exchange Command"),
        ("open_incidents", "open Incident"),
    ],
)
def test_dep_007_compatible_upgrade_source_gate_blocks_before_service_stop(
    source_gate: str,
    expected_message: str,
) -> None:
    backend = FakeDeploymentBackend(
        source_schema_revision=SOURCE_SCHEMA_REVISION,
        source_gate=source_gate,
    )

    with pytest.raises(DeploymentBlocked, match=expected_message):
        deploy_tokyo_release(backend, _compatible_plan(enable_entry=False))

    assert not any(call[0] == "stop_services" for call in backend.calls)
    assert not any(call[0] == "migrate_schema" for call in backend.calls)


def test_mig_008_preservation_mismatch_keeps_entry_fenced() -> None:
    backend = FakeDeploymentBackend(
        source_schema_revision=SOURCE_SCHEMA_REVISION,
        preservation_matches=False,
    )

    with pytest.raises(DeploymentBlocked, match="history preservation digest"):
        deploy_tokyo_release(backend, _compatible_plan(enable_entry=False))

    assert backend.entry_fenced is True
    assert not any(call == ("unfence_entry",) for call in backend.calls)
    assert not any(call == ("start_services", (ENTRY_SERVICE,)) for call in backend.calls)


def test_migration_unknown_outcome_confirmed_source_keeps_all_workers_stopped() -> None:
    """Catches treating a failed SSH result as proof that migration can be resent."""

    backend = FakeDeploymentBackend(
        source_schema_revision=SOURCE_SCHEMA_REVISION,
        fail_at="migrate_schema_unknown_source",
    )

    with pytest.raises(RuntimeError, match="simulated migration unknown outcome"):
        deploy_tokyo_release(backend, _compatible_plan(enable_entry=False))

    migration = backend.calls.index(
        ("migrate_schema", TARGET_RELEASE, SOURCE_SCHEMA_REVISION, TARGET_SCHEMA_REVISION)
    )
    recovery_inspection = backend.calls.index(
        ("inspect_schema", TARGET_RELEASE),
        migration + 1,
    )
    assert migration < recovery_inspection
    assert sum(call[0] == "migrate_schema" for call in backend.calls) == 1
    assert not any(
        call == ("start_services", SAFETY_SERVICES)
        for call in backend.calls[migration + 1 :]
    )
    assert not any(call[0] == "activate_release" for call in backend.calls)
    assert backend.active_services == set()
    assert backend.entry_is_inactive_disabled_and_fenced()


def test_migration_unknown_outcome_confirmed_target_enters_fix_forward() -> None:
    """Catches leaving a committed target stopped after an SSH outcome is unknown."""

    backend = FakeDeploymentBackend(
        source_schema_revision=SOURCE_SCHEMA_REVISION,
        fail_at="migrate_schema_unknown_target",
    )

    with pytest.raises(RuntimeError, match="simulated migration unknown outcome"):
        deploy_tokyo_release(backend, _compatible_plan(enable_entry=False))

    migration = backend.calls.index(
        ("migrate_schema", TARGET_RELEASE, SOURCE_SCHEMA_REVISION, TARGET_SCHEMA_REVISION)
    )
    recovery_inspection = backend.calls.index(
        ("inspect_schema", TARGET_RELEASE),
        migration + 1,
    )
    recovery_activation = backend.calls.index(
        (
            "activate_release",
            TARGET_RELEASE,
            TARGET_COMMIT,
            TARGET_SCHEMA_REVISION,
            SEED_IDENTITY,
        ),
        recovery_inspection + 1,
    )
    recovery_start = backend.calls.index(
        ("start_services", SAFETY_SERVICES),
        recovery_activation + 1,
    )
    assert migration < recovery_inspection < recovery_activation < recovery_start
    assert sum(call[0] == "migrate_schema" for call in backend.calls) == 1
    assert backend.current_release == TARGET_RELEASE
    assert backend.active_services == set(SAFETY_SERVICES)
    assert backend.entry_is_inactive_disabled_and_fenced()


def test_target_schema_fix_forward_recertifies_without_a_stale_manifest() -> None:
    """Catches rebuilding a source manifest after the target schema committed."""

    backend = FakeDeploymentBackend(
        source_schema_revision=TARGET_SCHEMA_REVISION,
        current_release=RECOVERY_RELEASE,
        current_release_schema_marker=SOURCE_SCHEMA_REVISION,
        entry_gate_ready=True,
    )

    result = deploy_tokyo_release(backend, _compatible_plan(enable_entry=False))

    assert result.status == "pass"
    assert any(call[0] == "certify_r4_recovery" for call in backend.calls)
    assert not any(call[0] == "verify_preservation" for call in backend.calls)


def test_target_schema_recovery_rejects_wrong_operator_source_commit() -> None:
    backend = FakeDeploymentBackend(
        source_schema_revision=TARGET_SCHEMA_REVISION,
        current_release=RECOVERY_RELEASE,
        current_release_schema_marker=SOURCE_SCHEMA_REVISION,
        entry_gate_ready=True,
    )
    plan = _compatible_plan(
        enable_entry=False,
        runtime_release_compatibility_fact=_compatible_fact(
            from_commit="c" * 40,
        ),
    )

    with pytest.raises(
        DeploymentBlocked,
        match="release compatibility source commit differs from current release",
    ):
        deploy_tokyo_release(backend, plan)

    assert not any(call[0] == "stop_services" for call in backend.calls)
    assert not any(
        call[0] == "persist_runtime_release_compatibility_fact"
        for call in backend.calls
    )


def test_target_schema_active_target_without_compatibility_fact_fails_closed() -> None:
    backend = FakeDeploymentBackend(
        source_schema_revision=TARGET_SCHEMA_REVISION,
        current_release=TARGET_RELEASE,
        target_release_exists=True,
        entry_gate_ready=True,
    )
    backend.runtime_commit = TARGET_COMMIT

    with pytest.raises(
        DeploymentBlocked,
        match="active target release lacks exact release compatibility fact",
    ):
        deploy_tokyo_release(backend, _compatible_plan(enable_entry=False))

    assert not any(call[0] == "stop_services" for call in backend.calls)
    assert not any(
        call[0] == "persist_runtime_release_compatibility_fact"
        for call in backend.calls
    )


def test_migration_unknown_outcome_remains_primary_when_target_recovery_activation_fails(
) -> None:
    """Catches a target activation error replacing the migration outcome."""

    backend = FakeDeploymentBackend(
        source_schema_revision=SOURCE_SCHEMA_REVISION,
        fail_at="migrate_schema_unknown_target_recovery_activation_failure",
    )

    with pytest.raises(RuntimeError) as exc_info:
        deploy_tokyo_release(backend, _compatible_plan(enable_entry=False))

    assert exc_info.value is backend.migration_unknown_outcome_error
    assert str(exc_info.value) == "simulated migration unknown outcome"
    assert exc_info.value.__cause__ is backend.target_recovery_error
    assert str(exc_info.value.__cause__) == "simulated target recovery failure"
    assert sum(call[0] == "migrate_schema" for call in backend.calls) == 1
    assert not any(call[0] == "start_services" for call in backend.calls)
    assert backend.current_release == CURRENT_RELEASE
    assert backend.active_services == set()
    assert backend.entry_is_inactive_disabled_and_fenced()


def test_migration_unknown_outcome_remains_primary_when_target_recovery_start_fails(
) -> None:
    """Catches a target safety start error replacing the migration outcome."""

    backend = FakeDeploymentBackend(
        source_schema_revision=SOURCE_SCHEMA_REVISION,
        fail_at="migrate_schema_unknown_target_recovery_start_failure",
    )

    with pytest.raises(RuntimeError) as exc_info:
        deploy_tokyo_release(backend, _compatible_plan(enable_entry=False))

    assert exc_info.value is backend.migration_unknown_outcome_error
    assert str(exc_info.value) == "simulated migration unknown outcome"
    assert exc_info.value.__cause__ is backend.target_recovery_error
    assert str(exc_info.value.__cause__) == "simulated target recovery failure"
    assert sum(call[0] == "migrate_schema" for call in backend.calls) == 1
    assert not any(
        call == ("start_services", (ENTRY_SERVICE,)) for call in backend.calls
    )
    assert backend.current_release == TARGET_RELEASE
    assert backend.active_services == set()
    assert backend.entry_is_inactive_disabled_and_fenced()


def test_migration_unknown_outcome_unconfirmed_keeps_all_workers_stopped() -> None:
    """Catches guessing a migration result from a failed schema inspection."""

    backend = FakeDeploymentBackend(
        source_schema_revision=SOURCE_SCHEMA_REVISION,
        fail_at="migrate_schema_unknown_revision",
    )

    with pytest.raises(RuntimeError, match="simulated migration unknown outcome"):
        deploy_tokyo_release(backend, _compatible_plan(enable_entry=False))

    migration = backend.calls.index(
        ("migrate_schema", TARGET_RELEASE, SOURCE_SCHEMA_REVISION, TARGET_SCHEMA_REVISION)
    )
    recovery_inspection = backend.calls.index(
        ("inspect_schema", TARGET_RELEASE),
        migration + 1,
    )
    assert migration < recovery_inspection
    assert sum(call[0] == "migrate_schema" for call in backend.calls) == 1
    assert not any(call[0] == "activate_release" for call in backend.calls)
    assert not any(call[0] == "start_services" for call in backend.calls)
    assert backend.active_services == set()
    assert backend.entry_is_inactive_disabled_and_fenced()


def test_migration_inspection_failure_preserves_original_unknown_outcome() -> None:
    """Catches replacing the migration outcome with a secondary inspect error."""

    backend = FakeDeploymentBackend(
        source_schema_revision=SOURCE_SCHEMA_REVISION,
        fail_at="migrate_schema_inspection_failure",
    )

    with pytest.raises(
        RuntimeError,
        match="simulated migration unknown outcome",
    ) as exc_info:
        deploy_tokyo_release(backend, _compatible_plan(enable_entry=False))

    migration = backend.calls.index(
        ("migrate_schema", TARGET_RELEASE, SOURCE_SCHEMA_REVISION, TARGET_SCHEMA_REVISION)
    )
    recovery_inspection = backend.calls.index(
        ("inspect_schema", TARGET_RELEASE),
        migration + 1,
    )
    assert migration < recovery_inspection
    assert sum(call[0] == "migrate_schema" for call in backend.calls) == 1
    assert not any(call[0] == "activate_release" for call in backend.calls)
    assert not any(call[0] == "start_services" for call in backend.calls)
    assert backend.active_services == set()
    assert backend.entry_is_inactive_disabled_and_fenced()
    assert isinstance(exc_info.value.__cause__, RuntimeError)
    assert str(exc_info.value.__cause__) == "simulated schema inspection failure"


def test_post_migration_recovery_certification_failure_enters_fenced_target_fix_forward() -> None:
    """Catches leaving the target without safety or restarting source workers."""

    backend = FakeDeploymentBackend(
        source_schema_revision=SOURCE_SCHEMA_REVISION,
        fail_at="certify_r4_recovery",
    )

    with pytest.raises(RuntimeError, match="simulated R4 recovery certification failure"):
        deploy_tokyo_release(backend, _compatible_plan(enable_entry=False))

    migration = backend.calls.index(
        ("migrate_schema", TARGET_RELEASE, SOURCE_SCHEMA_REVISION, TARGET_SCHEMA_REVISION)
    )
    recovery_activation = max(
        index
        for index, call in enumerate(backend.calls)
        if call
        == (
            "activate_release",
            TARGET_RELEASE,
            TARGET_COMMIT,
            TARGET_SCHEMA_REVISION,
            SEED_IDENTITY,
        )
    )
    recovery_start = max(
        index
        for index, call in enumerate(backend.calls)
        if call == ("start_services", SAFETY_SERVICES)
    )
    assert migration < recovery_activation < recovery_start
    assert backend.current_release == TARGET_RELEASE
    assert backend.active_services == set(SAFETY_SERVICES)
    assert backend.entry_is_inactive_disabled_and_fenced()


def test_partial_target_activation_failure_recovers_target_safety_workers() -> None:
    """Catches trusting a flag when activation changed the symlink before failing."""

    backend = FakeDeploymentBackend(
        source_schema_revision=SOURCE_SCHEMA_REVISION,
        fail_at="activate_release_partial",
    )

    with pytest.raises(RuntimeError, match="simulated partial activation failure"):
        deploy_tokyo_release(backend, _compatible_plan(enable_entry=False))

    activation = backend.calls.index(
        (
            "activate_release",
            TARGET_RELEASE,
            TARGET_COMMIT,
            TARGET_SCHEMA_REVISION,
            SEED_IDENTITY,
        )
    )
    recovery_start = max(
        index
        for index, call in enumerate(backend.calls)
        if call == ("start_services", SAFETY_SERVICES)
    )
    assert activation < recovery_start
    assert backend.current_release == TARGET_RELEASE
    assert backend.active_services == set(SAFETY_SERVICES)
    assert backend.entry_is_inactive_disabled_and_fenced()


def test_mig_009_wrong_source_blocks_before_service_mutation() -> None:
    backend = FakeDeploymentBackend(
        source_schema_revision="0001_trading_kernel_baseline_v4",
        entry_gate_ready=True,
    )

    with pytest.raises(DeploymentBlocked, match="source schema revision"):
        deploy_tokyo_release(backend, _compatible_plan(enable_entry=False))

    assert not any(call[0] in {"fence_entry", "stop_services"} for call in backend.calls)
    assert not any(call[0] == "migrate_schema" for call in backend.calls)


@pytest.mark.parametrize(
    ("source_authority_drift", "source_seed_marker", "expected_message"),
    [
        ("registry", SEED_IDENTITY, "source Registry"),
        ("policy", SEED_IDENTITY, "source Owner Policy"),
        (None, "sha256:" + "0" * 64, "source Seed marker"),
    ],
)
def test_compatible_source_authority_drift_blocks_before_entry_fence(
    source_authority_drift: str | None,
    source_seed_marker: str,
    expected_message: str,
) -> None:
    """Catches mutating services before exact certified source authority is proven."""

    backend = FakeDeploymentBackend(
        source_schema_revision=SOURCE_SCHEMA_REVISION,
        source_authority_drift=source_authority_drift,
        source_seed_marker=source_seed_marker,
    )

    with pytest.raises(DeploymentBlocked, match=expected_message):
        deploy_tokyo_release(backend, _compatible_plan(enable_entry=False))

    assert not any(
        call[0] in {"fence_entry", "stop_services"} for call in backend.calls
    )
    assert not any(call[0] == "migrate_schema" for call in backend.calls)


def test_migration_requires_four_stopped_writers_disabled_entry_and_fence() -> None:
    backend = FakeDeploymentBackend(
        source_schema_revision=SOURCE_SCHEMA_REVISION,
        migration_stop_prerequisite=False,
    )

    with pytest.raises(DeploymentBlocked, match="migration writer stop prerequisite"):
        deploy_tokyo_release(backend, _compatible_plan(enable_entry=False))

    assert ("fence_entry",) in backend.calls
    assert ("stop_services", SAFETY_SERVICES) in backend.calls
    assert not any(call[0] == "migrate_schema" for call in backend.calls)


def test_dep_004_missing_target_safety_worker_fails_with_entry_fenced() -> None:
    backend = FakeDeploymentBackend(
        source_schema_revision=SOURCE_SCHEMA_REVISION,
        omitted_safety_service=SAFETY_SERVICES[-1],
    )

    with pytest.raises(DeploymentBlocked, match="safety services"):
        deploy_tokyo_release(backend, _compatible_plan(enable_entry=False))

    assert backend.entry_fenced is True
    assert ENTRY_SERVICE not in backend.active_services


@pytest.mark.parametrize(
    ("postflight_drift", "expected_message"),
    [
        ("policy", "Owner Policy"),
        ("registry", "Registry identity"),
        ("universe", "Universe identity"),
        ("universe_digest", "Universe identity"),
        ("schema", "schema revision"),
        ("seed", "Seed identity"),
        ("dynamic_runtime", "unexpected Dynamic Selection runtime facts"),
        ("exit_profile_authority", "ExitProfile/Binding manifest"),
    ],
)
def test_dep_005_exact_target_identity_drift_blocks_postflight(
    postflight_drift: str,
    expected_message: str,
) -> None:
    backend = FakeDeploymentBackend(
        source_schema_revision=SOURCE_SCHEMA_REVISION,
        postflight_drift=postflight_drift,
    )

    with pytest.raises(DeploymentBlocked, match=expected_message):
        deploy_tokyo_release(backend, _compatible_plan(enable_entry=False))

    assert backend.entry_fenced is True
    assert ENTRY_SERVICE not in backend.active_services


def test_dep_006_pending_shadow_does_not_authorize_entry() -> None:
    backend = FakeDeploymentBackend(
        source_schema_revision=SOURCE_SCHEMA_REVISION,
        shadow_pending_count=3,
    )

    result = deploy_tokyo_release(backend, _compatible_plan(enable_entry=False))

    assert result.status == "pass"
    assert backend.active_services == set(SAFETY_SERVICES)
    assert backend.entry_is_inactive_disabled_and_fenced()


def test_compatible_upgrade_resumes_target_fix_forward_idempotently() -> None:
    backend = FakeDeploymentBackend(
        source_schema_revision=TARGET_SCHEMA_REVISION,
        current_release=CURRENT_RELEASE,
        current_release_schema_marker=SOURCE_SCHEMA_REVISION,
        preservation_verified=True,
        target_release_exists=True,
    )
    backend.runtime_commit = TARGET_COMMIT
    backend.active_services = {SAFETY_SERVICES[0]}
    backend.entry_fenced = True
    backend.entry_enabled = False

    result = deploy_tokyo_release(backend, _compatible_plan(enable_entry=False))

    assert result.status == "pass"
    assert not any(call[0] == "install_release" for call in backend.calls)
    assert not any(call[0] == "migrate_schema" for call in backend.calls)
    assert not any(call[0] == "recover_preservation_proof" for call in backend.calls)
    assert not any(call[0] == "verify_preservation" for call in backend.calls)
    assert backend.active_services == set(SAFETY_SERVICES)
    assert backend.entry_is_inactive_disabled_and_fenced()


def test_resume_recertifies_the_database_instead_of_trusting_a_file_marker() -> None:
    """Catches reusing a release-local proof marker against a restored database."""

    backend = FakeDeploymentBackend(
        source_schema_revision=TARGET_SCHEMA_REVISION,
        current_release=TARGET_RELEASE,
        preservation_verified=True,
        preservation_database_proof_matches=False,
        target_release_exists=True,
    )
    backend.runtime_commit = TARGET_COMMIT
    backend.runtime_release_compatibility_fact = _compatible_fact()
    backend.active_services = set(SAFETY_SERVICES)
    backend.entry_fenced = True
    backend.entry_enabled = False

    result = deploy_tokyo_release(backend, _compatible_plan(enable_entry=False))

    assert result.status == "pass"
    assert any(call[0] == "certify_r4_recovery" for call in backend.calls)


def test_regular_release_uses_database_derived_probe_manifest() -> None:
    backend = FakeDeploymentBackend()
    plan = DeploymentPlan(
        target_commit=TARGET_COMMIT,
        target_release=TARGET_RELEASE,
        schema_revision=TARGET_SCHEMA_REVISION,
        expected_configured_leverage=5,
        enable_entry=False,
    )

    deploy_tokyo_release(backend, plan)

    assert [call for call in backend.calls if call[0] == "probe_exchange"] == [
        ("probe_exchange", TARGET_RELEASE),
        ("probe_exchange", TARGET_RELEASE),
    ]


def test_fenced_regular_release_resumes_target_postflight_without_reinstall() -> None:
    """Catches abandoning a target release after identity rotation postflight."""

    backend = FakeDeploymentBackend(
        current_release=TARGET_RELEASE,
        target_release_exists=True,
        entry_gate_ready=True,
    )
    backend.runtime_commit = TARGET_COMMIT

    result = deploy_tokyo_release(backend, _plan(enable_entry=False))

    assert result.status == "pass"
    assert result.entry_enabled is False
    assert not any(call[0] == "install_release" for call in backend.calls)
    assert not any(call[0] == "deploy_identity" for call in backend.calls)
    assert not any(call[0] == "activate_release" for call in backend.calls)
    assert ("refresh_active_certification_batch", TARGET_RELEASE) in backend.calls
    assert backend.entry_fenced is True
    assert backend.active_services == set(SAFETY_SERVICES)


def test_regular_release_refreshes_target_batch_before_postflight() -> None:
    """Catches checking a target commit before its release-bound Batch exists."""

    backend = FakeDeploymentBackend(expired_certification_batch=True)

    result = deploy_tokyo_release(backend, _plan(enable_entry=False))

    assert result.status == "pass"
    identity = backend.calls.index(
        (
            "activate_release",
            TARGET_RELEASE,
            TARGET_COMMIT,
            TARGET_SCHEMA_REVISION,
            SEED_IDENTITY,
        )
    )
    safety = backend.calls.index(("start_services", SAFETY_SERVICES))
    refresh = backend.calls.index(
        ("refresh_active_certification_batch", TARGET_RELEASE)
    )
    postflight = max(
        index
        for index, call in enumerate(backend.calls)
        if call == ("certify_flat", TARGET_RELEASE)
    )
    assert identity < safety < refresh < postflight


def test_fenced_regular_release_accepts_an_expired_promotion_batch() -> None:
    """Catches coupling an Entry-fenced code deploy to a short-lived Batch."""

    backend = FakeDeploymentBackend(expired_certification_batch=True)

    result = deploy_tokyo_release(backend, _plan(enable_entry=False))

    assert result.status == "pass"
    assert result.entry_enabled is False
    assert ("start_services", (ENTRY_SERVICE,)) not in backend.calls
    assert backend.entry_fenced is True
    assert backend.active_services == set(SAFETY_SERVICES)


def test_entry_enabling_regular_release_still_requires_a_fresh_batch() -> None:
    """Catches weakening the fresh Batch gate when deployment enables Entry."""

    backend = FakeDeploymentBackend(expired_certification_batch=True)

    with pytest.raises(DeploymentBlocked, match="StrategyUniverse bootstrap"):
        deploy_tokyo_release(backend, _plan(enable_entry=True))

    assert not any(call[0] == "stop_services" for call in backend.calls)


def test_fenced_regular_release_requires_compatible_batch_identity() -> None:
    """Catches accepting an expired Batch whose immutable identity differs."""

    backend = FakeDeploymentBackend(
        expired_certification_batch=True,
        certification_gate_failure=(1, "compatible_certification_batch_pass"),
    )

    with pytest.raises(DeploymentBlocked, match="compatible Certification Batch"):
        deploy_tokyo_release(backend, _plan(enable_entry=False))

    assert not any(call[0] == "stop_services" for call in backend.calls)


def test_fenced_regular_release_accepts_current_entry_authority_from_completed_batch() -> None:
    """The external Fence, not a historical Policy bit, owns source safety.

    A regular release starts from the already disabled-and-fenced source
    Worker.  That source may legitimately retain its Owner-approved ENTRY
    Policy until the target identity atomically installs its paused posture.
    Its fresh *completed* Certification Batch remains the authority for the
    source preflight; the target still has to pass the stricter compatible
    Batch postflight before it can be promoted.
    """

    backend = FakeDeploymentBackend(
        source_entry_authority_armed=True,
        target_entry_authority_retained=True,
        entry_gate_ready=True,
    )

    result = deploy_tokyo_release(backend, _plan(enable_entry=False))

    assert result.status == "pass"
    assert backend.entry_fenced is True
    source_refresh = backend.calls.index(
        ("refresh_active_certification_batch", CURRENT_RELEASE)
    )
    source_stop = backend.calls.index(("stop_services", ALL_SERVICES))
    target_refresh = backend.calls.index(
        ("refresh_active_certification_batch", TARGET_RELEASE)
    )
    assert source_refresh < source_stop < target_refresh


def test_fenced_regular_release_requires_exact_active_universes() -> None:
    """Catches using compatible Batch history with a drifted current manifest."""

    backend = FakeDeploymentBackend(
        expired_certification_batch=True,
        active_universe_count=5,
    )

    with pytest.raises(DeploymentBlocked, match="Active StrategyUniverse"):
        deploy_tokyo_release(backend, _plan(enable_entry=False))

    assert not any(call[0] == "stop_services" for call in backend.calls)


@pytest.mark.parametrize(
    ("certification_gate", "expected_message"),
    [
        ("universe_bootstrap_pass", "StrategyUniverse bootstrap"),
        ("certification_batch_pass", "Certification Batch"),
        ("flatness_pass", "database flatness gate"),
    ],
)
def test_release_certification_requires_every_entry_promotion_fact_before_stop(
    certification_gate: str,
    expected_message: str,
) -> None:
    backend = FakeDeploymentBackend(
        certification_gate_failure=(1, certification_gate),
    )

    with pytest.raises(DeploymentBlocked, match=expected_message):
        deploy_tokyo_release(backend, _plan(enable_entry=True))

    assert not any(call[0] == "stop_services" for call in backend.calls)
    assert not any(call == ("start_services", (ENTRY_SERVICE,)) for call in backend.calls)


def test_final_database_postflight_failure_restores_fence_and_stops_entry() -> None:
    backend = FakeDeploymentBackend(
        certification_gate_failure=(3, "flatness_pass"),
    )

    with pytest.raises(DeploymentBlocked, match="database flatness gate"):
        deploy_tokyo_release(backend, _plan(enable_entry=True))

    entry_start = backend.calls.index(("start_services", (ENTRY_SERVICE,)))
    final_certification = max(
        index
        for index, call in enumerate(backend.calls)
        if call == ("certify_flat", TARGET_RELEASE)
    )
    recovery_fence = max(
        index for index, call in enumerate(backend.calls) if call == ("fence_entry",)
    )
    assert entry_start < final_certification < recovery_fence
    assert ("unfence_entry",) not in backend.calls
    assert backend.entry_fenced is True
    assert backend.active_services == set(SAFETY_SERVICES)


def test_final_exchange_postflight_failure_restores_fence_and_stops_entry() -> None:
    backend = FakeDeploymentBackend(probe_non_flat_failure_call=3)

    with pytest.raises(DeploymentBlocked, match="exchange position is not flat"):
        deploy_tokyo_release(backend, _plan(enable_entry=True))

    entry_start = backend.calls.index(("start_services", (ENTRY_SERVICE,)))
    final_probe = max(
        index
        for index, call in enumerate(backend.calls)
        if call == ("probe_exchange", TARGET_RELEASE)
    )
    recovery_fence = max(
        index for index, call in enumerate(backend.calls) if call == ("fence_entry",)
    )
    assert entry_start < final_probe < recovery_fence
    assert ("unfence_entry",) not in backend.calls
    assert backend.entry_fenced is True
    assert backend.active_services == set(SAFETY_SERVICES)


def test_ssh_probe_exchange_has_no_operator_instrument_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = SshTokyoReleaseBackend(
        target="tokyo",
        repo_root=Path("."),
        timeout_seconds=30,
    )
    calls: list[tuple[object, ...]] = []

    def release_json(
        release: str,
        script: str,
        *args: str,
    ) -> Mapping[str, object]:
        calls.append((release, script, *args))
        return {}

    monkeypatch.setattr(backend, "_release_json", release_json)

    backend.probe_exchange(TARGET_RELEASE)

    assert calls == [(TARGET_RELEASE, "scripts/trading_kernel/probe_production_runtime.py")]


def test_compatible_upgrade_verifies_0005_preservation_without_bootstrap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = SshTokyoReleaseBackend(
        target="tokyo",
        repo_root=Path("."),
        timeout_seconds=30,
    )
    calls: list[tuple[object, ...]] = []

    def release_json(release: str, *args: str, **_kwargs: object) -> Mapping[str, object]:
        calls.append((release, *args))
        return {"status": "pass"}

    monkeypatch.setattr(backend, "_release_json", release_json)

    backend.verify_preservation(
        TARGET_RELEASE,
        SOURCE_SCHEMA_REVISION,
        PRESERVATION_DIGEST,
    )

    assert calls == [
        (
            TARGET_RELEASE,
            "scripts/trading_kernel/verify_schema.py",
            "--preserve-source-revision",
            SOURCE_SCHEMA_REVISION,
            "--expected-preservation-digest",
            PRESERVATION_DIGEST,
            "--summary-only",
        ),
    ]


def test_ssh_release_compatibility_backend_uses_the_formal_kernel_cli(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = SshTokyoReleaseBackend(
        target="tokyo",
        repo_root=Path("/repo"),
        timeout_seconds=60,
    )
    fact = _compatible_fact()
    calls: list[tuple[object, ...]] = []

    def release_json(
        release: str,
        script: str,
        *args: str,
        **_kwargs: object,
    ) -> Mapping[str, object]:
        calls.append((release, script, *args))
        return {"status": "pass", "created": True, "fact": fact.model_dump(mode="json")}

    monkeypatch.setattr(backend, "_release_json", release_json)

    backend.persist_runtime_release_compatibility_fact(TARGET_RELEASE, fact)
    assert (
        backend.read_runtime_release_compatibility_fact(
            TARGET_RELEASE,
            fact.release_compatibility_id,
        )
        == fact
    )

    assert calls[0][:3] == (
        TARGET_RELEASE,
        "scripts/trading_kernel/persist_runtime_release_fact.py",
        "write",
    )
    assert "--certification-manifest-digest" in calls[0]
    assert calls[1] == (
        TARGET_RELEASE,
        "scripts/trading_kernel/persist_runtime_release_fact.py",
        "read",
        "--release-compatibility-id",
        fact.release_compatibility_id,
    )

    deployment_backend = FakeDeploymentBackend(
        source_schema_revision=SOURCE_SCHEMA_REVISION,
        universe_stage="active",
        active_universe_count=8,
        warming_universe_count=0,
    )

    result = deploy_tokyo_release(
        deployment_backend,
        _compatible_plan(enable_entry=False),
    )

    assert result.status == "pass"
    safety_start = deployment_backend.calls.index(
        ("start_services", SAFETY_SERVICES)
    )
    postflight = max(
        index
        for index, call in enumerate(deployment_backend.calls)
        if call == ("certify_flat", TARGET_RELEASE)
    )
    assert safety_start < postflight
    assert not any(
        call[0] == "bootstrap_strategy_universes"
        for call in deployment_backend.calls
    )


def test_compatible_restart_deployment_does_not_wait_for_universe_warming() -> None:
    backend = FakeDeploymentBackend(
        source_schema_revision=SOURCE_SCHEMA_REVISION,
        universe_stage="active",
        active_universe_count=8,
        warming_universe_count=1,
    )

    result = deploy_tokyo_release(
        backend,
        _compatible_plan(enable_entry=False),
    )

    assert result.status == "pass"
    assert not any(
        call[0] == "bootstrap_strategy_universes" for call in backend.calls
    )


def test_regular_release_runs_one_bounded_flow_and_enables_entry_last() -> None:
    backend = FakeDeploymentBackend()

    result = deploy_tokyo_release(backend, _plan(enable_entry=True))

    assert result.status == "pass"
    assert result.target_commit == TARGET_COMMIT
    assert result.entry_enabled is True
    assert backend.calls == [
        ("read_current_release",),
        ("entry_is_inactive_disabled_and_fenced",),
        ("install_release", TARGET_COMMIT, TARGET_RELEASE),
        ("certify_flat", TARGET_RELEASE),
        ("probe_exchange", TARGET_RELEASE),
        ("read_release_marker", CURRENT_RELEASE, ".brc-runtime-commit"),
        ("read_release_marker", CURRENT_RELEASE, ".brc-schema-revision"),
        ("stop_services", ALL_SERVICES),
        ("fence_entry",),
        ("services_active", ALL_SERVICES),
        (
            "deploy_identity",
            TARGET_RELEASE,
            TARGET_COMMIT,
            TARGET_SCHEMA_REVISION,
        ),
        (
            "activate_release",
            TARGET_RELEASE,
            TARGET_COMMIT,
            TARGET_SCHEMA_REVISION,
            SEED_IDENTITY,
        ),
        ("read_current_release",),
        ("read_release_marker", TARGET_RELEASE, ".brc-runtime-commit"),
        ("read_release_marker", TARGET_RELEASE, ".brc-schema-revision"),
        ("read_release_marker", TARGET_RELEASE, ".brc-seed-identity"),
        ("start_services", SAFETY_SERVICES),
        ("refresh_active_certification_batch", TARGET_RELEASE),
        ("certify_flat", TARGET_RELEASE),
        ("probe_exchange", TARGET_RELEASE),
        ("start_services", (ENTRY_SERVICE,)),
        ("services_active", ALL_SERVICES),
        ("certify_flat", TARGET_RELEASE),
        ("probe_exchange", TARGET_RELEASE),
        ("unfence_entry",),
        ("services_active", ALL_SERVICES),
    ]


def test_preflight_leverage_drift_blocks_before_any_service_stop() -> None:
    backend = FakeDeploymentBackend(configured_leverage=3)

    with pytest.raises(DeploymentBlocked, match="configured leverage"):
        deploy_tokyo_release(backend, _plan(enable_entry=True))

    assert not any(call[0] == "stop_services" for call in backend.calls)
    assert not any(call[0] == "deploy_identity" for call in backend.calls)
    assert not any(call[0] == "activate_release" for call in backend.calls)


def test_database_derived_probe_rejects_rule_scope_that_differs_from_postgresql() -> None:
    backend = FakeDeploymentBackend(
        rule_instrument_ids=(
            *TARGET_EXCHANGE_INSTRUMENT_IDS[:-1],
            "binance-usdm:AVAXUSDT:perpetual",
        )
    )

    with pytest.raises(DeploymentBlocked, match="rule identity"):
        deploy_tokyo_release(backend, _plan(enable_entry=False))


def test_identity_rotated_activation_failure_keeps_all_workers_stopped() -> None:
    """Catches restarting an old worker after PostgreSQL identity has changed."""

    backend = FakeDeploymentBackend(fail_at="activate_release")

    with pytest.raises(RuntimeError, match="simulated activation failure"):
        deploy_tokyo_release(backend, _plan(enable_entry=True))

    assert ("fence_entry",) in backend.calls
    assert backend.calls[-1] == ("fence_entry",)
    assert ("start_services", SAFETY_SERVICES) not in backend.calls
    assert ("start_services", (ENTRY_SERVICE,)) not in backend.calls


def test_closure_only_release_requires_one_exact_ticket_and_keeps_entry_fenced() -> None:
    plan = _plan(
        enable_entry=False,
        closure_ticket_id="ticket:btc-settlement",
    )

    assert plan.closure_ticket_id == "ticket:btc-settlement"
    with pytest.raises(ValueError, match="closure-only"):
        _plan(
            enable_entry=True,
            closure_ticket_id="ticket:btc-settlement",
        )


def test_closure_only_release_recovers_only_the_exact_pending_ticket() -> None:
    ticket_id = "ticket:btc-settlement"
    backend = FakeDeploymentBackend(closure_ticket_id=ticket_id)

    result = deploy_tokyo_release(
        backend,
        _plan(enable_entry=False, closure_ticket_id=ticket_id),
    )

    assert result.status == "pass"
    assert result.entry_enabled is False
    assert backend.calls == [
        ("read_current_release",),
        ("entry_is_inactive_disabled_and_fenced",),
        ("install_release", TARGET_COMMIT, TARGET_RELEASE),
        ("certify_closure", TARGET_RELEASE, ticket_id),
        ("probe_exchange", TARGET_RELEASE),
        ("read_release_marker", CURRENT_RELEASE, ".brc-runtime-commit"),
        ("read_release_marker", CURRENT_RELEASE, ".brc-schema-revision"),
        ("stop_services", ALL_SERVICES),
        ("fence_entry",),
        ("services_active", ALL_SERVICES),
        ("certify_closure", TARGET_RELEASE, ticket_id),
        ("probe_exchange", TARGET_RELEASE),
        (
            "deploy_closure_identity",
            TARGET_RELEASE,
            TARGET_COMMIT,
            TARGET_SCHEMA_REVISION,
            ticket_id,
        ),
        (
            "activate_release",
            TARGET_RELEASE,
            TARGET_COMMIT,
            TARGET_SCHEMA_REVISION,
            SEED_IDENTITY,
        ),
        ("read_current_release",),
        ("read_release_marker", TARGET_RELEASE, ".brc-runtime-commit"),
        ("read_release_marker", TARGET_RELEASE, ".brc-schema-revision"),
        ("read_release_marker", TARGET_RELEASE, ".brc-seed-identity"),
        ("start_services", SAFETY_SERVICES),
        ("certify_closure", TARGET_RELEASE, ticket_id),
        ("probe_exchange", TARGET_RELEASE),
        ("entry_is_inactive_disabled_and_fenced",),
        ("services_active", ALL_SERVICES),
    ]


def _plan(
    *,
    enable_entry: bool,
    closure_ticket_id: str | None = None,
) -> DeploymentPlan:
    return DeploymentPlan(
        target_commit=TARGET_COMMIT,
        target_release=TARGET_RELEASE,
        schema_revision=TARGET_SCHEMA_REVISION,
        expected_configured_leverage=5,
        enable_entry=enable_entry,
        closure_ticket_id=closure_ticket_id,
    )


def _compatible_plan(
    *,
    enable_entry: bool,
    drain_active_tickets: bool = False,
    drain_authorization_id: str | None = None,
    runtime_release_compatibility_fact: RuntimeReleaseCompatibilityFact | None = None,
) -> DeploymentPlan:
    return DeploymentPlan(
        target_commit=TARGET_COMMIT,
        target_release=TARGET_RELEASE,
        schema_revision=TARGET_SCHEMA_REVISION,
        source_schema_revision=SOURCE_SCHEMA_REVISION,
        mode=DeploymentMode.COMPATIBLE_UPGRADE,
        expected_configured_leverage=5,
        enable_entry=enable_entry,
        drain_active_tickets=drain_active_tickets,
        drain_authorization_id=drain_authorization_id,
        runtime_release_compatibility_fact=(
            _compatible_fact()
            if runtime_release_compatibility_fact is None
            else runtime_release_compatibility_fact
        ),
    )


def _compatible_fact(
    *,
    from_commit: str = CURRENT_COMMIT,
    to_commit: str = TARGET_COMMIT,
    classification: RuntimeCompatibilityClassification = (
        RuntimeCompatibilityClassification.COMPATIBLE_RESTART
    ),
    reason_codes: tuple[str, ...] = (
        "PERSISTED_ACTIVE_UNIVERSE_CONTRACT_UNCHANGED",
    ),
) -> RuntimeReleaseCompatibilityFact:
    return RuntimeReleaseCompatibilityFact(
        release_compatibility_id=f"release-compatibility:{from_commit}:{to_commit}",
        from_commit=from_commit,
        to_commit=to_commit,
        from_schema_revision=SOURCE_SCHEMA_REVISION,
        to_schema_revision=TARGET_SCHEMA_REVISION,
        classification=classification,
        compatibility_basis_digest="sha256:" + "8" * 64,
        reason_codes=reason_codes,
        certification_manifest_digest="sha256:" + "9" * 64,
        created_at_ms=1_775_000_000_000,
    )


class FakeDeploymentBackend:
    def __init__(
        self,
        *,
        configured_leverage: int = 5,
        active_ticket_count: int = 0,
        closure_ticket_id: str | None = None,
        open_order_domain_count: int | None = None,
        rule_instrument_ids: tuple[str, ...] = TARGET_EXCHANGE_INSTRUMENT_IDS,
        probe_manifest: tuple[str, ...] = TARGET_EXCHANGE_INSTRUMENT_IDS,
        source_schema_revision: str = TARGET_SCHEMA_REVISION,
        source_gate: str | None = None,
        source_authority_drift: str | None = None,
        source_seed_marker: str = SEED_IDENTITY,
        current_release_schema_marker: str | None = None,
        source_preservation_changes_before_stop: bool = False,
        source_gate_after_stop: str | None = None,
        preservation_matches: bool = True,
        preservation_verified: bool = False,
        preservation_database_proof_matches: bool = True,
        migration_stop_prerequisite: bool = True,
        omitted_safety_service: str | None = None,
        postflight_drift: str | None = None,
        shadow_pending_count: int = 0,
        universe_stage: str = "active",
        active_universe_count: int = 8,
        warming_universe_count: int = 0,
        current_release: str = CURRENT_RELEASE,
        target_release_exists: bool = False,
        certification_gate_failure: tuple[int, str] | None = None,
        probe_non_flat_failure_call: int | None = None,
        drain_status: str = "flat",
        fail_at: str | None = None,
        entry_gate_ready: bool | None = None,
        expired_certification_batch: bool = False,
        source_entry_authority_armed: bool = False,
        target_entry_authority_retained: bool = False,
    ) -> None:
        self.configured_leverage = configured_leverage
        self.closure_ticket_id = closure_ticket_id
        self.active_ticket_count = active_ticket_count
        self.open_order_domain_count = (
            self.active_ticket_count
            if open_order_domain_count is None
            else open_order_domain_count
        )
        self.rule_instrument_ids = rule_instrument_ids
        self.probe_manifest = probe_manifest
        self.source_schema_revision = source_schema_revision
        self.source_gate = source_gate
        self.source_authority_drift = source_authority_drift
        self.source_seed_marker = source_seed_marker
        self.current_release_schema_marker = current_release_schema_marker
        self.source_preservation_changes_before_stop = (
            source_preservation_changes_before_stop
        )
        self.source_gate_after_stop = source_gate_after_stop
        self.preservation_matches = preservation_matches
        self.preservation_is_verified = preservation_verified
        self.preservation_database_proof_matches = (
            preservation_database_proof_matches
        )
        self.migration_stop_prerequisite = migration_stop_prerequisite
        self.omitted_safety_service = omitted_safety_service
        self.postflight_drift = postflight_drift
        self.shadow_pending_count = shadow_pending_count
        self.universe_stage = universe_stage
        self.active_universe_count = active_universe_count
        self.warming_universe_count = warming_universe_count
        self.certification_gate_failure = certification_gate_failure
        self.expired_certification_batch = expired_certification_batch
        self.source_entry_authority_armed = source_entry_authority_armed
        self.target_entry_authority_retained = target_entry_authority_retained
        self.probe_non_flat_failure_call = probe_non_flat_failure_call
        self.drain_status = drain_status
        self.fail_at = fail_at
        self.migration_unknown_outcome_error = RuntimeError(
            "simulated migration unknown outcome"
        )
        self.target_recovery_error = RuntimeError(
            "simulated target recovery failure"
        )
        self.calls: list[tuple[object, ...]] = []
        self.current_release = current_release
        self.target_release_exists = (
            target_release_exists or current_release == TARGET_RELEASE
        )
        self.runtime_commit = CURRENT_COMMIT
        if entry_gate_ready is None:
            entry_gate_ready = source_schema_revision == SOURCE_SCHEMA_REVISION
        self.active_services = set(
            SAFETY_SERVICES if entry_gate_ready else ALL_SERVICES
        )
        self.entry_fenced = entry_gate_ready
        self.entry_enabled = not entry_gate_ready
        self.certification_call_count = 0
        self.probe_call_count = 0
        self.runtime_release_compatibility_fact: RuntimeReleaseCompatibilityFact | None = None

    def read_current_release(self) -> str:
        self.calls.append(("read_current_release",))
        return self.current_release

    def release_exists(self, release: str) -> bool:
        self.calls.append(("release_exists", release))
        return self.target_release_exists and release == TARGET_RELEASE

    def certify_flat(self, release: str) -> Mapping[str, object]:
        self.calls.append(("certify_flat", release))
        self.certification_call_count += 1
        payload: dict[str, object] = {
            "status": "pass",
            "database_integrity_pass": True,
            "flatness_pass": True,
            "universe_bootstrap_pass": not self.expired_certification_batch,
            "certification_batch_pass": not self.expired_certification_batch,
            "runtime_identity": {
                "runtime_commit": self.runtime_commit,
                "schema_revision": TARGET_SCHEMA_REVISION,
                "seed_identity": SEED_IDENTITY,
            },
            "active_counts": {
                "tickets": 0,
                "commands": 0,
                "positions": 0,
                "incidents": 0,
            },
            "dynamic_selection_runtime_counts": {
                "jobs": 0,
                "snapshots": 0,
                "generations": 0,
                "vacuums": 0,
                "authorities": 0,
                "gap_audits": 0,
            },
            "exit_profile_authority": {
                "status": "pass",
                "catalog_digest": build_exit_profile_catalog_digest(),
                "profile_count": 8,
                "binding_fact_count": 8,
                "current_binding_count": 8,
                "binding_event_count": 8,
            },
            "owner_policy": {
                "policy_version": 4,
                "new_entry_submit_enabled": (
                    self.source_entry_authority_armed
                    and self.runtime_commit == CURRENT_COMMIT
                )
                or (
                    self.target_entry_authority_retained
                    and self.runtime_commit == TARGET_COMMIT
                ),
            },
            "registry_identity": {
                "status": "pass",
                "expected_semantic_hash": REGISTRY_DIGEST,
                "metadata_semantic_hash": REGISTRY_DIGEST,
                "expected_live_semantic_hash": REGISTRY_DIGEST,
                "live_semantic_hash": REGISTRY_DIGEST,
            },
            "strategy_universe": {
                "identity_status": "pass",
                "semantic_digest_status": "pass",
                "deployment_stage": self.universe_stage,
                "active_current_count": self.active_universe_count,
                "warming_count": self.warming_universe_count,
                "shadow_pending_count": self.shadow_pending_count,
            },
            "seed_identity": {
                "status": "pass",
                "expected": SEED_IDENTITY,
                "actual": SEED_IDENTITY,
            },
            "compatible_certification_batch_pass": not (
                (
                    self.source_entry_authority_armed
                    and self.runtime_commit == CURRENT_COMMIT
                )
                or (
                    self.target_entry_authority_retained
                    and self.runtime_commit == TARGET_COMMIT
                )
            ),
            "entry_promotion_counts": {
                "active_current_universes": 8,
                "active_instruments": 15,
                "active_scopes": 58,
                "warming_scopes": 0,
            },
        }
        if self.postflight_drift == "policy":
            payload["owner_policy"] = {
                "policy_version": 5,
                "new_entry_submit_enabled": True,
            }
        elif self.postflight_drift == "registry":
            payload["registry_identity"] = {
                "status": "fail",
                "expected_semantic_hash": REGISTRY_DIGEST,
                "metadata_semantic_hash": "sha256:" + "0" * 64,
                "expected_live_semantic_hash": REGISTRY_DIGEST,
                "live_semantic_hash": REGISTRY_DIGEST,
            }
        elif self.postflight_drift == "universe":
            payload["strategy_universe"] = {
                "identity_status": "fail",
                "semantic_digest_status": "fail",
                "deployment_stage": self.universe_stage,
                "active_current_count": self.active_universe_count,
                "warming_count": self.warming_universe_count,
                "shadow_pending_count": self.shadow_pending_count,
            }
        elif self.postflight_drift == "universe_digest":
            payload["strategy_universe"] = {
                "identity_status": "pass",
                "semantic_digest_status": "fail",
                "deployment_stage": self.universe_stage,
                "active_current_count": self.active_universe_count,
                "warming_count": self.warming_universe_count,
                "shadow_pending_count": self.shadow_pending_count,
            }
        elif self.postflight_drift == "batch":
            payload["certification_batch_pass"] = False
        elif self.postflight_drift == "schema":
            payload["runtime_identity"] = {
                "runtime_commit": self.runtime_commit,
                "schema_revision": SOURCE_SCHEMA_REVISION,
                "seed_identity": SEED_IDENTITY,
            }
        elif self.postflight_drift == "seed":
            payload["seed_identity"] = {
                "status": "fail",
                "expected": SEED_IDENTITY,
                "actual": "sha256:" + "0" * 64,
            }
        elif self.postflight_drift == "dynamic_runtime":
            payload["dynamic_selection_runtime_counts"] = {
                "jobs": 0,
                "snapshots": 1,
                "generations": 0,
                "vacuums": 0,
                "authorities": 0,
                "gap_audits": 0,
            }
        elif self.postflight_drift == "exit_profile_authority":
            payload["exit_profile_authority"] = {
                "status": "fail",
                "catalog_digest": "sha256:" + "0" * 64,
                "profile_count": 7,
                "binding_fact_count": 8,
                "current_binding_count": 7,
                "binding_event_count": 8,
            }
        if (
            self.certification_gate_failure is not None
            and self.certification_gate_failure[0] == self.certification_call_count
        ):
            payload[self.certification_gate_failure[1]] = False
        return payload

    def certify_closure(
        self,
        release: str,
        ticket_id: str,
    ) -> Mapping[str, object]:
        self.calls.append(("certify_closure", release, ticket_id))
        payload: dict[str, object] = {
            "status": "pass",
            "runtime_identity": {
                "runtime_commit": self.runtime_commit,
                "schema_revision": TARGET_SCHEMA_REVISION,
                "seed_identity": SEED_IDENTITY,
            },
            "active_counts": {
                "tickets": 0,
                "commands": 0,
                "positions": 0,
                "incidents": 0,
            },
            "closure_ticket": {
                "ticket_id": ticket_id,
                "aggregate_status": "settlement_pending",
                "position_quantity": "0",
                "protected_quantity": "0",
                "owned_order_residue_count": 0,
                "unresolved_command_count": 0,
                "open_incident_count": 0,
                "budget_reservation_status": "released",
                "account_capacity_released": True,
                "netting_domain_released": True,
                "review_presence": False,
            },
        }
        return payload

    def probe_exchange(self, release: str) -> Mapping[str, object]:
        self.calls.append(("probe_exchange", release))
        self.probe_call_count += 1
        payload = self._probe_payload()
        if self.probe_non_flat_failure_call == self.probe_call_count:
            payload["non_flat_domain_count"] = 1
        return payload

    def _probe_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "venue_id": "binance-usdm",
            "account_position_mode": "independent_sides",
            "account_margin_mode": "cross",
            "non_flat_domain_count": self.active_ticket_count,
            "open_order_domain_count": self.open_order_domain_count,
            "rules": [
                {
                    "exchange_instrument_id": instrument_id,
                    "configured_leverage": self.configured_leverage,
                }
                for instrument_id in self.rule_instrument_ids
            ],
            "probe_manifest": list(self.probe_manifest),
        }
        return payload

    def certify_compatible_source(
        self,
        release: str,
        source_schema_revision: str,
    ) -> Mapping[str, object]:
        self.calls.append(
            ("certify_compatible_source", release, source_schema_revision)
        )
        source_certification_call_count = sum(
            call[0] == "certify_compatible_source" for call in self.calls
        )
        gates = {
            "active_tickets": self.active_ticket_count,
            "non_flat_positions": self.active_ticket_count,
            "active_reservations": 0,
            "active_domains": 0,
            "unreviewed_terminal_tickets": 0,
            "unresolved_commands": 0,
            "open_incidents": 0,
            "busy_entry_lane": 0,
            "nonterminal_aggregates": 0,
        }
        if self.source_gate is not None:
            gates[self.source_gate] = 1
        if self.source_gate_after_stop is not None and not self.active_services:
            gates[self.source_gate_after_stop] = 1
        preservation_digest = PRESERVATION_DIGEST
        if (
            self.source_preservation_changes_before_stop
            and source_certification_call_count == 1
        ):
            preservation_digest = "sha256:" + "e" * 64
        payload: dict[str, object] = {
            "status": "pass",
            "alembic_revision": self.source_schema_revision,
            "runtime_identity": {
                "runtime_commit": self.runtime_commit,
                "schema_revision": self.source_schema_revision,
                "seed_identity": SEED_IDENTITY,
            },
            "migration_gate": gates,
            "preservation_manifest": {"digest": preservation_digest},
            "registry_identity": {
                "status": "pass",
                "expected_semantic_hash": SOURCE_REGISTRY_DIGEST,
                "live_semantic_hash": SOURCE_REGISTRY_DIGEST,
            },
            "owner_policy": {
                "status": "pass",
                "policy_version": 5,
                "new_entry_submit_enabled": True,
            },
            "runtime_profile": {"status": "pass"},
            "capabilities": {
                "status": "pass",
                "exchange_commands": True,
            },
            "account_mode": {
                "status": "pass",
                "position_mode": "independent_sides",
                "margin_mode": "cross",
            },
        }
        if self.source_authority_drift == "registry":
            payload["registry_identity"] = {
                "status": "fail",
                "expected_semantic_hash": SOURCE_REGISTRY_DIGEST,
                "live_semantic_hash": "sha256:" + "0" * 64,
            }
        elif self.source_authority_drift == "policy":
            payload["owner_policy"] = {
                "status": "fail",
                "policy_version": 5,
                "new_entry_submit_enabled": False,
            }
        return payload

    def inspect_deployment_drain(
        self,
        release: str,
        source_schema_revision: str,
        target_commit: str,
    ) -> Mapping[str, object]:
        self.calls.append(
            (
                "inspect_deployment_drain",
                release,
                source_schema_revision,
                target_commit,
            )
        )
        status = "flat" if self.active_ticket_count == 0 else self.drain_status
        return {
            "status": status,
            "active_ticket_count": self.active_ticket_count,
            "blocked_ticket_ids": [],
        }

    def request_deployment_drain(
        self,
        release: str,
        source_schema_revision: str,
        authorization_id: str,
        target_commit: str,
    ) -> Mapping[str, object]:
        self.calls.append(
            (
                "request_deployment_drain",
                release,
                source_schema_revision,
                authorization_id,
                target_commit,
            )
        )
        if self.drain_status == "eligible":
            self.active_ticket_count = 0
            self.open_order_domain_count = 0
            self.drain_status = "flat"
            return {"status": "requested"}
        return {"status": self.drain_status}

    def read_release_marker(self, release: str, marker: str) -> str:
        self.calls.append(("read_release_marker", release, marker))
        if marker == ".brc-runtime-commit":
            return TARGET_COMMIT if release == TARGET_RELEASE else CURRENT_COMMIT
        if marker == ".brc-schema-revision":
            return (
                TARGET_SCHEMA_REVISION
                if release == TARGET_RELEASE
                else (
                    self.source_schema_revision
                    if self.current_release_schema_marker is None
                    else self.current_release_schema_marker
                )
            )
        if marker == ".brc-seed-identity":
            return (
                SEED_IDENTITY
                if release == TARGET_RELEASE
                else self.source_seed_marker
            )
        raise AssertionError(f"unexpected marker: {marker}")

    def stop_services(self, services: tuple[str, ...]) -> None:
        self.calls.append(("stop_services", services))
        self.active_services.difference_update(services)

    def inspect_schema(self, release: str) -> Mapping[str, object]:
        self.calls.append(("inspect_schema", release))
        if (
            self.fail_at == "migrate_schema_inspection_failure"
            and any(call[0] == "migrate_schema" for call in self.calls)
        ):
            raise RuntimeError("simulated schema inspection failure")
        return {
            "status": (
                "pass"
                if self.source_schema_revision
                in {SOURCE_SCHEMA_REVISION, TARGET_SCHEMA_REVISION}
                else "fail"
            ),
            "alembic_revision": self.source_schema_revision,
        }

    def migration_writers_stopped_and_entry_fenced(self) -> bool:
        self.calls.append(("migration_writers_stopped_and_entry_fenced",))
        return bool(
            self.migration_stop_prerequisite
            and not self.active_services.intersection(ALL_SERVICES)
            and self.entry_fenced
            and not self.entry_enabled
        )

    def services_active(self, services: tuple[str, ...]) -> frozenset[str]:
        self.calls.append(("services_active", services))
        return frozenset(self.active_services.intersection(services))

    def install_release(self, commit: str, release: str) -> None:
        self.calls.append(("install_release", commit, release))
        self.target_release_exists = True

    def deploy_identity(
        self,
        release: str,
        commit: str,
        schema_revision: str,
    ) -> Mapping[str, object]:
        self.calls.append(
            ("deploy_identity", release, commit, schema_revision)
        )
        self.runtime_commit = commit
        return {
            "runtime_commit": commit,
            "schema_revision": schema_revision,
            "runtime_seed_semantic_hash": SEED_IDENTITY,
            "refreshed_existing_authority": True,
        }

    def migrate_schema(
        self,
        release: str,
        source_schema_revision: str,
        target_schema_revision: str,
    ) -> None:
        self.calls.append(
            (
                "migrate_schema",
                release,
                source_schema_revision,
                target_schema_revision,
            )
        )
        if self.fail_at == "migrate_schema_unknown_source":
            raise RuntimeError("simulated migration unknown outcome")
        if self.fail_at == "migrate_schema_unknown_target":
            self.source_schema_revision = target_schema_revision
            raise RuntimeError("simulated migration unknown outcome")
        if self.fail_at in {
            "migrate_schema_unknown_target_recovery_activation_failure",
            "migrate_schema_unknown_target_recovery_start_failure",
        }:
            self.source_schema_revision = target_schema_revision
            raise self.migration_unknown_outcome_error
        if self.fail_at == "migrate_schema_unknown_revision":
            self.source_schema_revision = "0005_unknown"
            raise RuntimeError("simulated migration unknown outcome")
        if self.fail_at == "migrate_schema_inspection_failure":
            raise RuntimeError("simulated migration unknown outcome")
        self.source_schema_revision = target_schema_revision

    def verify_preservation(
        self,
        release: str,
        source_schema_revision: str,
        expected_digest: str,
    ) -> Mapping[str, object]:
        self.calls.append(
            (
                "verify_preservation",
                release,
                source_schema_revision,
                expected_digest,
            )
        )
        if self.fail_at == "verify_preservation":
            raise RuntimeError("simulated preservation failure")
        digest = expected_digest if self.preservation_matches else "sha256:" + "e" * 64
        return {
            "status": "pass" if self.preservation_matches else "fail",
            "alembic_revision": TARGET_SCHEMA_REVISION,
            "preservation_manifest": {"digest": digest},
        }

    def certify_r4_recovery(
        self,
        release: str,
        legacy_preservation_digest: str,
    ) -> Mapping[str, object]:
        self.calls.append(
            (
                "certify_r4_recovery",
                release,
                legacy_preservation_digest,
            )
        )
        if self.fail_at == "certify_r4_recovery":
            raise RuntimeError("simulated R4 recovery certification failure")
        return {
            "status": "pass" if self.preservation_matches else "fail",
            "alembic_revision": TARGET_SCHEMA_REVISION,
            "legacy_preservation_digest": legacy_preservation_digest,
            "target_shape": {"status": "pass"},
            "migration_gate": {
                "active_tickets": 0,
                "non_flat_positions": 0,
                "active_reservations": 0,
                "active_domains": 0,
                "unreviewed_terminal_tickets": 0,
                "unresolved_commands": 0,
                "open_incidents": 0,
                "busy_entry_lane": 0,
                "nonterminal_aggregates": 0,
            },
            "historical_preservation_proof": {"status": "pass"},
            "terminal_lineage_manifest": {"digest": PRESERVATION_DIGEST},
        }

    def persist_preservation_digest(self, release: str, digest: str) -> None:
        self.calls.append(("persist_preservation_digest", release, digest))

    def inherit_preservation_digest(
        self,
        source_release: str,
        target_release: str,
    ) -> None:
        self.calls.append(
            ("inherit_preservation_digest", source_release, target_release)
        )

    def read_preservation_digest(self, release: str) -> str:
        self.calls.append(("read_preservation_digest", release))
        return PRESERVATION_DIGEST

    def mark_preservation_verified(self, release: str, digest: str) -> None:
        self.calls.append(("mark_preservation_verified", release, digest))
        self.preservation_is_verified = True

    def preservation_verified(self, release: str, digest: str) -> bool:
        self.calls.append(("preservation_verified", release, digest))
        if (
            self.preservation_is_verified
            and not self.preservation_database_proof_matches
        ):
            raise DeploymentBlocked("database-bound preservation proof differs")
        return bool(
            self.preservation_is_verified
            and self.preservation_database_proof_matches
        )

    def deploy_compatible_identity(
        self,
        release: str,
        commit: str,
        schema_revision: str,
    ) -> Mapping[str, object]:
        self.calls.append(
            ("deploy_compatible_identity", release, commit, schema_revision)
        )
        self.runtime_commit = commit
        return {
            "runtime_commit": commit,
            "schema_revision": schema_revision,
            "runtime_seed_semantic_hash": SEED_IDENTITY,
            "refreshed_existing_authority": True,
        }

    def persist_runtime_release_compatibility_fact(
        self,
        release: str,
        fact: RuntimeReleaseCompatibilityFact,
    ) -> None:
        self.calls.append(
            (
                "persist_runtime_release_compatibility_fact",
                release,
                fact.release_compatibility_id,
            )
        )
        if self.fail_at == "persist_runtime_release_compatibility_fact":
            raise RuntimeError("simulated release compatibility persistence failure")
        self.runtime_release_compatibility_fact = fact
        if (
            self.fail_at
            == "persist_runtime_release_compatibility_fact_unknown_committed"
        ):
            raise RuntimeError("simulated release compatibility unknown outcome")

    def read_runtime_release_compatibility_fact(
        self,
        release: str,
        release_compatibility_id: str,
    ) -> RuntimeReleaseCompatibilityFact | None:
        self.calls.append(
            (
                "read_runtime_release_compatibility_fact",
                release,
                release_compatibility_id,
            )
        )
        if self.postflight_drift == "release_compatibility":
            return None
        return self.runtime_release_compatibility_fact

    def deploy_closure_identity(
        self,
        release: str,
        commit: str,
        schema_revision: str,
        ticket_id: str,
    ) -> Mapping[str, object]:
        self.calls.append(
            (
                "deploy_closure_identity",
                release,
                commit,
                schema_revision,
                ticket_id,
            )
        )
        self.runtime_commit = commit
        return {
            "runtime_commit": commit,
            "schema_revision": schema_revision,
            "runtime_seed_semantic_hash": SEED_IDENTITY,
            "refreshed_existing_authority": True,
        }

    def activate_release(
        self,
        release: str,
        commit: str,
        schema_revision: str,
        seed_identity: str,
    ) -> None:
        self.calls.append(
            (
                "activate_release",
                release,
                commit,
                schema_revision,
                seed_identity,
            )
        )
        if self.fail_at == "activate_release":
            raise RuntimeError("simulated activation failure")
        if (
            self.fail_at
            == "migrate_schema_unknown_target_recovery_activation_failure"
        ):
            raise self.target_recovery_error
        self.current_release = release
        if self.fail_at == "activate_release_partial":
            raise RuntimeError("simulated partial activation failure")

    def start_services(self, services: tuple[str, ...]) -> None:
        self.calls.append(("start_services", services))
        if (
            self.fail_at == "migrate_schema_unknown_target_recovery_start_failure"
            and services == SAFETY_SERVICES
        ):
            raise self.target_recovery_error
        started = set(services)
        if self.omitted_safety_service is not None:
            started.discard(self.omitted_safety_service)
        self.active_services.update(started)
        if ENTRY_SERVICE in services:
            self.entry_enabled = True

    def bootstrap_strategy_universes(self, release: str) -> None:
        self.calls.append(("bootstrap_strategy_universes", release))
        if self.fail_at == "bootstrap_strategy_universes":
            self.active_services.difference_update(SAFETY_SERVICES)
            raise RuntimeError("simulated bootstrap failure")

    def refresh_active_certification_batch(self, release: str) -> None:
        self.calls.append(("refresh_active_certification_batch", release))
        self.expired_certification_batch = False

    def fence_entry(self) -> None:
        self.calls.append(("fence_entry",))
        self.active_services.discard(ENTRY_SERVICE)
        self.entry_fenced = True
        self.entry_enabled = False

    def unfence_entry(self) -> None:
        self.calls.append(("unfence_entry",))
        self.entry_fenced = False

    def entry_is_inactive_disabled_and_fenced(self) -> bool:
        self.calls.append(("entry_is_inactive_disabled_and_fenced",))
        return (
            ENTRY_SERVICE not in self.active_services
            and not self.entry_enabled
            and self.entry_fenced
        )
