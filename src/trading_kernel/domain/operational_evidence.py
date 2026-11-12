"""Bounded, credential-free failure facts; evidence never grants trading authority."""

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest


class FailureDiagnostic(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    stage: Literal['admission','certification','observation','facts_refresh','signal_ingest','review','lifecycle_facts','exit_closure','dispatch_preflight']
    subject_id: str = Field(min_length=1, max_length=200)
    reason_code: str = Field(min_length=1, max_length=160)
    basis: dict[str, JsonValue]
    occurred_at_ms: int = Field(gt=0)

    @field_validator('basis')
    @classmethod
    def bounded_safe_basis(cls, value):
        def check(node):
            if isinstance(node, dict):
                for key, child in node.items():
                    if any(word in key.lower() for word in ('secret','password','credential','api_key','signature','webhook','token')):
                        raise ValueError('diagnostic basis contains forbidden credential field')
                    check(child)
            elif isinstance(node, list):
                for child in node:
                    check(child)
        check(value)
        if len(json.dumps(value,ensure_ascii=False).encode()) > 12_000:
            raise ValueError('diagnostic basis exceeds bound')
        return value

    def identity(self) -> str:
        return 'diagnostic:' + canonical_digest(self.model_dump(mode='json'))[7:]
