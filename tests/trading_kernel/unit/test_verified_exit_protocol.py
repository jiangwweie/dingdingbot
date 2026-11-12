import json
from copy import deepcopy
from decimal import Decimal as D
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.trading_kernel.domain.identities import NettingDomain
from src.trading_kernel.domain.order_attribution import TicketOrderReference
from src.trading_kernel.infrastructure.verified_exit_source import collect_verified_exit

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures/manual_natural_exit/ada_stop_protocol.json"
)


def fixture():
    raw = json.loads(FIXTURE.read_text())
    domain = NettingDomain(
        venue_id="binance-usdm",
        account_id="protocol-account",
        exchange_instrument_id="binance-usdm:ADAUSDT:perpetual",
        position_side="short",
    )
    refs = []
    for kind, key in [
        ("entry", "entry"),
        ("initial_stop", "stop"),
        ("take_profit", "tp"),
    ]:
        row = raw[key]
        cond = key == "stop"
        refs.append(
            TicketOrderReference(
                command_id="command-" + kind,
                command_kind=kind,
                role="entry" if kind == "entry" else "exit",
                namespace="conditional" if cond else "regular",
                venue_client_order_id=row["clientAlgoId" if cond else "clientOrderId"],
                submitted_exchange_order_id=str(row["algoId" if cond else "orderId"]),
                command_created_at_ms=1794387615656,
                conditional_expectation=None
                if not cond
                else {
                    "exchange_instrument_id": domain.exchange_instrument_id,
                    "position_side": "short",
                    "side": "buy",
                    "order_type": "stop_market",
                    "quantity": "13222",
                },
            )
        )
    a = SimpleNamespace(
        identity=SimpleNamespace(ticket_id="ticket-recorded", netting_domain=domain),
        ticket=SimpleNamespace(quantity=D(13222)),
        version=7,
        management_revision=2,
    )
    return raw, a, tuple(refs)


class Reader:
    def __init__(self, raw):
        self.raw = raw
        self.calls = []
        self.current_reads = 0

    async def read(self, name, params):
        self.calls.append((name, params))
        if name in ["positions", "orders", "algos"]:
            self.current_reads += 1
            return []
        if name == "mode":
            return {"dualSidePosition": True}
        if name == "algo_order":
            return self.raw["stop"]
        if name == "trades":
            return [
                t
                for t in self.raw["trades"]
                if str(t["orderId"]) == str(params["orderId"])
            ]
        for key in ["entry", "tp", "child"]:
            if str(self.raw[key]["orderId"]) == str(params["orderId"]):
                return self.raw[key]
        raise AssertionError("unexpected lookup")


@pytest.mark.asyncio
async def test_recorded_protocol_stop_and_expiry_prove_full_closure():
    raw, a, refs = fixture()
    reader = Reader(raw)
    proof = await collect_verified_exit(
        reader,
        aggregate=a,
        references=refs,
        incident_ids=("cause",),
        clock_ms=lambda: 1794393045000,
    )
    assert (
        proof.exit_quantity == D(13222)
        and proof.exit_reason == "initial_stop_triggered"
    )
    assert len(proof.exit_fills) == 4 and reader.current_reads == 3
    assert (
        proof.content_digest()
        == proof.model_copy(
            update={
                "observed_at_ms": proof.observed_at_ms + 1,
                "valid_until_ms": proof.valid_until_ms + 1,
                "snapshot": proof.snapshot.model_copy(
                    update={"observed_at_ms": proof.observed_at_ms + 1}
                ),
            }
        ).content_digest()
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault",
    [
        "child_id",
        "child_side",
        "child_qty",
        "client",
        "parent_qty",
        "truncated",
        "wrong_trade",
        "nonzero",
        "residual",
        "mode",
    ],
)
async def test_wrong_or_incomplete_protocol_never_proves_closure(fault):
    raw, a, refs = fixture()
    raw = deepcopy(raw)
    reader = Reader(raw)
    if fault == "child_id":
        raw["child"]["orderId"] = "alien"
    elif fault == "child_side":
        raw["child"]["side"] = "SELL"
    elif fault == "child_qty":
        raw["child"]["executedQty"] = "1"
    elif fault == "client":
        raw["stop"]["clientAlgoId"] = "alien"
    elif fault == "parent_qty":
        raw["stop"]["quantity"] = "13223"
    elif fault == "truncated":
        raw["trades"] = [raw["trades"][0]] * 1000
    elif fault == "wrong_trade":
        raw["trades"][1]["positionSide"] = "LONG"
    base = reader.read

    async def bad(name, params):
        if fault == "nonzero" and name == "positions":
            return [{"symbol": "ADAUSDT", "positionSide": "SHORT", "positionAmt": "1"}]
        if fault == "residual" and name == "orders":
            return [{"symbol": "ADAUSDT", "positionSide": "SHORT"}]
        if fault == "mode" and name == "mode":
            return {"dualSidePosition": False}
        return await base(name, params)

    reader.read = bad
    with pytest.raises((ValueError, RuntimeError, AssertionError)):
        await collect_verified_exit(
            reader,
            aggregate=a,
            references=refs,
            incident_ids=(),
            clock_ms=lambda: 1794393045000,
        )


@pytest.mark.asyncio
async def test_stop_actual_child_quantity_is_residual_after_exact_tp_fill():
    raw, a, refs = fixture()
    raw["tp"].update(status="FILLED", executedQty="661")
    raw["stop"]["actualQty"] = "12561"
    raw["child"].update(origQty="12561", executedQty="12561")
    # Reuse exact raw fill identities, with a separate proved TP trade.
    raw["trades"] = [
        raw["trades"][0],
        {**raw["trades"][1], "qty": "12561"},
        {
            **raw["trades"][1],
            "id": "tp-trade",
            "orderId": raw["tp"]["orderId"],
            "qty": "661",
            "price": "0.17260",
            "time": 1794393000000,
        },
    ]
    proof = await collect_verified_exit(
        Reader(raw),
        aggregate=a,
        references=refs,
        incident_ids=(),
        clock_ms=lambda: 1794393045000,
    )
    assert proof.exit_quantity == D(13222) and proof.orders[1].executed_quantity == D(
        12561
    )
