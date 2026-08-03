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

TARGET_COMMIT = "a" * 40
CURRENT_COMMIT = "b" * 40
CURRENT_RELEASE = "/opt/brc/releases/brc-trading-kernel-bbbbbbbbbbbb"
TARGET_RELEASE = "/opt/brc/releases/brc-trading-kernel-aaaaaaaaaaaa"
SOURCE_SCHEMA_REVISION = "0002_sor_v3_strategy_group_capacity"
TARGET_SCHEMA_REVISION = "0003_portfolio_admission_observability"
SEED_IDENTITY = "sha256:" + "c" * 64
PRESERVATION_DIGEST = "sha256:" + "d" * 64
REGISTRY_DIGEST = "sha256:" + "f" * 64
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


def test_dep_002_compatible_upgrade_accepts_only_exact_0002_to_0003() -> None:
    plan = DeploymentPlan(
        target_commit=TARGET_COMMIT,
        target_release=TARGET_RELEASE,
        schema_revision=TARGET_SCHEMA_REVISION,
        source_schema_revision=SOURCE_SCHEMA_REVISION,
        mode=DeploymentMode.COMPATIBLE_UPGRADE,
        expected_configured_leverage=5,
        enable_entry=False,
    )

    assert plan.mode is DeploymentMode.COMPATIBLE_UPGRADE
    assert plan.source_schema_revision == SOURCE_SCHEMA_REVISION

    with pytest.raises(ValueError, match="exact 0002 source"):
        DeploymentPlan(
            target_commit=TARGET_COMMIT,
            target_release=TARGET_RELEASE,
            schema_revision=TARGET_SCHEMA_REVISION,
            source_schema_revision="0000_unknown",
            mode=DeploymentMode.COMPATIBLE_UPGRADE,
            expected_configured_leverage=5,
            enable_entry=False,
        )


def test_dep_003_portfolio_admission_upgrade_rejects_enable_entry() -> None:
    with pytest.raises(ValueError, match="keep ENTRY disabled"):
        _compatible_plan(enable_entry=True)


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
        "verify_preservation",
        TARGET_RELEASE,
        SOURCE_SCHEMA_REVISION,
        PRESERVATION_DIGEST,
    ) in backend.calls
    bootstrap_index = backend.calls.index(
        ("bootstrap_strategy_universes", TARGET_RELEASE)
    )
    target_postflight_index = max(
        index
        for index, call in enumerate(backend.calls[: bootstrap_index + 2])
        if call == ("certify_flat", TARGET_RELEASE)
    )
    safety_start_index = backend.calls.index(("start_services", SAFETY_SERVICES))
    assert bootstrap_index < target_postflight_index < safety_start_index
    assert ("start_services", (ENTRY_SERVICE,)) not in backend.calls
    assert backend.active_services == set(SAFETY_SERVICES)
    assert backend.entry_is_inactive_disabled_and_fenced()


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

    with pytest.raises(DeploymentBlocked, match="preservation digest"):
        deploy_tokyo_release(backend, _compatible_plan(enable_entry=False))

    assert backend.entry_fenced is True
    assert not any(call == ("unfence_entry",) for call in backend.calls)
    assert not any(call == ("start_services", (ENTRY_SERVICE,)) for call in backend.calls)


def test_mig_009_wrong_source_blocks_before_service_mutation() -> None:
    backend = FakeDeploymentBackend(
        source_schema_revision="0001_trading_kernel_baseline_v4",
    )

    with pytest.raises(DeploymentBlocked, match="source schema revision"):
        deploy_tokyo_release(backend, _compatible_plan(enable_entry=False))

    assert not any(call[0] in {"fence_entry", "stop_services"} for call in backend.calls)
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
        ("policy", "Policy v4"),
        ("registry", "Registry identity"),
        ("universe", "Universe identity"),
        ("universe_digest", "Universe identity"),
        ("batch", "Certification Batch"),
        ("schema", "schema revision"),
        ("seed", "Seed identity"),
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


def test_compatible_postflight_rejects_active_only_vnext_universe_stage() -> None:
    backend = FakeDeploymentBackend(
        source_schema_revision=SOURCE_SCHEMA_REVISION,
        universe_stage="active",
    )

    with pytest.raises(DeploymentBlocked, match="Warming Universe stage"):
        deploy_tokyo_release(backend, _compatible_plan(enable_entry=False))

    assert backend.entry_fenced is True
    assert ENTRY_SERVICE not in backend.active_services


def test_compatible_upgrade_resumes_target_fix_forward_idempotently() -> None:
    backend = FakeDeploymentBackend(
        source_schema_revision=TARGET_SCHEMA_REVISION,
        current_release=CURRENT_RELEASE,
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
    assert backend.active_services == set(SAFETY_SERVICES)
    assert backend.entry_is_inactive_disabled_and_fenced()


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


def test_ssh_compatible_bootstrap_prepares_warming_batch_without_active_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = SshTokyoReleaseBackend(
        target="tokyo",
        repo_root=Path("."),
        timeout_seconds=30,
    )
    calls: list[tuple[object, ...]] = []

    def release_command(release: str, *args: str) -> object:
        calls.append((release, *args))
        return object()

    monkeypatch.setattr(backend, "_release_command", release_command)

    backend.bootstrap_strategy_universes(TARGET_RELEASE)

    assert calls == [
        (
            TARGET_RELEASE,
            "scripts/trading_kernel/bootstrap_strategy_universes.py",
            "--runtime-profile-id",
            "tiny-live-v1",
            "--prepare-certification-batch-only",
        )
    ]


def test_regular_release_runs_one_bounded_flow_and_enables_entry_last() -> None:
    backend = FakeDeploymentBackend()

    result = deploy_tokyo_release(backend, _plan(enable_entry=True))

    assert result.status == "pass"
    assert result.target_commit == TARGET_COMMIT
    assert result.entry_enabled is True
    assert backend.calls == [
        ("read_current_release",),
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


def _compatible_plan(*, enable_entry: bool) -> DeploymentPlan:
    return DeploymentPlan(
        target_commit=TARGET_COMMIT,
        target_release=TARGET_RELEASE,
        schema_revision=TARGET_SCHEMA_REVISION,
        source_schema_revision=SOURCE_SCHEMA_REVISION,
        mode=DeploymentMode.COMPATIBLE_UPGRADE,
        expected_configured_leverage=5,
        enable_entry=enable_entry,
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
        preservation_matches: bool = True,
        preservation_verified: bool = False,
        migration_stop_prerequisite: bool = True,
        omitted_safety_service: str | None = None,
        postflight_drift: str | None = None,
        shadow_pending_count: int = 0,
        universe_stage: str = "warming",
        current_release: str = CURRENT_RELEASE,
        target_release_exists: bool = False,
        certification_gate_failure: tuple[int, str] | None = None,
        probe_non_flat_failure_call: int | None = None,
        fail_at: str | None = None,
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
        self.preservation_matches = preservation_matches
        self.preservation_is_verified = preservation_verified
        self.migration_stop_prerequisite = migration_stop_prerequisite
        self.omitted_safety_service = omitted_safety_service
        self.postflight_drift = postflight_drift
        self.shadow_pending_count = shadow_pending_count
        self.universe_stage = universe_stage
        self.certification_gate_failure = certification_gate_failure
        self.probe_non_flat_failure_call = probe_non_flat_failure_call
        self.fail_at = fail_at
        self.calls: list[tuple[object, ...]] = []
        self.current_release = current_release
        self.target_release_exists = (
            target_release_exists or current_release == TARGET_RELEASE
        )
        self.runtime_commit = CURRENT_COMMIT
        self.active_services = set(ALL_SERVICES)
        self.entry_fenced = False
        self.entry_enabled = True
        self.certification_call_count = 0
        self.probe_call_count = 0

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
            "flatness_pass": True,
            "universe_bootstrap_pass": True,
            "certification_batch_pass": True,
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
            "owner_policy": {
                "policy_version": 4,
                "new_entry_submit_enabled": False,
            },
            "registry_identity": {
                "status": "pass",
                "expected_semantic_hash": REGISTRY_DIGEST,
                "metadata_semantic_hash": REGISTRY_DIGEST,
            },
            "strategy_universe": {
                "identity_status": "pass",
                "semantic_digest_status": "pass",
                "deployment_stage": self.universe_stage,
                "shadow_pending_count": self.shadow_pending_count,
            },
            "seed_identity": {
                "status": "pass",
                "expected": SEED_IDENTITY,
                "actual": SEED_IDENTITY,
            },
            "compatible_certification_batch_pass": True,
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
            }
        elif self.postflight_drift == "universe":
            payload["strategy_universe"] = {
                "identity_status": "fail",
                "semantic_digest_status": "fail",
                "deployment_stage": self.universe_stage,
                "shadow_pending_count": self.shadow_pending_count,
            }
        elif self.postflight_drift == "universe_digest":
            payload["strategy_universe"] = {
                "identity_status": "pass",
                "semantic_digest_status": "fail",
                "deployment_stage": self.universe_stage,
                "shadow_pending_count": self.shadow_pending_count,
            }
        elif self.postflight_drift == "batch":
            payload["compatible_certification_batch_pass"] = False
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
        return {
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
        gates = {
            "active_tickets": 0,
            "non_flat_positions": 0,
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
        return {
            "status": "pass",
            "alembic_revision": self.source_schema_revision,
            "runtime_identity": {
                "runtime_commit": self.runtime_commit,
                "schema_revision": self.source_schema_revision,
                "seed_identity": SEED_IDENTITY,
            },
            "migration_gate": gates,
            "preservation_manifest": {"digest": PRESERVATION_DIGEST},
        }

    def read_release_marker(self, release: str, marker: str) -> str:
        self.calls.append(("read_release_marker", release, marker))
        if marker == ".brc-runtime-commit":
            return TARGET_COMMIT if release == TARGET_RELEASE else CURRENT_COMMIT
        if marker == ".brc-schema-revision":
            return (
                TARGET_SCHEMA_REVISION
                if release == TARGET_RELEASE
                else self.source_schema_revision
            )
        if marker == ".brc-seed-identity":
            return SEED_IDENTITY
        raise AssertionError(f"unexpected marker: {marker}")

    def stop_services(self, services: tuple[str, ...]) -> None:
        self.calls.append(("stop_services", services))
        self.active_services.difference_update(services)

    def inspect_schema(self, release: str) -> Mapping[str, object]:
        self.calls.append(("inspect_schema", release))
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
        digest = expected_digest if self.preservation_matches else "sha256:" + "e" * 64
        return {
            "status": "pass" if self.preservation_matches else "fail",
            "alembic_revision": TARGET_SCHEMA_REVISION,
            "preservation_manifest": {"digest": digest},
        }

    def persist_preservation_digest(self, release: str, digest: str) -> None:
        self.calls.append(("persist_preservation_digest", release, digest))

    def read_preservation_digest(self, release: str) -> str:
        self.calls.append(("read_preservation_digest", release))
        return PRESERVATION_DIGEST

    def mark_preservation_verified(self, release: str, digest: str) -> None:
        self.calls.append(("mark_preservation_verified", release, digest))
        self.preservation_is_verified = True

    def preservation_verified(self, release: str, digest: str) -> bool:
        self.calls.append(("preservation_verified", release, digest))
        return self.preservation_is_verified

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
        self.current_release = release

    def start_services(self, services: tuple[str, ...]) -> None:
        self.calls.append(("start_services", services))
        started = set(services)
        if self.omitted_safety_service is not None:
            started.discard(self.omitted_safety_service)
        self.active_services.update(started)
        if ENTRY_SERVICE in services:
            self.entry_enabled = True

    def bootstrap_strategy_universes(self, release: str) -> None:
        self.calls.append(("bootstrap_strategy_universes", release))

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
