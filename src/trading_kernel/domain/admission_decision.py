"""Immutable evidence for one final portfolio-admission result."""

from __future__ import annotations

import re
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.signal import StrategySignal
from src.trading_kernel.domain.strategy_registry import ExposureFamily

_SHA256_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


class AdmissionDecisionStatus(StrEnum):
    ADMITTED = "admitted"
    REJECTED = "rejected"


class AdmissionCandidateSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    rank: int
    signal_event_id: str
    exposure_episode_id: str
    strategy_group_id: str
    strategy_version_id: str
    event_spec_id: str
    exchange_instrument_id: str
    position_side: Literal["long", "short"]
    occurred_at_ms: int

    @field_validator(
        "signal_event_id",
        "exposure_episode_id",
        "strategy_group_id",
        "strategy_version_id",
        "event_spec_id",
        "exchange_instrument_id",
        mode="before",
    )
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("candidate summary identities must be non-blank")
        return normalized

    @field_validator("rank", "occurred_at_ms")
    @classmethod
    def _require_positive_integer(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("candidate summary rank and time must be positive")
        return value


class CandidateSetSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ranked_signal_event_ids: tuple[str, ...]
    candidate_count: int
    candidate_set_digest: str
    candidate_set_summary: tuple[AdmissionCandidateSummary, ...]

    @field_validator("candidate_set_digest")
    @classmethod
    def _require_digest(cls, value: str) -> str:
        if _SHA256_DIGEST.fullmatch(value) is None:
            raise ValueError("candidate set requires a canonical sha256 digest")
        return value

    @model_validator(mode="after")
    def _validate_snapshot(self) -> CandidateSetSnapshot:
        if self.candidate_count <= 0 or self.candidate_count > 64:
            raise ValueError("candidate set count must be between 1 and 64")
        if (
            len(self.ranked_signal_event_ids) != self.candidate_count
            or len(self.candidate_set_summary) != self.candidate_count
        ):
            raise ValueError("candidate set count differs from its summary")
        if len(set(self.ranked_signal_event_ids)) != self.candidate_count:
            raise ValueError("candidate set Signal identities must be unique")
        expected_ranks = tuple(range(1, self.candidate_count + 1))
        actual_ranks = tuple(item.rank for item in self.candidate_set_summary)
        summary_ids = tuple(
            item.signal_event_id for item in self.candidate_set_summary
        )
        if actual_ranks != expected_ranks or summary_ids != self.ranked_signal_event_ids:
            raise ValueError("candidate set summary differs from ranked identities")
        expected_digest = canonical_digest(
            [item.model_dump(mode="python") for item in self.candidate_set_summary]
        )
        if self.candidate_set_digest != expected_digest:
            raise ValueError("candidate set digest differs from its summary")
        return self


class AdmissionPortfolioUsage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    active_ticket_count: int
    active_family_ticket_count: int
    gross_risk_at_stop: Decimal
    directional_risk_at_stop: Decimal | None
    current_reserved_margin: Decimal
    remaining_ticket_slots: int
    remaining_family_slots: int
    remaining_gross_stop_risk: Decimal | None
    remaining_directional_stop_risk: Decimal | None
    remaining_initial_margin: Decimal | None

    @field_validator(
        "active_ticket_count",
        "active_family_ticket_count",
        "remaining_ticket_slots",
        "remaining_family_slots",
    )
    @classmethod
    def _require_nonnegative_count(cls, value: int) -> int:
        if value < 0:
            raise ValueError("admission usage counts cannot be negative")
        return value

    @field_validator(
        "gross_risk_at_stop",
        "current_reserved_margin",
    )
    @classmethod
    def _require_nonnegative_decimal(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value < 0:
            raise ValueError("admission usage values must be finite and nonnegative")
        return value

    @field_validator(
        "directional_risk_at_stop",
        "remaining_gross_stop_risk",
        "remaining_directional_stop_risk",
        "remaining_initial_margin",
    )
    @classmethod
    def _require_optional_nonnegative_decimal(
        cls,
        value: Decimal | None,
    ) -> Decimal | None:
        if value is not None and (not value.is_finite() or value < 0):
            raise ValueError(
                "optional admission usage values must be finite and nonnegative"
            )
        return value


class AdmissionDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    admission_decision_id: str
    signal_event_id: str
    exposure_episode_id: str
    strategy_group_id: str
    strategy_version_id: str
    event_spec_id: str
    universe_version_id: str
    universe_semantic_digest: str
    runtime_profile_id: str
    runtime_scope_id: str
    runtime_scope_version: int
    owner_policy_id: str
    owner_policy_version: int
    venue_id: str
    account_id: str
    exchange_instrument_id: str
    position_side: Literal["long", "short"]
    exposure_family: ExposureFamily
    candidate_rank: int
    candidate_set: CandidateSetSnapshot
    portfolio_usage: AdmissionPortfolioUsage
    decision_status: AdmissionDecisionStatus
    first_blocker: str | None
    binding_constraint: str | None
    capacity_claim_id: str | None
    ticket_id: str | None
    entry_admission_snapshot_digest: str | None
    decision_digest: str
    decided_at_ms: int

    @field_validator(
        "admission_decision_id",
        "signal_event_id",
        "exposure_episode_id",
        "strategy_group_id",
        "strategy_version_id",
        "event_spec_id",
        "universe_version_id",
        "runtime_profile_id",
        "runtime_scope_id",
        "owner_policy_id",
        "venue_id",
        "account_id",
        "exchange_instrument_id",
        mode="before",
    )
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("AdmissionDecision identities must be non-blank")
        return normalized

    @field_validator(
        "capacity_claim_id",
        "ticket_id",
        "first_blocker",
        "binding_constraint",
        mode="before",
    )
    @classmethod
    def _normalize_optional_identity(cls, value: object) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    @field_validator(
        "universe_semantic_digest",
        "decision_digest",
    )
    @classmethod
    def _require_digest(cls, value: str) -> str:
        if _SHA256_DIGEST.fullmatch(value) is None:
            raise ValueError("AdmissionDecision digests must be canonical sha256")
        return value

    @field_validator("entry_admission_snapshot_digest")
    @classmethod
    def _require_optional_digest(cls, value: str | None) -> str | None:
        if value is not None and _SHA256_DIGEST.fullmatch(value) is None:
            raise ValueError("admission snapshot digest must be canonical sha256")
        return value

    @model_validator(mode="after")
    def _validate_decision(self) -> AdmissionDecision:
        if (
            self.runtime_scope_version <= 0
            or self.owner_policy_version <= 0
            or self.candidate_rank <= 0
            or self.decided_at_ms <= 0
        ):
            raise ValueError("AdmissionDecision versions, rank, and time must be positive")
        if self.candidate_rank > self.candidate_set.candidate_count:
            raise ValueError("AdmissionDecision candidate rank is outside its set")
        candidate = self.candidate_set.candidate_set_summary[
            self.candidate_rank - 1
        ]
        if (
            candidate.signal_event_id != self.signal_event_id
            or candidate.exposure_episode_id != self.exposure_episode_id
            or candidate.strategy_group_id != self.strategy_group_id
            or candidate.strategy_version_id != self.strategy_version_id
            or candidate.event_spec_id != self.event_spec_id
            or candidate.exchange_instrument_id
            != self.exchange_instrument_id
            or candidate.position_side != self.position_side
        ):
            raise ValueError("AdmissionDecision differs from its ranked candidate")
        if self.decision_status is AdmissionDecisionStatus.ADMITTED:
            if (
                self.first_blocker is not None
                or self.capacity_claim_id is None
                or self.ticket_id is None
                or self.entry_admission_snapshot_digest is None
            ):
                raise ValueError(
                    "admitted AdmissionDecision requires Claim, Ticket, and snapshot"
                )
        elif (
            self.first_blocker is None
            or self.capacity_claim_id is not None
            or self.ticket_id is not None
        ):
            raise ValueError(
                "rejected AdmissionDecision requires blocker and forbids Claim/Ticket"
            )
        expected_digest = build_admission_decision_digest(self)
        if self.decision_digest != expected_digest:
            raise ValueError("AdmissionDecision digest differs from its payload")
        expected_id = (
            "admission:"
            f"{expected_digest.removeprefix('sha256:')[:32]}"
        )
        if self.admission_decision_id != expected_id:
            raise ValueError("AdmissionDecision identity differs from its digest")
        return self


def freeze_admission_decision(
    *,
    signal: StrategySignal,
    candidate_set: CandidateSetSnapshot,
    exposure_family: ExposureFamily,
    runtime_profile_id: str,
    owner_policy_id: str,
    owner_policy_version: int,
    venue_id: str,
    account_id: str,
    portfolio_usage: AdmissionPortfolioUsage,
    decision_status: AdmissionDecisionStatus,
    first_blocker: str | None,
    binding_constraint: str | None,
    capacity_claim_id: str | None,
    ticket_id: str | None,
    entry_admission_snapshot_digest: str | None,
    decided_at_ms: int,
) -> AdmissionDecision:
    try:
        candidate_rank = (
            candidate_set.ranked_signal_event_ids.index(signal.signal_event_id)
            + 1
        )
    except ValueError as exc:
        raise ValueError("Signal is absent from the candidate set") from exc
    payload = {
        "admission_decision_id": "admission:pending",
        "signal_event_id": signal.signal_event_id,
        "exposure_episode_id": signal.exposure_episode_id,
        "strategy_group_id": signal.strategy_group_id,
        "strategy_version_id": signal.strategy_version_id,
        "event_spec_id": signal.event_spec_id,
        "universe_version_id": signal.universe_version_id,
        "universe_semantic_digest": signal.universe_semantic_digest,
        "runtime_profile_id": runtime_profile_id,
        "runtime_scope_id": signal.runtime_scope_id,
        "runtime_scope_version": signal.runtime_scope_version,
        "owner_policy_id": owner_policy_id,
        "owner_policy_version": owner_policy_version,
        "venue_id": venue_id,
        "account_id": account_id,
        "exchange_instrument_id": signal.exchange_instrument_id,
        "position_side": signal.position_side,
        "exposure_family": exposure_family,
        "candidate_rank": candidate_rank,
        "candidate_set": candidate_set,
        "portfolio_usage": portfolio_usage,
        "decision_status": decision_status,
        "first_blocker": first_blocker,
        "binding_constraint": binding_constraint,
        "capacity_claim_id": capacity_claim_id,
        "ticket_id": ticket_id,
        "entry_admission_snapshot_digest": entry_admission_snapshot_digest,
        "decision_digest": "sha256:" + "0" * 64,
        "decided_at_ms": decided_at_ms,
    }
    decision_digest = canonical_digest(_decision_digest_payload(payload))
    payload["decision_digest"] = decision_digest
    payload["admission_decision_id"] = (
        f"admission:{decision_digest.removeprefix('sha256:')[:32]}"
    )
    return AdmissionDecision.model_validate(payload)


def build_admission_decision_digest(decision: AdmissionDecision) -> str:
    return canonical_digest(
        _decision_digest_payload(decision.model_dump(mode="python"))
    )


def _decision_digest_payload(payload: dict[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in payload.items()
        if key not in {"admission_decision_id", "decision_digest"}
    }
