from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.trading_kernel.application.certify_universe_instrument import (
    CertifyUniverseInstrumentRequest,
    InstrumentCertificationSnapshot,
    certify_universe_instrument,
)
from src.trading_kernel.application.ports import (
    InstrumentCertificationTarget,
    MonitorOwnerStatus,
    MonitorStateRecord,
)
from src.trading_kernel.application.runtime_facts import InstrumentRulesFacts
from src.trading_kernel.domain.cross_margin_stress import MaintenanceMarginBracket
from src.trading_kernel.domain.entry_admission_snapshot import AdmissionOwnership
from src.trading_kernel.domain.instrument_certification import (
    InstrumentCertificationFacts,
)
from src.trading_kernel.infrastructure.venue_adapter import (
    InstrumentCertificationSnapshotContradiction,
)


class _State:
    def __init__(self, *, existing_monitor: bool = False) -> None:
        self.active_transactions = 0
        self.existing_monitor = existing_monitor
        self.persisted: list[dict[str, object]] = []
        self.rules: list[dict[str, object]] = []
        self.monitors: list[MonitorStateRecord] = []

    def factory(self):
        return _UnitOfWork(self)


class _UnitOfWork:
    def __init__(self, state: _State) -> None:
        self.state = state
        self.entry_admission = _OwnershipRepository()
        self.strategy_universes = _UniverseRepository(state)
        self.signals = _RulesRepository(state)
        self.monitors = _MonitorRepository(state)
        self.exchange_commands = _NoUnknownCommands()
        self.aggregates = _SafetyAggregateRepository()

    async def __aenter__(self):
        self.state.active_transactions += 1
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        del exc_type, exc, traceback
        self.state.active_transactions -= 1


class _OwnershipRepository:
    async def read_admission_ownership(self, **kwargs):
        del kwargs
        return AdmissionOwnership()


class _NoUnknownCommands:
    async def get_one_unknown(self):
        return None


class _SafetyAggregateRepository:
    async def claim_next_critical_reconciliation_work(self, *, now_ms):
        del now_ms
        return object()


class _UniverseRepository:
    def __init__(self, state: _State) -> None:
        self.state = state

    async def save_instrument_certification(self, **kwargs):
        self.state.persisted.append(kwargs)


class _RulesRepository:
    def __init__(self, state: _State) -> None:
        self.state = state

    async def upsert_instrument_rules(self, **kwargs):
        self.state.rules.append(kwargs)


class _MonitorRepository:
    def __init__(self, state: _State) -> None:
        self.state = state

    async def get(self, monitor_key):
        if not self.state.existing_monitor:
            return None
        return self.state.monitors[-1]

    async def save_if_changed(self, state):
        self.state.monitors.append(state)
        return state


class _ReadonlySource:
    def __init__(
        self,
        state: _State,
        *,
        changes: dict[str, object] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.state = state
        self.changes = changes or {}
        self.error = error
        self.requests: list[object] = []

    async def read_instrument_certification(self, request):
        assert self.state.active_transactions == 0
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        values = _facts(observed_at_ms=request.observed_at_ms).model_dump(
            mode="python"
        )
        values.update(self.changes)
        facts = InstrumentCertificationFacts.model_validate(
            values
        )
        return InstrumentCertificationSnapshot(
            facts=facts,
            instrument_rules=_rules(observed_at_ms=request.observed_at_ms),
        )


class _MissingRulesSource:
    async def read_instrument_certification(self, request):
        return InstrumentCertificationSnapshot(
            facts=InstrumentCertificationFacts(
                runtime_profile_id=request.target.runtime_profile_id,
                exchange_instrument_id=request.target.exchange_instrument_id,
                product_status="trading",
                tick_size=Decimal("0.1"),
                step_size=Decimal("0.001"),
                min_qty=Decimal("0.001"),
                min_notional=None,
                position_mode="independent_sides",
                margin_mode="cross",
                configured_leverage=5,
                notional_coefficient_certified=True,
                unowned_position_qty=Decimal(0),
                unowned_open_order_count=0,
                observed_at_ms=request.observed_at_ms,
            ),
            instrument_rules=None,
        )


class _SchemaDriftSource:
    async def read_instrument_certification(self, request):
        facts = _facts(observed_at_ms=request.observed_at_ms).model_dump(
            mode="python"
        )
        facts["unknown_venue_field"] = "drift"
        return InstrumentCertificationSnapshot.model_validate(
            {
                "facts": facts,
                "instrument_rules": _rules(
                    observed_at_ms=request.observed_at_ms
                ),
            }
        )


class _IdentityDriftSource:
    async def read_instrument_certification(self, request):
        values = _facts(observed_at_ms=request.observed_at_ms).model_dump(
            mode="python"
        )
        values["runtime_profile_id"] = "profile:wrong"
        return InstrumentCertificationSnapshot(
            facts=InstrumentCertificationFacts.model_validate(values),
            instrument_rules=_rules(observed_at_ms=request.observed_at_ms),
        )


@pytest.mark.asyncio
async def test_certification_reads_venue_without_open_transaction_and_persists_eligible() -> None:
    """Catches a Venue call made while a certification claim transaction is open."""

    state = _State()
    source = _ReadonlySource(state)

    result = await certify_universe_instrument(
        state.factory,
        source,
        _request(),
    )

    assert result.certification.status == "eligible"
    assert len(source.requests) == 1
    assert len(state.persisted) == 1
    assert len(state.rules) == 1
    assert state.monitors == []
    assert state.active_transactions == 0


@pytest.mark.asyncio
async def test_owner_action_persists_needs_intervention_monitor_once() -> None:
    """Catches an account-setting blocker being downgraded to a transient retry."""

    state = _State()

    result = await certify_universe_instrument(
        state.factory,
        _ReadonlySource(state, changes={"configured_leverage": 3}),
        _request(),
    )

    assert result.certification.status == "owner_action_required"
    assert result.certification.blocker_code == "configured_leverage_mismatch"
    assert len(state.rules) == 1
    assert len(state.monitors) == 1
    assert state.monitors[0].owner_status is MonitorOwnerStatus.NEEDS_INTERVENTION
    assert state.monitors[0].summary.startswith("OWNER_ACTION_REQUIRED:")


@pytest.mark.asyncio
async def test_transient_read_failure_releases_claim_without_owner_monitor() -> None:
    """Catches a Venue timeout becoming an Owner action or a permanent lease."""

    state = _State()

    result = await certify_universe_instrument(
        state.factory,
        _ReadonlySource(state, error=TimeoutError("readonly timeout")),
        _request(),
    )

    assert result.certification.status == "temporarily_unavailable"
    assert result.certification.blocker_code == "readonly_facts_unavailable"
    assert state.rules == []
    assert state.monitors == []
    assert state.persisted[0]["next_check_at_ms"] == 31_000


@pytest.mark.asyncio
async def test_projection_contradiction_blocks_only_the_instrument_and_releases_claim() -> None:
    """Catches an ownership contradiction escaping and killing Reconciliation."""

    state = _State()

    result = await certify_universe_instrument(
        state.factory,
        _ReadonlySource(
            state,
            error=InstrumentCertificationSnapshotContradiction(
                "projected_position_exceeds_venue"
            ),
        ),
        _request(),
    )

    assert result.certification.status == "temporarily_unavailable"
    assert (
        result.certification.blocker_code
        == "projected_position_exceeds_venue"
    )
    assert state.rules == []
    assert state.monitors == []
    assert state.persisted[0]["next_check_at_ms"] == 31_000


@pytest.mark.asyncio
async def test_missing_order_rule_is_owner_action_not_transient_retry() -> None:
    """Catches deterministic raw product-rule absence being hidden as retry."""

    state = _State()

    result = await certify_universe_instrument(
        state.factory,
        _MissingRulesSource(),
        _request(),
    )

    assert result.certification.status == "owner_action_required"
    assert result.certification.blocker_code == "missing_order_rule"
    assert state.rules == []
    assert state.monitors[0].owner_status is MonitorOwnerStatus.NEEDS_INTERVENTION


@pytest.mark.asyncio
async def test_pydantic_unknown_field_drift_fails_closed_without_transient_write() -> None:
    """Catches an upstream schema drift being persisted as retryable downtime."""

    state = _State()

    with pytest.raises(ValidationError, match="unknown_venue_field"):
        await certify_universe_instrument(
            state.factory,
            _SchemaDriftSource(),
            _request(),
        )

    assert state.persisted == []
    assert state.monitors == []


@pytest.mark.asyncio
async def test_snapshot_identity_drift_fails_closed_without_transient_write() -> None:
    """Catches a wrong profile/instrument snapshot being downgraded to retry."""

    state = _State()

    with pytest.raises(ValueError, match="identity mismatch"):
        await certify_universe_instrument(
            state.factory,
            _IdentityDriftSource(),
            _request(),
        )

    assert state.persisted == []
    assert state.monitors == []


@pytest.mark.asyncio
async def test_eligible_recheck_resolves_an_existing_owner_monitor() -> None:
    """Catches a recovered account setting leaving stale intervention state."""

    state = _State()
    blocked = await certify_universe_instrument(
        state.factory,
        _ReadonlySource(state, changes={"margin_mode": "isolated"}),
        _request(),
    )
    assert blocked.certification.status == "owner_action_required"
    state.existing_monitor = True

    resolved = await certify_universe_instrument(
        state.factory,
        _ReadonlySource(state),
        _request(now_ms=6_000),
    )

    assert resolved.certification.status == "eligible"
    assert len(state.monitors) == 2
    assert state.monitors[-1].owner_status is MonitorOwnerStatus.RUNNING
    assert state.monitors[-1].summary == "instrument_certification:resolved"


def _request(*, now_ms: int = 1_000) -> CertifyUniverseInstrumentRequest:
    return CertifyUniverseInstrumentRequest(
        target=InstrumentCertificationTarget(
            runtime_profile_id="profile:main",
            venue_id="binance-usdm",
            account_id="account:main",
            universe_version_id="universe:event:v1",
            exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
            lease_owner="reconciliation-worker",
            lease_expires_at_ms=61_000,
        ),
        now_ms=now_ms,
        timeout_seconds=1,
        required_leverage=5,
        required_margin_mode="cross",
        valid_for_ms=60_000,
        eligible_check_interval_ms=60_000,
        owner_action_check_interval_ms=300_000,
        transient_retry_interval_ms=30_000,
    )


def _facts(*, observed_at_ms: int = 1_000) -> InstrumentCertificationFacts:
    return InstrumentCertificationFacts(
        runtime_profile_id="profile:main",
        exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
        product_status="trading",
        tick_size=Decimal("0.1"),
        step_size=Decimal("0.001"),
        min_qty=Decimal("0.001"),
        min_notional=Decimal(5),
        position_mode="independent_sides",
        margin_mode="cross",
        configured_leverage=5,
        notional_coefficient_certified=True,
        unowned_position_qty=Decimal(0),
        unowned_open_order_count=0,
        observed_at_ms=observed_at_ms,
    )


def _rules(*, observed_at_ms: int = 1_000) -> InstrumentRulesFacts:
    return InstrumentRulesFacts(
        exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
        quantity_step=Decimal("0.001"),
        price_tick=Decimal("0.1"),
        min_quantity=Decimal("0.001"),
        min_notional=Decimal(5),
        exchange_max_leverage=125,
        maintenance_margin_brackets=(
            MaintenanceMarginBracket(
                bracket_id="1",
                notional_floor=Decimal(0),
                notional_cap=Decimal(50000),
                maintenance_margin_rate=Decimal("0.004"),
                maintenance_amount=Decimal(0),
            ),
        ),
        maintenance_margin_brackets_digest=(
            "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        ),
        notional_coefficient=Decimal(1),
        notional_coefficient_certified=True,
        observed_at_ms=observed_at_ms,
        valid_until_ms=observed_at_ms + 60_000,
    )
