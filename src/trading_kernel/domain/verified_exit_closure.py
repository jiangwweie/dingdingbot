"""Exact system-exit facts that authorize accounting closure, never venue writes."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.identities import NettingDomain
from src.trading_kernel.domain.order_attribution import (
    OrderNamespace,
    OrderRole,
    TicketOrderReference,
)
from src.trading_kernel.domain.position import PositionSnapshot
from src.trading_kernel.domain.readonly_closure import ClosureFill
from src.trading_kernel.domain.trade_management import OrderTerms


class VerifiedClosureOrder(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    reference: TicketOrderReference
    terms: OrderTerms
    status: Literal[
        "FILLED", "CANCELED", "EXPIRED", "EXPIRED_IN_MATCH", "FINISHED", "REJECTED"
    ]
    executed_quantity: Decimal = Field(ge=0, allow_inf_nan=False)
    actual_order_id: str | None = None
    updated_at_ms: int = Field(gt=0)

    @model_validator(mode="after")
    def exact(self):
        r, t = self.reference, self.terms
        if (
            r.submitted_exchange_order_id != t.exchange_order_id
            or r.venue_client_order_id != t.client_order_id
            or r.namespace.value != t.order_namespace
        ):
            raise ValueError("closure order differs from durable identity")
        if t.quantity is None or self.executed_quantity > t.quantity:
            raise ValueError("closure execution exceeds original order")
        if r.namespace is OrderNamespace.CONDITIONAL:
            e = r.conditional_expectation
            if e is None or (
                t.exchange_instrument_id,
                t.position_side,
                t.side,
                t.order_type.lower(),
                t.quantity,
            ) != (
                e.exchange_instrument_id,
                e.position_side,
                e.side,
                e.order_type,
                e.quantity,
            ):
                raise ValueError("closure conditional terms differ")
            if self.executed_quantity > 0 and (
                self.status != "FINISHED" or not self.actual_order_id
            ):
                raise ValueError("executed conditional needs finished child identity")
        elif self.actual_order_id is not None:
            raise ValueError("regular order cannot declare conditional child")
        if self.updated_at_ms < r.command_created_at_ms:
            raise ValueError("closure terminal order predates command")
        if (
            r.namespace is OrderNamespace.REGULAR
            and self.executed_quantity > 0
            and self.status not in {"FILLED", "CANCELED", "EXPIRED", "EXPIRED_IN_MATCH"}
        ):
            raise ValueError("regular execution terminal status differs")
        return self

    @property
    def executable_id(self) -> str | None:
        return (
            self.actual_order_id
            if self.reference.namespace is OrderNamespace.CONDITIONAL
            else self.terms.exchange_order_id
        )


class VerifiedExitClosureProof(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    ticket_id: str = Field(min_length=1)
    domain: NettingDomain
    expected_version: int = Field(gt=0)
    management_revision: int = Field(gt=0)
    entry_quantity: Decimal = Field(gt=0, allow_inf_nan=False)
    orders: tuple[VerifiedClosureOrder, ...] = Field(min_length=2, max_length=128)
    entry_fills: tuple[ClosureFill, ...] = Field(min_length=1, max_length=1000)
    exit_fills: tuple[ClosureFill, ...] = Field(min_length=1, max_length=1000)
    snapshot: PositionSnapshot
    incident_ids: tuple[str, ...] = Field(default=(), max_length=16)
    observed_at_ms: int = Field(gt=0)
    valid_until_ms: int = Field(gt=0)

    @model_validator(mode="after")
    def coherent(self):
        if (
            self.snapshot.netting_domain != self.domain
            or self.snapshot.quantity != 0
            or self.snapshot.open_orders
            or not self.snapshot.orders_complete
        ):
            raise ValueError("closure requires exact flat complete snapshot")
        if (
            self.snapshot.observed_at_ms != self.observed_at_ms
            or not 0 < self.valid_until_ms - self.observed_at_ms <= 30_000
        ):
            raise ValueError("closure freshness window differs")
        if len(set(self.incident_ids)) != len(self.incident_ids) or any(
            not x.strip() for x in self.incident_ids
        ):
            raise ValueError("closure incident identities differ")
        keys = [
            (o.reference.namespace, o.reference.submitted_exchange_order_id)
            for o in self.orders
        ]
        if len(set(keys)) != len(keys):
            raise ValueError("closure order duplicated")
        entry = [o for o in self.orders if o.reference.role is OrderRole.ENTRY]
        if (
            len(entry) != 1
            or entry[0].executed_quantity != self.entry_quantity
            or entry[0].status != "FILLED"
        ):
            raise ValueError("closure needs exact complete entry")
        domain = (
            self.domain.venue_id,
            self.domain.account_id,
            self.domain.exchange_instrument_id,
            self.domain.position_side,
        )
        for o in self.orders:
            if o.terms.identity[:4] != domain or o.updated_at_ms > self.observed_at_ms:
                raise ValueError("closure order domain or timestamp differs")
            expected_side = (
                ("buy" if self.domain.position_side == "long" else "sell")
                if o.reference.role is OrderRole.ENTRY
                else ("sell" if self.domain.position_side == "long" else "buy")
            )
            if o.terms.side != expected_side:
                raise ValueError("closure direction differs")
        all_fills = (*self.entry_fills, *self.exit_fills)
        if len({f.trade_id for f in all_fills}) != len(all_fills):
            raise ValueError("closure trade duplicated")
        if any(
            sum((f.quantity for f in fills), Decimal(0)) != self.entry_quantity
            for fills in [self.entry_fills, self.exit_fills]
        ):
            raise ValueError("closure quantity does not conserve entry")
        if (
            max(f.occurred_at_ms for f in self.entry_fills)
            > min(f.occurred_at_ms for f in self.exit_fills)
            or max(f.occurred_at_ms for f in all_fills) > self.observed_at_ms
        ):
            raise ValueError("closure execution chronology differs")
        executable = {
            o.executable_id: o for o in self.orders if o.executable_id is not None
        }
        if len(executable) != len(
            [o for o in self.orders if o.executable_id is not None]
        ):
            raise ValueError("closure executable identity duplicated")
        for role, fills in [
            (OrderRole.ENTRY, self.entry_fills),
            (OrderRole.EXIT, self.exit_fills),
        ]:
            for f in fills:
                o = executable.get(f.order_id)
                if (
                    o is None
                    or o.reference.role is not role
                    or f.occurred_at_ms < o.reference.command_created_at_ms
                ):
                    raise ValueError("closure trade does not belong to exact command")
        for oid, o in executable.items():
            if (
                sum((f.quantity for f in all_fills if f.order_id == oid), Decimal(0))
                != o.executed_quantity
            ):
                raise ValueError("closure order and trade quantity disagree")
        return self

    @property
    def exit_quantity(self) -> Decimal:
        return sum((f.quantity for f in self.exit_fills), Decimal(0))

    @property
    def exit_time_ms(self) -> int:
        return max(f.occurred_at_ms for f in self.exit_fills)

    @property
    def exit_reason(self) -> str:
        last = max(self.exit_fills, key=lambda f: (f.occurred_at_ms, f.trade_id))
        order = next(o for o in self.orders if o.executable_id == last.order_id)
        return {
            "initial_stop": "initial_stop_triggered",
            "replace_protection": "runner_stop",
            "take_profit": "take_profit_triggered",
        }.get(order.reference.command_kind.value, "strategy_exit")

    def digest(self) -> str:
        return canonical_digest(self.model_dump(mode="json"))

    def content_digest(self) -> str:
        payload = self.model_dump(mode="json")
        payload.pop("observed_at_ms")
        payload.pop("valid_until_ms")
        payload["snapshot"].pop("observed_at_ms")

        def financial(value):
            if isinstance(value, dict):
                return {k: financial(v) for k, v in value.items()}
            if isinstance(value, (tuple, list)):
                return [financial(v) for v in value]
            if isinstance(value, Decimal):
                return format(value.normalize(), "f")
            return value

        exact = self.model_dump(mode="python")
        exact.pop("observed_at_ms")
        exact.pop("valid_until_ms")
        exact["snapshot"].pop("observed_at_ms")
        return canonical_digest(financial(exact))
