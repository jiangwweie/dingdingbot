"""Create and read one exact release-scoped Certification Batch."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.application.ports import KernelUnitOfWork
from src.trading_kernel.domain.instrument_certification import (
    CertificationBatchStatus,
    build_certification_manifest_digest,
)


class StartCertificationBatchRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    certification_batch_id: str
    runtime_profile_id: str
    target_commit: str
    target_schema_revision: str
    target_seed_identity: str
    owner_policy_id: str
    owner_policy_version: int
    exchange_instrument_ids: tuple[str, ...]
    started_at_ms: int
    minimum_valid_until_ms: int

    @field_validator(
        "certification_batch_id",
        "runtime_profile_id",
        "target_commit",
        "target_schema_revision",
        "target_seed_identity",
        "owner_policy_id",
        mode="before",
    )
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("certification batch identities must be non-blank")
        return normalized

    @model_validator(mode="after")
    def _validate_request(self) -> StartCertificationBatchRequest:
        build_certification_manifest_digest(self.exchange_instrument_ids)
        if self.owner_policy_version <= 0 or self.started_at_ms <= 0:
            raise ValueError("certification batch version and time must be positive")
        if self.minimum_valid_until_ms <= self.started_at_ms:
            raise ValueError("certification batch promotion window must be future-dated")
        if (
            len(self.target_seed_identity) != 71
            or not self.target_seed_identity.startswith("sha256:")
        ):
            raise ValueError("certification batch seed identity must be sha256")
        return self


class CertificationBatchSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    certification_batch_id: str
    runtime_profile_id: str
    target_commit: str
    target_schema_revision: str
    target_seed_identity: str
    owner_policy_id: str
    owner_policy_version: int
    manifest_digest: str
    exchange_instrument_ids: tuple[str, ...]
    status: CertificationBatchStatus
    started_at_ms: int
    minimum_valid_until_ms: int
    completed_at_ms: int | None
    valid_until_ms: int | None
    blocker_code: str | None


async def start_certification_batch(
    uow: KernelUnitOfWork,
    request: StartCertificationBatchRequest,
) -> CertificationBatchSnapshot:
    """Create one immutable exact batch or return its identical current state."""

    return await uow.strategy_universes.start_certification_batch(
        request=request,
        manifest_digest=build_certification_manifest_digest(
            request.exchange_instrument_ids
        ),
    )
