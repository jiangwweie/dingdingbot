from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.trading_kernel.application.install_strategy_universe import (
    OwnerUniverseConfigurationRequest,
    UniverseControlConflict,
    UniverseCurrent,
    UniverseInstallContext,
    UniverseInstallResult,
    UniverseInstallStatus,
    configure_strategy_universe_by_owner,
)


class _OwnerControls:
    def __init__(self) -> None:
        self.authorizations = []

    async def get_authorization_by_idempotency_key(self, _key: str):
        return None

    async def add_authorization(self, authorization) -> None:
        self.authorizations.append(authorization)


class _Universes:
    def __init__(self) -> None:
        self.install_requests = []
        self.current = UniverseCurrent(
            event_spec_id="event_spec:SOR-US-EQ-PERP-001:SOR-US-LONG-15M:v1",
            universe_version_id="universe:SOR-US-LONG-15M:v1",
            semantic_digest="sha256:" + "1" * 64,
            activation_generation=1,
            activated_at_ms=1_799_999_000_000,
        )

    async def resolve_install_context(self, **_kwargs):
        return UniverseInstallContext(
            event_spec_id=self.current.event_spec_id,
            owner_policy_id="policy-tradfi-observe",
        )

    async def get_current(self, _event_spec_id: str):
        return self.current

    async def install(self, request):
        self.install_requests.append(request)
        return UniverseInstallResult(
            status=UniverseInstallStatus.INSTALLED,
            universe=None,
            lifecycle_state="warming",
            inserted_instrument_count=0,
            inserted_version_count=1,
            inserted_member_count=2,
            inserted_scope_count=2,
        )


def _request(**overrides: object) -> OwnerUniverseConfigurationRequest:
    values = {
        "runtime_profile_id": "tradfi-equity-observe-v1",
        "event_id": "SOR-US-LONG-15M",
        "exchange_instrument_ids": (
            "binance-usdm:AAPLUSDT:perpetual",
            "binance-usdm:GOOGLUSDT:perpetual",
        ),
        "expected_base_universe_version_id": "universe:SOR-US-LONG-15M:v1",
        "reason": "调整美股多头观察池",
        "idempotency_key": "owner-request:universe:1",
        "owner_identity": "owner",
        "installed_at_ms": 1_800_000_000_000,
    }
    values.update(overrides)
    return OwnerUniverseConfigurationRequest.model_validate(values)


async def test_owner_universe_configuration_persists_step_up_authorization() -> None:
    owner_controls = _OwnerControls()
    universes = _Universes()
    uow = SimpleNamespace(
        owner_controls=owner_controls,
        strategy_universes=universes,
    )

    result = await configure_strategy_universe_by_owner(uow, _request())

    assert result.status is UniverseInstallStatus.INSTALLED
    assert len(universes.install_requests) == 1
    assert len(owner_controls.authorizations) == 1
    authorization = owner_controls.authorizations[0]
    assert authorization.purpose == "universe_configure"
    assert authorization.authentication_strength == "totp_step_up"
    assert authorization.target_scope["event_id"] == "SOR-US-LONG-15M"


async def test_owner_universe_configuration_rejects_stale_base_before_write() -> None:
    owner_controls = _OwnerControls()
    universes = _Universes()
    uow = SimpleNamespace(
        owner_controls=owner_controls,
        strategy_universes=universes,
    )

    with pytest.raises(UniverseControlConflict, match="universe_base_changed"):
        await configure_strategy_universe_by_owner(
            uow,
            _request(expected_base_universe_version_id="universe:stale"),
        )

    assert universes.install_requests == []
    assert owner_controls.authorizations == []
