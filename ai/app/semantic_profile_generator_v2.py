"""Offline Generator V2 contract and evidence-grounded validation helpers."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.semantic_profile_quality_gate import normalize_whitespace, raw_evidence_text

MAX_GENERATED_CLAIMS = 5
MAX_CLAIM_TEXT_LENGTH = 500
GENERATOR_CLAIM_TYPES = {
    "FOOD_TYPE",
    "FOOD_MENTION",
    "MENU_CHARACTERISTIC",
    "TASTE",
    "DINING_CONTEXT",
    "VENUE_CHARACTERISTIC",
}
CLAIM_SOURCE_TYPES = {
    "FOOD_TYPE": {"menu"},
    "FOOD_MENTION": {"keyword", "review"},
    "MENU_CHARACTERISTIC": {"menu"},
    "TASTE": {"keyword", "review"},
    "DINING_CONTEXT": {"keyword", "review"},
    "VENUE_CHARACTERISTIC": {"keyword", "review"},
}


class GeneratorSupportQuote(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    evidenceId: str = Field(min_length=1)
    quote: str = Field(min_length=1)


class GeneratorClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    claimType: Literal[
        "FOOD_TYPE",
        "FOOD_MENTION",
        "MENU_CHARACTERISTIC",
        "TASTE",
        "DINING_CONTEXT",
        "VENUE_CHARACTERISTIC",
    ]
    claimText: str = Field(min_length=1, max_length=MAX_CLAIM_TEXT_LENGTH)
    evidenceIds: list[str] = Field(min_length=1)
    supportQuotes: list[GeneratorSupportQuote] = Field(min_length=1)


class GeneratorOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    # The default V2 request schema still caps output at five; validation may
    # accept the V2.1 bounded cap of eight without widening that request.
    claims: list[GeneratorClaim] = Field(max_length=8)


def generator_schema(*, max_claims: int = MAX_GENERATED_CLAIMS) -> dict[str, Any]:
    quote = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "evidenceId": {"type": "string", "minLength": 1},
            "quote": {"type": "string", "minLength": 1},
        },
        "required": ["evidenceId", "quote"],
    }
    claim = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "claimType": {"type": "string", "enum": sorted(GENERATOR_CLAIM_TYPES)},
            "claimText": {"type": "string", "minLength": 1, "maxLength": MAX_CLAIM_TEXT_LENGTH},
            "evidenceIds": {"type": "array", "minItems": 1, "items": {"type": "string"}},
            "supportQuotes": {"type": "array", "minItems": 1, "items": quote},
        },
        "required": ["claimType", "claimText", "evidenceIds", "supportQuotes"],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {"claims": {"type": "array", "maxItems": max_claims, "items": claim}},
        "required": ["claims"],
    }


def generator_prompt(
    restaurant: dict[str, Any],
    evidence: list[dict[str, Any]],
    *,
    max_claims: int = MAX_GENERATED_CLAIMS,
    korean: bool = False,
    source_contract_v22: bool = False,
) -> str:
    if korean:
        instructions = (
            f"제공된 Evidence만 사용해 최대 {max_claims}개의 짧고 독립적인 의미 Claim을 "
            "생성하세요. "
            "claimText는 자연스럽고 검색에 쓸 수 있는 한국어 문장이어야 합니다. 메뉴명·브랜드명 등 "
            "고유명사는 원문을 유지할 수 있습니다. 한 Claim에는 검증 가능한 사실 하나만 담으세요. "
            "claimText에는 출처 라벨, Evidence ID, 인용문, 근거나 설명을 넣지 마세요. Evidence가 "
            "직접 뒷받침하는 유용한 이용 맥락·평가가 있으면 검토하되, "
            "source별 개수나 비율을 맞추기 위해 "
            "억지로 Claim을 만들지 마세요. 같은 메뉴 존재 사실만 반복해 개수를 채우지 말고, 근거가 "
            "불충분하면 생략하세요. 모든 evidenceId는 이 식당의 입력 목록에 있어야 하며 "
            "supportQuote는 해당 rawText의 실제 부분 문자열을 그대로 복사해야 합니다. "
            "quote를 번역·의역·정규화하거나 "
            "여러 문장을 조합하지 마세요. MENU는 메뉴 항목이 등록되어 있다는 사실만 보장합니다. "
            "REVIEW와 REVIEW_KEYWORD는 고객의 언급 또는 평가만 보장하며 "
            "공식 판매 사실을 보장하지 않습니다. "
            "리뷰 음식 언급을 공식 메뉴로 바꾸거나, 부재를 부정 증거로 해석하거나, "
            "상식으로 확장하지 마세요. "
            "ID, hash, 상태, confidence, rationale는 생성하지 말고 요구된 JSON만 반환하세요.\n"
        )
        if source_contract_v22:
            instructions += (
                "ClaimType은 다음 의미대로 고르세요: FOOD_TYPE은 MENU에 직접 표시된 음식 종류, "
                "FOOD_MENTION은 REVIEW_KEYWORD/REVIEW에서 고객이 음식명을 언급하거나 먹었다고 "
                "말한 사실, MENU_CHARACTERISTIC은 MENU의 공식 메뉴 항목/표시 특성, TASTE는 "
                "고객이 음식의 맛/품질을 명시적으로 평가한 경우, "
                "DINING_CONTEXT는 고객이 직접 표현한 식사 상황·시점·적합성·속도, "
                "VENUE_CHARACTERISTIC은 고객이 매장·서비스·환경을 평가한 경우입니다. "
                "음식 이름만 단독으로 나오면 FOOD_MENTION, 음식에 대한 명시적 평가면 TASTE, "
                "식사 상황·시점·적합성·속도면 DINING_CONTEXT, "
                "직원·서비스·매장 평가면 VENUE_CHARACTERISTIC을 선택하세요. "
                "REVIEW에 음식 언급과 평가가 함께 있으면 언급만으로 축소하지 말고 "
                "평가의 의미를 TASTE로 표현하세요. 한 Claim에 두 사실을 연결하지 마세요. "
                "원인과 결과가 함께 적힌 문장이라도 "
                "각각 독립적으로 확인 가능한 하나의 사실만 선택하세요. "
                "FOOD_TYPE과 MENU_CHARACTERISTIC은 MENU에서만 사용하세요. 나머지 REVIEW-derived "
                "Claim은 고객 언급/경험/평가임을 문장에 보존하세요. REVIEW_KEYWORD의 음식명은 "
                "‘고객 리뷰에서 [음식명]이 언급된다’처럼 FOOD_MENTION으로만 표현하고 판매한다고 "
                "말하지 마세요. REVIEW에서 먹었다는 음식 언급도 고객 리뷰에서 먹었다고 표현하고 "
                "공식 메뉴라고 하지 마세요. REVIEW_KEYWORD/REVIEW는 공식 메뉴, 시설, 정책, "
                "식당 분류를 증명하지 않습니다. Claim 문장에 식당 이름을 넣지 마세요; "
                "식당 정체성은 restaurantId metadata로 관리합니다. "
                "supportQuote는 rawText 하나에서 짧고 연속된 부분 하나를 그대로 복사하세요. "
                "서로 떨어진 구절을 연결하거나 순서를 바꾸지 마세요.\n"
            )
    else:
        instructions = (
            f"Generate up to {max_claims} short, independent semantic claims for this restaurant "
            "using only the supplied evidence. Each claim must express exactly one verifiable fact "
            "as a natural standalone sentence. Keep provenance outside claimText: claimText must "
            "contain no source "
            "labels, evidence IDs, quotes, rationale, or explanation. Every cited evidenceId must "
            "exist in this restaurant's catalog, and provide an exact substring copied from that "
            "evidence as its supportQuote; never paraphrase, translate, normalize, or compose "
            "quotes. MENU proves only that the named menu item is listed. "
            "REVIEW and REVIEW_KEYWORD prove only "
            "customer mention or evaluation, not official sale. Do not infer from absent evidence, "
            "or turn review food mentions into official menu claims. Omit claims that cannot be "
            "directly supported. Do not produce IDs, hashes, status, confidence, or rationale. "
            "Return "
            "only the required JSON object.\n"
        )
    return instructions + json.dumps(
        {"restaurant": restaurant, "evidence": evidence}, ensure_ascii=False
    )


_PROVENANCE_MARKERS = re.compile(r"(?:근거\s*:|evidence\s*:|source\s*:|\bE\d{2,}\b)", re.IGNORECASE)
_CLAIM_TYPE_PREFIX = re.compile(
    r"^(?:FOOD_TYPE|FOOD_MENTION|MENU_CHARACTERISTIC|TASTE|DINING_CONTEXT|VENUE_CHARACTERISTIC)\s*:",
    re.IGNORECASE,
)


def has_provenance_leak(claim_text: str) -> bool:
    return bool(
        _PROVENANCE_MARKERS.search(claim_text) or _CLAIM_TYPE_PREFIX.search(claim_text.strip())
    )


def atomicity_rejection(assertion_count: int) -> str | None:
    """A candidate is atomic only when V2.2 yields exactly one assertion."""
    return None if assertion_count == 1 else "GENERATOR_NON_ATOMIC"


def canonical_evidence(catalog: dict[str, Any], restaurant_id: int) -> dict[str, dict[str, Any]]:
    """Map catalog items to the V2.2 verifier evidence contract."""
    mapped: dict[str, dict[str, Any]] = {}
    for item in catalog.get("items", []):
        content = item.get("content")
        mapped[item["evidenceId"]] = {
            "restaurantId": item.get("restaurantId", restaurant_id),
            "evidenceId": item["evidenceId"],
            "evidenceType": item.get("evidenceType"),
            "status": item.get("status"),
            "rawText": raw_evidence_text(item),
            "rawEvidence": content,
            "sourceField": item.get("sourceField"),
        }
    return mapped


def validate_generator_output(
    raw: str | dict[str, Any],
    *,
    restaurant_id: int,
    catalog: dict[str, Any],
) -> dict[str, Any]:
    try:
        payload = json.loads(raw) if isinstance(raw, str) else raw
        output = GeneratorOutput.model_validate(payload)
    except (json.JSONDecodeError, ValidationError, TypeError) as error:
        return {
            "schemaValid": False,
            "errors": [{"code": "INVALID_SCHEMA", "detail": str(error)}],
            "claims": [],
        }

    evidence_by_id = canonical_evidence(catalog, restaurant_id)
    seen_claims: set[tuple[str, str]] = set()
    checked_claims: list[dict[str, Any]] = []
    for index, claim in enumerate(output.claims):
        errors: list[dict[str, str]] = []
        claim_text = claim.claimText.strip()
        key = (claim.claimType, normalize_whitespace(claim_text).casefold())
        if not claim_text:
            errors.append({"code": "EMPTY_CLAIM"})
        if has_provenance_leak(claim_text):
            errors.append({"code": "PROVENANCE_TEXT_IN_CLAIM"})
        if _english_dominant(claim_text):
            errors.append({"code": "CLAIM_NOT_KOREAN_DOMINANT"})
        if key in seen_claims:
            errors.append({"code": "DUPLICATE"})
        seen_claims.add(key)
        if len(set(claim.evidenceIds)) != len(claim.evidenceIds):
            errors.append({"code": "DUPLICATE_EVIDENCE_ID"})
        if not set(claim.evidenceIds).issubset(evidence_by_id):
            for evidence_id in sorted(set(claim.evidenceIds) - set(evidence_by_id)):
                errors.append({"code": "UNKNOWN_EVIDENCE", "evidenceId": evidence_id})

        quotes_by_id: dict[str, list[str]] = {}
        for quote in claim.supportQuotes:
            quotes_by_id.setdefault(quote.evidenceId, []).append(quote.quote)
            source = evidence_by_id.get(quote.evidenceId)
            if quote.evidenceId not in claim.evidenceIds:
                errors.append({"code": "QUOTE_EVIDENCE_MISMATCH", "evidenceId": quote.evidenceId})
            elif source is None or not isinstance(source.get("rawText"), str):
                errors.append({"code": "QUOTE_SOURCE_UNRESOLVED", "evidenceId": quote.evidenceId})
            elif normalize_whitespace(quote.quote) not in normalize_whitespace(source["rawText"]):
                errors.append({"code": "QUOTE_MISMATCH", "evidenceId": quote.evidenceId})

        resolved = [evidence_by_id[eid] for eid in claim.evidenceIds if eid in evidence_by_id]
        for evidence_id in claim.evidenceIds:
            source = evidence_by_id.get(evidence_id)
            if source is None:
                continue
            if source.get("restaurantId") != restaurant_id:
                errors.append({"code": "EVIDENCE_OWNER_MISMATCH", "evidenceId": evidence_id})
            if source.get("status") != "SUCCESS":
                errors.append({"code": "EVIDENCE_NOT_SUCCESS", "evidenceId": evidence_id})
            if source.get("evidenceType") not in CLAIM_SOURCE_TYPES[claim.claimType]:
                errors.append(
                    {"code": "EVIDENCE_SOURCE_TYPE_NOT_ALLOWED", "evidenceId": evidence_id}
                )
            if not quotes_by_id.get(evidence_id):
                errors.append({"code": "SUPPORT_QUOTE_MISSING", "evidenceId": evidence_id})

        claim_id = hashlib.sha256(
            f"{restaurant_id}\0{claim.claimType}\0{normalize_whitespace(claim_text)}\0{index}".encode()
        ).hexdigest()[:16]
        normalized_claim = {
            "restaurantId": restaurant_id,
            "claimId": f"{restaurant_id}:{claim.claimType}:{claim_id}",
            **claim.model_dump(mode="json"),
        }
        checked_claims.append(
            {
                "claim": normalized_claim,
                "valid": not errors,
                "errors": errors,
                "resolvedEvidence": resolved,
            }
        )
    return {"schemaValid": True, "errors": [], "claims": checked_claims}


_HANGUL = re.compile(r"[가-힣]")
_LATIN = re.compile(r"[A-Za-z]")


def _english_dominant(text: str) -> bool:
    """Reject English boilerplate while tolerating Latin-script names in Korean prose."""
    hangul_count = len(_HANGUL.findall(text))
    latin_count = len(_LATIN.findall(text))
    return hangul_count == 0 or (latin_count >= 12 and latin_count > hangul_count * 2)
