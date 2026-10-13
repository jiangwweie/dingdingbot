from decimal import Decimal

import pytest

from src.trading_kernel.application.coordinate_selection_materialization import (
    AuthorityGapAuditEvaluationRequest,
    MaterializationPlanningFacts,
    _build_first_dynamic_no_change_authority,
    _pair_scopes,
    _sor_detector_semantic_digest,
    plan_authority_gap_audit_window,
    plan_selection_materialization,
)
from src.trading_kernel.domain.market import ClosedCandle
from src.trading_kernel.domain.orb_session_selection import (
    ORB_EVENT_SPEC_IDS,
    ORB_SELECTION_SPEC_ID,
)
from src.trading_kernel.domain.owner_control import StrategyEntryState
from src.trading_kernel.domain.selection_authority import (
    AuthorityGapAudit,
    AuthorityGapAuditKind,
    AuthorityGapAuditState,
    AuthorityGapScope,
    AuthorityOutcome,
    SelectionControl,
    SelectionMode,
    UniverseAuthorityPair,
)
from src.trading_kernel.interfaces.authority_gap_audit_source import (
    PublicMarketAuthorityGapAuditSource,
)

D = 1704067200000
H = 3600000


def pending_audit():
    return AuthorityGapAudit(
        authority_gap_audit_id="gap:orb:test",
        selection_spec_id=ORB_SELECTION_SPEC_ID,
        session_start_ms=D,
        gap_kind=AuthorityGapAuditKind.ENTRY_VACUUM,
        source_entry_vacuum_id="vacuum:orb:test",
        source_generation_id="generation:orb:test",
        proposed_authority_outcome=AuthorityOutcome.ACTIVE_NEW,
        unauthorized_from_close_time_ms=D + 2 * H,
        audited_through_close_time_ms=None,
        first_eligible_close_time_ms=None,
        audit_scope_digest=None,
        audit_result_digest=None,
        detector_semantic_digest="sha256:" + "a" * 64,
        state=AuthorityGapAuditState.PENDING,
        first_blocker=None,
        projection_version=1,
    )


@pytest.mark.parametrize(
    "now,first,through",
    [(D + H + 1, D + 2 * H, D + H), (D + 2 * H, D + 3 * H, D + 2 * H)],
)
def test_hourly_gap_uses_future_hour_and_allows_pre_entry_empty_window(
    now, first, through
):
    audit = pending_audit()
    plan = plan_authority_gap_audit_window(audit, now_ms=now)
    assert plan.disposition == "READY"
    assert plan.first_eligible_close_time_ms == first
    assert plan.audited_through_close_time_ms == through
    complete = AuthorityGapAudit.model_validate(
        {
            **audit.model_dump(),
            "state": AuthorityGapAuditState.COMPLETE,
            "projection_version": 2,
            "audited_through_close_time_ms": through,
            "first_eligible_close_time_ms": first,
            "audit_scope_digest": "sha256:" + "b" * 64,
            "audit_result_digest": "sha256:" + "c" * 64,
        }
    )
    assert complete.first_eligible_close_time_ms == first


def test_hourly_gap_cannot_grant_final_midnight_close():
    assert (
        plan_authority_gap_audit_window(pending_audit(), now_ms=D + 23 * H).disposition
        == "SESSION_EXPIRED"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "through,expected", [(D + H, (None, None)), (D + 2 * H, (D + 2 * H, None))]
)
async def test_hourly_gap_replays_only_matching_pair_and_hourly_path(through, expected):
    class Market:
        async def fetch_closed_candles(self, request):
            assert request.timeframe == "1h" and request.limit == (through - D) // H
            return tuple(
                ClosedCandle(
                    open_time_ms=D + i * H,
                    close_time_ms=D + (i + 1) * H,
                    open=Decimal(100),
                    high=Decimal(103 if i else 101),
                    low=Decimal(99),
                    close=Decimal(102 if i else 100),
                    volume=Decimal(100),
                )
                for i in range(request.limit)
            )

    scopes = tuple(
        AuthorityGapScope(event_spec_id=e, exchange_instrument_id="BTCUSDT")
        for e in ORB_EVENT_SPEC_IDS
    )
    results = await PublicMarketAuthorityGapAuditSource(
        Market()
    ).evaluate_authority_gap(
        AuthorityGapAuditEvaluationRequest(
            audit=pending_audit(), scopes=scopes, audited_through_close_time_ms=through
        )
    )
    assert tuple(r.first_natural_trigger_at_ms for r in results) == expected


def planning_facts(**updates):
    values = {
        "selection_spec_id": ORB_SELECTION_SPEC_ID,
        "strategy_group_id": "SOR-1H-001",
        "session_start_ms": D,
        "now_ms": D + H + 1,
        "selection_mode": SelectionMode.DYNAMIC_SELECTION,
        "pending_selection_mode": None,
        "pending_effective_session_start_ms": None,
        "owner_entry_state": StrategyEntryState.ENABLED,
        "current_long_members": (),
        "current_short_members": (),
        "snapshot": None,
        "selected_members": (),
        "continuity_exists": False,
        "open_vacuum": False,
    }
    return MaterializationPlanningFacts.model_validate({**values, **updates})


def test_hourly_materialization_retains_earliest_owner_intent_on_later_day():
    plan = plan_selection_materialization(
        planning_facts(
            selection_mode=SelectionMode.STATIC_BASELINE,
            pending_selection_mode=SelectionMode.DYNAMIC_SELECTION,
            pending_effective_session_start_ms=D - 24 * H,
        )
    )
    assert plan.disposition == "KEEP_STATIC_PENDING_DYNAMIC"


@pytest.mark.parametrize(
    "now,first,audit", [(D + H + 1, D + 2 * H, False), (D + 2 * H, D + 3 * H, True)]
)
def test_hourly_continuity_planning_uses_exact_entry_clock(now, first, audit):
    plan = plan_selection_materialization(planning_facts(now_ms=now))
    assert plan.disposition == "PRE_FENCE_CONTINUITY"
    assert (
        plan.first_eligible_close_time_ms == first and plan.requires_gap_audit == audit
    )


def test_hourly_audit_scope_and_detector_digest_never_alias_old_pair():
    scopes = _pair_scopes(
        selection_spec_id=ORB_SELECTION_SPEC_ID,
        long_members=("BTCUSDT",),
        short_members=("BTCUSDT",),
    )
    assert tuple(s.event_spec_id for s in scopes) == ORB_EVENT_SPEC_IDS
    assert (
        _sor_detector_semantic_digest(ORB_SELECTION_SPEC_ID)
        != _sor_detector_semantic_digest()
    )


def test_hourly_first_no_change_freezes_owner_epoch_and_activating_control_version():
    control = SelectionControl(
        strategy_group_id="SOR-1H-001",
        selection_spec_id=ORB_SELECTION_SPEC_ID,
        selection_mode=SelectionMode.STATIC_BASELINE,
        pending_selection_mode=SelectionMode.DYNAMIC_SELECTION,
        pending_effective_period_anchor_ms=D - 24 * H,
        pending_authorization_id="owner:orb:first",
        control_version=2,
        rollback_baseline_id="baseline:orb",
        selection_epoch_id="epoch:orb:first",
        updated_at_ms=D,
    )
    authority = _build_first_dynamic_no_change_authority(
        selection_spec_id=ORB_SELECTION_SPEC_ID,
        session_start_ms=D,
        selection_snapshot_id="snapshot:orb:test",
        pair=UniverseAuthorityPair(
            long_universe_version_id="orb:long", short_universe_version_id="orb:short"
        ),
        owner_control_version=2,
        current_projection=None,
        created_at_ms=D + H + 1,
        selection_control=control,
    )
    assert authority.selection_epoch_id == control.selection_epoch_id
    assert authority.selection_control_version == 3
    assert authority.activation_authorization_id == "owner:orb:first"
    assert (
        authority.expires_at_ms == D + 24 * H
        and authority.first_eligible_close_time_ms == D + 2 * H
    )
