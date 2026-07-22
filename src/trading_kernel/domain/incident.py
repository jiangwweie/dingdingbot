"""Typed abnormal runtime state owned by one Ticket when available."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class IncidentKind(StrEnum):
    ENTRY_OUTCOME_UNKNOWN = "entry_outcome_unknown"
    EXIT_OUTCOME_UNKNOWN = "exit_outcome_unknown"
    UNSUPPORTED_PARTIAL_FILL = "unsupported_partial_entry_fill"
    EXTERNAL_FLAT = "external_flat"
    UNOWNED_OPEN_ORDER = "unowned_open_order"
    PROTECTION_RESIDUE = "protection_residue"


class RuntimeIncident(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    incident_id: str
    ticket_id: str | None
    kind: IncidentKind
    first_blocker: str
    details: dict[str, JsonValue] = Field(default_factory=dict)
    opened_at_ms: int
