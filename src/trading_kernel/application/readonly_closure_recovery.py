"""Recover one externally closed trade through normal events; no venue write port."""

from __future__ import annotations

from decimal import Decimal

from src.trading_kernel.application.management_intents import accepted_order_identities
from src.trading_kernel.application.observe_trade_management import (
    observe_trade_management,
)
from src.trading_kernel.application.ports import KernelUnitOfWork
from src.trading_kernel.application.reconcile_ticket import (
    ReconcileTicketRequest,
    reconcile_ticket,
)
from src.trading_kernel.application.settle_ticket import (
    RecordTradeReviewRequest,
    SettleTicketRequest,
    record_trade_review,
    settle_ticket,
)
from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.readonly_closure import ReadonlyClosureProof


async def recover_readonly_closure(uow: KernelUnitOfWork, *, proof: ReadonlyClosureProof, now_ms: int) -> str:
    proof=ReadonlyClosureProof.model_validate(proof.model_dump())
    a=await uow.aggregates.get_for_update(proof.ticket_id)
    if a is None or a.identity.netting_domain != proof.domain:
        raise ValueError("closure Ticket identity differs")
    if a.status is AggregateStatus.TERMINAL:
        return "terminal"
    if not proof.observed_at_ms<=now_ms<proof.valid_until_ms:
        raise ValueError("closure proof expired")
    if a.management_mode.value not in {"REVIEW_REQUIRED","MANUAL"} or a.post_fill_stress_status != "passed":
        raise ValueError("closure requires previously protected managed Ticket")
    rows=await uow.management.command_rows(proof.ticket_id)
    if any(r['status'] in {'prepared','claimed','dispatch_started','outcome_unknown'} for r in rows):
        raise ValueError("closure has unresolved command")
    own=accepted_order_identities(rows)
    terminal={(o.namespace,o.order_id):o for o in proof.terminal_orders}
    if not own <= terminal.keys() or ('regular',proof.exit_order_id) in own:
        raise ValueError("closure orders unresolved or exit is system-owned")
    entries=[r for r in rows if r['command_kind']=='entry' and r['status'] in {'accepted','reconciled_accepted'}]
    if len(entries)!=1 or entries[0]['result_payload'].get('exchange_order_id')!=proof.entry_order_id:
        raise ValueError("closure entry identity differs")
    quantity=a.ticket.quantity
    if any(sum((f.quantity for f in fills),Decimal(0))!=quantity for fills in [proof.entry_fills,proof.exit_fills]):
        raise ValueError("closure does not account for full entry and exit")
    if min(f.occurred_at_ms for f in proof.entry_fills)<a.ticket.created_at_ms:
        raise ValueError("closure entry predates Ticket")
    for order_id in [proof.entry_order_id,proof.exit_order_id]:
        o=terminal.get(('regular',order_id))
        if o is None or o.status!='FILLED' or o.executed_quantity!=quantity:
            raise ValueError("closure filled order proof missing")
    if any(o.executed_quantity != 0 for o in proof.terminal_orders if (o.namespace,o.order_id) not in {('regular',proof.entry_order_id),('regular',proof.exit_order_id)}):
        raise ValueError("closure has additional executions")
    if proof.exit_evidence.executed_quantity != quantity:
        raise ValueError("closure execution evidence quantity differs")
    evidence=proof.exit_evidence
    await observe_trade_management(uow,ticket_id=proof.ticket_id,evidence=evidence,now_ms=now_ms)
    await reconcile_ticket(uow,ReconcileTicketRequest(ticket_id=proof.ticket_id,snapshot=proof.snapshot))
    a=await uow.aggregates.get(proof.ticket_id)
    if a is None or a.status is not AggregateStatus.SETTLEMENT_PENDING:
        raise ValueError("closure did not release exactly proven authorities")
    await settle_ticket(uow,SettleTicketRequest(ticket_id=proof.ticket_id,settled_at_ms=now_ms))
    entry_value=sum((f.quantity*f.price for f in proof.entry_fills),Decimal(0))
    exit_value=sum((f.quantity*f.price for f in proof.exit_fills),Decimal(0))
    gross=(exit_value-entry_value)*(1 if proof.domain.position_side=='long' else -1)
    await record_trade_review(uow,RecordTradeReviewRequest(ticket_id=proof.ticket_id,
        review_id=f"review:readonly-closure:{proof.ticket_id}",outcome='external_closed_readonly',
        metrics={'gross_realized_pnl_quote':str(gross),'net_pnl_quote':None,
            'economics_completeness':'incomplete_evidence','unavailable_reason':'fees_and_funding_not_yet_valued',
            'readonly_closure_proof':proof.model_dump(mode='json'),'readonly_closure_proof_digest':proof.digest()},
        decision_impact={'source':'confirmed_external_exit','net_pnl_status':'unavailable'},recorded_at_ms=now_ms))
    return "terminal"
