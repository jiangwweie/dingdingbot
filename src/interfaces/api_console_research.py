from __future__ import annotations

from fastapi import APIRouter, HTTPException

from src.application.readmodels.candidate_service import CandidateArtifactService
from src.application.readmodels.console_models import (
    CandidateDetailResponse,
    CandidateListItem,
    ConfigSnapshotResponse,
    ReplayContextResponse,
    ReviewSummaryResponse,
)
from src.application.readmodels.runtime_config_snapshot import RuntimeConfigSnapshotReadModel

router = APIRouter(prefix="/api/research", tags=["Console Research"])


@router.get("/candidates", response_model=list[CandidateListItem])
async def list_candidates(limit: int = 100) -> list[CandidateListItem]:
    service = CandidateArtifactService()
    return service.list_candidates(limit=limit)


@router.get("/candidates/{candidate_name}", response_model=CandidateDetailResponse)
async def get_candidate_detail(candidate_name: str) -> CandidateDetailResponse:
    service = CandidateArtifactService()
    result = service.get_candidate_detail(candidate_name)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Candidate not found: {candidate_name}")
    return result


@router.get("/replay/{candidate_name}", response_model=ReplayContextResponse)
async def get_replay_context(candidate_name: str) -> ReplayContextResponse:
    service = CandidateArtifactService()
    result = service.get_replay_context(candidate_name)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Candidate not found: {candidate_name}")
    return result


@router.get("/candidates/{candidate_name}/review-summary", response_model=ReviewSummaryResponse)
async def get_review_summary(candidate_name: str) -> ReviewSummaryResponse:
    service = CandidateArtifactService()
    result = service.get_review_summary(candidate_name)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Candidate not found: {candidate_name}")
    return result


# Separate router for /api/config/* endpoints
config_router = APIRouter(prefix="/api/config", tags=["Console Config"])


@config_router.get("/snapshot", response_model=ConfigSnapshotResponse)
async def get_config_snapshot() -> ConfigSnapshotResponse:
    from src.interfaces import api as api_module

    provider = getattr(api_module, "_runtime_config_provider", None)
    read_model = RuntimeConfigSnapshotReadModel()
    return read_model.build(runtime_config_provider=provider)
