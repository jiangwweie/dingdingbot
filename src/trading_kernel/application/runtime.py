"""Shared bounded-worker contracts; no combined runtime orchestration."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


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
    def _validate_window(self) -> "RuntimeDispatchRequest":
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
