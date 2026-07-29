from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest

from scripts.trading_kernel.deploy_tokyo_release import (
    ALL_SERVICES,
    ENTRY_SERVICE,
    SAFETY_SERVICES,
    DeploymentBlocked,
    DeploymentPlan,
    SshTokyoReleaseBackend,
    deploy_tokyo_release,
)

TARGET_COMMIT = "a" * 40
CURRENT_COMMIT = "b" * 40
CURRENT_RELEASE = "/opt/brc/releases/brc-trading-kernel-bbbbbbbbbbbb"
TARGET_RELEASE = "/opt/brc/releases/brc-trading-kernel-aaaaaaaaaaaa"
SEED_IDENTITY = "sha256:" + "c" * 64
TARGET_EXCHANGE_INSTRUMENT_IDS = (
    "binance-usdm:ADAUSDT:perpetual",
    "binance-usdm:BNBUSDT:perpetual",
    "binance-usdm:BTCUSDT:perpetual",
    "binance-usdm:DOGEUSDT:perpetual",
    "binance-usdm:ETHUSDT:perpetual",
    "binance-usdm:SOLUSDT:perpetual",
    "binance-usdm:XRPUSDT:perpetual",
)


def test_regular_plan_freezes_current_schema_and_probe_instruments() -> None:
    plan = DeploymentPlan(
        target_commit=TARGET_COMMIT,
        target_release=TARGET_RELEASE,
        schema_revision="0003_cross_margin_stop_stress",
        expected_configured_leverage=5,
        enable_entry=False,
        exchange_instrument_ids=TARGET_EXCHANGE_INSTRUMENT_IDS,
    )

    assert plan.schema_revision == "0003_cross_margin_stop_stress"
    assert plan.exchange_instrument_ids == TARGET_EXCHANGE_INSTRUMENT_IDS


def test_regular_release_passes_exact_probe_instruments() -> None:
    backend = FakeDeploymentBackend()
    plan = DeploymentPlan(
        target_commit=TARGET_COMMIT,
        target_release=TARGET_RELEASE,
        schema_revision="0003_cross_margin_stop_stress",
        expected_configured_leverage=5,
        enable_entry=False,
        exchange_instrument_ids=TARGET_EXCHANGE_INSTRUMENT_IDS,
    )

    deploy_tokyo_release(backend, plan)

    assert [call for call in backend.calls if call[0] == "probe_exchange"] == [
        (
            "probe_exchange",
            TARGET_RELEASE,
            TARGET_EXCHANGE_INSTRUMENT_IDS,
        ),
        (
            "probe_exchange",
            TARGET_RELEASE,
            TARGET_EXCHANGE_INSTRUMENT_IDS,
        ),
    ]


def test_ssh_probe_exchange_passes_exact_instrument_arguments(
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

    backend.probe_exchange(TARGET_RELEASE, TARGET_EXCHANGE_INSTRUMENT_IDS)

    assert calls == [
        (
            TARGET_RELEASE,
            "scripts/trading_kernel/probe_production_runtime.py",
            *(
                argument
                for instrument_id in TARGET_EXCHANGE_INSTRUMENT_IDS
                for argument in ("--exchange-instrument-id", instrument_id)
            ),
        )
    ]


def test_ssh_protected_probe_passes_instruments_before_ticket_manifest(
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

    backend.probe_protected_exchange(
        TARGET_RELEASE,
        [{"ticket_id": "ticket:btc"}],
        TARGET_EXCHANGE_INSTRUMENT_IDS,
    )

    expected_instrument_args = tuple(
        argument
        for instrument_id in TARGET_EXCHANGE_INSTRUMENT_IDS
        for argument in ("--exchange-instrument-id", instrument_id)
    )
    assert calls[0][0:2] == (
        TARGET_RELEASE,
        "scripts/trading_kernel/probe_production_runtime.py",
    )
    assert calls[0][2 : 2 + len(expected_instrument_args)] == (
        expected_instrument_args
    )
    assert calls[0][2 + len(expected_instrument_args)] == (
        "--protected-ticket-json"
    )


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
        (
            "probe_exchange",
            TARGET_RELEASE,
            TARGET_EXCHANGE_INSTRUMENT_IDS,
        ),
        ("read_release_marker", CURRENT_RELEASE, ".brc-runtime-commit"),
        ("read_release_marker", CURRENT_RELEASE, ".brc-schema-revision"),
        ("stop_services", ALL_SERVICES),
        ("fence_entry",),
        ("services_active", ALL_SERVICES),
        (
            "deploy_identity",
            TARGET_RELEASE,
            TARGET_COMMIT,
            "0003_cross_margin_stop_stress",
        ),
        (
            "activate_release",
            TARGET_RELEASE,
            TARGET_COMMIT,
            "0003_cross_margin_stop_stress",
            SEED_IDENTITY,
        ),
        ("certify_flat", TARGET_RELEASE),
        (
            "probe_exchange",
            TARGET_RELEASE,
            TARGET_EXCHANGE_INSTRUMENT_IDS,
        ),
        ("read_current_release",),
        ("read_release_marker", TARGET_RELEASE, ".brc-runtime-commit"),
        ("read_release_marker", TARGET_RELEASE, ".brc-schema-revision"),
        ("read_release_marker", TARGET_RELEASE, ".brc-seed-identity"),
        ("start_services", SAFETY_SERVICES),
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


def test_preflight_rule_identity_drift_blocks_before_service_stop() -> None:
    backend = FakeDeploymentBackend(
        rule_instrument_ids=(
            *TARGET_EXCHANGE_INSTRUMENT_IDS[:-1],
            "binance-usdm:AVAXUSDT:perpetual",
        )
    )

    with pytest.raises(DeploymentBlocked, match="instrument rule identity"):
        deploy_tokyo_release(backend, _plan(enable_entry=False))

    assert not any(call[0] == "stop_services" for call in backend.calls)


def test_post_stop_failure_fences_entry_and_restores_safety_workers() -> None:
    backend = FakeDeploymentBackend(fail_at="activate_release")

    with pytest.raises(RuntimeError, match="simulated activation failure"):
        deploy_tokyo_release(backend, _plan(enable_entry=True))

    assert ("fence_entry",) in backend.calls
    assert backend.calls[-1] == ("start_services", SAFETY_SERVICES)
    assert ("start_services", (ENTRY_SERVICE,)) not in backend.calls


def test_protected_release_rotates_only_the_explicit_ticket_set() -> None:
    ticket_ids = ("ticket:avax", "ticket:btc", "ticket:sol")
    backend = FakeDeploymentBackend(protected_ticket_ids=ticket_ids)

    result = deploy_tokyo_release(
        backend,
        _plan(
            enable_entry=False,
            protected_ticket_ids=ticket_ids,
        ),
    )

    assert result.status == "pass"
    assert backend.calls == [
        ("read_current_release",),
        ("install_release", TARGET_COMMIT, TARGET_RELEASE),
        ("certify_protected", TARGET_RELEASE),
        (
            "probe_protected_exchange",
            TARGET_RELEASE,
            ticket_ids,
            TARGET_EXCHANGE_INSTRUMENT_IDS,
        ),
        ("read_release_marker", CURRENT_RELEASE, ".brc-runtime-commit"),
        ("read_release_marker", CURRENT_RELEASE, ".brc-schema-revision"),
        ("stop_services", ALL_SERVICES),
        ("fence_entry",),
        ("services_active", ALL_SERVICES),
        (
            "deploy_protected_identity",
            TARGET_RELEASE,
            TARGET_COMMIT,
            "0003_cross_margin_stop_stress",
            ticket_ids,
        ),
        (
            "activate_release",
            TARGET_RELEASE,
            TARGET_COMMIT,
            "0003_cross_margin_stop_stress",
            SEED_IDENTITY,
        ),
        ("certify_protected", TARGET_RELEASE),
        (
            "probe_protected_exchange",
            TARGET_RELEASE,
            ticket_ids,
            TARGET_EXCHANGE_INSTRUMENT_IDS,
        ),
        ("read_current_release",),
        ("read_release_marker", TARGET_RELEASE, ".brc-runtime-commit"),
        ("read_release_marker", TARGET_RELEASE, ".brc-schema-revision"),
        ("read_release_marker", TARGET_RELEASE, ".brc-seed-identity"),
        ("start_services", SAFETY_SERVICES),
        ("services_active", ALL_SERVICES),
    ]


def test_protected_release_refuses_exchange_domains_outside_ticket_set() -> None:
    ticket_ids = ("ticket:avax", "ticket:btc", "ticket:sol")
    backend = FakeDeploymentBackend(
        protected_ticket_ids=ticket_ids,
        open_order_domain_count=2,
    )

    with pytest.raises(DeploymentBlocked, match="protected order count"):
        deploy_tokyo_release(
            backend,
            _plan(
                enable_entry=False,
                protected_ticket_ids=ticket_ids,
            ),
        )

    assert not any(call[0] == "stop_services" for call in backend.calls)


def test_protected_release_forbids_enabling_entry() -> None:
    with pytest.raises(ValueError, match="ENTRY"):
        _plan(
            enable_entry=True,
            protected_ticket_ids=("ticket:avax",),
        )


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
        (
            "probe_exchange",
            TARGET_RELEASE,
            TARGET_EXCHANGE_INSTRUMENT_IDS,
        ),
        ("read_release_marker", CURRENT_RELEASE, ".brc-runtime-commit"),
        ("read_release_marker", CURRENT_RELEASE, ".brc-schema-revision"),
        ("stop_services", ALL_SERVICES),
        ("fence_entry",),
        ("services_active", ALL_SERVICES),
        ("certify_closure", TARGET_RELEASE, ticket_id),
        (
            "probe_exchange",
            TARGET_RELEASE,
            TARGET_EXCHANGE_INSTRUMENT_IDS,
        ),
        (
            "deploy_closure_identity",
            TARGET_RELEASE,
            TARGET_COMMIT,
            "0003_cross_margin_stop_stress",
            ticket_id,
        ),
        (
            "activate_release",
            TARGET_RELEASE,
            TARGET_COMMIT,
            "0003_cross_margin_stop_stress",
            SEED_IDENTITY,
        ),
        ("certify_closure", TARGET_RELEASE, ticket_id),
        (
            "probe_exchange",
            TARGET_RELEASE,
            TARGET_EXCHANGE_INSTRUMENT_IDS,
        ),
        ("read_current_release",),
        ("read_release_marker", TARGET_RELEASE, ".brc-runtime-commit"),
        ("read_release_marker", TARGET_RELEASE, ".brc-schema-revision"),
        ("read_release_marker", TARGET_RELEASE, ".brc-seed-identity"),
        ("start_services", SAFETY_SERVICES),
        ("entry_is_inactive_disabled_and_fenced",),
        ("services_active", ALL_SERVICES),
    ]


def test_protected_release_refuses_count_only_exchange_evidence() -> None:
    ticket_ids = ("ticket:avax", "ticket:btc", "ticket:sol")
    backend = FakeDeploymentBackend(
        protected_ticket_ids=ticket_ids,
        include_exact_protected_facts=False,
    )

    with pytest.raises(DeploymentBlocked, match="exact protected exchange facts"):
        deploy_tokyo_release(
            backend,
            _plan(
                enable_entry=False,
                protected_ticket_ids=ticket_ids,
            ),
        )

    assert not any(call[0] == "stop_services" for call in backend.calls)


def test_failed_protected_postflight_starts_no_mutating_worker() -> None:
    ticket_ids = ("ticket:avax", "ticket:btc", "ticket:sol")
    backend = FakeDeploymentBackend(
        protected_ticket_ids=ticket_ids,
        fail_at="target_protected_certification",
    )

    with pytest.raises(RuntimeError, match="simulated protected certification failure"):
        deploy_tokyo_release(
            backend,
            _plan(
                enable_entry=False,
                protected_ticket_ids=ticket_ids,
            ),
        )

    assert not any(call[0] == "start_services" for call in backend.calls)
    assert ("fence_entry",) in backend.calls


def _plan(
    *,
    enable_entry: bool,
    protected_ticket_ids: tuple[str, ...] = (),
    closure_ticket_id: str | None = None,
) -> DeploymentPlan:
    return DeploymentPlan(
        target_commit=TARGET_COMMIT,
        target_release=TARGET_RELEASE,
        schema_revision="0003_cross_margin_stop_stress",
        expected_configured_leverage=5,
        enable_entry=enable_entry,
        exchange_instrument_ids=TARGET_EXCHANGE_INSTRUMENT_IDS,
        protected_ticket_ids=protected_ticket_ids,
        closure_ticket_id=closure_ticket_id,
    )


class FakeDeploymentBackend:
    def __init__(
        self,
        *,
        configured_leverage: int = 5,
        active_ticket_count: int = 0,
        protected_ticket_ids: tuple[str, ...] = (),
        closure_ticket_id: str | None = None,
        open_order_domain_count: int | None = None,
        include_exact_protected_facts: bool = True,
        rule_instrument_ids: tuple[str, ...] = TARGET_EXCHANGE_INSTRUMENT_IDS,
        fail_at: str | None = None,
    ) -> None:
        self.configured_leverage = configured_leverage
        self.protected_ticket_ids = protected_ticket_ids
        self.closure_ticket_id = closure_ticket_id
        self.active_ticket_count = (
            len(protected_ticket_ids)
            if protected_ticket_ids
            else active_ticket_count
        )
        self.open_order_domain_count = (
            self.active_ticket_count
            if open_order_domain_count is None
            else open_order_domain_count
        )
        self.include_exact_protected_facts = include_exact_protected_facts
        self.rule_instrument_ids = rule_instrument_ids
        self.fail_at = fail_at
        self.protected_certification_calls = 0
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
                "schema_revision": "0003_cross_margin_stop_stress",
                "seed_identity": SEED_IDENTITY,
            },
            "active_counts": {
                "tickets": 0,
                "commands": 0,
                "positions": 0,
                "incidents": 0,
            },
        }

    def certify_protected(self, release: str) -> Mapping[str, object]:
        self.calls.append(("certify_protected", release))
        self.protected_certification_calls += 1
        if (
            self.fail_at == "target_protected_certification"
            and self.protected_certification_calls == 2
        ):
            raise RuntimeError("simulated protected certification failure")
        payload: dict[str, object] = {
            "status": "pass",
            "runtime_identity": {
                "runtime_commit": self.runtime_commit,
                "schema_revision": "0003_cross_margin_stop_stress",
                "seed_identity": SEED_IDENTITY,
            },
            "active_counts": {
                "tickets": self.active_ticket_count,
                "commands": 0,
                "positions": self.active_ticket_count,
                "incidents": 0,
            },
        }
        if self.include_exact_protected_facts:
            payload["protected_tickets"] = self._protected_ticket_facts()
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
                "schema_revision": "0003_cross_margin_stop_stress",
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

    def probe_exchange(
        self,
        release: str,
        exchange_instrument_ids: tuple[str, ...],
    ) -> Mapping[str, object]:
        self.calls.append(
            ("probe_exchange", release, exchange_instrument_ids)
        )
        return self._probe_payload()

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
        }
        if self.include_exact_protected_facts:
            payload["protected_tickets"] = self._protected_ticket_facts()
        return payload

    def probe_protected_exchange(
        self,
        release: str,
        protected_tickets: list[object],
        exchange_instrument_ids: tuple[str, ...],
    ) -> Mapping[str, object]:
        self.calls.append(
            (
                "probe_protected_exchange",
                release,
                tuple(
                    str(row["ticket_id"])
                    for row in protected_tickets
                    if isinstance(row, Mapping)
                ),
                exchange_instrument_ids,
            )
        )
        return self._probe_payload()

    def _protected_ticket_facts(self) -> list[dict[str, object]]:
        return [
            {
                "ticket_id": ticket_id,
                "netting_domain_key": (
                    f"binance-usdm:subaccount-main:instrument-{index}:short"
                ),
                "aggregate_status": "runner_protected",
                "position_quantity": "1",
                "protected_quantity": "1",
                "active_stop_order": {
                    "exchange_order_id": f"stop-{index}",
                    "order_namespace": "conditional",
                    "position_side": "short",
                    "order_side": "buy",
                    "quantity": "1",
                    "reduce_only": True,
                    "stop_price": "101",
                },
                "recorded_tp1_fill_quantity": "1",
            }
            for index, ticket_id in enumerate(self.protected_ticket_ids, start=1)
        ]

    def read_release_marker(self, release: str, marker: str) -> str:
        self.calls.append(("read_release_marker", release, marker))
        if marker == ".brc-runtime-commit":
            return TARGET_COMMIT if release == TARGET_RELEASE else CURRENT_COMMIT
        if marker == ".brc-schema-revision":
            return "0003_cross_margin_stop_stress"
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

    def deploy_protected_identity(
        self,
        release: str,
        commit: str,
        schema_revision: str,
        ticket_ids: tuple[str, ...],
    ) -> Mapping[str, object]:
        self.calls.append(
            (
                "deploy_protected_identity",
                release,
                commit,
                schema_revision,
                ticket_ids,
            )
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
        self.active_services.update(services)

    def fence_entry(self) -> None:
        self.calls.append(("fence_entry",))
        self.active_services.discard(ENTRY_SERVICE)

    def entry_is_inactive_disabled_and_fenced(self) -> bool:
        self.calls.append(("entry_is_inactive_disabled_and_fenced",))
        return ENTRY_SERVICE not in self.active_services
