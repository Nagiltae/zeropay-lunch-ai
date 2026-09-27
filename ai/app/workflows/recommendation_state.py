"""Minimal state shared by the recommendation retrieval workflow."""

from typing import Any, TypedDict

from app.semantic_runtime import IntentResponse, RetrievalResponse


class RecommendationWorkflowState(TypedDict, total=False):
    originalQuery: str
    candidateRestaurantIds: tuple[int, ...]
    topK: int
    intent: IntentResponse | None
    semanticEligible: bool
    semanticQuery: str | None
    semanticResults: RetrievalResponse | None
    retrievalStatus: str
    retryCount: int
    maxRetries: int
    fallbackReason: str | None
    errors: list[str]
    workflowRoute: str
    trace: list[dict[str, Any]]
    startedAt: float
    elapsedMs: float
    response: RetrievalResponse
