"""Generic period-based claims sharing the same queue with SOR Session claims."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_validator

from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.instrument_selection import SelectionJobClaim


def selection_job_identity(selection_spec_id: str, period_anchor_ms: int, selection_epoch_id: str = "sor-v0") -> str:
    if selection_epoch_id == "sor-v0":
        return f"selection-job:{selection_spec_id}:{period_anchor_ms}"
    return "selection-job:" + canonical_digest({"spec": selection_spec_id, "epoch": selection_epoch_id, "cutoff": period_anchor_ms})[7:]


class GenericSelectionJobClaim(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    selection_job_id: str
    selection_spec_id: str
    period_anchor_ms: int
    worker_id: str
    attempt_number: int
    projection_version: int
    started_at_ms: int
    lease_expires_at_ms: int
    selection_epoch_id: str
    selection_control_version: int
    predecessor_snapshot_id: str | None = None
    predecessor_member_digest: str | None = None

    @model_validator(mode="after")
    def _validate_claim(self) -> GenericSelectionJobClaim:
        if not self.selection_epoch_id.strip() or self.selection_epoch_id == "sor-v0":
            raise ValueError("Generic claim requires its own explicit epoch")
        if self.selection_job_id != selection_job_identity(self.selection_spec_id, self.period_anchor_ms, self.selection_epoch_id):
            raise ValueError("Generic Selection Job identity is not canonical")
        if not self.worker_id.strip() or min(self.attempt_number, self.projection_version, self.selection_control_version) <= 0:
            raise ValueError("Generic Selection Job ownership/version is invalid")
        if self.lease_expires_at_ms <= self.started_at_ms or self.period_anchor_ms <= 0 or self.period_anchor_ms > self.started_at_ms:
            raise ValueError("Generic Selection Job lease timing is invalid")
        if (self.predecessor_snapshot_id is None) != (self.predecessor_member_digest is None):
            raise ValueError("Generic Selection predecessor is incomplete")
        digest = self.predecessor_member_digest
        if digest is not None and (len(digest)!=71 or not digest.startswith("sha256:") or any(c not in "0123456789abcdef" for c in digest[7:])):
            raise ValueError("Generic Selection predecessor digest is invalid")
        return self


SelectionJobLease = SelectionJobClaim | GenericSelectionJobClaim


def job_period_anchor(claim: SelectionJobLease) -> int:
    return claim.period_anchor_ms if isinstance(claim, GenericSelectionJobClaim) else claim.session_start_ms


def job_selection_epoch(claim: SelectionJobLease) -> str:
    return claim.selection_epoch_id if isinstance(claim, GenericSelectionJobClaim) else "sor-v0"
