"""Bounded Owner Console overview route."""

from __future__ import annotations

from fastapi import APIRouter, Request

from src.trading_kernel.application.owner_console.models import (
    ApiEnvelope,
    Freshness,
    OverviewFacts,
    OwnerOverview,
)
from src.trading_kernel.application.owner_console.overview import (
    build_owner_overview,
)
from src.trading_kernel.interfaces.owner_console_http.dependencies import (
    get_clock_ms,
)
from src.trading_kernel.interfaces.owner_console_http.routes._shared import (
    envelope,
    evidence_watermark,
    latest_ms,
    read_page_facts,
    utc_day_start_ms,
)

router = APIRouter(prefix="/api/owner/v1", tags=["owner-read"])


@router.get("/overview", response_model=ApiEnvelope[OwnerOverview])
async def overview(request: Request) -> ApiEnvelope[OwnerOverview]:
    """Return one internally consistent Owner overview snapshot."""

    now_ms = get_clock_ms(request)
    facts = await read_page_facts(
        request,
        lambda repository: repository.read_overview_facts(
            utc_day_start_ms(now_ms),
            now_ms,
        ),
    )
    data = build_owner_overview(facts, now_ms=now_ms)
    return envelope(
        data,
        now_ms=now_ms,
        source_watermark_ms=_source_watermark(facts),
        freshness=facts.runtime_freshness,
    )


def _source_watermark(facts: OverviewFacts) -> int | None:
    """Exclude request-time placeholders used only to identify missing rows."""

    missing_gap_reasons = {
        "configured_owner_authority_missing",
        "account_exposure_current_missing",
    }
    freshness_timestamp = (
        facts.freshness_evidence_at_ms
        if facts.runtime_freshness in {Freshness.FRESH, Freshness.STALE}
        or (
            facts.runtime_freshness is Freshness.UNAVAILABLE
            and facts.freshness_evidence_identity != "monitor:current"
            and not any(
                gap.reason in missing_gap_reasons for gap in facts.evidence_gaps
            )
        )
        else None
    )
    return latest_ms(
        freshness_timestamp,
        facts.latest_claim_created_at_ms,
        facts.open_owner_incident_opened_at_ms,
        facts.needs_intervention_monitor_updated_at_ms,
        *(facts.attention_incident_opened_at_ms),
        *(facts.monitor_updated_at_ms),
        evidence_watermark(facts.evidence),
        evidence_watermark(
            gap.evidence
            for gap in facts.evidence_gaps
            if gap.reason not in missing_gap_reasons
        ),
    )
