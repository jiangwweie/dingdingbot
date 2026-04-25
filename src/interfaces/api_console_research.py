from __future__ import annotations

from fastapi import APIRouter

from src.application.readmodels.candidate_service import CandidateArtifactService
from src.application.readmodels.console_models import CandidateListItem

router = APIRouter(prefix="/api/research", tags=["Console Research"])


@router.get("/candidates", response_model=list[CandidateListItem])
async def list_candidates(limit: int = 100) -> list[CandidateListItem]:
    service = CandidateArtifactService()
    return service.list_candidates(limit=limit)
