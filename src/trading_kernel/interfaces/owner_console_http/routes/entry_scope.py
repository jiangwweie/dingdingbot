"""Read-only current effective Entry scope projection."""

from __future__ import annotations

from fastapi import APIRouter, Request

from src.trading_kernel.application.owner_console.entry_scope import (
    build_effective_entry_scope,
)
from src.trading_kernel.application.owner_console.models import (
    ApiEnvelope,
    EffectiveEntryScope,
)
from src.trading_kernel.interfaces.owner_console_http.dependencies import (
    get_clock_ms,
    get_settings,
)
from src.trading_kernel.interfaces.owner_console_http.routes._shared import (
    envelope,
    evidence_watermark,
    read_page_facts,
)

router = APIRouter(prefix="/api/owner/v1", tags=["owner-read"])


@router.get("/entry-scope", response_model=ApiEnvelope[EffectiveEntryScope])
async def effective_entry_scope(request: Request) -> ApiEnvelope[EffectiveEntryScope]:
    """Explain current scope-level Entry eligibility; this never grants admission."""

    now_ms = get_clock_ms(request)
    settings = get_settings(request)
    facts = await read_page_facts(
        request,
        lambda repository: repository.read_effective_entry_scope_facts(
            settings.owner_policy_id
        ),
    )
    data = build_effective_entry_scope(facts, now_ms=now_ms)
    return envelope(
        data,
        now_ms=now_ms,
        source_watermark_ms=evidence_watermark(data.evidence),
    )
