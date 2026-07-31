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


def test_regular_plan_freezes_current_schema_without_operator_probe_scope() -> None:
    plan = DeploymentPlan(
        target_commit=TARGET_COMMIT,
        target_release=TARGET_RELEASE,
        schema_revision="0002_sor_v3_strategy_group_capacity",
        expected_configured_leverage=5,
        enable_entry=False,
    )

    assert plan.schema_revision == "0002_sor_v3_strategy_group_capacity"
    assert "exchange_instrument_ids" not in plan.__dataclass_fields__


def test_regular_release_uses_database_derived_probe_manifest() -> None:
    backend = FakeDeploymentBackend()
    plan = DeploymentPlan(
        target_commit=TARGET_COMMIT,
        target_release=TARGET_RELEASE,
        schema_revision="0002_sor_v3_strategy_group_capacity",
        expected_configured_leverage=5,
        enable_entry=False,
    )

    deploy_tokyo_release(backend, plan)

    assert [call for call in backend.calls if call[0] == "probe_exchange"] == [
        ("probe_exchange", TARGET_RELEASE),
        ("probe_exchange", TARGET_RELEASE),
    ]


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


def test_ssh_protected_probe_passes_only_ticket_manifest(
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
    )

    assert calls[0][0:2] == (
        TARGET_RELEASE,
        "scripts/trading_kernel/probe_production_runtime.py",
    )
    assert calls[0][2] == "--protected-ticket-json"


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
            "0002_sor_v3_strategy_group_capacity",
        ),
        (
            "activate_release",
            TARGET_RELEASE,
            TARGET_COMMIT,
            "0002_sor_v3_strategy_group_capacity",
            SEED_IDENTITY,
        ),
        ("certify_flat", TARGET_RELEASE),
        ("probe_exchange", TARGET_RELEASE),
        ("read_current_release",),
        ("read_release_marker", TARGET_RELEASE, ".brc-runtime-commit"),
        ("read_release_marker", TARGET_RELEASE, ".brc-schema-revision"),
        ("read_release_marker", TARGET_RELEASE, ".brc-seed-identity"),
        ("start_services", SAFETY_SERVICES),
        ("start_services", (ENTRY_SERVICE,)),
        ("services_active", ALL_SERVICES),
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
            "0002_sor_v3_strategy_group_capacity",
            ticket_ids,
        ),
        (
            "activate_release",
            TARGET_RELEASE,
            TARGET_COMMIT,
            "0002_sor_v3_strategy_group_capacity",
            SEED_IDENTITY,
        ),
        ("certify_protected", TARGET_RELEASE),
        (
            "probe_protected_exchange",
            TARGET_RELEASE,
            ticket_ids,
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
            "0002_sor_v3_strategy_group_capacity",
            ticket_id,
        ),
        (
            "activate_release",
            TARGET_RELEASE,
            TARGET_COMMIT,
            "0002_sor_v3_strategy_group_capacity",
            SEED_IDENTITY,
        ),
        ("certify_closure", TARGET_RELEASE, ticket_id),
        ("probe_exchange", TARGET_RELEASE),
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


def test_protected_release_accepts_missing_and_null_optional_tp1_fill_quantity() -> None:
    ticket_ids = ("ticket:bnb",)
    backend = FakeDeploymentBackend(
        protected_ticket_ids=ticket_ids,
        certification_omits_tp1_fill_quantity=True,
        probe_tp1_fill_quantity=None,
    )

    result = deploy_tokyo_release(
        backend,
        _plan(
            enable_entry=False,
            protected_ticket_ids=ticket_ids,
        ),
    )

    assert result.status == "pass"
    assert ("stop_services", ALL_SERVICES) in backend.calls


def test_protected_release_refuses_non_null_tp1_fill_quantity_difference() -> None:
    ticket_ids = ("ticket:bnb",)
    backend = FakeDeploymentBackend(
        protected_ticket_ids=ticket_ids,
        probe_tp1_fill_quantity="2",
    )

    with pytest.raises(DeploymentBlocked, match="exact protected exchange facts differ"):
        deploy_tokyo_release(
            backend,
            _plan(
                enable_entry=False,
                protected_ticket_ids=ticket_ids,
            ),
        )

    assert not any(call[0] == "stop_services" for call in backend.calls)


def test_failed_protected_postflight_restores_safety_workers_with_entry_fenced() -> None:
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

    assert backend.calls[-2:] == [
        ("fence_entry",),
        ("start_services", SAFETY_SERVICES),
    ]
    assert backend.entry_fenced is True


def _plan(
    *,
    enable_entry: bool,
    protected_ticket_ids: tuple[str, ...] = (),
    closure_ticket_id: str | None = None,
) -> DeploymentPlan:
    return DeploymentPlan(
        target_commit=TARGET_COMMIT,
        target_release=TARGET_RELEASE,
        schema_revision="0002_sor_v3_strategy_group_capacity",
        expected_configured_leverage=5,
        enable_entry=enable_entry,
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
        certification_omits_tp1_fill_quantity: bool = False,
        probe_tp1_fill_quantity: str | None = "1",
        rule_instrument_ids: tuple[str, ...] = TARGET_EXCHANGE_INSTRUMENT_IDS,
        probe_manifest: tuple[str, ...] = TARGET_EXCHANGE_INSTRUMENT_IDS,
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
        self.certification_omits_tp1_fill_quantity = (
            certification_omits_tp1_fill_quantity
        )
        self.probe_tp1_fill_quantity = probe_tp1_fill_quantity
        self.rule_instrument_ids = rule_instrument_ids
        self.probe_manifest = probe_manifest
        self.fail_at = fail_at
        self.protected_certification_calls = 0
        self.calls: list[tuple[object, ...]] = []
        self.current_release = CURRENT_RELEASE
        self.runtime_commit = CURRENT_COMMIT
        self.active_services = set(ALL_SERVICES)
        self.entry_fenced = False

    def read_current_release(self) -> str:
        self.calls.append(("read_current_release",))
        return self.current_release

    def certify_flat(self, release: str) -> Mapping[str, object]:
        self.calls.append(("certify_flat", release))
        return {
            "status": "pass",
            "runtime_identity": {
                "runtime_commit": self.runtime_commit,
                "schema_revision": "0002_sor_v3_strategy_group_capacity",
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
                "schema_revision": "0002_sor_v3_strategy_group_capacity",
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
            payload["protected_tickets"] = self._protected_ticket_facts(
                omit_tp1_fill_quantity=self.certification_omits_tp1_fill_quantity,
            )
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
                "schema_revision": "0002_sor_v3_strategy_group_capacity",
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
            "probe_manifest": list(self.probe_manifest),
        }
        if self.include_exact_protected_facts:
            payload["protected_tickets"] = self._protected_ticket_facts(
                recorded_tp1_fill_quantity=self.probe_tp1_fill_quantity,
            )
        return payload

    def probe_protected_exchange(
        self,
        release: str,
        protected_tickets: list[object],
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
            )
        )
        return self._probe_payload()

    def _protected_ticket_facts(
        self,
        *,
        omit_tp1_fill_quantity: bool = False,
        recorded_tp1_fill_quantity: str | None = "1",
    ) -> list[dict[str, object]]:
        tickets = [
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
                "recorded_tp1_fill_quantity": recorded_tp1_fill_quantity,
            }
            for index, ticket_id in enumerate(self.protected_ticket_ids, start=1)
        ]
        if omit_tp1_fill_quantity:
            for ticket in tickets:
                ticket.pop("recorded_tp1_fill_quantity")
        return tickets

    def read_release_marker(self, release: str, marker: str) -> str:
        self.calls.append(("read_release_marker", release, marker))
        if marker == ".brc-runtime-commit":
            return TARGET_COMMIT if release == TARGET_RELEASE else CURRENT_COMMIT
        if marker == ".brc-schema-revision":
            return "0002_sor_v3_strategy_group_capacity"
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
        self.entry_fenced = True

    def unfence_entry(self) -> None:
        self.calls.append(("unfence_entry",))
        self.entry_fenced = False

    def entry_is_inactive_disabled_and_fenced(self) -> bool:
        self.calls.append(("entry_is_inactive_disabled_and_fenced",))
        return ENTRY_SERVICE not in self.active_services and self.entry_fenced
