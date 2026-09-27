"""Stateful orchestration for candidate-scoped semantic retrieval."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.semantic_runtime import (
    DependencyUnavailable,
    RetrievalRequest,
    RetrievalResponse,
    RetryableDependencyUnavailable,
    SemanticRetrievalService,
    analyze,
)
from app.workflows.recommendation_state import RecommendationWorkflowState

logger = logging.getLogger(__name__)
MAX_RETRIES = 1


def _trace(state: RecommendationWorkflowState, node: str, status: str, **fields: Any) -> list[dict]:
    return [*state.get("trace", []), {"node": node, "status": status, **fields}]


def _empty_response() -> RetrievalResponse:
    return RetrievalResponse(candidates=[])


def build_recommendation_graph(
    retrieval_service: SemanticRetrievalService,
    *,
    max_retries: int = MAX_RETRIES,
    clock: Callable[[], float] = time.monotonic,
):
    """Build and compile once; retrieval remains the existing service operation."""

    if max_retries < 0:
        raise ValueError("max_retries must be non-negative")

    def prepare(state: RecommendationWorkflowState) -> dict:
        # Candidate IDs are frozen as a tuple and copied unchanged through the graph.
        candidate_ids = tuple(state["candidateRestaurantIds"])
        return {
            "candidateRestaurantIds": candidate_ids,
            "retryCount": 0,
            "maxRetries": max_retries,
            "errors": [],
            "trace": _trace(state, "prepare", "SUCCESS"),
            "startedAt": clock(),
        }

    def intent_analysis(state: RecommendationWorkflowState) -> dict:
        intent = analyze(state["originalQuery"])
        eligible = intent.primaryIntent != "UNKNOWN"
        return {
            "intent": intent,
            "semanticEligible": eligible,
            "semanticQuery": state["originalQuery"] if eligible else None,
            "trace": _trace(
                state,
                "intent_analysis",
                "SUCCESS",
                semanticEligible=eligible,
                primaryIntent=intent.primaryIntent,
            ),
        }

    def after_intent(state: RecommendationWorkflowState) -> str:
        if not state.get("semanticEligible") or not state["candidateRestaurantIds"]:
            return "semantic_skip"
        return "semantic_retrieval"

    def semantic_skip(state: RecommendationWorkflowState) -> dict:
        reason = "UNKNOWN_INTENT" if not state.get("semanticEligible") else "EMPTY_CANDIDATE_SCOPE"
        return {
            "retrievalStatus": "EMPTY",
            "fallbackReason": reason,
            "semanticResults": _empty_response(),
            "trace": _trace(state, "semantic_skip", "SKIPPED", reason=reason),
        }

    def semantic_retrieval(state: RecommendationWorkflowState) -> dict:
        try:
            result = retrieval_service.retrieve(
                RetrievalRequest(
                    query=state["semanticQuery"],
                    candidateRestaurantIds=list(state["candidateRestaurantIds"]),
                    topK=state["topK"],
                ),
                intent=state["intent"],
            )
            status = "SUCCESS" if result.candidates else "EMPTY"
            return {
                "semanticResults": result,
                "retrievalStatus": status,
                "fallbackReason": None if status == "SUCCESS" else "EMPTY_RESULT",
                "trace": _trace(
                    state,
                    "semantic_retrieval",
                    status,
                    attempt=state["retryCount"] + 1,
                    candidateCount=len(result.candidates),
                ),
            }
        except RetryableDependencyUnavailable:
            return {
                "retrievalStatus": "RETRYABLE_FAILURE",
                "fallbackReason": "TRANSIENT_DEPENDENCY_FAILURE",
                "errors": [
                    *state.get("errors", []),
                    "TRANSIENT_DEPENDENCY_FAILURE",
                ],
                "trace": _trace(
                    state,
                    "semantic_retrieval",
                    "RETRYABLE_FAILURE",
                    attempt=state["retryCount"] + 1,
                ),
            }
        except DependencyUnavailable:
            return {
                "retrievalStatus": "NON_RETRYABLE_FAILURE",
                "fallbackReason": "NON_RETRYABLE_DEPENDENCY_FAILURE",
                "errors": [
                    *state.get("errors", []),
                    "NON_RETRYABLE_DEPENDENCY_FAILURE",
                ],
                "trace": _trace(
                    state,
                    "semantic_retrieval",
                    "NON_RETRYABLE_FAILURE",
                    attempt=state["retryCount"] + 1,
                ),
            }

    def evaluate_retrieval(state: RecommendationWorkflowState) -> dict:
        status = state["retrievalStatus"]
        return {"trace": _trace(state, "retrieval_evaluation", status)}

    def after_retrieval_evaluation(state: RecommendationWorkflowState) -> str:
        status = state["retrievalStatus"]
        if status == "SUCCESS":
            return "finalize"
        if status == "RETRYABLE_FAILURE" and state["retryCount"] < state["maxRetries"]:
            return "bounded_retry"
        return "fallback"

    def bounded_retry(state: RecommendationWorkflowState) -> dict:
        retry_count = state["retryCount"] + 1
        return {
            "retryCount": retry_count,
            "trace": _trace(
                state,
                "bounded_retry",
                "RETRY",
                retry=retry_count,
                maxRetries=state["maxRetries"],
                inputUnchanged=True,
            ),
        }

    def fallback(state: RecommendationWorkflowState) -> dict:
        return {
            "semanticResults": _empty_response(),
            "workflowRoute": (
                "SEMANTIC_EMPTY_FALLBACK"
                if state["retrievalStatus"] == "EMPTY"
                else "SEMANTIC_FAILURE_FALLBACK"
            ),
            "trace": _trace(state, "fallback", "SUCCESS", reason=state.get("fallbackReason")),
        }

    def finalize(state: RecommendationWorkflowState) -> dict:
        route = state.get("workflowRoute") or None
        if route is None:
            if not state.get("semanticEligible"):
                route = "SEMANTIC_SKIPPED"
            elif state["retryCount"]:
                route = "SEMANTIC_RETRY_SUCCESS"
            else:
                route = "SEMANTIC_SUCCESS"
        result = state.get("semanticResults") or _empty_response()
        elapsed_ms = max(0.0, (clock() - state["startedAt"]) * 1000)
        trace = _trace(state, "finalize", "SUCCESS", route=route)
        logger.info(
            "recommendation_workflow route=%s nodes=%s retry_count=%d retrieval_status=%s "
            "fallback_reason=%s elapsed_ms=%.2f",
            route,
            ",".join(item["node"] for item in trace),
            state["retryCount"],
            state["retrievalStatus"],
            state.get("fallbackReason"),
            elapsed_ms,
        )
        return {
            "workflowRoute": route,
            "semanticResults": result,
            "response": result,
            "elapsedMs": elapsed_ms,
            "trace": trace,
        }

    graph = StateGraph(RecommendationWorkflowState)
    graph.add_node("prepare", prepare)
    graph.add_node("intent_analysis", intent_analysis)
    graph.add_node("semantic_skip", semantic_skip)
    graph.add_node("semantic_retrieval", semantic_retrieval)
    graph.add_node("retrieval_evaluation", evaluate_retrieval)
    graph.add_node("bounded_retry", bounded_retry)
    graph.add_node("fallback", fallback)
    graph.add_node("finalize", finalize)

    graph.add_edge(START, "prepare")
    graph.add_edge("prepare", "intent_analysis")
    graph.add_conditional_edges("intent_analysis", after_intent)
    graph.add_edge("semantic_skip", "finalize")
    graph.add_edge("semantic_retrieval", "retrieval_evaluation")
    graph.add_conditional_edges("retrieval_evaluation", after_retrieval_evaluation)
    graph.add_edge("bounded_retry", "semantic_retrieval")
    graph.add_edge("fallback", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile()


class RecommendationWorkflow:
    """Async entry point for the compiled graph."""

    def __init__(
        self, retrieval_service: SemanticRetrievalService, *, max_retries: int = MAX_RETRIES
    ):
        self.graph = build_recommendation_graph(retrieval_service, max_retries=max_retries)
        self.last_route: str | None = None

    async def run(self, request: Any) -> tuple[RetrievalResponse, str]:
        state = await self.graph.ainvoke(
            {
                "originalQuery": request.query,
                "candidateRestaurantIds": tuple(request.candidateRestaurantIds),
                "topK": request.topK,
                "intent": None,
                "semanticEligible": False,
                "semanticQuery": None,
                "semanticResults": None,
                "retrievalStatus": "NOT_STARTED",
                "retryCount": 0,
                "maxRetries": MAX_RETRIES,
                "fallbackReason": None,
                "errors": [],
                "workflowRoute": "",
                "trace": [],
            }
        )
        return state["response"], state["workflowRoute"]
