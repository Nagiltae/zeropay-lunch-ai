"""Evidence integrity and semantic support gate for shadow profile claims.

This module is deliberately offline from recommendation runtime and never
writes MySQL, embeddings, or Qdrant. Existing point claims without stored
support quotes fail the new indexability contract even when semantically
supported; the shadow verifier still evaluates their meaning for diagnosis.
"""

from __future__ import annotations

import json
import re
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

ALLOWED_CLAIM_TYPES = {
    "FOOD_TYPE",
    "FOOD_MENTION",
    "MENU_CHARACTERISTIC",
    "TASTE",
    "DINING_CONTEXT",
    "VENUE_CHARACTERISTIC",
}
VERDICTS = {"SUPPORTED", "PARTIAL", "UNSUPPORTED"}
MAX_CLAIM_LENGTH = 500


class SupportQuote(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidenceId: str = Field(min_length=1)
    quote: str = Field(min_length=1)


class ClaimCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    restaurantId: int
    claimId: str = Field(min_length=1)
    claimType: str = Field(min_length=1)
    claimText: str = Field(min_length=1)
    evidenceIds: list[str] = Field(min_length=1)
    supportQuotes: list[SupportQuote] = Field(default_factory=list)


class SemanticVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verdict: Literal["SUPPORTED", "PARTIAL", "UNSUPPORTED"]
    supportedPortion: str
    unsupportedPortion: str
    evidenceIds: list[str] = Field(min_length=1)


class AtomicAssertion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assertionId: str = Field(min_length=1)
    text: str = Field(min_length=1)
    sourceSpan: str = Field(min_length=1)


class AtomicizerAssertionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1)
    startToken: int = Field(ge=0, strict=True)
    endToken: int = Field(ge=0, strict=True)


class AtomicizerOutput(BaseModel):
    """Assertion prose is paired with model-selected source token indices."""

    model_config = ConfigDict(extra="forbid")
    assertions: list[AtomicizerAssertionOutput] = Field(min_length=1, max_length=8)


class Atomicization(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assertions: list[AtomicAssertion] = Field(min_length=1, max_length=8)


class AssertionVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verdict: Literal["SUPPORTED", "UNSUPPORTED"]
    evidenceIds: list[str] = Field(default_factory=list)


class Verifier(Protocol):
    def verify(self, claim: ClaimCandidate, evidence: list[dict[str, Any]]) -> SemanticVerdict: ...


class AtomicClaimVerifier(Protocol):
    def decompose(self, claim: ClaimCandidate) -> Atomicization: ...

    def verify_assertion(
        self,
        claim_type: str,
        assertion: AtomicAssertion,
        evidence: list[dict[str, Any]],
    ) -> AssertionVerdict: ...


def normalize_whitespace(value: str) -> str:
    return " ".join(value.split())


def raw_evidence_text(item: dict[str, Any]) -> str | None:
    """Select source text from the existing catalog without paraphrasing it."""
    content = item.get("content")
    if isinstance(content, str):
        value = content
    elif isinstance(content, dict):
        evidence_type = item.get("evidenceType")
        fields = {
            "menu": ("name",),
            "keyword": ("keyword",),
            "review": ("text",),
            "business_hours": ("description", "raw_text", "day_label"),
            "identity": ("restaurantName", "restaurantAddress"),
        }.get(evidence_type, ())
        values = [content.get(field) for field in fields]
        value = "\n".join(str(part) for part in values if isinstance(part, str) and part.strip())
    else:
        return None
    return value if isinstance(value, str) and value.strip() else None


def validate_claim(
    claim_data: dict[str, Any],
    evidence_by_id: dict[str, dict[str, Any]],
    *,
    expected_restaurant_id: int,
    duplicate: bool = False,
) -> dict[str, Any]:
    errors: list[str] = []
    try:
        claim = ClaimCandidate.model_validate(claim_data)
    except ValidationError as error:
        return {"valid": False, "quoteValid": False, "errors": [str(error)], "claim": None}

    if claim.restaurantId != expected_restaurant_id:
        errors.append("RESTAURANT_ID_MISMATCH")
    if claim.claimType not in ALLOWED_CLAIM_TYPES:
        errors.append("INVALID_CLAIM_TYPE")
    if not normalize_whitespace(claim.claimText):
        errors.append("EMPTY_CLAIM_TEXT")
    if len(claim.claimText) > MAX_CLAIM_LENGTH:
        errors.append("CLAIM_TOO_LONG")
    if duplicate:
        errors.append("DUPLICATE_CLAIM")
    if len(set(claim.evidenceIds)) != len(claim.evidenceIds):
        errors.append("DUPLICATE_EVIDENCE_ID")

    resolved: list[dict[str, Any]] = []
    integrity_errors: list[str] = []
    for evidence_id in claim.evidenceIds:
        item = evidence_by_id.get(evidence_id)
        if item is None:
            integrity_errors.append(f"EVIDENCE_NOT_FOUND:{evidence_id}")
            continue
        if item.get("restaurantId") != expected_restaurant_id:
            integrity_errors.append(f"EVIDENCE_RESTAURANT_MISMATCH:{evidence_id}")
        if not item.get("evidenceType"):
            integrity_errors.append(f"EVIDENCE_SOURCE_TYPE_MISSING:{evidence_id}")
        if item.get("status") != "SUCCESS":
            integrity_errors.append(f"EVIDENCE_NOT_SUCCESS:{evidence_id}")
        text = item.get("rawText")
        if not isinstance(text, str) or not text.strip():
            integrity_errors.append(f"EVIDENCE_RAW_TEXT_MISSING:{evidence_id}")
        resolved.append(item)

    quotes = [quote.model_dump(mode="json") for quote in claim.supportQuotes]
    quotes_by_id: dict[str, list[str]] = {}
    quote_errors: list[str] = []
    for quote in claim.supportQuotes:
        quotes_by_id.setdefault(quote.evidenceId, []).append(quote.quote)
        item = evidence_by_id.get(quote.evidenceId)
        raw_text = item.get("rawText") if item else None
        if quote.evidenceId not in claim.evidenceIds:
            quote_errors.append(f"QUOTE_EVIDENCE_NOT_CITED:{quote.evidenceId}")
        elif not isinstance(raw_text, str):
            quote_errors.append(f"QUOTE_SOURCE_UNRESOLVED:{quote.evidenceId}")
        elif normalize_whitespace(quote.quote) not in normalize_whitespace(raw_text):
            quote_errors.append(f"QUOTE_NOT_EXACT_SUBSTRING:{quote.evidenceId}")
    for evidence_id in claim.evidenceIds:
        if not quotes_by_id.get(evidence_id):
            quote_errors.append(f"SUPPORT_QUOTE_MISSING:{evidence_id}")
    errors.extend(integrity_errors)
    errors.extend(quote_errors)
    return {
        "valid": not errors,
        "evidenceIntegrityValid": not integrity_errors,
        "quoteValid": not quote_errors,
        "errors": errors,
        "claim": claim.model_dump(mode="json"),
        "supportQuotes": quotes,
        "resolvedEvidence": resolved,
    }


def normalize_claim_key(claim: ClaimCandidate) -> tuple[int, str, str]:
    text = normalize_whitespace(claim.claimText).casefold()
    return claim.restaurantId, claim.claimType, text


def verdict_is_indexable(deterministic: dict[str, Any], verdict: SemanticVerdict | None) -> bool:
    return bool(
        verdict is not None
        and deterministic.get("valid")
        and deterministic.get("quoteValid")
        and verdict.verdict == "SUPPORTED"
    )


def regression_is_blocked(verdict: str, expected_verdicts: list[str], indexable: bool) -> bool:
    return verdict in expected_verdicts and not indexable


def parse_verdict(raw: str | dict[str, Any], allowed_evidence_ids: set[str]) -> SemanticVerdict:
    try:
        payload = json.loads(raw) if isinstance(raw, str) else raw
        verdict = SemanticVerdict.model_validate(payload)
    except (json.JSONDecodeError, ValidationError, TypeError) as error:
        raise ValueError("INVALID_VERIFIER_OUTPUT") from error
    if not set(verdict.evidenceIds).issubset(allowed_evidence_ids):
        raise ValueError("VERIFIER_RETURNED_UNKNOWN_EVIDENCE")
    return verdict


def verifier_prompt(claim: ClaimCandidate, evidence: list[dict[str, Any]]) -> str:
    """Independent verifier input; excludes generator rationale and old status."""
    minimal_evidence = [
        {
            "evidenceId": item["evidenceId"],
            "sourceType": item["evidenceType"],
            "rawText": item["rawText"],
            "sourceData": item.get("rawEvidence"),
        }
        for item in evidence
    ]
    body = {
        "claimType": claim.claimType,
        "claimText": claim.claimText,
        "evidence": minimal_evidence,
    }
    return (
        "독립적인 근거 검증자다. claim의 의미상 사실 주장을 각각 확인한 뒤 판정하라. "
        "SUPPORTED는 모든 중요한 주장이 제공된 원문에서 직접 지지될 때만 사용한다. "
        "주장 일부만 지지되면 PARTIAL, 핵심이 지지되지 않으면 UNSUPPORTED다. "
        "유사하거나 그럴듯하다는 이유로 추론하지 말고 외부 지식을 사용하지 마라. "
        "메뉴 원문은 기재된 항목만 증명한다. 전문성·다양성·기재되지 않은 재료는 "
        "자동으로 증명되지 않는다. "
        "리뷰 keyword와 mentionCount는 고객이 해당 문구를 선택한 근거다. "
        "공식 메뉴나 다른 속성을 증명하지 않는다. "
        "단체 이용 근거만으로 가족행사·기업회식·넓은 공간·편안함을 추론하지 않는다. "
        "‘맛있다’는 근거만으로 식감, 육즙, 부드러움을 추론하지 않는다. "
        "FOOD_MENTION은 review keyword의 반복 언급만 나타내며 공식 판매 여부를 주장하지 않는다. "
        "supportedPortion과 unsupportedPortion은 짧게 쓰고, supplied evidenceIds만 반환한다. "
        "지정 JSON 이외의 텍스트를 반환하지 마라.\n" + json.dumps(body, ensure_ascii=False)
    )


def verifier_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "verdict": {"type": "string", "enum": sorted(VERDICTS)},
            "supportedPortion": {"type": "string"},
            "unsupportedPortion": {"type": "string"},
            "evidenceIds": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["verdict", "supportedPortion", "unsupportedPortion", "evidenceIds"],
    }


def atomicizer_schema(token_count: int) -> dict[str, Any]:
    if token_count < 1:
        raise ValueError("ATOMICIZER_EMPTY_CLAIM_TOKENS")
    allowed_indices = list(range(token_count))
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "assertions": {
                "type": "array",
                "minItems": 1,
                "maxItems": 8,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "text": {"type": "string", "minLength": 1},
                        "startToken": {"type": "integer", "enum": allowed_indices},
                        "endToken": {"type": "integer", "enum": allowed_indices},
                    },
                    "required": ["text", "startToken", "endToken"],
                },
            }
        },
        "required": ["assertions"],
    }


def assertion_verifier_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "verdict": {"type": "string", "enum": ["SUPPORTED", "UNSUPPORTED"]},
            "evidenceIds": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["verdict", "evidenceIds"],
    }


def _claim_tokens(claim_text: str) -> list[re.Match[str]]:
    return list(re.finditer(r"\S+", claim_text))


def parse_atomicization(raw: str | dict[str, Any], claim_text: str) -> Atomicization:
    if isinstance(raw, str) and not raw.strip():
        raise ValueError("ATOMICIZER_EMPTY_OUTPUT")
    try:
        payload = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError as error:
        raise ValueError("ATOMICIZER_INVALID_JSON") from error
    try:
        model_output = AtomicizerOutput.model_validate(payload)
    except (ValidationError, TypeError) as error:
        locations = []
        if isinstance(error, ValidationError):
            locations = [".".join(str(part) for part in item["loc"]) for item in error.errors()]
        if not isinstance(payload, dict):
            category = "ATOMICIZER_ROOT_SCHEMA_MISMATCH"
        elif "assertions" not in payload:
            category = "ATOMICIZER_ASSERTIONS_MISSING"
        elif isinstance(payload.get("assertions"), list) and not payload["assertions"]:
            category = "ATOMICIZER_ASSERTIONS_EMPTY"
        elif any(not isinstance(item, dict) for item in payload.get("assertions", [])):
            category = "ATOMICIZER_INVALID_FIELD_TYPE"
        elif len(payload.get("assertions", [])) > 8:
            category = "ATOMICIZER_INVALID_ASSERTION_COUNT"
        elif set(payload) - {"assertions"}:
            category = "ATOMICIZER_EXTRA_UNEXPECTED_STRUCTURE"
        elif any(
            set(item) - {"text", "startToken", "endToken"} for item in payload.get("assertions", [])
        ):
            category = "ATOMICIZER_EXTRA_UNEXPECTED_STRUCTURE"
        elif any(
            not {"text", "startToken", "endToken"}.issubset(item)
            for item in payload.get("assertions", [])
        ):
            category = "ATOMICIZER_ASSERTION_FIELD_MISSING"
        elif isinstance(error, ValidationError) and error.errors():
            category = "ATOMICIZER_INVALID_FIELD_TYPE"
        else:
            category = "ATOMICIZER_SCHEMA_ERROR"
        error_location = ",".join(locations) or "assertions"
        raise ValueError(f"{category}:location={error_location}") from error

    tokens = _claim_tokens(claim_text)
    seen_spans: set[tuple[int, int]] = set()
    assertions: list[AtomicAssertion] = []
    seen_text: set[str] = set()
    ordered_outputs = sorted(model_output.assertions, key=lambda item: item.startToken)
    for index, item in enumerate(ordered_outputs, start=1):
        span = item
        start_token = span.startToken
        end_token = span.endToken
        if start_token > end_token or end_token >= len(tokens):
            raise ValueError(f"ATOMICIZER_INVALID_TOKEN_RANGE:location=assertions.{index - 1}")
        if (start_token, end_token) in seen_spans:
            raise ValueError(f"ATOMICIZER_DUPLICATE_ASSERTION:location=assertions.{index - 1}")
        normalized_text = normalize_whitespace(item.text).casefold()
        if normalized_text in seen_text:
            raise ValueError(f"ATOMICIZER_DUPLICATE_ASSERTION:location=assertions.{index - 1}")
        seen_text.add(normalized_text)
        seen_spans.add((start_token, end_token))
        source_slice = claim_text[tokens[start_token].start() : tokens[end_token].end()]
        assertions.append(
            AtomicAssertion(assertionId=f"A{index}", text=item.text, sourceSpan=source_slice)
        )
    return Atomicization(assertions=assertions)


def parse_assertion_verdict(
    raw: str | dict[str, Any], allowed_evidence_ids: set[str]
) -> AssertionVerdict:
    if isinstance(raw, str) and not raw.strip():
        raise ValueError("ASSERTION_VERIFIER_EMPTY_OUTPUT")
    try:
        payload = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError as error:
        raise ValueError("ASSERTION_VERIFIER_INVALID_JSON") from error
    try:
        verdict = AssertionVerdict.model_validate(payload)
    except (ValidationError, TypeError) as error:
        raise ValueError("ASSERTION_VERIFIER_SCHEMA_ERROR") from error
    if not set(verdict.evidenceIds).issubset(allowed_evidence_ids):
        raise ValueError("ASSERTION_VERIFIER_UNKNOWN_EVIDENCE")
    if verdict.verdict == "SUPPORTED" and not verdict.evidenceIds:
        raise ValueError("ASSERTION_VERIFIER_SUPPORTED_WITHOUT_EVIDENCE")
    return verdict


def aggregate_assertion_verdicts(
    assertions: list[AtomicAssertion], verdicts: list[AssertionVerdict]
) -> Literal["SUPPORTED", "PARTIAL", "UNSUPPORTED"]:
    if not assertions or len(assertions) != len(verdicts):
        raise ValueError("ASSERTION_VERDICT_COUNT_MISMATCH")
    supported = sum(item.verdict == "SUPPORTED" for item in verdicts)
    if supported == len(verdicts):
        return "SUPPORTED"
    if supported == 0:
        return "UNSUPPORTED"
    return "PARTIAL"


def semantic_error_category(error: Exception) -> str:
    message = str(error)
    if isinstance(error, TimeoutError) or "timed out" in message.casefold():
        return "TIMEOUT"
    if "EMPTY_OUTPUT" in message:
        return "EMPTY_OUTPUT"
    if "INVALID_JSON" in message:
        return "INVALID_JSON"
    for category in (
        "ASSERTIONS_MISSING",
        "ASSERTIONS_EMPTY",
        "INVALID_FIELD_TYPE",
        "INVALID_ASSERTION_COUNT",
        "ROOT_SCHEMA_MISMATCH",
        "EXTRA_UNEXPECTED_STRUCTURE",
        "EMPTY_ASSERTION",
        "INVALID_TOKEN_RANGE",
        "ASSERTION_FIELD_MISSING",
        "DUPLICATE_OR_OVERLAPPING_SPAN",
        "UNSORTED_SPAN",
        "SOURCE_SPAN_NOT_IN_CLAIM",
        "DUPLICATE_ASSERTION",
    ):
        if category in message:
            return category
    if "SCHEMA_ERROR" in message:
        return "SCHEMA_ERROR"
    if type(error).__name__ == "LlmUnavailable":
        return "MODEL_ERROR"
    return "UNKNOWN_ERROR"


def atomicizer_prompt(claim: ClaimCandidate, *, correction: bool = False) -> str:
    tokens = _claim_tokens(claim.claimText)
    prompt = (
        "주어진 claim만 검토하여 검증 가능한 atomic fact로 분해하라. Evidence는 제공되지 않는다. "
        "각 assertion은 claim에 있는 사실 하나만 자연스러운 완결 문장으로 표현하고, "
        "그 사실을 직접 포함하는 가장 짧은 claimUnits 연속 범위의 "
        "startToken/endToken을 함께 반환하라. "
        "인덱스는 0부터 시작하고 양 끝을 포함한다. 새 사실·근거·설명을 추가하지 마라. "
        "서로 독립적인 절이나 쉼표로 나열된 사실은 각각 별도 범위로 분리하고, "
        "사실을 빠뜨리지 않고 범위를 원문 순서로 최대 8개 반환하라. "
        "공통 서술어를 나누는 데 필요하면 서로 다른 assertion의 원문 범위가 겹쳐도 된다. "
        'JSON은 {"assertions":[{"text":"단일 사실","startToken":0,"endToken":1}]} 형태만 반환하라. '
        "Assertion ID와 sourceSpan은 Python이 원문에서 생성한다. Evidence 판정을 하지 마라.\n"
        + json.dumps(
            {
                "claimType": claim.claimType,
                "validTokenIndices": list(range(len(tokens))),
                "claimUnits": [
                    {"index": index, "text": token.group(0)} for index, token in enumerate(tokens)
                ],
            },
            ensure_ascii=False,
        )
    )
    if correction:
        prompt += (
            "\nCorrection: previous output violated the generic atomic assertion/source span "
            "contract. "
            "Use only listed token indices, in ascending non-overlapping ranges; "
            "do not repeat or merge independent listed facts. Return only the required JSON."
        )
    return prompt


def assertion_verifier_prompt(
    claim_type: str, assertion: AtomicAssertion, evidence: list[dict[str, Any]]
) -> str:
    source = [
        {
            "evidenceId": item["evidenceId"],
            "sourceType": item["evidenceType"],
            "rawText": item["rawText"],
            "sourceData": item.get("rawEvidence"),
        }
        for item in evidence
    ]
    body = {"claimType": claim_type, "assertion": assertion.text, "evidence": source}
    return (
        "이 atomic assertion 하나만 검증하라. 결과는 SUPPORTED 또는 UNSUPPORTED뿐이다. "
        "제공된 Evidence가 assertion 전체를 직접 지지할 때만 SUPPORTED다. 상식, 일반적 식당 특성, "
        "인과 추론, 유사 의미의 구체화, 누락된 목적·상황·속성 추론은 금지한다. "
        "MENU는 기재된 메뉴 존재만 증명한다. REVIEW/keyword는 고객의 언급·평가만 증명하며 "
        "공식 판매를 증명하지 않는다. "
        "근거가 없거나 일부만 지지하면 UNSUPPORTED다. 해당 assertion을 지지하는 "
        "제공된 Evidence ID만 반환하고 JSON만 출력하라.\n" + json.dumps(body, ensure_ascii=False)
    )


class OllamaSemanticVerifier:
    """Single-claim verifier using the existing local profile model adapter."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def verify(self, claim: ClaimCandidate, evidence: list[dict[str, Any]]) -> SemanticVerdict:
        raw = self._client.complete(
            "/no_think\nYou are an independent evidence entailment verifier. Be conservative.",
            verifier_prompt(claim, evidence),
            verifier_schema(),
        )
        return parse_verdict(raw, set(claim.evidenceIds))


class OllamaAtomicClaimVerifier:
    """Two-stage V2 verifier: claim-only decomposition then per-assertion evidence checks."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def decompose(self, claim: ClaimCandidate, *, correction: bool = False) -> Atomicization:
        token_count = len(_claim_tokens(claim.claimText))
        raw = self._client.complete(
            "/no_think\nYou decompose claims into atomic assertions without judging them.",
            atomicizer_prompt(claim, correction=correction),
            atomicizer_schema(token_count),
        )
        return parse_atomicization(raw, claim.claimText)

    def verify_assertion(
        self, claim_type: str, assertion: AtomicAssertion, evidence: list[dict[str, Any]]
    ) -> AssertionVerdict:
        raw = self._client.complete(
            "/no_think\nYou are a conservative direct-evidence verifier.",
            assertion_verifier_prompt(claim_type, assertion, evidence),
            assertion_verifier_schema(),
        )
        return parse_assertion_verdict(raw, {item["evidenceId"] for item in evidence})
