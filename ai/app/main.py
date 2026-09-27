"""Spring 내부 AI 계약: health, deterministic intent, scoped semantic retrieval."""

from functools import lru_cache

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.recommendation_explanation import (
    ExplanationRequest,
    ExplanationResponse,
    RecommendationExplanationService,
    configured_explanation_service,
)
from app.semantic_runtime import (
    DependencyUnavailable,
    IntentRequest,
    IntentResponse,
    RetrievalRequest,
    RetrievalResponse,
    SemanticRetrievalService,
    analyze,
)
from app.workflows.recommendation_graph import RecommendationWorkflow


class HealthResponse(BaseModel):
    status: str
    service: str


app = FastAPI(
    title="ZeroPay Lunch AI Server",
    version="0.1.0",
)


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    # Liveness is deliberately independent of Ollama/Qdrant availability.
    return HealthResponse(status="ok", service="ai")


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, error: RequestValidationError):
    return JSONResponse(
        status_code=400, content={"code": "INVALID_REQUEST", "message": "invalid AI request"}
    )


@app.exception_handler(DependencyUnavailable)
async def unavailable(request: Request, error: DependencyUnavailable):
    return JSONResponse(
        status_code=503,
        content={
            "code": "SEMANTIC_RETRIEVAL_UNAVAILABLE",
            "message": "semantic retrieval dependency unavailable",
        },
    )


@app.exception_handler(Exception)
async def internal_error(request: Request, error: Exception):
    return JSONResponse(
        status_code=500, content={"code": "INTERNAL_ERROR", "message": "internal AI error"}
    )


@app.post("/internal/v1/intent-analysis", response_model=IntentResponse)
def intent_analysis(request: IntentRequest):
    return analyze(request.query)


@lru_cache(maxsize=1)
def recommendation_workflow():
    # Compiled once per FastAPI process; graph nodes reuse the retrieval service.
    return RecommendationWorkflow(SemanticRetrievalService())


@app.post("/internal/v1/semantic-retrieval", response_model=RetrievalResponse)
async def semantic_retrieval(
    request: RetrievalRequest,
    workflow: RecommendationWorkflow = Depends(recommendation_workflow),  # noqa: B008
):
    result, route = await workflow.run(request)
    if route == "SEMANTIC_FAILURE_FALLBACK":
        # Keep the 503 boundary so Spring's configured fallback remains authoritative.
        raise DependencyUnavailable("semantic retrieval unavailable")
    return result


@lru_cache(maxsize=1)
def recommendation_explanation_service():
    return configured_explanation_service()


@app.post(
    "/internal/v1/recommendation-explanations",
    response_model=ExplanationResponse,
    tags=["recommendations"],
)
def recommendation_explanations(
    request: ExplanationRequest,
    service: RecommendationExplanationService = Depends(recommendation_explanation_service),  # noqa: B008
):
    return service.explain(request)
