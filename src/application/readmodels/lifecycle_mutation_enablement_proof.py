"""Frozen v2 identities for Action-Time and lifecycle mutation enablement."""

from __future__ import annotations

from hashlib import sha256
import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


SHA256 = r"^sha256:[0-9a-f]{64}$"
ACTION_TIME_REF = r"^action-time-cert:v2:[0-9a-f]{64}$"


class FrozenModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, populate_by_name=True, serialize_by_alias=True
    )


class LaneSourceWatermarkV1(FrozenModel):
    lane_scope_key: str = Field(min_length=1, max_length=320)
    lane_identity_key: str = Field(min_length=1, max_length=512)
    source_watermark: str = Field(min_length=1, max_length=512)
    process_outcome_id: str = Field(min_length=1, max_length=220)


class ActionTimeCertificationReferenceV2(FrozenModel):
    schema_: Literal["brc.action_time_certification_reference.v2"] = Field(
        "brc.action_time_certification_reference.v2"
        , alias="schema"
    )
    stage: Literal["pre_canary", "post_canary"]
    target_runtime_head: str = Field(pattern=r"^[0-9a-f]{40}$")
    certification_input_digest_schema: Literal[
        "brc.action_time_capability_certification_input.v1"
    ] = "brc.action_time_capability_certification_input.v1"
    certification_input_digest: str = Field(pattern=SHA256)
    release_activation_outcome_id: str = Field(min_length=1, max_length=220)
    release_activation_source_watermark: str = Field(min_length=1, max_length=512)
    lane_source_watermarks: tuple[LaneSourceWatermarkV1, ...] = Field(
        min_length=1, max_length=128
    )
    fact_snapshot_ids: tuple[str, ...] = Field(min_length=1, max_length=128)
    fact_set_digest_schema: Literal["brc.action_time_fact_set_digest.v1"] = (
        "brc.action_time_fact_set_digest.v1"
    )
    fact_set_digest: str = Field(pattern=SHA256)
    fact_min_valid_until_ms: int = Field(ge=0)
    deploy_nonce: str = Field(min_length=1, max_length=220)

    @model_validator(mode="after")
    def validate_ordered_unique_inputs(self) -> "ActionTimeCertificationReferenceV2":
        lane_keys = [item.lane_identity_key for item in self.lane_source_watermarks]
        if lane_keys != sorted(lane_keys) or len(lane_keys) != len(set(lane_keys)):
            raise ValueError("action_time_lane_watermarks_not_ordered_unique")
        if tuple(sorted(self.fact_snapshot_ids)) != self.fact_snapshot_ids:
            raise ValueError("action_time_fact_ids_not_ordered")
        if len(set(self.fact_snapshot_ids)) != len(self.fact_snapshot_ids):
            raise ValueError("action_time_fact_ids_duplicate")
        return self

    def certification_ref(self) -> str:
        return "action-time-cert:v2:" + _digest(self.model_dump(mode="json"))

    @property
    def schema(self) -> str:
        return self.schema_


class LifecycleMutationEnablementProof(FrozenModel):
    schema_: Literal["brc.lifecycle_mutation_enablement_proof.v2"] = Field(
        "brc.lifecycle_mutation_enablement_proof.v2"
        , alias="schema"
    )
    target_runtime_head: str = Field(pattern=r"^[0-9a-f]{40}$")
    lane_identity_digest: str = Field(pattern=SHA256)
    action_time_certification_ref: str = Field(pattern=ACTION_TIME_REF)
    action_time_certification_payload: ActionTimeCertificationReferenceV2
    certification_projection_digest_schema: Literal[
        "brc.certification_projection_digest.v1"
    ] = "brc.certification_projection_digest.v1"
    certification_projection_digest: str = Field(pattern=SHA256)

    @model_validator(mode="after")
    def validate_bound_payload(self) -> "LifecycleMutationEnablementProof":
        if self.target_runtime_head != self.action_time_certification_payload.target_runtime_head:
            raise ValueError("lifecycle_proof_runtime_head_mismatch")
        if self.action_time_certification_ref != self.action_time_certification_payload.certification_ref():
            raise ValueError("lifecycle_proof_action_time_ref_mismatch")
        return self

    @property
    def proof_schema(self) -> str:
        return self.schema_

    @property
    def schema(self) -> str:
        return self.schema_

    def canonical_payload(self) -> dict:
        return self.model_dump(mode="json")

    def lifecycle_certification_ref(self) -> str:
        return "lifecycle-cert:v2:" + _digest(self.canonical_payload())


def _digest(payload: dict) -> str:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(raw) > 64 * 1024:
        raise ValueError("lifecycle_proof_payload_too_large")
    return sha256(raw).hexdigest()
