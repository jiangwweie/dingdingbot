"""Frozen independent hourly ORB identities and daily clocks; no trading grants."""

from __future__ import annotations

from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.trading_kernel.domain.instrument_selection import (
    CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS,
    DAY_MS,
    HOUR_MS,
    SelectionSnapshot,
)

ORB_STRATEGY_GROUP_ID: Final = "SOR-1H-001"
ORB_STRATEGY_VERSION_ID: Final = "sgv:SOR-1H-001:v1"
ORB_LONG_EVENT_SPEC_ID = "event_spec:SOR-1H-001:SOR-1H-LONG:v1"
ORB_SHORT_EVENT_SPEC_ID = "event_spec:SOR-1H-001:SOR-1H-SHORT:v1"
ORB_EVENT_SPEC_IDS = (ORB_LONG_EVENT_SPEC_ID, ORB_SHORT_EVENT_SPEC_ID)
ORB_SELECTION_SPEC_ID: Final = "SOR_1H_OR_ATR_DYNAMIC_V1"
ORB_SELECTION_KIND: Final = "orb_session_dynamic_v1"
ORB_STATIC_MEMBERS = tuple(
    sorted(
        f"binance-usdm:{s}USDT:perpetual"
        for s in ("BTC", "ETH", "BNB", "SOL", "XRP", "DOGE", "ADA")
    )
)


class OrbSessionSelectionSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    selection_spec_id: Literal["SOR_1H_OR_ATR_DYNAMIC_V1"] = ORB_SELECTION_SPEC_ID
    strategy_group_id: Literal["SOR-1H-001"] = ORB_STRATEGY_GROUP_ID
    strategy_version_id: Literal["sgv:SOR-1H-001:v1"] = ORB_STRATEGY_VERSION_ID
    selection_kind: Literal["orb_session_dynamic_v1"] = ORB_SELECTION_KIND
    event_spec_ids: tuple[str, ...] = ORB_EVENT_SPEC_IDS
    candidate_ids: tuple[str, ...] = CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS
    selected_count_max: Literal[7] = 7
    near_count_max: Literal[7] = 7
    input_window_bars: Literal[96] = 96
    opening_range_bars: Literal[4] = 4
    pre_or_atr_bars: Literal[14] = 14
    activity_floor_quote_usdt: Literal[20000000] = 20000000
    decimal_precision: Literal[38] = 38
    decimal_rounding: Literal["ROUND_HALF_EVEN"] = "ROUND_HALF_EVEN"
    entry_interval_ms: Literal[3600000] = 3600000
    materialization_timeout_ms: Literal[1800000] = 1800000

    @model_validator(mode="after")
    def _exact_inputs(self) -> OrbSessionSelectionSpec:
        if (
            self.event_spec_ids != ORB_EVENT_SPEC_IDS
            or self.candidate_ids != CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS
        ):
            raise ValueError(
                "hourly ORB requires exact independent Events and canonical Candidate24"
            )
        return self


class InstalledOrbSessionSelectionSpec(OrbSessionSelectionSpec):
    installed_at_ms: int = Field(gt=0, exclude=True)

    @property
    def candidate_exchange_instrument_ids(self) -> tuple[str, ...]:
        return self.candidate_ids

    @property
    def algorithm_semantic_digest(self) -> str:
        from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest

        return canonical_digest(self.model_dump(mode="json"))

    @property
    def eligibility_not_before_offset_utc_seconds(self) -> int:
        return 7200


class OrbSessionPeriod(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    session_start_ms: int
    feature_cutoff_at_ms: int
    prepare_not_before_ms: int
    eligibility_not_before_ms: int
    snapshot_expires_at_ms: int
    trading_expires_at_ms: int

    @model_validator(mode="after")
    def _exact_period(self) -> OrbSessionPeriod:
        d = self.session_start_ms
        if (
            d <= 0
            or d % DAY_MS
            or (
                self.feature_cutoff_at_ms,
                self.prepare_not_before_ms,
                self.eligibility_not_before_ms,
                self.snapshot_expires_at_ms,
                self.trading_expires_at_ms,
            )
            != (
                d + HOUR_MS,
                d + HOUR_MS,
                d + 2 * HOUR_MS,
                d + DAY_MS + HOUR_MS,
                d + DAY_MS,
            )
        ):
            raise ValueError(
                "hourly ORB period requires exact UTC day, cutoff and eligibility clocks"
            )
        return self


def build_orb_session_period(session_start_ms: int) -> OrbSessionPeriod:
    d = session_start_ms
    return OrbSessionPeriod(
        session_start_ms=d,
        feature_cutoff_at_ms=d + HOUR_MS,
        prepare_not_before_ms=d + HOUR_MS,
        eligibility_not_before_ms=d + 2 * HOUR_MS,
        snapshot_expires_at_ms=d + DAY_MS + HOUR_MS,
        trading_expires_at_ms=d + DAY_MS,
    )


def next_orb_eligible_close(*, session_start_ms: int, now_ms: int) -> int | None:
    p = build_orb_session_period(session_start_ms)
    if now_ms < p.session_start_ms:
        raise ValueError("hourly ORB grant clock precedes its Session")
    first = max(p.eligibility_not_before_ms, (now_ms // HOUR_MS + 1) * HOUR_MS)
    return first if first < p.trading_expires_at_ms else None


class OrbSessionSelectionSnapshot(SelectionSnapshot):
    model_config = ConfigDict(frozen=True, extra="forbid")
    selection_snapshot_id: str
    selection_spec_id: Literal["SOR_1H_OR_ATR_DYNAMIC_V1"] = ORB_SELECTION_SPEC_ID
    strategy_group_id: Literal["SOR-1H-001"] = ORB_STRATEGY_GROUP_ID
    strategy_version_id: Literal["sgv:SOR-1H-001:v1"] = ORB_STRATEGY_VERSION_ID
    selection_epoch_id: str
    session_start_ms: int
    feature_cutoff_at_ms: int
    eligibility_not_before_ms: int
    expires_at_ms: int
    decision_at_ms: int
    source_observed_at_ms: int
    created_at_ms: int
    candidate_count: Literal[24] = 24
    ready_count: int
    selected_count: int
    source_semantic_digest: str
    selection_semantic_digest: str

    @model_validator(mode="after")
    def _validate_snapshot(self) -> OrbSessionSelectionSnapshot:
        period = build_orb_session_period(self.session_start_ms)
        require_orb_epoch(self.selection_epoch_id)
        if self.selection_snapshot_id != orb_snapshot_identity(
            self.selection_epoch_id, self.session_start_ms
        ):
            raise ValueError(
                "hourly ORB Snapshot identity differs from its exact epoch and Session"
            )
        if (
            self.feature_cutoff_at_ms,
            self.eligibility_not_before_ms,
            self.expires_at_ms,
        ) != (
            period.feature_cutoff_at_ms,
            period.eligibility_not_before_ms,
            period.snapshot_expires_at_ms,
        ):
            raise ValueError("hourly ORB Snapshot time mismatch")
        if (
            not period.feature_cutoff_at_ms
            <= self.decision_at_ms
            <= self.source_observed_at_ms
            <= self.created_at_ms
            < self.expires_at_ms
        ):
            raise ValueError(
                "hourly ORB source cannot precede cutoff or commit after expiry"
            )
        if not 0 <= self.ready_count <= 24 or self.selected_count != min(
            7, self.ready_count
        ):
            raise ValueError("hourly ORB member counts differ from frozen rank")
        for d in (self.source_semantic_digest, self.selection_semantic_digest):
            if len(d) != 71 or not d.startswith("sha256:"):
                raise ValueError(
                    "hourly ORB Snapshot requires canonical source digests"
                )
            int(d[7:], 16)
        return self


def require_orb_epoch(epoch: str) -> None:
    if (
        not epoch.strip()
        or epoch != epoch.strip()
        or len(epoch) > 160
        or epoch == "sor-v0"
    ):
        raise ValueError("hourly ORB requires independent bounded epoch")


def orb_snapshot_identity(epoch: str, session_start_ms: int) -> str:
    from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest

    require_orb_epoch(epoch)
    return (
        "selection:orb:"
        + canonical_digest(
            {
                "selection_spec_id": ORB_SELECTION_SPEC_ID,
                "selection_epoch_id": epoch,
                "session_start_ms": session_start_ms,
            }
        )[7:]
    )


from src.trading_kernel.domain.instrument_selection import (
    SelectionMemberDecision,
    SelectionSourceIntegrityError,
    SelectionSourceWindow,
    compute_opening_range_member_decisions,
)


class OrbSessionSelectionComputation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    snapshot: OrbSessionSelectionSnapshot
    member_decisions: tuple[SelectionMemberDecision, ...]

    @model_validator(mode="after")
    def _exact_members(self) -> OrbSessionSelectionComputation:
        if tuple(
            m.exchange_instrument_id for m in self.member_decisions
        ) != CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS or any(
            m.selection_snapshot_id != self.snapshot.selection_snapshot_id
            or m.selection_spec_id != ORB_SELECTION_SPEC_ID
            or m.session_start_ms != self.snapshot.session_start_ms
            for m in self.member_decisions
        ):
            raise ValueError("hourly ORB members do not belong to exact Snapshot")
        return self


def compute_orb_selection(
    *,
    spec: OrbSessionSelectionSpec,
    period: OrbSessionPeriod,
    selection_epoch_id: str,
    source_windows: tuple[SelectionSourceWindow, ...],
    decision_at_ms: int,
    source_observed_at_ms: int,
    created_at_ms: int,
) -> OrbSessionSelectionComputation:
    from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest

    spec = OrbSessionSelectionSpec.model_validate(spec.model_dump())
    period = OrbSessionPeriod.model_validate(period.model_dump())
    require_orb_epoch(selection_epoch_id)
    if tuple(
        sorted(w.exchange_instrument_id for w in source_windows)
    ) != spec.candidate_ids or any(
        w.input_window_start_ms != period.session_start_ms - 23 * HOUR_MS
        or w.feature_cutoff_at_ms != period.feature_cutoff_at_ms
        for w in source_windows
    ):
        raise SelectionSourceIntegrityError(
            "hourly ORB requires exact Candidate24 windows at 01:00 cutoff"
        )
    sid = orb_snapshot_identity(selection_epoch_id, period.session_start_ms)
    decisions, ready = compute_opening_range_member_decisions(
        source_windows=source_windows,
        selection_snapshot_id=sid,
        selection_spec_id=spec.selection_spec_id,
        session_start_ms=period.session_start_ms,
        feature_cutoff_at_ms=period.feature_cutoff_at_ms,
    )
    source_digest = canonical_digest(
        [[m.exchange_instrument_id, m.input_window_digest] for m in decisions]
    )
    digest = canonical_digest(
        {
            "spec": spec.model_dump(mode="json"),
            "selection_epoch_id": selection_epoch_id,
            "period": period.model_dump(),
            "source_semantic_digest": source_digest,
            "member_semantic_digests": [m.member_semantic_digest for m in decisions],
        }
    )
    snapshot = OrbSessionSelectionSnapshot(
        selection_snapshot_id=sid,
        selection_epoch_id=selection_epoch_id,
        session_start_ms=period.session_start_ms,
        feature_cutoff_at_ms=period.feature_cutoff_at_ms,
        eligibility_not_before_ms=period.eligibility_not_before_ms,
        expires_at_ms=period.snapshot_expires_at_ms,
        decision_at_ms=decision_at_ms,
        source_observed_at_ms=source_observed_at_ms,
        created_at_ms=created_at_ms,
        ready_count=ready,
        selected_count=min(7, ready),
        source_semantic_digest=source_digest,
        selection_semantic_digest=digest,
    )
    return OrbSessionSelectionComputation(snapshot=snapshot, member_decisions=decisions)


def orb_spec_semantic_digest(spec: OrbSessionSelectionSpec) -> str:
    from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest

    return canonical_digest(spec.model_dump(mode="json"))


def daily_event_spec_ids(selection_spec_id: str) -> tuple[str, str]:
    if selection_spec_id == ORB_SELECTION_SPEC_ID:
        return ORB_LONG_EVENT_SPEC_ID, ORB_SHORT_EVENT_SPEC_ID
    if selection_spec_id == "sor-dynamic-selection-v0":
        return "event_spec:SOR-001:SOR-LONG:v4", "event_spec:SOR-001:SOR-SHORT:v4"
    raise ValueError("daily ORB requires an exact installed Selection identity")


def daily_entry_interval_ms(selection_spec_id: str) -> int:
    daily_event_spec_ids(selection_spec_id)
    return HOUR_MS if selection_spec_id == ORB_SELECTION_SPEC_ID else 900000


def daily_first_offset_ms(selection_spec_id: str) -> int:
    return (
        2 * HOUR_MS
        if daily_entry_interval_ms(selection_spec_id) == HOUR_MS
        else 5 * 900000
    )


def daily_authority_expires_at(selection_spec_id: str, session_start_ms: int) -> int:
    daily_event_spec_ids(selection_spec_id)
    return (
        session_start_ms
        + DAY_MS
        + (0 if selection_spec_id == ORB_SELECTION_SPEC_ID else HOUR_MS)
    )


def next_daily_eligible_close(
    *, selection_spec_id: str, session_start_ms: int, now_ms: int
) -> int:
    interval = daily_entry_interval_ms(selection_spec_id)
    first = max(
        session_start_ms + daily_first_offset_ms(selection_spec_id),
        (now_ms // interval + 1) * interval,
    )
    if (
        selection_spec_id == ORB_SELECTION_SPEC_ID
        and first >= session_start_ms + DAY_MS
    ):
        raise ValueError("NO_ELIGIBLE_CLOSE_BEFORE_SESSION_END")
    return first


class OrbStaticSourceEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    event_spec_id: str
    position_side: Literal["long", "short"]
    universe_version_id: str
    universe_semantic_digest: str
    member_set_digest: str

    @model_validator(mode="after")
    def _exact_side(self) -> OrbStaticSourceEvent:
        if (
            self.event_spec_id
            != ORB_EVENT_SPEC_IDS[0 if self.position_side == "long" else 1]
            or not self.universe_version_id.strip()
        ):
            raise ValueError(
                "ORB Static source must reference its own exact Event and Universe"
            )
        return self


class OrbStaticRollbackBaseline(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    rollback_baseline_id: str
    strategy_group_id: Literal["SOR-1H-001"] = ORB_STRATEGY_GROUP_ID
    strategy_version_id: Literal["sgv:SOR-1H-001:v1"] = ORB_STRATEGY_VERSION_ID
    selection_spec_id: Literal["SOR_1H_OR_ATR_DYNAMIC_V1"] = ORB_SELECTION_SPEC_ID
    source_events: tuple[OrbStaticSourceEvent, ...]
    captured_at_ms: int
    semantic_digest: str

    @classmethod
    def build(
        cls, *, source_events: tuple[OrbStaticSourceEvent, ...], captured_at_ms: int
    ) -> OrbStaticRollbackBaseline:
        from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest

        if (
            tuple(e.event_spec_id for e in source_events) != ORB_EVENT_SPEC_IDS
            or captured_at_ms <= 0
        ):
            raise ValueError("ORB Static baseline requires exact LONG/SHORT references")
        digest = canonical_digest(
            {
                "selection_spec_id": ORB_SELECTION_SPEC_ID,
                "strategy_group_id": ORB_STRATEGY_GROUP_ID,
                "strategy_version_id": ORB_STRATEGY_VERSION_ID,
                "source_events": [e.model_dump() for e in source_events],
                "captured_at_ms": captured_at_ms,
            }
        )
        return cls(
            rollback_baseline_id="rollback:orb:" + digest[7:],
            source_events=source_events,
            captured_at_ms=captured_at_ms,
            semantic_digest=digest,
        )


class OrbStaticMaterializationSource(BaseModel):
    """Frozen Static baseline source for the shared pair materializer, never a Snapshot."""
    model_config=ConfigDict(frozen=True,extra='forbid')
    selection_spec_id: Literal['SOR_1H_OR_ATR_DYNAMIC_V1']=ORB_SELECTION_SPEC_ID
    strategy_group_id: Literal['SOR-1H-001']=ORB_STRATEGY_GROUP_ID
    strategy_version_id: Literal['sgv:SOR-1H-001:v1']=ORB_STRATEGY_VERSION_ID
    selection_snapshot_id: None = None
    session_start_ms: int
    selection_epoch_id: str
    rollback_baseline_id: str
    selected_count: Literal[7]=7
    @model_validator(mode='after')
    def _validate_static_source(self):
        build_orb_session_period(self.session_start_ms)
        require_orb_epoch(self.selection_epoch_id)
        if not self.rollback_baseline_id.strip():raise ValueError('ORB Static source requires frozen baseline')
        return self
