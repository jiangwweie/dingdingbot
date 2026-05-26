from __future__ import annotations

import os
import time
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from src.interfaces.operator_auth import require_operator_session
from src.interfaces import api_console_runtime as runtime


router = APIRouter(
    prefix="/api/brc",
    tags=["BRC Console"],
    dependencies=[Depends(require_operator_session)],
)

operator_router = APIRouter(
    prefix="/api/brc/operator",
    tags=["BRC Operator"],
    dependencies=[Depends(require_operator_session)],
)

workflow_router = APIRouter(
    prefix="/api/brc/llm/workflows",
    tags=["BRC LLM Workflows"],
    dependencies=[Depends(require_operator_session)],
)

dev_testnet_router = APIRouter(
    prefix="/api/dev/testnet/brc",
    tags=["BRC Controlled Testnet"],
    dependencies=[Depends(require_operator_session)],
)


class BrcDashboardResponse(BaseModel):
    current_stage: str = "BRC-R4 local operator console"
    next_recommended_step: str = "Review runtime safety, create an operator plan, then confirm only the intended action."
    global_planning_stage: str = "Bounded Risk Campaign System mainline; strategy pool, Feishu approval, cloud hardening, and real live remain deferred."
    terminology: dict[str, str] = {
        "Risk Envelope": "风险边界：这轮 campaign 允许承担的最大风险范围。",
        "Loss Lock": "亏损锁定：亏损触发硬停止，不能通过切换 playbook 重置。",
        "Profit Protect": "盈利保护：盈利触发保护/复盘，不自动扩大风险。",
        "Workflow": "操作流程：从 Owner 文本到计划、确认、执行、证据的链路。",
        "Evidence Packet": "证据包：用于复盘和验收的只读事实集合。",
    }
    owner_questions: list[str] = [
        "现在能不能做？",
        "为什么能/不能？",
        "下一步该做什么？",
    ]
    live_ready: bool = False


class BrcActionReadiness(BaseModel):
    action_id: str
    title: str
    description: str
    enabled: bool
    disabled_reason: Optional[str] = None
    route: Optional[str] = None
    button_label: str
    what_happens: str
    what_will_not_happen: str = (
        "不会真实下单、提现、转账、自动调整仓位、启用实盘或执行策略池。"
    )
    account_impact: str = "不会影响真实账户。"
    risk_level: Literal["read_only", "controlled_testnet", "blocked"] = "read_only"


RiskDecision = Literal[
    "ALLOW_READ",
    "ALLOW_MONITOR",
    "BLOCK_TESTNET",
    "ATTENTION_REQUIRED",
    "BLOCK_ALL_STATE_CHANGE",
]
RuntimeState = Literal[
    "observe",
    "monitor",
    "testnet_rehearsal",
    "paused",
    "stopped",
    "flattening",
    "attention_required",
]
ActionCardType = Literal[
    "read_status",
    "enter_monitor",
    "testnet_rehearsal",
    "pause_new_entries",
    "emergency_stop_runtime",
    "emergency_flatten",
]


class BrcActionCard(BaseModel):
    action_card_id: str
    title: str
    action_type: ActionCardType
    enabled: bool
    disabled_reason: Optional[str] = None
    route: Optional[str] = None
    button_label: str
    authority_source: Literal["application_preflight"] = "application_preflight"
    fact_snapshot_id: str
    preflight_result_id: str
    idempotency_key: str
    expiry_time: Optional[int] = None
    current_state: RuntimeState
    allowed_next_states: list[RuntimeState] = Field(default_factory=list)
    blocked_next_states: list[str] = Field(default_factory=list)
    reversible: bool = False
    final_state_proof_required: bool = False
    hard_blocks: list[str] = Field(default_factory=list)
    advisory_warnings: list[str] = Field(default_factory=list)
    confirmation_phrase: Optional[str] = None
    account_impact: str = "不会影响真实账户。"
    what_will_change: str
    what_will_not_change: str = "不会启用真实实盘、提现/转账、自动 sizing/leverage 或策略池执行。"


class BrcReadinessResponse(BaseModel):
    mode: Literal[
        "standalone_console",
        "runtime_bound_console",
        "brc_ready",
        "testnet_ready",
        "blocked",
    ]
    current_conclusion: str
    why: list[str] = Field(default_factory=list)
    account_impact: str
    next_step: str
    available_actions: list[BrcActionReadiness] = Field(default_factory=list)
    disabled_actions: list[BrcActionReadiness] = Field(default_factory=list)
    latest_campaign: Optional[dict[str, Any]] = None
    environment_boundary: dict[str, Any] = Field(default_factory=dict)
    runtime_state: RuntimeState = "observe"
    risk_decision: RiskDecision = "ALLOW_READ"
    risk_account_summary: dict[str, Any] = Field(default_factory=dict)
    strategy_playbook_summary: dict[str, Any] = Field(default_factory=dict)
    action_cards: list[BrcActionCard] = Field(default_factory=list)
    global_cutoff_controls: list[BrcActionCard] = Field(default_factory=list)
    latest_audit: Optional[dict[str, Any]] = None
    runtime_summary: dict[str, Any] = Field(default_factory=dict)
    review_summary: dict[str, Any] = Field(default_factory=dict)
    markets_summary: dict[str, Any] = Field(default_factory=dict)
    playbook_summary: dict[str, Any] = Field(default_factory=dict)
    parameter_summary: dict[str, Any] = Field(default_factory=dict)
    audit_summary: dict[str, Any] = Field(default_factory=dict)
    ai_investigator_summary: dict[str, Any] = Field(default_factory=dict)
    developer_details: dict[str, Any] = Field(default_factory=dict)
    live_ready: Literal[False] = False


class BrcMarketsOrdersResponse(BaseModel):
    conclusion: str
    account_impact: str
    symbols: list[dict[str, Any]] = Field(default_factory=list)
    open_orders: list[dict[str, Any]] = Field(default_factory=list)
    active_positions: list[dict[str, Any]] = Field(default_factory=list)
    developer_details: dict[str, Any] = Field(default_factory=dict)
    live_ready: Literal[False] = False


class BrcAuditTrailResponse(BaseModel):
    conclusion: str
    account_impact: str
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    operator_actions: list[dict[str, Any]] = Field(default_factory=list)
    workflow_runs: list[dict[str, Any]] = Field(default_factory=list)
    review_decisions: list[dict[str, Any]] = Field(default_factory=list)
    developer_details: dict[str, Any] = Field(default_factory=dict)
    live_ready: Literal[False] = False


class BrcInvestigatorAskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    context_type: Optional[str] = Field(default=None, max_length=64)
    context_id: Optional[str] = Field(default=None, max_length=256)


class BrcInvestigatorAskResponse(BaseModel):
    intent: str
    conclusion: str
    reason: str
    account_impact: str
    evidence_summary: list[str] = Field(default_factory=list)
    trace: list[dict[str, Any]] = Field(default_factory=list)
    next_step: str
    developer_details: dict[str, Any] = Field(default_factory=dict)
    live_ready: Literal[False] = False


_CONTROLLED_SYMBOLS: list[dict[str, Any]] = [
    {
        "symbol_key": "eth",
        "display_symbol": "ETHUSDT",
        "exchange_symbol": "ETH/USDT:USDT",
        "allowed_amount": "0.01",
        "max_notional_usdt": "25",
        "leverage_cap": "1x",
    },
    {
        "symbol_key": "btc",
        "display_symbol": "BTCUSDT",
        "exchange_symbol": "BTC/USDT:USDT",
        "allowed_amount": "0.002",
        "max_notional_usdt": "250",
        "leverage_cap": "1x",
    },
]


def _api_module() -> Any:
    from src.interfaces import api as api_module

    return api_module


def _runtime_profile_summary(api_module: Any) -> tuple[Optional[str], Optional[bool], list[str], list[str]]:
    provider = getattr(api_module, "_runtime_config_provider", None)
    resolved = getattr(provider, "resolved_config", None) if provider is not None else None
    if resolved is None:
        return None, None, ["运行配置 Profile 尚未解析，无法确认是否处于 BRC testnet profile。"], []
    profile = getattr(resolved, "profile_name", None)
    environment = getattr(resolved, "environment", None)
    testnet = getattr(environment, "exchange_testnet", None)
    if testnet is None:
        testnet = getattr(environment, "testnet", None)
    market = getattr(resolved, "market", None)
    symbols = list(getattr(market, "symbols", []) or [])
    reasons = []
    if profile != "brc_btc_eth_testnet_runtime":
        reasons.append("当前运行配置 Profile 不是 brc_btc_eth_testnet_runtime。")
    if testnet is not True:
        reasons.append("当前未确认处于 Exchange Testnet 测试网。")
    if set(symbols) != {"BTC/USDT:USDT", "ETH/USDT:USDT"}:
        reasons.append("当前运行配置没有固定在 BRC BTC/ETH 测试网 symbol scope。")
    return profile, testnet, reasons, symbols


def _guard_summary(api_module: Any) -> tuple[Optional[bool], Optional[bool]]:
    gks_active = None
    gks = getattr(api_module, "_global_kill_switch_service", None)
    if gks is not None and hasattr(gks, "get_state"):
        state = gks.get_state()
        gks_active = bool(getattr(state, "active", state.get("active") if isinstance(state, dict) else None))
    elif gks is not None and hasattr(gks, "is_active"):
        gks_active = bool(gks.is_active())
    startup_guard_armed = None
    guard = getattr(api_module, "_startup_trading_guard_service", None)
    if guard is not None and hasattr(guard, "get_state"):
        state = guard.get_state()
        startup_guard_armed = bool(getattr(state, "armed", state.get("armed") if isinstance(state, dict) else None))
    elif guard is not None and hasattr(guard, "is_armed"):
        startup_guard_armed = bool(guard.is_armed())
    return gks_active, startup_guard_armed


def _env_enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _dump_jsonable(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "dict"):
        return value.dict()
    if isinstance(value, dict):
        return dict(value)
    payload: dict[str, Any] = {}
    for key in dir(value):
        if key.startswith("_"):
            continue
        attr = getattr(value, key, None)
        if callable(attr):
            continue
        if isinstance(attr, (str, int, float, bool, type(None), list, dict)):
            payload[key] = attr
        else:
            payload[key] = str(attr)
    return payload


def _campaign_summary(campaign: Any) -> Optional[dict[str, Any]]:
    if campaign is None:
        return None
    return {
        "campaign_id": campaign.campaign_id,
        "status": campaign.status.value if hasattr(campaign.status, "value") else str(campaign.status),
        "outcome": campaign.outcome.value if getattr(campaign, "outcome", None) is not None else None,
        "current_playbook_id": campaign.current_playbook_id,
        "realized_pnl": str(campaign.realized_pnl),
        "attempt_count": campaign.attempt_count,
        "max_attempts": campaign.risk_envelope.max_attempts,
        "profit_protect_trigger": str(campaign.risk_envelope.profit_protect_trigger),
        "max_campaign_loss": str(campaign.risk_envelope.max_campaign_loss),
        "finalized_at_ms": campaign.finalized_at_ms,
    }


async def _markets_orders_summary(api_module: Any) -> tuple[dict[str, Any], list[str]]:
    """Build a read-only BTC/ETH status summary without exchange mutation."""
    errors: list[str] = []
    position_repo = getattr(api_module, "_position_repo", None)
    order_repo = getattr(api_module, "_order_repo", None)
    symbols: list[dict[str, Any]] = []
    all_positions: list[dict[str, Any]] = []
    all_open_orders: list[dict[str, Any]] = []

    for spec in _CONTROLLED_SYMBOLS:
        exchange_symbol = str(spec["exchange_symbol"])
        positions: list[Any] = []
        orders: list[Any] = []
        if position_repo is not None and hasattr(position_repo, "list_active"):
            try:
                positions = list(await position_repo.list_active(symbol=exchange_symbol, limit=20))
            except Exception as exc:  # pragma: no cover - defensive product summary
                errors.append(f"{exchange_symbol} active position read failed: {exc}")
        if order_repo is not None and hasattr(order_repo, "get_open_orders"):
            try:
                orders = list(await order_repo.get_open_orders(exchange_symbol))
            except TypeError:
                try:
                    orders = list(await order_repo.get_open_orders())
                except Exception as exc:  # pragma: no cover
                    errors.append(f"{exchange_symbol} open order read failed: {exc}")
            except Exception as exc:  # pragma: no cover
                errors.append(f"{exchange_symbol} open order read failed: {exc}")

        position_payloads = [_dump_jsonable(item) for item in positions]
        order_payloads = [_dump_jsonable(item) for item in orders]
        all_positions.extend(position_payloads)
        all_open_orders.extend(order_payloads)
        symbols.append(
            {
                **spec,
                "testnet_only": True,
                "live_enabled": False,
                "strategy_execution_enabled": False,
                "active_position_count": len(position_payloads),
                "open_order_count": len(order_payloads),
                "status_label": "flat" if not position_payloads and not order_payloads else "attention_required",
                "owner_meaning": (
                    "当前未发现本地 active position/open order。"
                    if not position_payloads and not order_payloads
                    else "发现本地 active position 或 open order，请先核对完整链路。"
                ),
            }
        )

    return (
        {
            "symbols": symbols,
            "active_positions": all_positions,
            "open_orders": all_open_orders,
            "active_position_count": len(all_positions),
            "open_order_count": len(all_open_orders),
            "all_local_flat": len(all_positions) == 0 and len(all_open_orders) == 0,
            "data_source": "local_pg_repositories_only",
        },
        errors,
    )


async def _audit_summary(service: Any, *, limit: int = 10) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    actions: list[Any] = []
    workflows: list[Any] = []
    reviews: list[Any] = []
    if service is None:
        return {
            "timeline": [],
            "operator_actions": [],
            "workflow_runs": [],
            "review_decisions": [],
            "latest_event": None,
        }, ["BRC Campaign service unavailable"]

    for label, method_name, target in [
        ("operator actions", "list_operator_actions", "actions"),
        ("workflow runs", "list_workflow_runs", "workflows"),
        ("review decisions", "list_review_decisions", "reviews"),
    ]:
        method = getattr(service, method_name, None)
        if not callable(method):
            continue
        try:
            items = list(await method(limit=limit))
            if target == "actions":
                actions = items
            elif target == "workflows":
                workflows = items
            else:
                reviews = items
        except Exception as exc:  # pragma: no cover - defensive product summary
            errors.append(f"{label} read failed: {exc}")

    action_payloads = [_dump_jsonable(item) for item in actions]
    workflow_payloads = [_dump_jsonable(item) for item in workflows]
    review_payloads = [_dump_jsonable(item) for item in reviews]
    timeline: list[dict[str, Any]] = []
    for item in action_payloads:
        timeline.append(
            {
                "type": "operator_action",
                "id": item.get("action_id"),
                "title": "Owner 操作计划 / Operator action",
                "result": item.get("decision_result"),
                "occurred_at_ms": item.get("executed_at_ms") or item.get("created_at_ms"),
                "summary": item.get("source_text") or item.get("draft_action"),
                "account_impact": "不会影响真实账户；mutation/live/withdrawal flags are false.",
                "raw": item,
            }
        )
    for item in workflow_payloads:
        timeline.append(
            {
                "type": "workflow_run",
                "id": item.get("workflow_run_id"),
                "title": "受控流程 / Workflow",
                "result": item.get("status"),
                "occurred_at_ms": item.get("updated_at_ms") or item.get("created_at_ms"),
                "summary": item.get("action") or item.get("normalized_action"),
                "account_impact": "创建 workflow 本身不影响真实账户；执行仍需 Owner confirmation.",
                "raw": item,
            }
        )
    for item in review_payloads:
        timeline.append(
            {
                "type": "review_decision",
                "id": item.get("review_id"),
                "title": "复盘决策 / Review decision",
                "result": item.get("decision"),
                "occurred_at_ms": item.get("created_at_ms"),
                "summary": item.get("reason_text") or item.get("next_recommended_task"),
                "account_impact": "复盘记录只写数据库事实，不创建 campaign 或触发 testnet.",
                "raw": item,
            }
        )
    timeline.sort(key=lambda item: int(item.get("occurred_at_ms") or 0), reverse=True)
    return {
        "timeline": timeline[:limit],
        "operator_actions": action_payloads,
        "workflow_runs": workflow_payloads,
        "review_decisions": review_payloads,
        "latest_event": timeline[0] if timeline else None,
    }, errors


def _parameter_summary(profile: Optional[str], testnet: Optional[bool]) -> dict[str, Any]:
    return {
        "runtime_profile": profile,
        "exchange_testnet": testnet,
        "controlled_symbols": _CONTROLLED_SYMBOLS,
        "risk_envelope": {
            "max_simultaneous_positions": 1,
            "max_attempts": 2,
            "mock_pnl_only": True,
            "loss_counter_resets_on_playbook_switch": False,
        },
        "confirmation_phrases": {
            "read_only": "CONFIRM_READ_ONLY_BRC",
            "controlled_testnet": "CONFIRM_BRC_TESTNET_REHEARSAL",
        },
        "unauthorized_capabilities": [
            "real_live",
            "withdrawal_or_transfer",
            "automatic_strategy_execution",
            "automatic_sizing_or_leverage_override",
            "strategy_pool_execution",
        ],
    }


def _action(
    *,
    action_id: str,
    title: str,
    description: str,
    enabled: bool,
    disabled_reason: Optional[str],
    route: Optional[str],
    button_label: str,
    what_happens: str,
    risk_level: Literal["read_only", "controlled_testnet", "blocked"] = "read_only",
) -> BrcActionReadiness:
    return BrcActionReadiness(
        action_id=action_id,
        title=title,
        description=description,
        enabled=enabled,
        disabled_reason=None if enabled else disabled_reason,
        route=route if enabled else route,
        button_label=button_label,
        what_happens=what_happens,
        risk_level=risk_level if enabled else "blocked",
    )


def _risk_decision(
    *,
    runtime_ready: bool,
    service_error: Optional[str],
    market_errors: list[str],
    audit_errors: list[str],
    markets_summary: dict[str, Any],
    mutation_env_ready: bool,
) -> RiskDecision:
    if service_error:
        return "BLOCK_ALL_STATE_CHANGE"
    if market_errors or audit_errors:
        return "ATTENTION_REQUIRED"
    if not bool(markets_summary.get("all_local_flat", False)):
        return "ATTENTION_REQUIRED"
    if not runtime_ready:
        return "ALLOW_READ"
    if not mutation_env_ready:
        return "ALLOW_MONITOR"
    return "ALLOW_MONITOR"


def _runtime_state(
    *,
    risk_decision: RiskDecision,
    runtime_ready: bool,
    mutation_env_ready: bool,
    gks_active: Optional[bool],
) -> RuntimeState:
    if risk_decision in {"ATTENTION_REQUIRED", "BLOCK_ALL_STATE_CHANGE"}:
        return "attention_required"
    if not runtime_ready:
        return "observe"
    if gks_active is True:
        return "paused"
    if mutation_env_ready:
        return "monitor"
    return "monitor"


def _fact_snapshot_id(
    *,
    runtime_ready: bool,
    profile: Optional[str],
    testnet: Optional[bool],
    markets_summary: dict[str, Any],
    audit_summary: dict[str, Any],
    risk_decision: RiskDecision,
) -> str:
    latest = audit_summary.get("latest_event") or {}
    parts = [
        "brc-v0",
        "runtime" if runtime_ready else "standalone",
        str(profile or "no-profile"),
        "testnet" if testnet is True else "not-testnet",
        f"pos{markets_summary.get('active_position_count', 'x')}",
        f"ord{markets_summary.get('open_order_count', 'x')}",
        str(latest.get("id") or "no-audit"),
        risk_decision,
    ]
    return ":".join(parts)


def _action_card(
    *,
    action_type: ActionCardType,
    title: str,
    enabled: bool,
    disabled_reason: Optional[str],
    route: Optional[str],
    button_label: str,
    fact_snapshot_id: str,
    current_state: RuntimeState,
    allowed_next_states: list[RuntimeState],
    blocked_next_states: Optional[list[str]] = None,
    reversible: bool = False,
    final_state_proof_required: bool = False,
    hard_blocks: Optional[list[str]] = None,
    advisory_warnings: Optional[list[str]] = None,
    confirmation_phrase: Optional[str] = None,
    account_impact: str = "不会影响真实账户。",
    what_will_change: str = "只读取当前系统状态。",
    what_will_not_change: str = "不会启用真实实盘、提现/转账、自动 sizing/leverage 或策略池执行。",
    expiry_seconds: Optional[int] = 300,
) -> BrcActionCard:
    action_card_id = f"brc-card-{action_type}"
    preflight_result_id = f"preflight-{action_type}-{'allow' if enabled else 'block'}"
    expiry_time = int(time.time() * 1000) + expiry_seconds * 1000 if expiry_seconds is not None else None
    blocks = list(hard_blocks or [])
    if not enabled and disabled_reason:
        blocks.append(disabled_reason)
    return BrcActionCard(
        action_card_id=action_card_id,
        title=title,
        action_type=action_type,
        enabled=enabled,
        disabled_reason=None if enabled else disabled_reason,
        route=route,
        button_label=button_label,
        fact_snapshot_id=fact_snapshot_id,
        preflight_result_id=preflight_result_id,
        idempotency_key=f"{fact_snapshot_id}:{action_type}",
        expiry_time=expiry_time,
        current_state=current_state,
        allowed_next_states=allowed_next_states if enabled else [],
        blocked_next_states=list(blocked_next_states or []),
        reversible=reversible,
        final_state_proof_required=final_state_proof_required,
        hard_blocks=blocks,
        advisory_warnings=list(advisory_warnings or []),
        confirmation_phrase=confirmation_phrase,
        account_impact=account_impact,
        what_will_change=what_will_change,
        what_will_not_change=what_will_not_change,
    )


@router.get("/readiness", response_model=BrcReadinessResponse)
async def get_brc_readiness() -> BrcReadinessResponse:
    api_module = _api_module()
    runtime_context = api_module.get_runtime_context()
    service = getattr(api_module, "_brc_campaign_service", None)
    profile, testnet, profile_reasons, symbols = _runtime_profile_summary(api_module)
    gks_active, startup_guard_armed = _guard_summary(api_module)

    latest_campaign = None
    latest_review = None
    latest_operator_action = None
    service_error = None
    if service is not None:
        try:
            latest_campaign = await service.get_latest_campaign()
            latest_review = await service.get_latest_review_decision()
            if hasattr(service, "list_operator_actions"):
                actions = await service.list_operator_actions(limit=1)
                latest_operator_action = actions[0] if actions else None
        except Exception as exc:  # pragma: no cover - defensive product summary
            service_error = str(exc)

    markets_summary, market_errors = await _markets_orders_summary(api_module)
    audit_summary, audit_errors = await _audit_summary(service, limit=5)

    reasons: list[str] = []
    if runtime_context is None:
        reasons.append("当前只是 Standalone Console，后端没有绑定运行时 Runtime。")
    if service is None:
        reasons.append("当前没有连接 BRC Campaign 服务，不能读取或写入 campaign 治理数据。")
    if service_error:
        reasons.append("BRC Campaign 服务读取失败，页面只能显示安全说明。")
    reasons.extend(profile_reasons)
    if market_errors:
        reasons.append("交易对/订单摘要只能部分读取，详情见 Developer Detail。")
    if audit_errors and service is not None:
        reasons.append("审计摘要只能部分读取，详情见 Developer Detail。")

    runtime_ready = runtime_context is not None and service is not None and not profile_reasons
    has_campaign = latest_campaign is not None
    mutation_env_ready = _env_enabled("RUNTIME_CONTROL_API_ENABLED") and _env_enabled(
        "RUNTIME_TEST_SIGNAL_INJECTION_ENABLED"
    )
    testnet_ready = runtime_ready and mutation_env_ready
    risk_decision = _risk_decision(
        runtime_ready=runtime_ready,
        service_error=service_error,
        market_errors=market_errors,
        audit_errors=audit_errors if service is not None else [],
        markets_summary=markets_summary,
        mutation_env_ready=mutation_env_ready,
    )
    runtime_state = _runtime_state(
        risk_decision=risk_decision,
        runtime_ready=runtime_ready,
        mutation_env_ready=mutation_env_ready,
        gks_active=gks_active,
    )
    fact_snapshot_id = _fact_snapshot_id(
        runtime_ready=runtime_ready,
        profile=profile,
        testnet=testnet,
        markets_summary=markets_summary,
        audit_summary=audit_summary,
        risk_decision=risk_decision,
    )

    if runtime_context is None:
        mode: Literal["standalone_console", "runtime_bound_console", "brc_ready", "testnet_ready", "blocked"] = "standalone_console"
        conclusion = "当前只能查看，不能执行 BRC campaign 操作。"
        next_step = "启动绑定 BRC runtime 的后端后，回到 Command Center 刷新状态。"
    elif not runtime_ready:
        mode = "runtime_bound_console"
        conclusion = "运行时已连接，但 BRC 操作条件还不完整。"
        next_step = "先检查运行配置 Profile、测试网 Testnet 和 BRC 服务初始化状态。"
    elif testnet_ready:
        mode = "testnet_ready"
        conclusion = "当前满足受控测试网 workflow 的基础门槛。"
        next_step = "主链路已可进入：打开 LLM Copilot，创建 testnet_rehearsal action card，并手动输入确认短语。"
    else:
        mode = "brc_ready"
        conclusion = "当前可以进行 BRC 只读治理操作；testnet 演练仍需额外门槛。"
        next_step = "优先生成只读操作计划或复盘最近 campaign。"

    if not reasons:
        reasons.append("基础 BRC 运行条件已满足；具体动作仍需要 Owner 手动确认。")

    no_runtime_reason = "需要绑定 BRC runtime、解析 BRC testnet profile，并初始化 BRC Campaign 服务。"
    no_campaign_reason = "当前没有可复盘的 campaign，Review decision 需要绑定一轮已存在的 campaign。"
    testnet_missing = []
    if not runtime_ready:
        testnet_missing.append(no_runtime_reason)
    if not _env_enabled("RUNTIME_CONTROL_API_ENABLED"):
        testnet_missing.append("本地 runtime control mutation 开关未开启。")
    if not _env_enabled("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED"):
        testnet_missing.append("本地 test signal injection 开关未开启。")
    no_testnet_reason = " ".join(testnet_missing) or "受控 testnet workflow 需要 BRC profile、Exchange Testnet 和本地 mutation/test-signal 开关同时满足。"

    actions = [
        _action(
            action_id="view_runtime_safety",
            title="查看运行安全 Runtime Safety",
            description="查看运行时 Runtime、测试网 Testnet、全局安全开关 GKS 和启动保护 Startup Guard。",
            enabled=True,
            disabled_reason=None,
            route="/runtime-safety",
            button_label="查看运行安全",
            what_happens="打开只读安全检查页面，不会触发 runtime 或 exchange 动作。",
        ),
        _action(
            action_id="create_read_only_plan",
            title="生成只读计划 Operator Plan",
            description="把 Owner 文本转成 review/evidence/eligibility 等只读操作计划。",
            enabled=runtime_ready,
            disabled_reason=no_runtime_reason,
            route="/operator",
            button_label="生成只读计划",
            what_happens="创建一条 operator action 计划；执行前仍需手动输入确认短语。",
        ),
        _action(
            action_id="create_workflow",
            title="创建受控流程 Workflow",
            description="让 LLM workflow 归一化 Owner 意图，并进入确认前检查。",
            enabled=runtime_ready,
            disabled_reason=no_runtime_reason,
            route="/workflow",
            button_label="创建 Workflow",
            what_happens="创建 workflow run；不会自动执行交易或绕过 Owner confirmation。",
        ),
        _action(
            action_id="write_review_decision",
            title="写入复盘决策 Review",
            description="基于最近 campaign 证据写入 Owner 复盘结论和下一步任务。",
            enabled=runtime_ready and has_campaign,
            disabled_reason=no_campaign_reason if runtime_ready else no_runtime_reason,
            route="/review",
            button_label="写复盘决策",
            what_happens="写入 review decision 记录，不会创建 campaign 或触发 testnet。",
        ),
        _action(
            action_id="view_ledger",
            title="查看操作记录 Ledger",
            description="查看 operator actions、workflow runs 和 review decisions 的审计摘要。",
            enabled=runtime_ready,
            disabled_reason=no_runtime_reason,
            route="/ledger",
            button_label="查看操作记录",
            what_happens="读取数据库事实记录，不会重放或修改任何历史动作。",
        ),
        _action(
            action_id="run_controlled_testnet_workflow",
            title="受控测试网演练 Controlled Testnet",
            description="执行固定 ETH -> mock profit -> BTC -> mock loss -> finalize 的受控 testnet workflow。",
            enabled=testnet_ready,
            disabled_reason=no_testnet_reason,
            route="/workflow",
            button_label="准备 testnet 演练",
            what_happens="只有在专用确认短语输入后，固定 workflow 才会临时打开 entry window，并在结束后恢复 GKS/Startup Guard 保护态。",
            risk_level="controlled_testnet",
        ),
    ]

    available = [action for action in actions if action.enabled]
    disabled = [action for action in actions if not action.enabled]
    campaign_summary = _campaign_summary(latest_campaign)
    review_summary = {
        "latest_review_present": latest_review is not None,
        "latest_review": latest_review.model_dump(mode="json") if latest_review is not None else None,
        "latest_operator_action_present": latest_operator_action is not None,
        "latest_operator_action": latest_operator_action.model_dump(mode="json")
        if latest_operator_action is not None
        else None,
        "review_available": runtime_ready and has_campaign,
    }
    playbook_summary = {
        "current_playbook_id": campaign_summary.get("current_playbook_id") if campaign_summary else "PB-000-OBSERVE-ONLY",
        "current_playbook_meaning": "Playbook 是人工打法/治理框架，不等于可自动执行策略。",
        "strategy_execution_enabled": False,
        "strategy_execution_status": "未启用可执行 Strategy；策略池后续单独建设。",
        "catalog": [
            {"playbook_id": "PB-000-OBSERVE-ONLY", "label": "Observe Only", "status": "available"},
            {"playbook_id": "PB-001-DIRECTION-A-PAPER", "label": "Direction A Paper", "status": "observe_only"},
            {"playbook_id": "PB-002-SQ02-DOWNSIDE-PAPER", "label": "SQ02 Downside Paper", "status": "docs_only"},
            {"playbook_id": "PB-003-MANUAL-DISCRETIONARY", "label": "Manual Discretionary", "status": "governed_only"},
            {"playbook_id": "PB-004-BRC-CONTROLLED-TESTNET", "label": "BRC Controlled Testnet", "status": "testnet_only"},
        ],
    }
    parameter_summary = _parameter_summary(profile, testnet)
    environment_boundary = {
        "current": "simulation",
        "exchange_mode": "binance_testnet" if testnet is True else "unknown_or_not_testnet",
        "executable_modes": ["local", "mock", "binance_testnet"],
        "future_live": {
            "modeled": True,
            "available": False,
            "display": "disabled_boundary",
            "reason": "requires separate Owner production authorization plus cloud/security/secret/replay/permission work",
        },
        "production_authorized": False,
        "real_account_impact": "none",
    }
    risk_account_summary = {
        "risk_decision": risk_decision,
        "account_state": {
            "environment": environment_boundary["current"],
            "exchange_mode": environment_boundary["exchange_mode"],
            "real_account_impact": "none",
            "wallet_equity_available": False,
            "available_margin_available": False,
        },
        "exposure_orders": {
            "symbols": markets_summary.get("symbols", []),
            "active_positions": markets_summary.get("active_positions", []),
            "open_orders": markets_summary.get("open_orders", []),
            "active_position_count": markets_summary.get("active_position_count", 0),
            "open_order_count": markets_summary.get("open_order_count", 0),
            "order_source": "local_pg_repositories_only",
            "unknown_exposure": not bool(markets_summary.get("all_local_flat", False)),
            "flatness_proof": {
                "all_local_flat": bool(markets_summary.get("all_local_flat", False)),
                "source": markets_summary.get("data_source"),
                "timestamp_ms": int(time.time() * 1000),
            },
        },
        "risk_envelope": parameter_summary["risk_envelope"],
        "loss_lock_status": campaign_summary.get("status") if campaign_summary else "no_campaign",
        "profit_protect_status": "not_triggered_or_unknown",
        "daily_realized_pnl": "not_available_in_console_v0",
        "daily_trade_count": "not_available_in_console_v0",
        "audit_writable": service is not None and not audit_errors,
        "cutoff_available": runtime_ready,
    }
    strategy_playbook_summary = {
        **playbook_summary,
        "current_strategy_family": "Trend Following" if playbook_summary["current_playbook_id"] == "TF-001" else "BRC Controlled Testnet / Governance",
        "current_mode": runtime_state,
        "r5_carrier": {
            "playbook_id": "TF-001",
            "purpose": "carrier_validation_only",
            "implementation_status": "later_slice",
            "alpha_claim": False,
        },
    }
    read_enabled = True
    monitor_enabled = runtime_ready and risk_decision in {"ALLOW_MONITOR", "BLOCK_TESTNET"}
    testnet_action_enabled = testnet_ready and risk_decision == "ALLOW_MONITOR"
    cutoff_enabled = runtime_ready
    action_cards = [
        _action_card(
            action_type="read_status",
            title="Read current status",
            enabled=read_enabled,
            disabled_reason=None,
            route="/command-center",
            button_label="查看状态",
            fact_snapshot_id=fact_snapshot_id,
            current_state=runtime_state,
            allowed_next_states=[runtime_state],
            reversible=True,
            final_state_proof_required=False,
            what_will_change="只刷新 Command Center / Risk & Account 的只读状态。",
        ),
        _action_card(
            action_type="enter_monitor",
            title="Enter monitor",
            enabled=monitor_enabled,
            disabled_reason="需要绑定 runtime、BRC 服务、可读风险状态，并且不能处于 attention_required。",
            route="/llm-copilot",
            button_label="准备 monitor",
            fact_snapshot_id=fact_snapshot_id,
            current_state=runtime_state,
            allowed_next_states=["monitor"],
            blocked_next_states=["live_trade", "strategy_pool_execution"],
            reversible=True,
            final_state_proof_required=False,
            advisory_warnings=["Monitor 不授予订单权限。"],
            confirmation_phrase="CONFIRM_READ_ONLY_BRC",
            what_will_change="生成进入 monitor 的应用层 action card；不会直接下单。",
        ),
        _action_card(
            action_type="testnet_rehearsal",
            title="Fixed BRC testnet rehearsal",
            enabled=testnet_action_enabled,
            disabled_reason=no_testnet_reason if not testnet_ready else "当前风险判定不允许 testnet_rehearsal。",
            route="/llm-copilot",
            button_label="准备 testnet_rehearsal",
            fact_snapshot_id=fact_snapshot_id,
            current_state=runtime_state,
            allowed_next_states=["testnet_rehearsal", "attention_required"],
            blocked_next_states=["live_trade", "withdrawal", "transfer", "strategy_pool_execution"],
            reversible=False,
            final_state_proof_required=True,
            advisory_warnings=[
                "只允许固定 ETH/BTC BRC 测试网演练。",
                "策略证据是 advisory，不是执行授权。",
            ],
            confirmation_phrase="CONFIRM_BRC_TESTNET_REHEARSAL",
            account_impact="只影响 Binance testnet；不会影响真实账户。",
            what_will_change="Owner 确认后执行固定 BRC ETH/BTC testnet rehearsal 并写入审计和复盘证据。",
        ),
    ]
    global_cutoff_controls = [
        _action_card(
            action_type="pause_new_entries",
            title="Pause new entries",
            enabled=cutoff_enabled,
            disabled_reason=no_runtime_reason,
            route="/runtime-control",
            button_label="Pause",
            fact_snapshot_id=fact_snapshot_id,
            current_state=runtime_state,
            allowed_next_states=["paused"],
            reversible=True,
            final_state_proof_required=False,
            confirmation_phrase="CONFIRM_READ_ONLY_BRC",
            what_will_change="停止新增开仓意图；不主动平掉已有 exposure。",
        ),
        _action_card(
            action_type="emergency_stop_runtime",
            title="Emergency stop runtime",
            enabled=cutoff_enabled,
            disabled_reason=no_runtime_reason,
            route="/runtime-control",
            button_label="Stop runtime",
            fact_snapshot_id=fact_snapshot_id,
            current_state=runtime_state,
            allowed_next_states=["stopped"],
            reversible=False,
            final_state_proof_required=False,
            confirmation_phrase="CONFIRM_READ_ONLY_BRC",
            what_will_change="停止 runtime-driven 活动；不代表交易所残留单已自动消失。",
        ),
        _action_card(
            action_type="emergency_flatten",
            title="Emergency flatten",
            enabled=cutoff_enabled,
            disabled_reason=no_runtime_reason,
            route="/runtime-control",
            button_label="Flatten",
            fact_snapshot_id=fact_snapshot_id,
            current_state=runtime_state,
            allowed_next_states=["flattening", "attention_required"],
            reversible=False,
            final_state_proof_required=True,
            confirmation_phrase="CONFIRM_BRC_TESTNET_REHEARSAL",
            account_impact="v0 仅允许在 simulation/testnet 边界内执行；真实账户不可用。",
            what_will_change="尝试撤单/平仓并要求最终 flatness 证明；失败会进入 attention_required。",
        ),
    ]

    return BrcReadinessResponse(
        mode=mode,
        current_conclusion=conclusion,
        why=reasons,
        account_impact="不会影响真实账户；readiness 只读，不会下单、提现、转账或修改仓位。",
        next_step=next_step,
        available_actions=available,
        disabled_actions=disabled,
        latest_campaign=campaign_summary,
        environment_boundary=environment_boundary,
        runtime_state=runtime_state,
        risk_decision=risk_decision,
        risk_account_summary=risk_account_summary,
        strategy_playbook_summary=strategy_playbook_summary,
        action_cards=action_cards,
        global_cutoff_controls=global_cutoff_controls,
        latest_audit=audit_summary.get("latest_event"),
        runtime_summary={
            "runtime_bound": runtime_context is not None,
            "profile": profile,
            "testnet": testnet,
            "symbols": symbols,
            "gks_active": gks_active,
            "startup_guard_armed": startup_guard_armed,
            "brc_service_ready": service is not None,
            "mutation_env_ready": mutation_env_ready,
        },
        review_summary=review_summary,
        markets_summary=markets_summary,
        playbook_summary=playbook_summary,
        parameter_summary=parameter_summary,
        audit_summary=audit_summary,
        ai_investigator_summary={
            "mode": "controlled_read_only_resolver",
            "free_sql_enabled": False,
            "can_answer": [
                "这个订单怎么触发的？",
                "现在系统能不能继续？",
                "为什么 blocked？",
                "上一轮 campaign 结果是什么？",
                "最近发生了哪些关键操作？",
            ],
            "cannot_do": [
                "下单",
                "改参数",
                "切换 playbook",
                "提现/转账",
                "自由 SQL",
            ],
        },
        developer_details={
            "runtime_context_bound": runtime_context is not None,
            "brc_campaign_service_present": service is not None,
            "service_error": service_error,
            "profile_reasons": profile_reasons,
            "market_errors": market_errors,
            "audit_errors": audit_errors,
            "mutation_env": {
                "runtime_control_api_enabled": _env_enabled("RUNTIME_CONTROL_API_ENABLED"),
                "runtime_test_signal_injection_enabled": _env_enabled("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED"),
            },
            "live_ready": False,
        },
    )


@router.get("/dashboard", response_model=BrcDashboardResponse)
async def get_brc_dashboard() -> BrcDashboardResponse:
    return BrcDashboardResponse()


@router.get("/markets-orders", response_model=BrcMarketsOrdersResponse)
async def get_brc_markets_orders() -> BrcMarketsOrdersResponse:
    api_module = _api_module()
    summary, errors = await _markets_orders_summary(api_module)
    all_flat = bool(summary.get("all_local_flat"))
    return BrcMarketsOrdersResponse(
        conclusion=(
            "当前本地 PG 未发现 BRC BTC/ETH active position/open order。"
            if all_flat
            else "当前发现本地 active position 或 open order，需要核对订单触发链路。"
        ),
        account_impact="只读查询，不会下单、平仓、提现、转账或修改仓位。",
        symbols=list(summary.get("symbols", [])),
        open_orders=list(summary.get("open_orders", [])),
        active_positions=list(summary.get("active_positions", [])),
        developer_details={"errors": errors, "data_source": summary.get("data_source")},
    )


@router.get("/audit-trail", response_model=BrcAuditTrailResponse)
async def get_brc_audit_trail(limit: int = Query(default=50, ge=1, le=200)) -> BrcAuditTrailResponse:
    service = getattr(_api_module(), "_brc_campaign_service", None)
    summary, errors = await _audit_summary(service, limit=limit)
    timeline = list(summary.get("timeline", []))
    return BrcAuditTrailResponse(
        conclusion=(
            "已读取最近 BRC 操作审计记录。"
            if timeline
            else "当前没有可展示的 BRC 操作审计记录。"
        ),
        account_impact="只读审计查询，不会重放、修改或执行任何历史动作。",
        timeline=timeline,
        operator_actions=list(summary.get("operator_actions", [])),
        workflow_runs=list(summary.get("workflow_runs", [])),
        review_decisions=list(summary.get("review_decisions", [])),
        developer_details={"errors": errors},
    )


@router.post("/investigator/ask", response_model=BrcInvestigatorAskResponse)
async def ask_brc_investigator(body: BrcInvestigatorAskRequest) -> BrcInvestigatorAskResponse:
    api_module = _api_module()
    readiness = await get_brc_readiness()
    markets, market_errors = await _markets_orders_summary(api_module)
    audit, audit_errors = await _audit_summary(getattr(api_module, "_brc_campaign_service", None), limit=10)
    question = body.question.strip()
    lower = question.lower()

    if any(token in lower for token in ["order", "订单"]):
        intent = "order_trace"
        orders = list(markets.get("open_orders", []))
        conclusion = (
            "当前没有可追踪的本地 open order；如果你问的是历史成交，需要后续接入历史订单 trace。"
            if not orders
            else "当前发现本地 open order，需通过 operator/workflow/campaign 证据继续核对来源。"
        )
        evidence = [
            f"本地 open orders: {len(orders)}",
            f"本地 active positions: {markets.get('active_position_count', 0)}",
            "订单解释只读取本地 PG/order repository 摘要，不访问实盘账户。",
        ]
        trace = [
            {"step": "Owner question", "evidence": question},
            {"step": "Markets/orders resolver", "evidence": {"open_order_count": len(orders)}},
            {"step": "Audit resolver", "evidence": audit.get("latest_event")},
        ]
        next_step = "如果页面上有具体 order_id，后续版本会按 order_id 展开 workflow/action/campaign 完整链路。"
    elif any(token in lower for token in ["blocked", "block", "不能", "为什么"]):
        intent = "blocked_reason"
        conclusion = readiness.current_conclusion
        evidence = readiness.why
        trace = [
            {"step": "Readiness mode", "evidence": readiness.mode},
            {"step": "Disabled actions", "evidence": [item.model_dump(mode="json") for item in readiness.disabled_actions]},
        ]
        next_step = readiness.next_step
    elif any(token in lower for token in ["campaign", "轮", "亏损", "盈利", "loss", "profit"]):
        intent = "campaign_review"
        campaign = readiness.latest_campaign
        conclusion = (
            f"最近 campaign 状态是 {campaign.get('status')}，结果是 {campaign.get('outcome') or '未结束'}。"
            if campaign
            else "当前没有 latest campaign，无法进行 campaign 复盘解释。"
        )
        evidence = [
            f"latest_campaign_present: {campaign is not None}",
            f"review_available: {readiness.review_summary.get('review_available')}",
        ]
        trace = [
            {"step": "Latest campaign", "evidence": campaign},
            {"step": "Review summary", "evidence": readiness.review_summary},
        ]
        next_step = "有 campaign 时先看 Campaigns 页面和 Review 页面；没有 campaign 时不要手填 ID。"
    elif any(token in lower for token in ["最近", "发生", "日志", "审计", "audit"]):
        intent = "recent_audit"
        timeline = list(audit.get("timeline", []))
        conclusion = "已读取最近关键操作。" if timeline else "当前没有最近关键操作记录。"
        evidence = [f"timeline events: {len(timeline)}"]
        trace = timeline[:5]
        next_step = "进入 Audit Trail 查看完整时间线和对象链路。"
    else:
        intent = "runtime_status"
        conclusion = readiness.current_conclusion
        evidence = readiness.why
        trace = [
            {"step": "Runtime summary", "evidence": readiness.runtime_summary},
            {"step": "Markets summary", "evidence": markets},
        ]
        next_step = readiness.next_step

    return BrcInvestigatorAskResponse(
        intent=intent,
        conclusion=conclusion,
        reason="AI Investigator MVP 使用受控只读 resolver，不使用自由 SQL，也不会把模型输出当作事实源。",
        account_impact="不会影响真实账户；不会下单、提现、转账、改参数或切换 playbook。",
        evidence_summary=[str(item) for item in evidence],
        trace=trace,
        next_step=next_step,
        developer_details={
            "context_type": body.context_type,
            "context_id": body.context_id,
            "market_errors": market_errors,
            "audit_errors": audit_errors,
            "free_sql_enabled": False,
        },
    )


@router.get("/campaigns/current", response_model=runtime.BrcCampaignResponse)
async def get_current_campaign(request: Request) -> runtime.BrcCampaignResponse:
    return await runtime.get_current_brc_campaign(request)


@router.get("/evidence", response_model=runtime.BrcEvidenceResponse)
async def get_evidence(request: Request) -> runtime.BrcEvidenceResponse:
    return await runtime.get_brc_evidence(request)


@router.get("/review-packet", response_model=runtime.BrcReviewPacketResponse)
async def get_review_packet(request: Request) -> runtime.BrcReviewPacketResponse:
    return await runtime.get_brc_review_packet(request)


@router.get("/next-eligibility", response_model=runtime.BrcNextEligibilityResponse)
async def get_next_eligibility(request: Request) -> runtime.BrcNextEligibilityResponse:
    return await runtime.get_brc_next_eligibility(request)


@router.post("/review-decisions", response_model=runtime.BrcReviewDecisionResponse)
async def create_review_decision(
    request: Request,
    body: runtime.BrcReviewDecisionRequest,
) -> runtime.BrcReviewDecisionResponse:
    return await runtime.create_brc_review_decision(request, body)


@router.get("/review-decisions/latest", response_model=runtime.BrcReviewDecisionResponse)
async def get_latest_review_decision(request: Request) -> runtime.BrcReviewDecisionResponse:
    return await runtime.get_latest_brc_review_decision(request)


@router.get("/review-decisions", response_model=runtime.BrcReviewDecisionListResponse)
async def list_review_decisions(
    request: Request,
    campaign_id: Optional[str] = Query(default=None, max_length=128),
    limit: int = Query(default=50, ge=1, le=200),
) -> runtime.BrcReviewDecisionListResponse:
    return await runtime.list_brc_review_decisions(request, campaign_id=campaign_id, limit=limit)


@operator_router.post("/draft", response_model=runtime.BrcOperatorIntentDraftResponse)
async def draft_operator_intent(
    request: Request,
    body: runtime.BrcOperatorIntentDraftRequest,
) -> runtime.BrcOperatorIntentDraftResponse:
    return await runtime.draft_brc_operator_intent(request, body)


@operator_router.post("/plan", response_model=runtime.BrcOperatorPlanResponse)
async def plan_operator_action(
    request: Request,
    body: runtime.BrcOperatorIntentDraftRequest,
) -> runtime.BrcOperatorPlanResponse:
    return await runtime.plan_brc_operator_action(request, body)


@operator_router.get("/actions", response_model=runtime.BrcOperatorActionListResponse)
async def list_operator_actions(
    request: Request,
    campaign_id: Optional[str] = Query(default=None, max_length=128),
    limit: int = Query(default=50, ge=1, le=200),
) -> runtime.BrcOperatorActionListResponse:
    return await runtime.list_brc_operator_actions(request, campaign_id=campaign_id, limit=limit)


@operator_router.get("/actions/{action_id}", response_model=runtime.BrcOperatorActionResponse)
async def get_operator_action(
    action_id: str,
    request: Request,
) -> runtime.BrcOperatorActionResponse:
    return await runtime.get_brc_operator_action(action_id, request)


@operator_router.post("/actions/{action_id}/run", response_model=runtime.BrcOperatorRunResponse)
async def run_operator_action_by_id(
    action_id: str,
    request: Request,
    body: runtime.BrcOperatorActionRunRequest,
) -> runtime.BrcOperatorRunResponse:
    return await runtime.run_brc_operator_action_by_id(action_id, request, body)


@operator_router.post("/run", response_model=runtime.BrcOperatorRunResponse)
async def run_operator_action(
    request: Request,
    body: runtime.BrcOperatorRunRequest,
) -> runtime.BrcOperatorRunResponse:
    return await runtime.run_brc_operator_action(request, body)


@workflow_router.post("", response_model=runtime.BrcLlmWorkflowResponse)
async def create_llm_workflow(
    request: Request,
    body: runtime.BrcLlmWorkflowCreateRequest,
) -> runtime.BrcLlmWorkflowResponse:
    return await runtime.create_brc_llm_workflow(request, body)


@workflow_router.get("", response_model=runtime.BrcLlmWorkflowListResponse)
async def list_llm_workflows(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    status: Optional[runtime.BrcWorkflowStatus] = Query(default=None),
) -> runtime.BrcLlmWorkflowListResponse:
    return await runtime.list_brc_llm_workflows(request, limit=limit, status=status)


@workflow_router.get("/{workflow_run_id}", response_model=runtime.BrcLlmWorkflowResponse)
async def get_llm_workflow(
    workflow_run_id: str,
    request: Request,
) -> runtime.BrcLlmWorkflowResponse:
    return await runtime.get_brc_llm_workflow(workflow_run_id, request)


@workflow_router.post("/{workflow_run_id}/confirm", response_model=runtime.BrcLlmWorkflowResponse)
async def confirm_llm_workflow(
    workflow_run_id: str,
    request: Request,
    body: runtime.BrcLlmWorkflowConfirmRequest,
) -> runtime.BrcLlmWorkflowResponse:
    return await runtime.confirm_brc_llm_workflow(workflow_run_id, request, body)


@dev_testnet_router.post("/campaigns", response_model=runtime.BrcCampaignResponse)
async def create_testnet_campaign(
    request: Request,
    body: runtime.BrcCreateCampaignRequest,
) -> runtime.BrcCampaignResponse:
    return await runtime.create_brc_campaign(request, body)


@dev_testnet_router.post("/switch-playbook", response_model=runtime.BrcSwitchPlaybookResponse)
async def switch_testnet_playbook(
    request: Request,
    body: runtime.BrcSwitchPlaybookRequest,
) -> runtime.BrcSwitchPlaybookResponse:
    return await runtime.switch_brc_playbook(request, body)


@dev_testnet_router.post("/{symbol_key}/arm-attempt", response_model=runtime.BrcAttemptResponse)
async def arm_testnet_attempt(
    symbol_key: str,
    request: Request,
    body: runtime.BrcArmAttemptRequest,
) -> runtime.BrcAttemptResponse:
    return await runtime.arm_brc_attempt(symbol_key, request, body)


@dev_testnet_router.post("/{symbol_key}/execute-controlled-entry", response_model=runtime.ControlledEntryResponse)
async def execute_testnet_entry(symbol_key: str, request: Request) -> runtime.ControlledEntryResponse:
    return await runtime.execute_brc_controlled_entry(symbol_key, request)


@dev_testnet_router.post("/{symbol_key}/execute-controlled-close", response_model=runtime.ControlledCloseResponse)
async def execute_testnet_close(symbol_key: str, request: Request) -> runtime.ControlledCloseResponse:
    return await runtime.execute_brc_controlled_close(symbol_key, request)


@dev_testnet_router.post("/mock-pnl", response_model=runtime.BrcMockPnlResponse)
async def inject_testnet_mock_pnl(
    request: Request,
    body: runtime.BrcMockPnlRequest,
) -> runtime.BrcMockPnlResponse:
    return await runtime.inject_brc_mock_pnl(request, body)


@dev_testnet_router.post("/finalize", response_model=runtime.BrcCampaignResponse)
async def finalize_testnet_campaign(
    request: Request,
    body: runtime.BrcFinalizeRequest,
) -> runtime.BrcCampaignResponse:
    return await runtime.finalize_brc_campaign(request, body)
