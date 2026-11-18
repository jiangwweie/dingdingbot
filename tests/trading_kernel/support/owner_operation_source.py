"""Deterministic venue facts for persistent operation tests; no real exchange API."""
from src.trading_kernel.application.owner_operation_facts import (
    OwnerOrderObservation,
    OwnerPositionObservation,
)
from src.trading_kernel.domain.commands import ExchangeCommandKind as K
from src.trading_kernel.domain.commands import (
    ExchangeCommandResult,
    OrderCommandPayload,
)
from src.trading_kernel.domain.commands import ExchangeCommandStatus as S
from src.trading_kernel.domain.trade_management import (
    OrderAction,
    OrderEvidence,
    OrderTerms,
)
from tests.trading_kernel.support.owner_reduction import facts


class OwnerOperationVenue:
    async def execute(self,request):
        oid=request.payload.exchange_order_id if request.kind is K.CANCEL_ORDER else 'owner-order:'+request.command_id
        return ExchangeCommandResult(status=S.ACCEPTED,exchange_order_id=oid,observed_at_ms=request.deadline_at_ms-29000)


class OwnerOperationSource:
    at=7000
    async def read_owner_position(self,*,aggregate,commands,accepted_order_ids,operation_id):
        a=aggregate;d=a.identity.netting_domain
        cancelled={c.payload.exchange_order_id for c in commands if c.kind is K.CANCEL_ORDER and c.status in {S.ACCEPTED,S.RECONCILED_ABSENT}}
        observations=[]
        for c in commands:
            if not isinstance(c.payload,OrderCommandPayload) or c.command_id not in accepted_order_ids or c.kind is K.ENTRY:continue
            p=c.payload;oid=accepted_order_ids[c.command_id]
            ns='conditional' if p.order_type=='stop_market' else 'regular'
            terms=OrderTerms(venue_id=d.venue_id,account_id=d.account_id,exchange_instrument_id=d.exchange_instrument_id,
                position_side=d.position_side,order_namespace=ns,exchange_order_id=oid,client_order_id=c.venue_client_order_id,
                side=p.side,order_type=p.order_type.upper(),quantity=p.venue_quantity,price=p.limit_price,trigger_price=p.stop_price,
                close_position=p.close_position,reduce_only=p.reduce_only,time_in_force=p.time_in_force or 'GTC',working_type='CONTRACT_PRICE',
                price_protect=False,activation_price=None,callback_rate=None,price_match='NONE',self_trade_prevention_mode='NONE',good_till_date_ms=0)
            evidence=OrderEvidence(evidence_id='protocol:'+c.command_id+':'+str(self.at),terms=terms,
                action=OrderAction.CANCEL if oid in cancelled else OrderAction.NEW,created_at_ms=c.created_at_ms,
                exchange_event_at_ms=self.at,received_at_ms=self.at,executed_quantity=0,coverage_complete=True,known_command_outcome_pending=False)
            observations.append(OwnerOrderObservation(command_id=c.command_id,evidence=evidence,status='CANCELED' if oid in cancelled else 'NEW'))
        tp_cancel=a.tp1_exchange_order_id in cancelled
        return OwnerPositionObservation(facts=facts(a,observed_at_ms=self.at,valid_until_ms=self.at+3000,
            tp_state='cancelled' if tp_cancel else 'absent' if a.tp1_exchange_order_id is None else 'open'),
            orders=tuple(observations),protection_close_position=a.active_stop_close_position)
