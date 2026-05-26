from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

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
