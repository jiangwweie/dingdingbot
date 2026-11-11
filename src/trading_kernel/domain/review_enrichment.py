"""Frozen boundaries for one exact terminal-review difference and approval."""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest


class ReviewEnrichmentPreview(BaseModel):
    model_config=ConfigDict(frozen=True,extra='forbid')
    ticket_id: str
    expected_review_id: str
    old_metrics_digest: str
    old_metrics: dict[str,JsonValue]
    metrics: dict[str,JsonValue]
    entry_quantity: Decimal=Field(gt=0,allow_inf_nan=False)
    exit_quantity: Decimal=Field(gt=0,allow_inf_nan=False)
    prepared_at_ms: int=Field(gt=0)

    @model_validator(mode='after')
    def valid(self):
        import json
        if len(json.dumps(self.model_dump(mode="json")).encode())>2_000_000:
            raise ValueError("enrichment preview exceeds bound")
        if self.entry_quantity!=self.exit_quantity or canonical_digest(self.old_metrics)!=self.old_metrics_digest:
            raise ValueError('enrichment quantity or predecessor evidence differs')
        return self


class ReviewEnrichmentRequest(BaseModel):
    model_config=ConfigDict(frozen=True,extra='forbid')
    request_id: str
    ticket_id: str
    expected_review_id: str
    state: Literal['pending','preview_ready','approved','applied','superseded']
    owner_authorization_id: str | None=None
    preview: ReviewEnrichmentPreview | None=None
    preview_digest: str | None=None
    last_reason: str | None=None
    created_at_ms: int
    next_check_at_ms: int
    completed_at_ms: int | None=None

    @model_validator(mode='after')
    def valid(self):
        if self.preview is not None and (self.preview.ticket_id!=self.ticket_id
            or self.preview.expected_review_id!=self.expected_review_id or canonical_digest(self.preview)!=self.preview_digest):
            raise ValueError('enrichment preview identity or digest differs')
        if self.state in {'preview_ready','approved','applied'} and self.preview is None:
            raise ValueError('ready enrichment requires exact preview')
        if self.state in {'approved','applied'} and not self.owner_authorization_id:
            raise ValueError('approved enrichment requires Owner authorization')
        return self
