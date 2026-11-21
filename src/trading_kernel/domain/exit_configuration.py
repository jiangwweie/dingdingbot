"""Supported per-Event TP revisions and atomic manual-product configuration."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.exit_execution import (
    ExitExecutionPolicy,
    TpQuantityPolicy,
)
from src.trading_kernel.domain.exit_policy import ExitProfile
from src.trading_kernel.domain.orb_session_selection import (
    ORB_DIRECTIONAL_EVENTS,
    ORB_DIRECTIONAL_LONG_EVENT,
)

EXIT_EVENTS = (
    "event_spec:CPM-RO-001:CPM-LONG:v3",
    "event_spec:MI-001:MI-LONG:v3",
    "event_spec:MPG-001:MPG-LONG:v3",
    "event_spec:BRF2-001:BRF2-SHORT:v3",
    "event_spec:SOR-1H-001:SOR-1H-LONG:v1",
    "event_spec:SOR-1H-001:SOR-1H-SHORT:v1",
)
MA50_EVENTS = EXIT_EVENTS[:3]
DIRECTIONAL_EXIT_EVENTS = (*EXIT_EVENTS[:4], *ORB_DIRECTIONAL_EVENTS)
EXIT_CONFIGURATION_EVENT_SETS = (frozenset(EXIT_EVENTS), frozenset(DIRECTIONAL_EXIT_EVENTS))



class EventExitParameters(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_spec_id: str
    expected_binding_id: str
    expected_binding_revision: int
    reward_multiple: Decimal
    target_fraction: Decimal
    minimum_lift: bool
    max_actual_fraction: Decimal
    ma50_enabled: bool

    @model_validator(mode="after")
    def _supported(self) -> EventExitParameters:
        if (
            self.event_spec_id not in (*EXIT_EVENTS, *ORB_DIRECTIONAL_EVENTS)
            or not self.expected_binding_id.strip()
            or self.expected_binding_revision <= 0
        ):
            raise ValueError("unsupported Event or binding revision")
        if (
            not self.reward_multiple.is_finite()
            or not Decimal(".1") <= self.reward_multiple <= 5
            or self.reward_multiple % Decimal(".1")
        ):
            raise ValueError("reward multiple must be 0.1-5.0R in 0.1R steps")
        if any(
            not v.is_finite() for v in (self.target_fraction, self.max_actual_fraction)
        ):
            raise ValueError("TP fractions must be finite")
        if self.event_spec_id in EXIT_EVENTS[:4]:
            if (
                not Decimal(0)
                < self.target_fraction
                <= self.max_actual_fraction
                <= Decimal(".50")
            ):
                raise ValueError("four-strategy TP requires 0<f<=cap<=50%")
        elif self.minimum_lift or self.max_actual_fraction != 1:
            raise ValueError("SOR retains original floor quantity contract")
        if self.event_spec_id == ORB_DIRECTIONAL_LONG_EVENT:
            if not self.ma50_enabled:
                raise ValueError("MA50 is required for standalone hourly SOR LONG")
        elif self.event_spec_id not in MA50_EVENTS and self.ma50_enabled:
            raise ValueError("MA50 is unsupported for this Event")
        return self


class ExitConfigurationIntent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    product_id: Literal["brc-app-manual-v1"] = "brc-app-manual-v1"
    venue_id: Literal["binance-usdm"] = "binance-usdm"
    account_id: str
    expected_revision: int
    events: tuple[EventExitParameters, ...]

    @model_validator(mode="after")
    def _complete(self) -> ExitConfigurationIntent:
        if self.expected_revision < 0 or not self.account_id.strip():
            raise ValueError("configuration account and revision required")
        if len(self.events) != 6 or frozenset(e.event_spec_id for e in self.events) not in (
            EXIT_CONFIGURATION_EVENT_SETS
        ):
            raise ValueError(
                "configuration requires exactly six distinct Event bindings"
            )
        return self

    def digest(self) -> str:
        payload = self.model_dump(mode="json")
        payload["events"] = sorted(payload["events"], key=lambda e: e["event_spec_id"])
        return canonical_digest(payload)


def derive_exit_profile(
    *, source: ExitProfile, parameters: EventExitParameters, revision_id: str
) -> ExitProfile:
    if (
        parameters.event_spec_id in (*EXIT_EVENTS[4:], *ORB_DIRECTIONAL_EVENTS)
        and parameters.target_fraction != source.tp1.quantity_fraction
    ):
        raise ValueError("SOR original quantity fraction is immutable")
    payload = source.model_dump(mode="json")
    payload.update(
        exit_profile_id=revision_id,
        exit_profile_version=source.exit_profile_version + 1,
        profile_schema_version="exit_profile_v2",
        execution=ExitExecutionPolicy(
            price_basis="complete_entry_vwap",
            quantity_policy=TpQuantityPolicy.TARGET_FLOOR_THEN_MINIMUM
            if parameters.minimum_lift
            else TpQuantityPolicy.TARGET_FLOOR,
            max_actual_fraction=parameters.max_actual_fraction,
        ).model_dump(mode="json"),
    )
    payload["tp1"] = {
        **payload["tp1"],
        "reward_multiple": str(parameters.reward_multiple),
        "quantity_fraction": str(parameters.target_fraction),
    }
    return ExitProfile.model_validate(payload)


class ProfileRevisionLineage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_spec_id: str
    source_profile_id: str
    source_profile_hash: str
    profile: ExitProfile


class ExitConfigurationRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    configuration_id: str
    revision: int
    intent: ExitConfigurationIntent
    profiles: tuple[ProfileRevisionLineage, ...]
    owner_authorization_id: str
    activation_reason: str
    preview_digest: str
    preview_valid_until_ms: int
    created_at_ms: int

    @model_validator(mode="after")
    def _valid_record(self) -> ExitConfigurationRecord:
        if (
            self.revision != self.intent.expected_revision + 1
            or self.created_at_ms <= 0
        ):
            raise ValueError("configuration revision or time invalid")
        if len(self.profiles) != 6 or {p.event_spec_id for p in self.profiles} != {
            e.event_spec_id for e in self.intent.events
        }:
            raise ValueError("configuration lineage requires six Events")
        for p in self.profiles:
            if p.profile.profile_schema_version != "exit_profile_v2":
                raise ValueError("configuration requires v2 explicit execution")
        return self
