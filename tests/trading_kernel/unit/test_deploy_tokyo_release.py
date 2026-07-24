from __future__ import annotations

from collections.abc import Mapping

import pytest

from scripts.trading_kernel.deploy_tokyo_release import (
    ALL_SERVICES,
    ENTRY_SERVICE,
    SAFETY_SERVICES,
    DeploymentBlocked,
    DeploymentPlan,
    deploy_tokyo_release,
)

TARGET_COMMIT = "a" * 40
CURRENT_COMMIT = "b" * 40
CURRENT_RELEASE = "/opt/brc/releases/brc-trading-kernel-bbbbbbbbbbbb"
TARGET_RELEASE = "/opt/brc/releases/brc-trading-kernel-aaaaaaaaaaaa"
SEED_IDENTITY = "sha256:" + "c" * 64


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
            "0001_initial",
        ),
        (
            "activate_release",
            TARGET_RELEASE,
            TARGET_COMMIT,
            "0001_initial",
            SEED_IDENTITY,
        ),
        ("start_services", SAFETY_SERVICES),
        ("certify_flat", TARGET_RELEASE),
        ("probe_exchange", TARGET_RELEASE),
        ("read_current_release",),
        ("read_release_marker", TARGET_RELEASE, ".brc-runtime-commit"),
        ("read_release_marker", TARGET_RELEASE, ".brc-schema-revision"),
        ("read_release_marker", TARGET_RELEASE, ".brc-seed-identity"),
        ("start_services", (ENTRY_SERVICE,)),
        ("services_active", ALL_SERVICES),
    ]


def test_preflight_leverage_drift_blocks_before_any_service_stop() -> None:
    backend = FakeDeploymentBackend(configured_leverage=3)

    with pytest.raises(DeploymentBlocked, match="configured leverage"):
        deploy_tokyo_release(backend, _plan(enable_entry=True))

    assert not any(call[0] == "stop_services" for call in backend.calls)
    assert not any(call[0] == "deploy_identity" for call in backend.calls)
    assert not any(call[0] == "activate_release" for call in backend.calls)


def test_post_stop_failure_fences_entry_and_restores_safety_workers() -> None:
    backend = FakeDeploymentBackend(fail_at="activate_release")

    with pytest.raises(RuntimeError, match="simulated activation failure"):
        deploy_tokyo_release(backend, _plan(enable_entry=True))

    assert ("fence_entry",) in backend.calls
    assert backend.calls[-1] == ("start_services", SAFETY_SERVICES)
    assert ("start_services", (ENTRY_SERVICE,)) not in backend.calls


def _plan(*, enable_entry: bool) -> DeploymentPlan:
    return DeploymentPlan(
        target_commit=TARGET_COMMIT,
        target_release=TARGET_RELEASE,
        schema_revision="0001_initial",
        expected_configured_leverage=5,
        enable_entry=enable_entry,
    )


class FakeDeploymentBackend:
    def __init__(
        self,
        *,
        configured_leverage: int = 5,
        fail_at: str | None = None,
    ) -> None:
        self.configured_leverage = configured_leverage
        self.fail_at = fail_at
        self.calls: list[tuple[object, ...]] = []
        self.current_release = CURRENT_RELEASE
        self.runtime_commit = CURRENT_COMMIT
        self.active_services = set(ALL_SERVICES)

    def read_current_release(self) -> str:
        self.calls.append(("read_current_release",))
        return self.current_release

    def certify_flat(self, release: str) -> Mapping[str, object]:
        self.calls.append(("certify_flat", release))
        return {
            "status": "pass",
            "runtime_identity": {
                "runtime_commit": self.runtime_commit,
                "schema_revision": "0001_initial",
                "seed_identity": SEED_IDENTITY,
            },
            "active_counts": {
                "tickets": 0,
                "commands": 0,
                "positions": 0,
                "incidents": 0,
            },
        }

    def probe_exchange(self, release: str) -> Mapping[str, object]:
        self.calls.append(("probe_exchange", release))
        return {
            "venue_id": "binance-usdm",
            "account_position_mode": "independent_sides",
            "account_margin_mode": "cross",
            "non_flat_domain_count": 0,
            "open_order_domain_count": 0,
            "rules": [
                {
                    "exchange_instrument_id": f"instrument-{index}",
                    "configured_leverage": self.configured_leverage,
                }
                for index in range(6)
            ],
        }

    def read_release_marker(self, release: str, marker: str) -> str:
        self.calls.append(("read_release_marker", release, marker))
        if marker == ".brc-runtime-commit":
            return TARGET_COMMIT if release == TARGET_RELEASE else CURRENT_COMMIT
        if marker == ".brc-schema-revision":
            return "0001_initial"
        if marker == ".brc-seed-identity":
            return SEED_IDENTITY
        raise AssertionError(f"unexpected marker: {marker}")

    def stop_services(self, services: tuple[str, ...]) -> None:
        self.calls.append(("stop_services", services))
        self.active_services.difference_update(services)

    def services_active(self, services: tuple[str, ...]) -> frozenset[str]:
        self.calls.append(("services_active", services))
        return frozenset(self.active_services.intersection(services))

    def install_release(self, commit: str, release: str) -> None:
        self.calls.append(("install_release", commit, release))

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
        self.active_services.update(services)

    def fence_entry(self) -> None:
        self.calls.append(("fence_entry",))
        self.active_services.discard(ENTRY_SERVICE)
