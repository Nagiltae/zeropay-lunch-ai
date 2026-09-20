"""Small, mockable Ollama/Qwen adapter for ambiguous candidate selection."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SYSTEM_PROMPT = """/no_think

너는 음식점 검색 후보 랭커다.
너의 역할은 기준 음식점과 네이버 플레이스 검색 후보들을 비교하여
가장 유사한 후보 하나를 선택하는 것이다.
이 단계에서는 동일 매장임을 최종 확정하지 않으며, 최종 검증은 상세 페이지에서 수행된다.
핵심 상호명, 지점명, 도로명/지번 주소, 건물번호, 음식점 카테고리,
띄어쓰기, 약칭, 한글/영문 표기와 부가 설명을 종합한다.
후보가 하나 이상이면 가능한 후보 중 상위 min(5, 후보 수)개를
유사도 순서대로 모두 반환한다. 전달된 후보는 모두 순위에 포함한다.
Place ID를 생성하거나 추측하거나 반환하지 않는다.
반드시 지정된 JSON 구조만 반환한다.
"""


class LlmUnavailable(RuntimeError):
    """Ollama could not provide a response."""


@dataclass(frozen=True)
class QwenDecision:
    candidate_indices: tuple[int, ...]
    confidence: str


class LocalLlmClient(Protocol):
    def complete(self, system: str, user: str, response_schema: dict) -> str: ...


class OllamaClient:
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 15.0,
    ) -> None:
        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.model = model or os.getenv("LOCAL_LLM_MODEL", "qwen3:8b")
        self.timeout = timeout

    def complete(self, system: str, user: str, response_schema: dict | None = None) -> str:
        payload = {
            "model": self.model,
            "system": system,
            "prompt": user,
            "stream": False,
            "think": False,
            "format": response_schema
            or {
                "type": "object",
                "properties": {
                    "candidateIndices": {"type": "array", "items": {"type": "integer"}},
                    "confidence": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
                },
                "required": ["candidateIndices", "confidence"],
            },
            "options": {"temperature": 0, "num_predict": 80},
        }
        try:
            request = Request(
                f"{self.base_url.rstrip('/')}/api/generate",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode()).get("response", "")
        except (HTTPError, URLError, TimeoutError, ValueError, KeyError) as error:
            raise LlmUnavailable(str(error)) from error


def build_user_prompt(reference, candidates) -> str:
    lines = [
        "기준 음식점:",
        f"이름: {reference.komsco_name or '없음'}",
        f"주소: {reference.komsco_address or '없음'}",
        "카테고리: 음식점",
        "",
        "네이버 플레이스 검색 후보:",
    ]
    for index, candidate in enumerate(candidates):
        lines.extend(
            [
                f"[{index}]",
                f"이름: {candidate.name or '없음'}",
                f"주소: {candidate.address or '없음'}",
                f"카테고리: {candidate.category or '없음'}",
            ]
        )
    lines.append("가능한 후보 중 상위 min(5, 후보 수)개를 유사도 순서대로 모두 반환해라.")
    return "\n".join(lines)


def parse_qwen_decision(raw: str, candidate_count: int) -> QwenDecision:
    try:
        payload = json.loads(raw)
        indices = payload.get("candidateIndices")
        confidence = payload.get("confidence")
    except (json.JSONDecodeError, AttributeError, TypeError) as error:
        raise ValueError("invalid Qwen JSON") from error
    if confidence not in {"HIGH", "MEDIUM", "LOW"}:
        raise ValueError("invalid Qwen confidence")
    expected_count = min(5, candidate_count)
    if not isinstance(indices, list) or len(indices) != expected_count:
        raise ValueError(f"Qwen candidateIndices must contain exactly {expected_count} items")
    if any(not isinstance(index, int) or not 0 <= index < candidate_count for index in indices):
        raise ValueError("Qwen candidateIndex out of range")
    if len(set(indices)) != len(indices):
        raise ValueError("Qwen candidateIndices must be unique")
    return QwenDecision(tuple(indices), confidence)


class QwenCandidateMatcher:
    def __init__(self, client: LocalLlmClient) -> None:
        self.client = client

    def choose(self, reference, candidates) -> QwenDecision:
        if not candidates:
            raise ValueError("Qwen requires at least one candidate")
        schema = {
            "type": "object",
            "properties": {
                "candidateIndices": {
                    "type": "array",
                    "items": {"type": "integer", "enum": list(range(len(candidates)))},
                    "minItems": min(5, len(candidates)),
                    "maxItems": min(5, len(candidates)),
                    "uniqueItems": True,
                },
                "confidence": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
            },
            "required": ["candidateIndices", "confidence"],
        }
        prompt = build_user_prompt(reference, candidates)
        last_error: Exception | None = None
        for attempt in range(2):
            if attempt:
                prompt += (
                    "\n반드시 제공된 후보 중 상위 min(5, 후보 수)개 index를 "
                    "빠짐없이 순서대로 반환해라."
                )
            try:
                raw = self.client.complete(SYSTEM_PROMPT, prompt, schema)
                return parse_qwen_decision(raw, len(candidates))
            except (ValueError, LlmUnavailable) as error:
                last_error = error
        raise ValueError("Qwen response failed after one retry") from last_error
