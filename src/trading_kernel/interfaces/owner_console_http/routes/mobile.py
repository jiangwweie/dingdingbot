"""Mobile Owner endpoints: trusted-session reads and signed controlled writes."""

from __future__ import annotations

import hmac
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.trading_kernel.application.owner_control import (
    ControlMutationRequest,
    set_global_entry_state,
    set_strategy_entry_state,
)
from src.trading_kernel.domain.owner_control import StrategyEntryState
from src.trading_kernel.domain.owner_device_authority import (
    DEVICE_IDLE_MS,
    DeviceWriteProof,
)
from src.trading_kernel.domain.owner_position_intent import OwnerPositionIntent
from src.trading_kernel.infrastructure.owner_device_credentials import (
    public_key_thumbprint,
)
from src.trading_kernel.infrastructure.pg_models import (
    management_observation_current,
    owner_policy_current,
    strategy_entry_controls_current,
    strategy_selection_control_current,
    trade_aggregates,
    trade_tickets,
)
from src.trading_kernel.infrastructure.pg_owner_device_repository import (
    PostgresOwnerDeviceRepository,
)
from src.trading_kernel.infrastructure.pg_owner_position_operations import (
    PostgresOwnerPositionOperations,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.interfaces.owner_console_http.dependencies import (
    get_clock_ms,
    get_control_engine,
    get_settings,
)

COOKIE = "__Host-brc_device_session"


async def require_mobile_request(request: Request) -> None:
    settings = get_settings(request)
    if request.url.hostname != settings.public_host:
        raise HTTPException(403, "host_mismatch")
    if (
        request.method != "GET"
        and request.headers.get("origin") != settings.public_origin
    ):
        raise HTTPException(403, "origin_mismatch")
    if request.url.path == "/api/owner/v1/mobile/devices/bind":
        return
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, "device_session_required")
    async with get_control_engine(request).connect() as c:
        try:
            await PostgresOwnerDeviceRepository(c).authenticate(
                token, now_ms=get_clock_ms(request)
            )
        except ValueError:
            raise HTTPException(401, "device_session_unavailable") from None


router = APIRouter(
    prefix="/api/owner/v1/mobile",
    tags=["mobile-owner"],
    dependencies=[Depends(require_mobile_request)],
)


class BindBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=32, max_length=128, repr=False)
    public_key: dict[str, str]


class SignedBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    proof: DeviceWriteProof
    signature: str = Field(min_length=80, max_length=100)
    payload: dict[str, Any]


class GlobalControlPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    owner_policy_id: str = Field(min_length=1, max_length=160)
    enabled: bool
    expected_version: int = Field(gt=0)


class StrategyControlPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    enabled: bool
    expected_version: int = Field(gt=0)
    strategy_group_id: str = Field(min_length=1, max_length=160)


def serial(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: serial(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [serial(v) for v in value]
    return value


def set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE,
        token,
        max_age=DEVICE_IDLE_MS // 1000,
        secure=True,
        httponly=True,
        samesite="strict",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"


@router.post("/devices/bind")
async def bind(request: Request, body: BindBody, response: Response) -> dict:
    # Production is a private Unix socket behind Nginx. Only that peer may
    # supply its overwritten X-Real-IP; network peers cannot spoof the bucket.
    from ipaddress import ip_address

    peer = request.client.host if request.client is not None else None
    source = peer or "unix-socket"
    if peer is None or peer == "unix-socket":
        try:
            source = str(ip_address(request.headers.get("x-real-ip", "")))
        except ValueError:
            source = "unix-socket"
    now = get_clock_ms(request)
    status = 200
    bound = None
    async with get_control_engine(request).begin() as c:
        repository = PostgresOwnerDeviceRepository(c)
        await repository._lock()
        now = get_clock_ms(request)
        bucket, failures = await repository.binding_failures("ip:" + source, now_ms=now)
        token_bucket, token_failures = await repository.binding_failures(
            "token:" + body.token, now_ms=now
        )
        if len(failures) >= 5 or len(token_failures) >= 5:
            status = 429
        else:
            try:
                async with c.begin_nested():
                    bound = await repository.bind(
                        token=body.token, public_key=body.public_key, now_ms=now
                    )
            except ValueError:
                status = 403
            await repository.record_binding_result(
                bucket, failures, success=bound is not None, now_ms=now
            )
            await repository.record_binding_result(
                token_bucket, token_failures, success=bound is not None, now_ms=now
            )
    if status != 200:
        raise HTTPException(
            status,
            "binding_unavailable",
            headers={"Retry-After": "900"} if status == 429 else None,
        )
    assert bound is not None
    token = bound.pop("session_token")
    set_cookie(response, token)
    return bound


@router.get("/session")
async def session(request: Request) -> dict:
    async with get_control_engine(request).connect() as c:
        d, s = await PostgresOwnerDeviceRepository(c).authenticate(
            request.cookies[COOKIE], now_ms=get_clock_ms(request)
        )
    return {
        "device_id": d.device_id,
        "device_epoch": d.epoch,
        "expires_at_ms": s.expires_at_ms,
        "authenticated": True,
        "key_digest": public_key_thumbprint(d.public_key),
    }


@router.post("/session/renew")
async def renew(request: Request, response: Response) -> dict:
    async with get_control_engine(request).begin() as c:
        expiry = await PostgresOwnerDeviceRepository(c).renew(
            request.cookies[COOKIE], now_ms=get_clock_ms(request)
        )
    set_cookie(response, request.cookies[COOKIE])
    return {"expires_at_ms": expiry}


@router.post("/nonces")
async def nonce(request: Request) -> dict:
    async with get_control_engine(request).begin() as c:
        return await PostgresOwnerDeviceRepository(c).issue_nonce(
            request.cookies[COOKIE], now_ms=get_clock_ms(request)
        )


async def authorize(
    c, request: Request, body: SignedBody, purpose: str, now: int
) -> str:
    if body.proof.method != request.method or body.proof.path != request.url.path:
        raise HTTPException(403, "request_proof_target_mismatch")
    try:
        return await PostgresOwnerDeviceRepository(c).authorize(
            token=request.cookies[COOKIE],
            proof=body.proof,
            signature=body.signature,
            body=body.payload,
            purpose=purpose,
            now_ms=now,
            allow_idempotent_replay=True,
            clock_ms=lambda: get_clock_ms(request),
        )
    except ValueError as exc:
        if str(exc) == "request_key_already_used":
            raise HTTPException(409, "request_key_already_used") from None
        raise HTTPException(403, "device_write_unavailable") from None


@router.get("/controls")
async def controls(request: Request) -> dict:
    async with get_control_engine(request).connect() as c:
        policy = (
            (
                await c.execute(
                    sa.select(
                        owner_policy_current.c.owner_policy_id,
                        owner_policy_current.c.policy_version,
                        owner_policy_current.c.new_entry_submit_enabled,
                    ).limit(2)
                )
            )
            .mappings()
            .all()
        )
        if len(policy) != 1:
            raise HTTPException(503, "policy_unavailable")
        strategies = (
            (
                await c.execute(
                    sa.select(strategy_entry_controls_current)
                    .order_by(strategy_entry_controls_current.c.strategy_group_id)
                    .limit(30)
                )
            )
            .mappings()
            .all()
        )
        selection = (
            (
                await c.execute(
                    sa.select(
                        strategy_selection_control_current.c.strategy_group_id,
                        strategy_selection_control_current.c.selection_mode,
                    ).limit(30)
                )
            )
            .mappings()
            .all()
        )
    active = {"CPM-RO-001", "MI-001", "MPG-001", "BRF2-001", "SOR-1H-001"}
    return serial(
        {
            "global": dict(policy[0]),
            "strategies": [
                dict(x) for x in strategies if x["strategy_group_id"] in active
            ],
            "selection": [dict(x) for x in selection],
        }
    )


@router.post("/controls/global")
async def global_control(request: Request, body: SignedBody) -> dict:
    try:
        payload = GlobalControlPayload.model_validate(body.payload).model_dump()
    except ValidationError:
        raise HTTPException(422, "invalid_control") from None
    if payload["owner_policy_id"] != get_settings(request).owner_policy_id:
        raise HTTPException(403, "policy_identity_mismatch")
    now = get_clock_ms(request)
    async with PostgresKernelUnitOfWork(get_control_engine(request)) as u:
        c = u._require_connection()
        owner = await authorize(
            c,
            request,
            body,
            "entry_resume" if payload["enabled"] else "entry_pause",
            now,
        )
        receipt = await PostgresOwnerDeviceRepository(c).write_receipt(body.proof)
        if receipt is not None:
            return receipt
        now = await PostgresOwnerDeviceRepository(c).write_authorized_at(body.proof)
        result = await set_global_entry_state(
            u,
            owner_policy_id=get_settings(request).owner_policy_id,
            enabled=payload["enabled"],
            request=ControlMutationRequest(
                expected_version=payload["expected_version"],
                owner_identity=owner,
                reason="Owner mobile control",
                idempotency_key=body.proof.idempotency_key,
                now_ms=now,
            ),
            authentication_strength="trusted_device_session",
        )
        auth = await u.owner_controls.get_authorization_by_idempotency_key(
            body.proof.idempotency_key
        )
        response = {
            "enabled": result.new_entry_submit_enabled,
            "version": result.policy_version,
        }
        await PostgresOwnerDeviceRepository(u._require_connection()).finish_control(
            proof=body.proof,
            owner_identity=owner,
            authorization_id=None if auth is None else auth.authorization_id,
            result=response,
        )
    return response


@router.post("/controls/strategy")
async def strategy_control(request: Request, body: SignedBody) -> dict:
    try:
        p = StrategyControlPayload.model_validate(body.payload).model_dump()
    except ValidationError:
        raise HTTPException(422, "invalid_strategy_control") from None
    if p["strategy_group_id"] not in {
        "CPM-RO-001",
        "MI-001",
        "MPG-001",
        "BRF2-001",
        "SOR-1H-001",
    }:
        raise HTTPException(422, "invalid_strategy_control")
    now = get_clock_ms(request)
    async with PostgresKernelUnitOfWork(get_control_engine(request)) as u:
        owner = await authorize(
            u._require_connection(),
            request,
            body,
            "strategy_resume" if p["enabled"] else "strategy_pause",
            now,
        )
        receipt = await PostgresOwnerDeviceRepository(
            u._require_connection()
        ).write_receipt(body.proof)
        if receipt is not None:
            return receipt
        now = await PostgresOwnerDeviceRepository(
            u._require_connection()
        ).write_authorized_at(body.proof)
        result = await set_strategy_entry_state(
            u,
            strategy_group_id=p["strategy_group_id"],
            target_state=StrategyEntryState.ENABLED
            if p["enabled"]
            else StrategyEntryState.PAUSED,
            request=ControlMutationRequest(
                expected_version=p["expected_version"],
                owner_identity=owner,
                reason="Owner mobile control",
                idempotency_key=body.proof.idempotency_key,
                now_ms=now,
            ),
            authentication_strength="trusted_device_session",
        )
        auth = await u.owner_controls.get_authorization_by_idempotency_key(
            body.proof.idempotency_key
        )
        response = result.model_dump(mode="json")
        await PostgresOwnerDeviceRepository(u._require_connection()).finish_control(
            proof=body.proof,
            owner_identity=owner,
            authorization_id=None if auth is None else auth.authorization_id,
            result=response,
        )
    return response


def _reduction_basis(settings, *, ticket_id: str, version: int, quantity: str) -> str:
    import json

    message = json.dumps(
        ["mobile-reduce-v1", settings.venue_id, settings.account_id,
         ticket_id, version, quantity],
        separators=(",", ":"),
    ).encode()
    return hmac.digest(settings.auth.session_signing_key.encode(), message, "sha256").hex()


@router.get("/positions")
async def positions(request: Request) -> dict:
    settings = get_settings(request)
    async with get_control_engine(request).connect() as c:
        rows = (
            (
                await c.execute(
                    sa.select(
                        trade_tickets.c.ticket_id,
                        trade_tickets.c.exchange_instrument_id,
                        trade_tickets.c.position_side,
                        trade_tickets.c.strategy_group_id,
                        trade_tickets.c.selected_leverage,
                        trade_aggregates.c.version,
                        trade_aggregates.c.position_qty,
                        trade_aggregates.c.tp1_exchange_order_id,
                        trade_aggregates.c.manual_profit_plan,
                        trade_aggregates.c.average_fill_price,
                        trade_aggregates.c.active_stop_price,
                        trade_aggregates.c.protected_qty,
                        trade_aggregates.c.management_mode,
                        trade_aggregates.c.status,
                        trade_aggregates.c.updated_at_ms,
                    )
                    .join(
                        trade_aggregates,
                        trade_tickets.c.ticket_id == trade_aggregates.c.ticket_id,
                    )
                    .where(
                        trade_tickets.c.venue_id == settings.venue_id,
                        trade_tickets.c.account_id == settings.account_id,
                        trade_tickets.c.terminal_at_ms.is_(None),
                    )
                    .order_by(trade_tickets.c.created_at_ms)
                    .limit(51)
                )
            )
            .mappings()
            .all()
        )
    if len(rows) > 50:
        raise HTTPException(503, "position_scope_exceeded")
    async with get_control_engine(request).connect() as c:
        from src.trading_kernel.infrastructure.pg_models import (
            owner_position_operations as ops,
        )
        busy_ids=set((await c.execute(sa.select(ops.c.ticket_id).where(ops.c.ticket_id.in_([x['ticket_id'] for x in rows]),
            ops.c.completed_at_ms.is_(None),ops.c.state.notin_(['previewed','preview_requested'])))).scalars())
        try:
            await require_position_capability(c, request)
            capable = True
        except HTTPException:
            capable = False
    return serial(
        {
            "items": [
                {
                    **{k: v for k, v in x.items() if k != "manual_profit_plan"},
                    "manual_tp_active": bool(
                        x["tp1_exchange_order_id"] and x["manual_profit_plan"]
                        and not x["manual_profit_plan"]["cancelled"]
                    ),
                    "reduction_basis_token": _reduction_basis(
                        settings, ticket_id=x["ticket_id"], version=x["version"],
                        quantity=str(x["position_qty"]),
                    ) if x["position_qty"] > 0 else None,
                    "capabilities": {
                        "reduce": capable
                        and x["ticket_id"] not in busy_ids
                        and x["management_mode"] == "AUTO"
                        and x["position_qty"] > 0,
                        "close": capable
                        and x["ticket_id"] not in busy_ids
                        and x["management_mode"] == "AUTO"
                        and x["position_qty"] > 0,
                        "tighten": capable
                        and x["ticket_id"] not in busy_ids
                        and x["management_mode"] == "AUTO"
                        and x["position_qty"] > 0,
                        "tp": capable
                        and x["ticket_id"] not in busy_ids
                        and x["management_mode"] == "AUTO"
                        and x["position_qty"] > 0,
                    },
                }
                for x in rows
            ],
            "observed_at_ms": get_clock_ms(request),
        }
    )


@router.get("/operations/{operation_id}")
async def operation(request: Request, operation_id: str) -> dict:
    async with get_control_engine(request).connect() as c:
        d, _ = await PostgresOwnerDeviceRepository(c).authenticate(
            request.cookies[COOKIE], now_ms=get_clock_ms(request)
        )
        row = await PostgresOwnerPositionOperations(c).get(operation_id)
    if row is None or row["owner_identity"] != d.owner_identity:
        raise HTTPException(404, "operation_not_found")
    return serial(operation_view(row))


@router.get("/orders")
async def orders(request: Request) -> dict:
    """Display complete current snapshots; missing facts never mean no orders."""
    from src.trading_kernel.domain.position import VenueOrderSnapshot

    settings, now = get_settings(request), get_clock_ms(request)
    async with get_control_engine(request).connect() as c:
        rows = (
            (
                await c.execute(
                    sa.select(
                        trade_tickets.c.ticket_id,
                        trade_tickets.c.exchange_instrument_id,
                        trade_tickets.c.position_side,
                        trade_aggregates.c.management_orders,
                        management_observation_current.c.current_complete,
                        management_observation_current.c.updated_at_ms.label(
                            "observed_at_ms"
                        ),
                    )
                    .join(
                        trade_aggregates,
                        trade_aggregates.c.ticket_id == trade_tickets.c.ticket_id,
                    )
                    .outerjoin(
                        management_observation_current,
                        management_observation_current.c.ticket_id
                        == trade_tickets.c.ticket_id,
                    )
                    .where(
                        trade_tickets.c.venue_id == settings.venue_id,
                        trade_tickets.c.account_id == settings.account_id,
                        trade_tickets.c.terminal_at_ms.is_(None),
                    )
                    .order_by(trade_tickets.c.created_at_ms)
                    .limit(51)
                )
            )
            .mappings()
            .all()
        )
    if len(rows) > 50:
        raise HTTPException(503, "order_scope_exceeded")
    items, unavailable = [], []
    for row in rows:
        observed = row["observed_at_ms"]
        if (
            not row["current_complete"]
            or observed is None
            or not observed <= now < observed + 30000
            or len(row["management_orders"]) > 100
        ):
            unavailable.append(row["ticket_id"])
            continue
        current = []
        try:
            for raw in row["management_orders"]:
                order = VenueOrderSnapshot.model_validate(raw)
                terms = order.terms
                if (
                    terms is None
                    or terms.identity[:4]
                    != (
                        settings.venue_id,
                        settings.account_id,
                        row["exchange_instrument_id"],
                        row["position_side"],
                    )
                    or terms.exchange_order_id != order.exchange_order_id
                    or terms.order_namespace != order.order_namespace
                ):
                    raise ValueError("order_snapshot_identity_invalid")
                current.append(
                    {
                        "ticket_id": row["ticket_id"],
                        "exchange_order_id": terms.exchange_order_id,
                        "symbol": row["exchange_instrument_id"].split(":")[1],
                        "position_side": terms.position_side,
                        "kind": terms.order_type,
                        "namespace": terms.order_namespace,
                        "price": terms.price or terms.trigger_price,
                        "quantity": terms.quantity,
                        "remaining_quantity": order.remaining_quantity,
                        "close_position": terms.close_position,
                        "observed_at_ms": observed,
                        "capabilities": {"modify": False, "cancel": False},
                    }
                )
        except (ValueError, TypeError):
            unavailable.append(row["ticket_id"])
            continue
        items.extend(current)
    return serial(
        {
            "status": "unavailable" if unavailable else "ready",
            "items": items,
            "unavailable_ticket_ids": unavailable,
            "observed_at_ms": now,
        }
    )


@router.get("/requests/{idempotency_key}")
async def request_receipt(
    request: Request, idempotency_key: str, nonce_id: str | None = None
) -> dict:
    from src.trading_kernel.infrastructure.pg_models import (
        owner_device_write_evidence as writes,
    )

    if not 1 <= len(idempotency_key) <= 160:
        raise HTTPException(422, "request_key_invalid")
    async with get_control_engine(request).begin() as c:
        repository = PostgresOwnerDeviceRepository(c)
        await repository._lock()
        device, _session = await repository.authenticate(
            request.cookies[COOKIE], now_ms=get_clock_ms(request)
        )
        row = (
            (
                await c.execute(
                    sa.select(writes.c.result_kind, writes.c.result_payload).where(
                        writes.c.owner_identity == device.owner_identity,
                        writes.c.idempotency_key == idempotency_key,
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None and nonce_id is not None and len(nonce_id) <= 160:
            from src.trading_kernel.infrastructure.pg_models import (
                owner_device_registrations,
                owner_device_sessions,
                owner_request_nonces,
            )

            nonce = (
                (
                    await c.execute(
                        sa.select(
                            owner_request_nonces,
                            owner_device_sessions.c.revoked_at_ms.label(
                                "session_revoked"
                            ),
                            owner_device_sessions.c.expires_at_ms.label(
                                "session_expiry"
                            ),
                            owner_device_registrations.c.revoked_at_ms.label(
                                "device_revoked"
                            ),
                        )
                        .join(
                            owner_device_sessions,
                            owner_device_sessions.c.session_id
                            == owner_request_nonces.c.session_id,
                        )
                        .join(
                            owner_device_registrations,
                            owner_device_registrations.c.device_id
                            == owner_device_sessions.c.device_id,
                        )
                        .where(
                            owner_request_nonces.c.nonce_id == nonce_id,
                            owner_device_registrations.c.owner_identity
                            == device.owner_identity,
                        )
                    )
                )
                .mappings()
                .one_or_none()
            )
            if (
                nonce is not None
                and nonce["consumed_at_ms"] is None
                and (
                    nonce["expires_at_ms"] <= get_clock_ms(request)
                    or nonce["device_revoked"] is not None
                    or nonce["session_revoked"] is not None
                    or nonce["session_expiry"] <= get_clock_ms(request)
                )
            ):
                return {"state": "not_accepted"}
    if row is None or row["result_payload"] is None:
        return {"state": "pending"}
    return {"state": "completed", "result": row["result_payload"]}


def operation_view(row):
    return {
        **{
            k: row[k]
            for k in (
                "operation_id",
                "ticket_id",
                "kind",
                "state",
                "version",
                "first_blocker",
                "updated_at_ms",
                "completed_at_ms",
            )
        },
        "result": row["payload"].get("result"),
    }


async def require_position_capability(c, request):
    from src.trading_kernel.infrastructure.pg_models import (
        runtime_capabilities_current as caps,
    )

    row = (
        (
            await c.execute(
                sa.select(caps).where(caps.c.capability_key == "exchange_commands")
            )
        )
        .mappings()
        .one_or_none()
    )
    if (
        row is None
        or not row["enabled"]
        or row["certification"].get("owner_cooperation") != "owner-cooperation-v1"
    ):
        raise HTTPException(409, "position_operations_unavailable")


@router.post("/operations/preview", include_in_schema=False)
@router.post("/operations/submit", include_in_schema=False)
async def retired_position_preview() -> None:
    raise HTTPException(410, "mobile_refresh_required")


@router.post("/operations/intent")
async def submit_position_intent(request: Request, body: SignedBody) -> dict:
    try:
        intent = OwnerPositionIntent.model_validate(body.payload)
    except ValidationError as exc:
        reason = exc.errors(include_url=False, include_input=False)[0]["msg"]
        raise HTTPException(422, reason) from None

    settings = get_settings(request)
    if intent.kind == "position_reduce":
        assert intent.basis_version is not None
        assert intent.basis_quantity is not None and intent.basis_token is not None
        expected = _reduction_basis(
            settings, ticket_id=intent.ticket_id, version=intent.basis_version,
            quantity=intent.basis_quantity,
        )
        if not hmac.compare_digest(expected, intent.basis_token):
            raise HTTPException(409, "reduction_basis_invalid")
    async with get_control_engine(request).begin() as c:
        devices = PostgresOwnerDeviceRepository(c)
        owner = await authorize(c, request, body, intent.kind, get_clock_ms(request))
        receipt = await devices.write_receipt(body.proof)
        if receipt is not None:
            return receipt
        await require_position_capability(c, request)
        ticket = await c.scalar(sa.select(trade_tickets.c.ticket_id).where(
            trade_tickets.c.ticket_id == intent.ticket_id,
            trade_tickets.c.venue_id == settings.venue_id,
            trade_tickets.c.account_id == settings.account_id,
        ))
        if ticket is None:
            raise HTTPException(404, "ticket_not_found")
        try:
            return await PostgresOwnerPositionOperations(c).submit_intent(
                intent=intent, signed_payload=body.payload, owner_identity=owner,
                proof=body.proof, now_ms=await devices.write_authorized_at(body.proof),
            )
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None


@router.get("/operations")
async def operation_list(request: Request) -> dict:
    from src.trading_kernel.infrastructure.pg_models import (
        owner_position_operations as ops,
    )

    now = get_clock_ms(request)
    async with get_control_engine(request).connect() as c:
        d, _ = await PostgresOwnerDeviceRepository(c).authenticate(
            request.cookies[COOKIE], now_ms=now
        )
        rows = (
            (
                await c.execute(
                    sa.select(ops)
                    .where(
                        ops.c.owner_identity == d.owner_identity,
                        sa.or_(
                            ops.c.completed_at_ms.is_(None),
                            ops.c.completed_at_ms >= now - 86400000,
                        ),
                    )
                    .order_by(ops.c.updated_at_ms.desc(), ops.c.operation_id)
                    .limit(50)
                )
            )
            .mappings()
            .all()
        )
    return serial({"items": [operation_view(dict(r)) for r in rows]})
