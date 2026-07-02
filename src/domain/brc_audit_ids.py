"""Optional BRC runtime semantic audit identifiers.

These IDs are trace metadata only. They do not grant execution permission,
prove a runtime exists, create SignalEvaluation / OrderCandidate records, or
change order placement behavior.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class BrcSemanticIds(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_instance_id: Optional[str] = Field(default=None, max_length=128)
    trial_binding_id: Optional[str] = Field(default=None, max_length=128)
    strategy_family_id: Optional[str] = Field(default=None, max_length=128)
    strategy_family_version_id: Optional[str] = Field(default=None, max_length=128)
    signal_evaluation_id: Optional[str] = Field(default=None, max_length=128)
    order_candidate_id: Optional[str] = Field(default=None, max_length=128)
