"""Case analysis endpoints."""

from fastapi import APIRouter

from app.models.case_models import CaseAnalyzeRequest, CaseAnalyzeResponse
from app.services.case_analyzer import case_analyzer

router = APIRouter(prefix="/case", tags=["Case Analysis"])


@router.post("/analyze", response_model=CaseAnalyzeResponse)
def analyze_case(request: CaseAnalyzeRequest) -> CaseAnalyzeResponse:
    return case_analyzer.analyze(request.enriched_case_text or request.case_text)
