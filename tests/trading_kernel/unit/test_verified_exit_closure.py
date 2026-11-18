import pytest

from src.trading_kernel.domain.verified_exit_closure import VerifiedExitClosureProof


def proof_payload():
    from tests.trading_kernel.support.lifecycle import registered_sor_long_ticket

    t = registered_sor_long_ticket()
    d = t.identity.netting_domain

    def order(cid, kind, namespace, oid, side, typ, q, filled, child=None):
        terms = {
            "venue_id": d.venue_id,
            "account_id": d.account_id,
            "exchange_instrument_id": d.exchange_instrument_id,
            "position_side": d.position_side,
            "order_namespace": namespace,
            "exchange_order_id": oid,
            "client_order_id": cid,
            "side": side,
            "order_type": typ,
            "quantity": str(q),
            "price": None,
            "trigger_price": "59000" if namespace == "conditional" else None,
            "close_position": False,
            "reduce_only": namespace == "conditional",
            "time_in_force": "GTC",
            "working_type": "CONTRACT_PRICE",
            "price_protect": False,
            "activation_price": None,
            "callback_rate": None,
            "price_match": "NONE",
            "self_trade_prevention_mode": "EXPIRE_MAKER",
            "good_till_date_ms": 0,
        }
        ref = {
            "command_id": cid,
            "command_kind": kind,
            "role": "entry" if kind == "entry" else "exit",
            "namespace": namespace,
            "venue_client_order_id": cid,
            "submitted_exchange_order_id": oid,
            "command_created_at_ms": 1000,
            "conditional_expectation": None
            if namespace == "regular"
            else {
                "exchange_instrument_id": d.exchange_instrument_id,
                "position_side": d.position_side,
                "side": side,
                "order_type": "stop_market",
                "quantity": str(q),
            },
        }
        return {
            "reference": ref,
            "terms": terms,
            "status": "FILLED" if namespace == "regular" else "FINISHED",
            "executed_quantity": str(filled),
            "actual_order_id": child,
            "updated_at_ms": 3000,
        }

    q = t.quantity
    return {
        "ticket_id": t.identity.ticket_id,
        "domain": d.model_dump(mode="json"),
        "expected_version": 6,
        "management_revision": 1,
        "entry_quantity": str(q),
        "orders": [
            order("entry", "entry", "regular", "11", "buy", "MARKET", q, q),
            order(
                "stop",
                "initial_stop",
                "conditional",
                "12",
                "sell",
                "STOP_MARKET",
                q,
                q,
                "13",
            ),
        ],
        "entry_fills": [
            {
                "trade_id": "e1",
                "order_id": "11",
                "quantity": str(q),
                "price": "60000",
                "occurred_at_ms": 2000,
            }
        ],
        "exit_fills": [
            {
                "trade_id": "x1",
                "order_id": "13",
                "quantity": str(q),
                "price": "59000",
                "occurred_at_ms": 3000,
            }
        ],
        "snapshot": {
            "netting_domain": d.model_dump(mode="json"),
            "quantity": "0",
            "average_entry_price": None,
            "open_orders": [],
            "orders_complete": True,
            "observed_at_ms": 4000,
        },
        "incident_ids": [],
        "observed_at_ms": 4000,
        "valid_until_ms": 34000,
    }


def test_exact_stop_child_closure_and_partial_stop_quantity_are_distinct():
    p = VerifiedExitClosureProof.model_validate(proof_payload())
    assert p.exit_reason == "initial_stop_triggered"
    assert p.exit_quantity == p.entry_quantity


@pytest.mark.parametrize(
    "defect",
    [
        "quantity",
        "child",
        "duplicate_trade",
        "open_order",
        "stale_window",
        "wrong_side",
        "wrong_client",
    ],
)
def test_ambiguous_or_incomplete_closure_is_rejected(defect):
    p = proof_payload()
    if defect == "quantity":
        p["exit_fills"][0]["quantity"] = "0.00001"
    elif defect == "child":
        p["orders"][1]["actual_order_id"] = "unrelated"
    elif defect == "duplicate_trade":
        p["exit_fills"][0]["trade_id"] = "e1"
    elif defect == "open_order":
        p["snapshot"]["orders_complete"] = False
    elif defect == "stale_window":
        p["valid_until_ms"] = 4000
    elif defect == "wrong_side":
        p["orders"][1]["terms"]["side"] = "buy"
    elif defect == "wrong_client":
        p["orders"][1]["terms"]["client_order_id"] = "alien"
    with pytest.raises(ValueError):
        VerifiedExitClosureProof.model_validate(p)


@pytest.mark.parametrize('same_time',[False,True])
def test_partial_owner_reduction_is_accounted_separately_from_final_exit(same_time):
    from copy import deepcopy
    from decimal import Decimal
    p=proof_payload();half=Decimal(p['entry_quantity'])/2
    stop=p['orders'][1];stop['terms']['quantity']=str(half);stop['executed_quantity']=str(half)
    stop['reference']['conditional_expectation']['quantity']=str(half)
    owner=deepcopy(stop);owner.update(actual_order_id=None,status='FILLED')
    owner['reference'].update(command_id='reduce',command_kind='owner_reduce',namespace='regular',
        venue_client_order_id='reduce-client',submitted_exchange_order_id='reduce-order',conditional_expectation=None)
    owner['terms'].update(order_namespace='regular',exchange_order_id='reduce-order',client_order_id='reduce-client',order_type='MARKET',trigger_price=None)
    p['orders'].append(owner);p['exit_fills'][0]['quantity']=str(half)
    p['exit_fills'].append({'trade_id':'z-reduce','order_id':'reduce-order','quantity':str(half),'price':'61000','occurred_at_ms':3000 if same_time else 2500})
    proof=VerifiedExitClosureProof.model_validate(p)
    assert proof.exit_quantity==proof.entry_quantity
    assert proof.exit_reason==('concurrent_exit_fills' if same_time else 'initial_stop_triggered')


def test_close_all_closure_uses_executions_and_preserves_conservation():
    p = proof_payload()
    stop = p['orders'][1]
    stop['terms'].update(quantity=None, close_position=True, reduce_only=False)
    stop['reference']['conditional_expectation'].update(quantity=None, close_position=True)
    proof = VerifiedExitClosureProof.model_validate(p)
    assert proof.exit_quantity == proof.entry_quantity
    p['exit_fills'][0]['quantity'] = '0.00001'
    with pytest.raises(ValueError, match='conserve'):
        VerifiedExitClosureProof.model_validate(p)

def test_verified_external_close_can_complete_after_a_real_partial_system_tp():
    from copy import deepcopy
    from decimal import Decimal as D
    p=proof_payload()
    stop=p['orders'][1]
    stop.update(status='CANCELED',executed_quantity='0',actual_order_id=None)
    own_tp=deepcopy(p['orders'][0])
    half=D(p['entry_quantity'])/2
    own_tp['reference'].update(command_id='tp',command_kind='take_profit',role='exit',submitted_exchange_order_id='14',venue_client_order_id='tp')
    own_tp['terms'].update(exchange_order_id='14',client_order_id='tp',side='sell',quantity=str(half))
    own_tp['executed_quantity']=str(half)
    external=deepcopy(own_tp)
    external['terms'].update(exchange_order_id='15',client_order_id='app-close')
    external['reference']={'ticket_id':p['ticket_id'],'exposure_episode_id':'episode', 'evidence_id':'external-proof',
        'terms':external['terms'],'order_created_at_ms':2500,'evidence_at_ms':3000}
    p['orders'] += [own_tp,external]
    p['exit_fills']=[{'trade_id':'tp-fill','order_id':'14','quantity':str(half),'price':'61000','occurred_at_ms':2900},
        {'trade_id':'external-fill','order_id':'15','quantity':str(half),'price':'62000','occurred_at_ms':3000}]
    proof=VerifiedExitClosureProof.model_validate(p)
    assert proof.exit_quantity==proof.entry_quantity and proof.exit_reason=='verified_external_exit'
