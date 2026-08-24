"""Shared bounded-worker contracts; no combined runtime orchestration."""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

_COMMIT = re.compile(r"^[0-9a-f]{40}$")


class RuntimeCompatibilityClassification(StrEnum):
    COMPATIBLE_RESTART = "COMPATIBLE_RESTART"
    REQUIRES_RUNTIME_REMATERIALIZATION = "REQUIRES_RUNTIME_REMATERIALIZATION"


RUNTIME_COMPATIBILITY_REASONS = frozenset(
    {
        "PERSISTED_ACTIVE_UNIVERSE_CONTRACT_UNCHANGED",
        "STRATEGY_SEMANTICS_CHANGED",
        "REQUIRED_FACT_CONTRACT_CHANGED",
        "WARM_CERTIFICATION_CONTRACT_CHANGED",
        "RUNTIME_SCOPE_IDENTITY_CHANGED",
        "UNIVERSE_DATA_CONTRACT_CHANGED",
    }
)


class RuntimeReleaseCompatibilityFact(BaseModel):
    """Thin immutable projection bound to one exact R4 certification manifest."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    release_compatibility_id: str
    from_commit: str
    to_commit: str
    from_schema_revision: str
    to_schema_revision: str
    classification: RuntimeCompatibilityClassification
    compatibility_basis_digest: str
    reason_codes: tuple[str, ...]
    certification_manifest_digest: str
    created_at_ms: int

    @model_validator(mode="after")
    def _validate_fact(self) -> RuntimeReleaseCompatibilityFact:
        if (
            _COMMIT.fullmatch(self.from_commit) is None
            or _COMMIT.fullmatch(self.to_commit) is None
        ):
            raise ValueError("release compatibility commits must be exact")
        if self.release_compatibility_id != (
            f"release-compatibility:{self.from_commit}:{self.to_commit}"
        ):
            raise ValueError("release compatibility identity must match commits")
        if not self.from_schema_revision.strip() or not self.to_schema_revision.strip():
            raise ValueError("release compatibility schemas must be non-blank")
        if not self.reason_codes or tuple(sorted(set(self.reason_codes))) != self.reason_codes:
            raise ValueError("release compatibility reasons must be canonical and unique")
        if any(item not in RUNTIME_COMPATIBILITY_REASONS for item in self.reason_codes):
            raise ValueError("release compatibility reason is not approved")
        if self.classification is RuntimeCompatibilityClassification.COMPATIBLE_RESTART:
            if self.reason_codes != (
                "PERSISTED_ACTIVE_UNIVERSE_CONTRACT_UNCHANGED",
            ):
                raise ValueError("compatible restart requires the exact unchanged reason")
        elif "PERSISTED_ACTIVE_UNIVERSE_CONTRACT_UNCHANGED" in self.reason_codes:
            raise ValueError("rematerialization cannot claim an unchanged contract")
        for digest in (
            self.compatibility_basis_digest,
            self.certification_manifest_digest,
        ):
            if not digest.startswith("sha256:") or len(digest) != 71:
                raise ValueError("release compatibility digest must be canonical")
        if self.created_at_ms <= 0:
            raise ValueError("release compatibility creation time must be positive")
        return self


class RuntimeDispatchRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    worker_id: str
    ticket_id: str | None = None
    now_ms: int
    lease_until_ms: int
    timeout_seconds: float

    @field_validator("worker_id", mode="before")
    @classmethod
    def _require_worker_id(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("runtime worker identity must be non-blank")
        return normalized

    @field_validator("ticket_id", mode="before")
    @classmethod
    def _normalize_ticket_id(cls, value: object) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        if not normalized:
            raise ValueError("runtime Ticket identity must be non-blank")
        return normalized

    @model_validator(mode="after")
    def _validate_window(self) -> RuntimeDispatchRequest:
        if self.now_ms <= 0 or self.lease_until_ms <= self.now_ms:
            raise ValueError("runtime worker lease must end after its tick")
        if self.timeout_seconds <= 0:
            raise ValueError("runtime worker timeout must be positive")
        return self


def worker_ownership_map() -> dict[str, str]:
    return {
        "observation": "observation_worker",
        "entry": "entry_worker",
        "lifecycle": "lifecycle_worker",
        "reconciliation": "reconciliation_worker",
    }


def observation_process_component_map() -> dict[str, str]:
    """Freeze the three independently leased loops hosted by Observation."""

    return {
        "selection": "selection_runner",
        "materialization": "materialization_coordinator",
        "observation": "observation_runner",
    }
