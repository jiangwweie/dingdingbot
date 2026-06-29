"""Shared RequiredFacts readiness classification.

The helpers in this module classify fact status only. They do not grant
FinalGate, Operation Layer, exchange-write, or real-order authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Collection, Mapping


READY_SOURCE_STATUSES = frozenset(
    {"ready", "fresh", "available", "present", "pass", "clear", "sufficient"}
)
STALE_SOURCE_STATUSES = frozenset({"stale", "expired"})
MISSING_SOURCE_STATUSES = frozenset(
    {"conflict", "insufficient", "fail", "missing"}
)


@dataclass(frozen=True)
class RequiredFactSpec:
    key: str
    question: str
    ready_status: str
    stale_status: str
    missing_status: str


@dataclass(frozen=True)
class RequiredFactAssessment:
    key: str
    question: str
    status: str
    source_status: str
    check_surface: str
    action_time_check_active: bool
    blocks_live_submit_now: bool
    owner_wording: str

    @property
    def blocker(self) -> str | None:
        if not self.blocks_live_submit_now:
            return None
        return f"{self.key}:{self.status}"

    def as_runtime_safety_row(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "question": self.question,
            "status": self.status,
            "source_status": self.source_status,
            "check_surface": self.check_surface,
            "action_time_check_active": self.action_time_check_active,
            "blocks_live_submit_now": self.blocks_live_submit_now,
            "blocker": self.blocker,
            "owner_wording": self.owner_wording,
        }


@dataclass(frozen=True)
class RequiredFactAuthorityBoundary:
    fact_authority: str
    source_is_proxy_reference: bool
    usable_for_armed_observation: bool
    usable_for_market_wait_classification: bool
    action_time_required_facts_satisfied: bool
    usable_for_finalgate: bool
    usable_for_operation_layer: bool
    usable_for_exchange_write: bool
    notes: str

    def as_read_model(self) -> dict[str, Any]:
        if not self.fact_authority:
            return {
                "action_time_required_facts_satisfied": False,
                "usable_for_armed_observation": False,
                "usable_for_finalgate": False,
                "usable_for_operation_layer": False,
                "usable_for_exchange_write": False,
            }
        return {
            "fact_authority": self.fact_authority,
            "source_is_brf_reference_row": self.source_is_proxy_reference,
            "usable_for_armed_observation": self.usable_for_armed_observation,
            "usable_for_market_wait_classification": (
                self.usable_for_market_wait_classification
            ),
            "action_time_required_facts_satisfied": (
                self.action_time_required_facts_satisfied
            ),
            "usable_for_finalgate": self.usable_for_finalgate,
            "usable_for_operation_layer": self.usable_for_operation_layer,
            "usable_for_exchange_write": self.usable_for_exchange_write,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class RequiredFactObservation:
    key: str
    status: str
    raw_status: str
    fresh: bool

    def as_signal_observation_row(self) -> dict[str, Any]:
        return {
            "fact_key": self.key,
            "state": self.status,
            "raw_state": self.raw_status,
            "fresh": self.fresh,
        }


@dataclass(frozen=True)
class RequiredFactObservationSpec:
    key: str
    accepted_statuses: tuple[str, ...]

    def as_signal_observation_spec(self) -> dict[str, Any]:
        return {
            "fact_key": self.key,
            "accepted_statuses": list(self.accepted_statuses),
        }


@dataclass(frozen=True)
class RequiredFactDisableSpec:
    key: str
    active_statuses: tuple[str, ...]
    blocker: str

    def as_signal_disable_spec(self) -> dict[str, Any]:
        return {
            "fact_key": self.key,
            "active_statuses": list(self.active_statuses),
            "blocker": self.blocker,
        }


def read_only_required_fact_authority_boundary(
    *,
    fact_authority: str,
    source_is_proxy_reference: bool,
    proxy_note: str,
    read_only_note: str,
) -> RequiredFactAuthorityBoundary:
    return RequiredFactAuthorityBoundary(
        fact_authority=fact_authority,
        source_is_proxy_reference=source_is_proxy_reference,
        usable_for_armed_observation=bool(fact_authority),
        usable_for_market_wait_classification=bool(fact_authority),
        action_time_required_facts_satisfied=False,
        usable_for_finalgate=False,
        usable_for_operation_layer=False,
        usable_for_exchange_write=False,
        notes=proxy_note if source_is_proxy_reference else read_only_note,
    )


def assess_required_fact_observation(
    *,
    fact_key: str,
    fact_present: bool,
    raw_status: str,
    fresh: bool,
    accepted_statuses: Collection[str],
) -> RequiredFactObservation:
    if not fact_present:
        return RequiredFactObservation(
            key=fact_key,
            status="missing",
            raw_status="",
            fresh=False,
        )
    if not fresh:
        status = "stale"
    elif raw_status in accepted_statuses:
        status = "satisfied"
    else:
        status = "not_satisfied"
    return RequiredFactObservation(
        key=fact_key,
        status=status,
        raw_status=raw_status,
        fresh=fresh,
    )


def required_fact_observation_specs_from_rows(
    rows: list[Mapping[str, Any]],
) -> list[RequiredFactObservationSpec]:
    specs: list[RequiredFactObservationSpec] = []
    for row in rows:
        key = str(row.get("fact_key") or row.get("key") or "")
        accepted = tuple(
            sorted(
                {
                    str(status).strip().lower()
                    for status in row.get("accepted_statuses") or []
                    if str(status).strip()
                }
            )
        )
        if key and accepted:
            specs.append(
                RequiredFactObservationSpec(
                    key=key,
                    accepted_statuses=accepted,
                )
            )
    return specs


def required_fact_disable_specs_from_rows(
    rows: list[Mapping[str, Any]],
) -> list[RequiredFactDisableSpec]:
    specs: list[RequiredFactDisableSpec] = []
    for row in rows:
        key = str(row.get("fact_key") or row.get("key") or "")
        active = tuple(
            sorted(
                {
                    str(status).strip().lower()
                    for status in row.get("active_statuses") or []
                    if str(status).strip()
                }
            )
        )
        if key and active:
            specs.append(
                RequiredFactDisableSpec(
                    key=key,
                    active_statuses=active,
                    blocker=str(row.get("blocker") or ""),
                )
            )
    return specs


def required_fact_status(
    *,
    spec: RequiredFactSpec,
    raw_status: str,
    action_time_check_active: bool,
) -> str:
    if not action_time_check_active and raw_status == "pending_action_time":
        return "pending_action_time"
    if raw_status in READY_SOURCE_STATUSES:
        return spec.ready_status
    if raw_status in STALE_SOURCE_STATUSES:
        return spec.stale_status
    if raw_status in MISSING_SOURCE_STATUSES:
        return spec.missing_status
    return raw_status


def assess_required_fact(
    *,
    spec: RequiredFactSpec,
    raw_status: str,
    action_time_check_active: bool,
    check_surface: str,
    owner_wording: str,
) -> RequiredFactAssessment:
    status = required_fact_status(
        spec=spec,
        raw_status=raw_status,
        action_time_check_active=action_time_check_active,
    )
    blocks = action_time_check_active and status not in {
        spec.ready_status,
        "fresh",
        "clear",
        "sufficient",
        "pass",
    }
    return RequiredFactAssessment(
        key=spec.key,
        question=spec.question,
        status=status,
        source_status=raw_status,
        check_surface=check_surface,
        action_time_check_active=action_time_check_active,
        blocks_live_submit_now=blocks,
        owner_wording=owner_wording,
    )


def required_fact_specs_from_rows(
    rows: list[Mapping[str, str]],
) -> list[RequiredFactSpec]:
    return [
        RequiredFactSpec(
            key=str(row["key"]),
            question=str(row["question"]),
            ready_status=str(row["ready_status"]),
            stale_status=str(row["stale_status"]),
            missing_status=str(row["missing_status"]),
        )
        for row in rows
    ]


def required_facts_status_for_tradeability(
    *,
    strategy_group_id: str,
    stage: str,
    armed_observation_ready: bool,
    required_facts_mapping_ready: bool,
    has_required_facts_draft: bool,
    blocker_text: str,
    has_registry_required_facts_summary: bool,
) -> str:
    if (
        strategy_group_id == "BRF2-001"
        and armed_observation_ready
        and required_facts_mapping_ready
    ):
        return "ready"
    text = blocker_text.lower()
    if strategy_group_id == "MPG-001":
        return "action_time_only"
    if has_required_facts_draft:
        return "missing"
    if any(token in text for token in ("fact", "stale", "classifier", "rewrite", "squeeze")):
        return "missing"
    if has_registry_required_facts_summary:
        return "action_time_only"
    if stage in {"role_only_intake_candidate", "observe_only_would_enter"}:
        return "not_applicable"
    return "missing"
