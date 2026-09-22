"""Small, mockable Ollama/Qwen adapter for ambiguous candidate selection."""

from __future__ import annotations

import http.client
import json
import os
import threading
import time
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit

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


def configured_qwen_model() -> str:
    """Single switch for ranking and semantic Entity Resolution models."""
    return os.getenv("QWEN_MODEL") or os.getenv("LOCAL_LLM_MODEL") or "qwen3.5:9b"


@dataclass(frozen=True)
class QwenDecision:
    candidate_indices: tuple[int, ...]
    confidence: str


@dataclass(frozen=True)
class QwenSemanticDecision:
    entity_match: str
    business_type: str
    location_scope: str
    final_decision: str
    name_evidence: str
    address_evidence: str
    category_evidence: str
    coordinate_evidence: str
    reason: str
    conflicts: tuple[str, ...] = ()

    @property
    def decision(self) -> str:
        return self.entity_match


class LocalLlmClient(Protocol):
    def complete(self, system: str, user: str, response_schema: dict) -> str: ...


class OllamaClient:
    # 배치 동안 하나의 HTTP 연결을 재사용하되, Qwen 추론 자체는 순차 호출로 유지한다.
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.model = model or configured_qwen_model()
        self.timeout = timeout
        self._connection = None
        self._connection_lock = threading.Lock()

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
            # Semantic validation returns several evidence fields; keep enough
            # room for a complete structured response rather than truncating
            # the JSON before required fields are emitted.
            "options": {"temperature": 0, "num_predict": 384},
        }
        parsed = urlsplit(self.base_url)
        try:
            with self._connection_lock:
                connection = self._get_connection(parsed)
                connection.request(
                    "POST",
                    f"{parsed.path.rstrip('/')}/api/generate",
                    body=json.dumps(payload).encode(),
                    headers={"Content-Type": "application/json"},
                )
                response = connection.getresponse()
                body = response.read().decode("utf-8", errors="replace")
                if response.status >= 400:
                    raise LlmUnavailable(f"HTTP_{response.status}")
                return json.loads(body).get("response", "")
        except LlmUnavailable:
            self._close_connection()
            raise
        except (
            http.client.HTTPException,
            OSError,
            TimeoutError,
            ValueError,
            KeyError,
            AttributeError,
        ) as error:
            self._close_connection()
            raise LlmUnavailable(str(error)) from error

    def _get_connection(self, parsed):
        if self._connection is None:
            connection_type = (
                http.client.HTTPSConnection
                if parsed.scheme == "https"
                else http.client.HTTPConnection
            )
            self._connection = connection_type(
                parsed.hostname,
                parsed.port,
                timeout=self.timeout,
            )
        return self._connection

    def _close_connection(self) -> None:
        if self._connection is not None:
            try:
                self._connection.close()
            finally:
                self._connection = None

    def close(self) -> None:
        with self._connection_lock:
            self._close_connection()


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
        for label, value in (
            ("도로명주소", getattr(candidate, "road_address", "")),
            ("지번주소", getattr(candidate, "jibun_address", "")),
        ):
            if value:
                lines.append(f"{label}: {value}")
        category_values = getattr(candidate, "category_values", ())
        if category_values:
            lines.append(f"카테고리 원본: {json.dumps(category_values, ensure_ascii=False)}")
    lines.append("가능한 후보 중 상위 min(5, 후보 수)개를 유사도 순서대로 모두 반환해라.")
    return "\n".join(lines)


def build_semantic_prompt(reference, candidate) -> str:
    """Build a detail-page identity prompt without exposing Place IDs."""
    lines = [
        "기준 KOMSCO 음식점:",
        f"이름: {reference.komsco_name or '없음'}",
        f"주소: {reference.komsco_address or '없음'}",
        f"좌표: {reference.komsco_latitude}, {reference.komsco_longitude}",
        "",
        "PCMap 상세 음식점:",
        f"이름: {candidate.name or '없음'}",
        f"주소: {candidate.address or '없음'}",
        f"카테고리: {candidate.category or '없음'}",
    ]
    for label, value in (
        ("카테고리 원본", getattr(candidate, "category_values", ())),
        ("도로명주소", getattr(candidate, "road_address", "")),
        ("지번주소", getattr(candidate, "jibun_address", "")),
    ):
        if value:
            rendered = json.dumps(value, ensure_ascii=False) if label == "카테고리 원본" else value
            lines.append(f"{label}: {rendered}")
    if candidate.latitude is not None or candidate.longitude is not None:
        lines.append(f"좌표: {candidate.latitude}, {candidate.longitude}")
    lines.extend(
        [
            "",
            "entity_match(같은 사업체/지점), business_type(음식점 적격성), "
            "location_scope(논현동 범위), final_decision(최종 수용 여부)를 분리해 판단하라. "
            "문자열 완전 일치가 아니라 실제 같은 사업장인지 판단하라. "
            "KOMSCO가 음식점으로 등록되어 있어도 그 사실만으로 PCMap을 음식점으로 확정하지 마라. "
            "PCMap 상세 category가 미용실·병원·치과·약국·부동산·여행사 등 명백한 비음식 업종이면 "
            "business_type=NON_FOOD로 판단하라. 같은 사업체라면 entity_match=MATCH일 수 있지만 "
            "final_decision은 REJECT다. "
            "정보가 생략된 것과 실제로 충돌하는 것을 구분하라. "
            "논현동·층·호·건물명이 한쪽에 없다는 것만으로 NO_MATCH하지 마라. "
            "주소를 이름보다 우선하는 핵심 동일성 증거로 사용하라. "
            "시·구·동, 도로명, 건물번호가 서로 다르면 같은 구라는 이유만으로 MATCH하지 말고, "
            "상호가 비슷하거나 같은 브랜드여도 실제 지점이 다르면 반드시 NO_MATCH로 판단하라. "
            "법인명·지점명·본점/직영점·괄호·단어 순서·층/호·건물명 생략·도로명/지번 표현 차이는 "
            "주소의 핵심 위치가 같거나 양립할 때만 허용한다. "
            "도로명과 건물번호가 같고 핵심 상호명이 양립하면 강한 MATCH 증거다. "
            "주소 정보가 없거나 일부만 있어 동일성을 확정할 수 없으면 UNCERTAIN으로 판단하라. "
            "단 하나의 단어가 겹친다는 이유로 MATCH하지 말고, 주소·업종·지점 위치가 "
            "명백히 다르면 MATCH하지 마라. "
            "정보가 없다는 것과 반대되는 정보가 있다는 것을 구분하고, "
            "UNKNOWN category나 좌표 없음만으로 NO_MATCH하지 마라. "
            "동일 브랜드라도 도로명·건물번호·지점이 다르면 NO_MATCH이며, "
            "KOMSCO 원천 자체가 틀릴 가능성도 고려하라. "
            "KOMSCO가 음식점이어도 원천 데이터가 틀릴 수 있다. "
            "여행사·미용실·식료품점·정보통신·병원 등은 "
            "같은 사업체일 수 있어도 business_type=NON_FOOD이고 final_decision=REJECT다. "
            "category가 없거나 좌표가 없으면 UNKNOWN으로 두며, 정보 부족은 UNCERTAIN으로 처리한다. "
            "음식점이고 논현동이면 FOOD/IN_SCOPE/ACCEPT, 명백히 다른 지점·주소면 REJECT다. "
            '반드시 다음 JSON만 반환하라: {"entity_match":"MATCH|NO_MATCH|UNCERTAIN",'
            '"business_type":"FOOD|NON_FOOD|UNKNOWN","location_scope":"IN_SCOPE|OUT_OF_SCOPE|UNKNOWN",'
            '"final_decision":"ACCEPT|REJECT|UNCERTAIN","name_evidence":"...",'
            '"address_evidence":"...","category_evidence":"...","coordinate_evidence":"...","reason":"..."}',
        ]
    )
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


def parse_qwen_semantic_decision(raw: str) -> QwenSemanticDecision:
    text = raw.strip()
    if "```" in text:
        text = text.replace("```json", "").replace("```", "").strip()
    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, TypeError) as error:
        raise ValueError("invalid Qwen semantic JSON") from error
    if not isinstance(payload, dict):
        raise ValueError("invalid Qwen semantic object")
    entity_match = payload.get("entity_match", payload.get("decision"))
    if entity_match not in {"MATCH", "UNCERTAIN", "NO_MATCH"}:
        raise ValueError("invalid Qwen entity_match")
    business_type = payload.get("business_type", "UNKNOWN")
    location_scope = payload.get("location_scope", "UNKNOWN")
    if business_type not in {"FOOD", "NON_FOOD", "UNKNOWN"}:
        raise ValueError("invalid Qwen business_type")
    if location_scope not in {"IN_SCOPE", "OUT_OF_SCOPE", "UNKNOWN"}:
        raise ValueError("invalid Qwen location_scope")
    final_decision = payload.get("final_decision")
    if final_decision is None:
        final_decision = {"MATCH": "ACCEPT", "NO_MATCH": "REJECT", "UNCERTAIN": "UNCERTAIN"}[
            entity_match
        ]
    if final_decision not in {"ACCEPT", "REJECT", "UNCERTAIN"}:
        raise ValueError("invalid Qwen final_decision")
    conflicts = payload.get("conflicts", ())
    if isinstance(conflicts, str):
        conflicts = (conflicts,) if conflicts else ()
    if not isinstance(conflicts, (list, tuple)) or any(
        not isinstance(value, str) for value in conflicts
    ):
        raise ValueError("invalid Qwen semantic conflicts")
    return QwenSemanticDecision(
        entity_match,
        business_type,
        location_scope,
        final_decision,
        str(payload.get("name_evidence") or ""),
        str(payload.get("address_evidence") or ""),
        str(payload.get("category_evidence") or ""),
        str(payload.get("coordinate_evidence") or ""),
        str(payload.get("reason") or ""),
        tuple(conflicts),
    )


class QwenCandidateMatcher:
    def __init__(self, client: LocalLlmClient, on_call=None) -> None:
        self.client = client
        self._on_call = on_call or (lambda _operation, _latency: None)

    def _complete(self, operation: str, system: str, prompt: str, schema: dict) -> str:
        started = time.monotonic()
        try:
            return self.client.complete(system, prompt, schema)
        finally:
            self._on_call(operation, max(0.0, time.monotonic() - started))

    def choose(self, reference, candidates) -> QwenDecision:
        # 후보 순위는 Qwen의 구조화된 의미 판단으로만 정하고, 호출자는 결과를 임의로 뒤집지 않는다.
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
                raw = self._complete("choose", SYSTEM_PROMPT, prompt, schema)
                return parse_qwen_decision(raw, len(candidates))
            except (ValueError, LlmUnavailable) as error:
                last_error = error
        raise ValueError("Qwen response failed after one retry") from last_error

    def validate(self, reference, candidate) -> QwenSemanticDecision:
        schema = {
            "type": "object",
            "properties": {
                "entity_match": {"type": "string", "enum": ["MATCH", "UNCERTAIN", "NO_MATCH"]},
                "business_type": {"type": "string", "enum": ["FOOD", "NON_FOOD", "UNKNOWN"]},
                "location_scope": {
                    "type": "string",
                    "enum": ["IN_SCOPE", "OUT_OF_SCOPE", "UNKNOWN"],
                },
                "final_decision": {"type": "string", "enum": ["ACCEPT", "REJECT", "UNCERTAIN"]},
                "name_evidence": {"type": "string"},
                "address_evidence": {"type": "string"},
                "category_evidence": {"type": "string"},
                "coordinate_evidence": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": [
                "entity_match",
                "business_type",
                "location_scope",
                "final_decision",
                "reason",
            ],
        }
        prompt = build_semantic_prompt(reference, candidate)
        last_error: Exception | None = None
        for attempt in range(2):
            if attempt:
                prompt += "\n반드시 4개 enum과 짧은 evidence/reason을 포함한 JSON만 반환하라."
            try:
                raw = self._complete(
                    "validate",
                    "/no_think\n너는 음식점 entity matching 검증기다. "
                    "Place ID를 생성하거나 추측하지 마라.",
                    prompt,
                    schema,
                )
                return parse_qwen_semantic_decision(raw)
            except (ValueError, LlmUnavailable) as error:
                last_error = error
        raise ValueError("Qwen semantic response failed after one retry") from last_error
