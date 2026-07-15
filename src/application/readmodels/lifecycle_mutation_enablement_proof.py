"""Frozen v2 proof bound to lifecycle mutation enablement."""

from __future__ import annotations

from hashlib import sha256
import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ACTION_TIME_REF_RE = re.compile(r"^action-time-cert:v2:[0-9a-f]{64}$")


class LifecycleMutationEnablementProof(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    proof_schema: Literal["brc.lifecycle_mutation_enablement_proof.v2"] = (
        "brc.lifecycle_mutation_enablement_proof.v2"
    )
    target_runtime_head: str = Field(min_length=40, max_length=40)
    lane_digest: str = Field(min_length=64, max_length=64)
    release_activation_ref: str = Field(min_length=1, max_length=260)
    action_time_certification_ref: str = Field(min_length=84, max_length=84)
    certification_projection_digest: str = Field(min_length=64, max_length=64)
    enablement_fact_refs: tuple[str, ...] = Field(max_length=128)

    @model_validator(mode="after")
    def validate_hashes(self) -> "LifecycleMutationEnablementProof":
        if not re.fullmatch(r"[0-9a-f]{40}", self.target_runtime_head):
            raise ValueError("lifecycle_proof_runtime_head_invalid")
        for value in (self.lane_digest, self.certification_projection_digest):
            if not SHA256_RE.fullmatch(value):
                raise ValueError("lifecycle_proof_digest_invalid")
        if not ACTION_TIME_REF_RE.fullmatch(self.action_time_certification_ref):
            raise ValueError("lifecycle_proof_action_time_ref_invalid")
        if len(set(self.enablement_fact_refs)) != len(self.enablement_fact_refs):
            raise ValueError("lifecycle_proof_fact_refs_duplicate")
        return self

    def canonical_payload(self) -> dict:
        return self.model_dump(mode="json")

    def lifecycle_certification_ref(self) -> str:
        raw = json.dumps(
            self.canonical_payload(), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        if len(raw) > 64 * 1024:
            raise ValueError("lifecycle_proof_payload_too_large")
        return "lifecycle-cert:v2:" + sha256(raw).hexdigest()

