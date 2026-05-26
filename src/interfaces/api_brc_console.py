from __future__ import annotations

import os
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
    runtime_summary: dict[str, Any] = Field(default_factory=dict)
    review_summary: dict[str, Any] = Field(default_factory=dict)
    developer_details: dict[str, Any] = Field(default_factory=dict)
    live_ready: Literal[False] = False


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

    reasons: list[str] = []
    if runtime_context is None:
        reasons.append("当前只是 Standalone Console，后端没有绑定运行时 Runtime。")
    if service is None:
        reasons.append("当前没有连接 BRC Campaign 服务，不能读取或写入 campaign 治理数据。")
    if service_error:
        reasons.append("BRC Campaign 服务读取失败，页面只能显示安全说明。")
    reasons.extend(profile_reasons)

    runtime_ready = runtime_context is not None and service is not None and not profile_reasons
    has_campaign = latest_campaign is not None
    mutation_env_ready = _env_enabled("RUNTIME_CONTROL_API_ENABLED") and _env_enabled(
        "RUNTIME_TEST_SIGNAL_INJECTION_ENABLED"
    )
    testnet_ready = runtime_ready and gks_active is False and startup_guard_armed is True and mutation_env_ready

    if runtime_context is None:
        mode: Literal["standalone_console", "runtime_bound_console", "brc_ready", "testnet_ready", "blocked"] = "standalone_console"
        conclusion = "当前只能查看，不能执行 BRC campaign 操作。"
        next_step = "启动绑定 BRC runtime 的后端后，再回到 Guide 操作向导刷新状态。"
    elif not runtime_ready:
        mode = "runtime_bound_console"
        conclusion = "运行时已连接，但 BRC 操作条件还不完整。"
        next_step = "先检查运行配置 Profile、测试网 Testnet 和 BRC 服务初始化状态。"
    elif testnet_ready:
        mode = "testnet_ready"
        conclusion = "当前满足受控测试网 workflow 的基础门槛。"
        next_step = "如需 testnet 演练，请进入 Workflow 受控流程并手动确认。"
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
    if gks_active is not False:
        testnet_missing.append("全局安全开关 GKS 必须处于未阻断状态。")
    if startup_guard_armed is not True:
        testnet_missing.append("启动保护 Startup Guard 必须完成受控 armed 状态。")
    if not _env_enabled("RUNTIME_CONTROL_API_ENABLED"):
        testnet_missing.append("本地 runtime control mutation 开关未开启。")
    if not _env_enabled("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED"):
        testnet_missing.append("本地 test signal injection 开关未开启。")
    no_testnet_reason = " ".join(testnet_missing) or "受控 testnet workflow 需要 BRC profile、Exchange Testnet、GKS 和 Startup Guard 同时满足。"

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
            what_happens="只有在专用确认短语输入后，才可能进入固定 testnet rehearsal。",
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

    return BrcReadinessResponse(
        mode=mode,
        current_conclusion=conclusion,
        why=reasons,
        account_impact="不会影响真实账户；readiness 只读，不会下单、提现、转账或修改仓位。",
        next_step=next_step,
        available_actions=available,
        disabled_actions=disabled,
        latest_campaign=campaign_summary,
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
        developer_details={
            "runtime_context_bound": runtime_context is not None,
            "brc_campaign_service_present": service is not None,
            "service_error": service_error,
            "profile_reasons": profile_reasons,
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
