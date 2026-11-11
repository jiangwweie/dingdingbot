"""Terminal economics preview/revision through the existing Review lineage only."""

from src.trading_kernel.application.ports import KernelUnitOfWork
from src.trading_kernel.application.runtime_facts import (
    ReviewEconomicsRequest,
    ReviewEconomicsSource,
)
from src.trading_kernel.application.settle_ticket import (
    ReviseTradeReviewRequest,
    revise_trade_review,
)
from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.order_attribution import (
    ExternalExitOrderReference,
    OrderRole,
    attribution_digest,
)
from src.trading_kernel.domain.review import calculate_review_economics
from src.trading_kernel.domain.review_enrichment import ReviewEnrichmentPreview


async def request_review_enrichment(uow: KernelUnitOfWork, *, ticket_id: str, now_ms: int) -> str:
    aggregate = await uow.aggregates.get(ticket_id)
    if aggregate is None or aggregate.status is not AggregateStatus.TERMINAL or aggregate.review_id is None:
        raise ValueError('enrichment requires exact terminal review')
    current = await uow.reviews.get_for_ticket(ticket_id)
    if current is None or current.metrics.get('economics_completeness') == 'complete':
        raise ValueError('review is missing or already economically complete')
    request_id = 'review-enrichment:' + canonical_digest({'ticket_id':ticket_id,'review_id':aggregate.review_id})[7:]
    await uow.reviews.enqueue_enrichment(request_id=request_id,ticket_id=ticket_id,
        expected_review_id=aggregate.review_id,now_ms=now_ms)
    return request_id


async def prepare_review_enrichment(uow_factory, source: ReviewEconomicsSource, *, now_ms: int) -> bool:
    # One due exact Ticket per cadence; network calls occur after the UoW exits.
    from src.trading_kernel.application.review_window import _review_window

    async with uow_factory() as uow:
        request = await uow.reviews.claim_enrichment(now_ms=now_ms)
        if request is None:
            return False
        if request.state=='approved':
            assert request.preview_digest is not None and request.owner_authorization_id is not None
            await apply_review_enrichment(uow,request_id=request.request_id,approved_preview_digest=request.preview_digest,
                owner_authorization_id=request.owner_authorization_id,now_ms=now_ms)
            return True
        aggregate = await uow.aggregates.get(request.ticket_id)
        if aggregate is None or aggregate.status is not AggregateStatus.TERMINAL or aggregate.review_id != request.expected_review_id:
            await uow.reviews.finish_enrichment(request.request_id,state='superseded',now_ms=now_ms)
            return True
        old = await uow.reviews.get_for_ticket(aggregate.identity.ticket_id)
        events = await uow.events.list_for_ticket(aggregate.identity.ticket_id)
        window = _review_window(events,exposure_started_at_ms=aggregate.ticket.created_at_ms)
        if window is None or old is None:
            await uow.reviews.retry_enrichment(request.request_id,reason='review_window_unavailable',now_ms=now_ms)
            return True
        references = await uow.exchange_commands.list_order_references(aggregate.identity.ticket_id)
        entries = tuple(r for r in references if r.role is OrderRole.ENTRY)
        external = await uow.management.verified_exit_references(aggregate.identity.ticket_id,
            entry_time_ms=window.entry_time_ms,exit_time_ms=window.exit_time_ms,system_references=references)
        exits = tuple(r for r in references if r.role is OrderRole.EXIT) + external
        if len(entries) != 1 or not exits:
            await uow.reviews.retry_enrichment(request.request_id,reason='exit_evidence_unavailable',now_ms=now_ms)
            return True
        domain = aggregate.identity.netting_domain
        overlap = await uow.tickets.has_other_instrument_ticket_in_window(ticket_id=aggregate.identity.ticket_id,
            venue_id=domain.venue_id,account_id=domain.account_id,exchange_instrument_id=domain.exchange_instrument_id,
            entry_time_ms=window.entry_time_ms,exit_time_ms=window.exit_time_ms)
        query = ReviewEconomicsRequest(ticket_id=aggregate.identity.ticket_id,netting_domain=domain,
            expected_entry_quantity=window.executed_entry_quantity,entry_order_reference=entries[0],
            exit_order_references=exits,entry_time_ms=window.entry_time_ms,exit_time_ms=window.exit_time_ms,
            funding_attribution_exact=not overlap,observed_at_ms=now_ms)
    try:
        import asyncio
        facts = await asyncio.wait_for(source.read_review_economics(query),timeout=10)
        if facts.ticket_id != query.ticket_id:
            raise ValueError('enrichment economics identity mismatch')
        economics = calculate_review_economics(facts=facts,expected_entry_quantity=query.expected_entry_quantity,
            position_side=domain.position_side,planned_risk_at_stop=aggregate.ticket.risk_at_stop,
            actual_risk_at_stop=aggregate.actual_stop_risk)
        metrics = {**old.metrics,**economics.model_dump(mode='json'),
            'external_exit_evidence':[r.model_dump(mode='json') for r in exits if isinstance(r,ExternalExitOrderReference)],
            'order_attribution':[f.to_attributed_trade_fill().model_dump(mode='json') for f in (*facts.entry_fills,*facts.exit_fills)],
            'order_attribution_digest': attribution_digest(tuple(f.to_attributed_trade_fill() for f in (*facts.entry_fills,*facts.exit_fills)))}
        preview = ReviewEnrichmentPreview.model_validate({'ticket_id':query.ticket_id,'expected_review_id':old.review_id,
            'old_metrics_digest':canonical_digest(old.metrics),'old_metrics':old.metrics,'metrics':metrics,
            'entry_quantity':str(sum(f.quantity for f in facts.entry_fills)),
            'exit_quantity':str(sum(f.quantity for f in facts.exit_fills)),
            'prepared_at_ms':now_ms})
        digest = canonical_digest(preview)
    except Exception as exc:  # noqa: BLE001 - bounded readonly retry preserves missing economics.
        async with uow_factory() as uow:
            await uow.reviews.retry_enrichment(request.request_id,reason=type(exc).__name__,now_ms=now_ms)
            from src.trading_kernel.domain.operational_evidence import FailureDiagnostic
            await uow.signals.record_operational_failure(FailureDiagnostic(stage='review',subject_id=aggregate.identity.ticket_id,
                reason_code='review_evidence_unavailable',basis={'error_type':type(exc).__name__,'request_id':request.request_id,
                'account_id':domain.account_id,'instrument':domain.exchange_instrument_id},occurred_at_ms=now_ms))
        return True
    async with uow_factory() as uow:
        latest = await uow.aggregates.get_for_update(query.ticket_id)
        if latest is None or latest.review_id != old.review_id:
            await uow.reviews.finish_enrichment(request.request_id,state='superseded',now_ms=now_ms)
        else:
            await uow.reviews.save_enrichment_preview(request.request_id,preview=preview,digest=digest,now_ms=now_ms)
    return True


async def apply_review_enrichment(uow: KernelUnitOfWork, *, request_id: str, approved_preview_digest: str,
    owner_authorization_id: str, now_ms: int) -> str:
    """Called only after a human approved this exact accounting difference."""
    authorization = await uow.owner_controls.get_authorization(owner_authorization_id)
    if authorization is None or authorization.purpose != 'review_revise' or authorization.authentication_strength != 'totp_step_up':
        raise ValueError('genuine Owner review authorization required')
    if authorization.target_scope.get('request_id') != request_id or authorization.target_scope.get('preview_digest') != approved_preview_digest:
        raise ValueError('Owner authorization differs from exact preview')
    request = await uow.reviews.get_enrichment(request_id,for_update=True)
    if request is None or request.preview_digest != approved_preview_digest:
        raise ValueError('approved enrichment preview differs')
    new_id = 'review:enriched:' + approved_preview_digest[7:]
    if request.state == 'applied':
        return new_id
    if request.state not in {'preview_ready','approved'} or request.preview is None or canonical_digest(request.preview) != approved_preview_digest:
        raise ValueError('enrichment is not a verified preview')
    preview = request.preview
    aggregate = await uow.aggregates.get_for_update(request.ticket_id)
    if aggregate is None or aggregate.review_id != request.expected_review_id:
        raise ValueError('enrichment predecessor changed')
    if (authorization.target_scope.get('account_id') != aggregate.identity.netting_domain.account_id
        or authorization.target_scope.get('product_id') != 'brc-app-manual-v1'
        or authorization.authorized_at_ms > now_ms):
        raise ValueError('Owner authorization account, product or time differs')
    old = await uow.reviews.get_for_ticket(request.ticket_id)
    if old is None or canonical_digest(old.metrics) != preview.old_metrics_digest:
        raise ValueError('enrichment predecessor metrics changed')
    await revise_trade_review(uow,ReviseTradeReviewRequest(ticket_id=request.ticket_id,review_id=new_id,
        supersedes_review_id=old.review_id,outcome=old.outcome,metrics=preview.metrics,
        decision_impact={'status':'economics_enriched','preview_digest':approved_preview_digest,
            'owner_authorization_id':owner_authorization_id,'source_request_id':request_id},recorded_at_ms=now_ms))
    await uow.reviews.finish_enrichment(request_id,state='applied',now_ms=now_ms,owner_authorization_id=owner_authorization_id)
    from src.trading_kernel.application.reconciliation_health import (
        resolve_reconciliation_wait,
    )
    await resolve_reconciliation_wait(uow,key='reconciliation-closure:'+request.ticket_id,now_ms=now_ms,
        economics_complete=preview.metrics.get('economics_completeness')=='complete')
    return new_id
