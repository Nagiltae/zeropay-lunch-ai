"""PCMap Place ID resolver를 실행하는 수동 CLI와 로컬 resume checkpoint."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from time import monotonic
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from app.batch.place_request_limiter import NavigationRateLimiter
from app.entity_resolution.qwen_candidate_matcher import (
    LlmUnavailable,
    OllamaClient,
    QwenCandidateMatcher,
    configured_qwen_model,
)
from app.naver.place_allsearch import parse_allsearch_candidates
from app.naver.place_resolver import (
    PlaceCandidate,
    Resolution,
    ResolutionStatus,
    RestaurantReference,
    candidate_evidence,
    normalize_text,
    query_for,
    rank_candidates,
    resolve_candidate,
)

BLOCK_MARKERS = (
    "captcha",
    "접근이 제한",
    "비정상적인 접근",
    "서비스 이용이 제한",
    "과도한 접근 요청",
    "robot",
)
CATEGORY_TERMS = ("한식", "일식", "중식", "양식", "분식", "음식점", "카페", "식당", "술집")
SEARCH_CANDIDATE_LIMIT = 20
QWEN_CANDIDATE_LIMIT = 12


@dataclass(frozen=True)
class DetailData:
    url: str
    name: str
    address: str
    category: str
    jibun_address: str = ""
    route_text: str = ""
    address_label_found: bool = False
    address_section_found: bool = False
    address_expand_button_found: bool = False
    address_expand_clicked: bool = False
    road_address_found: bool = False
    jibun_address_found: bool = False
    route_text_found: bool = False
    address_status: str = "NO_DATA"


@dataclass(frozen=True)
class CandidateValidationAttempt:
    rank: int
    candidate_name: str
    candidate_address: str
    place_id: str
    detail_url: str
    detail_name: str
    detail_road_address: str
    detail_jibun_address: str
    normalized_source_name: str
    normalized_detail_name: str
    name_comparison: str
    normalized_source_address: str
    normalized_detail_road_address: str
    normalized_detail_jibun_address: str
    address_comparison: str
    validation_result: str
    failure_reason: str
    semantic_decision: str = ""
    semantic_reason: str = ""
    fatal_veto: str = ""
    category: str = ""
    category_values: tuple[str, ...] = ()
    candidate_road_address: str = ""
    candidate_jibun_address: str = ""
    candidate_latitude: float | None = None
    candidate_longitude: float | None = None
    entity_match: str = ""
    business_type: str = ""
    location_scope: str = ""
    final_decision: str = ""
    semantic_error: str = ""
    processing_time_ms: int = 0


@dataclass(frozen=True)
class CandidateDom:
    candidate: PlaceCandidate
    locator: object | None
    index: int
    place_ids: tuple[str, ...]


@dataclass(frozen=True)
class RunResult:
    reference: RestaurantReference
    query: str
    query_stage: str
    candidates: tuple[CandidateDom, ...]
    selected_index: int | None
    matcher_source: str
    qwen_used: bool
    qwen_confidence: str
    qwen_candidate_indices: tuple[int, ...]
    candidate: PlaceCandidate | None
    candidate_href_url: str
    place_id: str | None
    place_id_source: str
    detail: DetailData | None
    resolution: Resolution
    elapsed_ms: int
    detail_validation_attempts: int
    original_candidate_count: int = 0
    filtered_candidate_count: int = 0
    candidate_rejection_reasons: tuple[str, ...] = ()
    validation_attempts_detail: tuple[CandidateValidationAttempt, ...] = ()


@dataclass(frozen=True)
class KomscoPopulation:
    references: tuple[RestaurantReference, ...]
    total_count: int


VERIFIED_CHECKPOINT_FIELDS = (
    "restaurant_id",
    "place_id",
    "resolved_name",
    "resolved_address",
    "verification_status",
    "verified_at",
)
DEFAULT_CHECKPOINT_NAME = "verified-place-ids-komsco-only.csv"


def load_verified_checkpoint(path: Path) -> dict[int, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as stream:
        return {
            int(row["restaurant_id"]): row
            for row in csv.DictReader(stream)
            if row.get("restaurant_id") and row.get("verification_status") == "RESOLVED"
        }


def save_verified_checkpoint(path: Path, result: RunResult) -> None:
    if result.resolution.status != ResolutionStatus.RESOLVED or not result.place_id:
        return
    existing = load_verified_checkpoint(path)
    existing[result.reference.restaurant_id] = {
        "restaurant_id": str(result.reference.restaurant_id),
        "place_id": result.place_id,
        "resolved_name": result.detail.name
        if result.detail
        else result.candidate.name
        if result.candidate
        else "",
        "resolved_address": result.detail.address
        if result.detail
        else result.candidate.address
        if result.candidate
        else "",
        "verification_status": "RESOLVED",
        "verified_at": datetime.now().isoformat(timespec="seconds"),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=VERIFIED_CHECKPOINT_FIELDS)
        writer.writeheader()
        writer.writerows(existing.values())
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def _float(value: str) -> float | None:
    try:
        return float(value) if value else None
    except ValueError:
        return None


def _round_robin_by_dong(rows: list[dict[str, object]], limit: int) -> list[dict[str, object]]:
    by_dong: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_dong.setdefault(str(row.get("legal_dong_name") or ""), []).append(row)
    dongs = sorted(by_dong)
    selected: list[dict[str, object]] = []
    index = 0
    while len(selected) < limit and dongs:
        added = False
        for dong in dongs:
            if index < len(by_dong[dong]):
                selected.append(by_dong[dong][index])
                added = True
                if len(selected) == limit:
                    break
        if not added:
            break
        index += 1
    return selected


def _mysql_rows(root: Path, sql: str) -> list[dict[str, object]]:
    command = _docker_mysql_command(sql)
    try:
        completed = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(f"KOMSCO target query failed: {error}") from error
    if completed.returncode != 0:
        raise RuntimeError("KOMSCO target query failed; verify local MySQL and .env")
    rows: list[dict[str, object]] = []
    for line in completed.stdout.splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _docker_mysql_command(sql: str) -> list[str]:
    script = (
        'MYSQL_PWD="$MYSQL_PASSWORD" mysql --batch --skip-column-names --raw '
        "--default-character-set=utf8mb4 "
        '-u "$MYSQL_USER" "$MYSQL_DATABASE" -e "$1"'
    )
    return [
        "docker",
        "compose",
        "exec",
        "-T",
        "mysql",
        "sh",
        "-c",
        script,
        "mysql-query",
        sql,
    ]


def load_komsco_population(root: Path, limit: int | None) -> KomscoPopulation:
    sql = """
SELECT JSON_OBJECT(
    'restaurant_id', r.id,
    'external_merchant_id', r.external_merchant_id,
    'name', r.name,
    'address', r.address,
    'detail_address', COALESCE(r.detail_address, ''),
    'latitude', r.latitude,
    'longitude', r.longitude,
    'legal_dong_name', COALESCE(r.legal_dong_name, ''),
    'industry_name', COALESCE(r.industry_name, '')
)
FROM restaurants r
WHERE r.source_provider = 'KOMSCO'
  AND r.active = TRUE
  AND r.zero_pay_available = TRUE
  AND r.industry_code = '561'
  AND r.business_status_name = '계속사업자'
  AND r.legal_dong_code = '11680108'
  AND NULLIF(TRIM(r.name), '') IS NOT NULL
  AND NULLIF(TRIM(r.address), '') IS NOT NULL
ORDER BY r.legal_dong_name, r.id
"""
    rows = _mysql_rows(root, sql)
    # KOMSCO is the sole population source; external-place rows are not joined.
    matched = []
    unmatched = rows
    if limit is None:
        selected = rows
    elif matched and unmatched and limit >= 2:
        matched_limit = limit // 2
        unmatched_limit = limit - matched_limit
        first = _round_robin_by_dong(matched, matched_limit)
        second = _round_robin_by_dong(unmatched, unmatched_limit)
        selected = [item for pair in zip(first, second, strict=False) for item in pair]
        selected.extend(first[len(second) :])
        selected.extend(second[len(first) :])
        selected_ids = {int(row["restaurant_id"]) for row in selected}
        remaining = [row for row in rows if int(row["restaurant_id"]) not in selected_ids]
        selected.extend(_round_robin_by_dong(remaining, limit - len(selected)))
    else:
        selected = _round_robin_by_dong(rows, limit)
    references = tuple(
        RestaurantReference(
            restaurant_id=int(row["restaurant_id"]),
            komsco_name=str(row.get("name") or ""),
            komsco_address=" ".join(
                part
                for part in (
                    str(row.get("address") or ""),
                    str(row.get("detail_address") or ""),
                )
                if part
            ),
            komsco_latitude=_float(str(row.get("latitude") or "")),
            komsco_longitude=_float(str(row.get("longitude") or "")),
            legal_dong=str(row.get("legal_dong_name") or ""),
            external_merchant_id=str(row.get("external_merchant_id") or "") or None,
        )
        for row in selected
    )
    return KomscoPopulation(
        references,
        len(rows),
    )


def _check_block(page, response) -> None:
    if response is not None and response.status in {403, 429}:
        raise RuntimeError(f"BLOCKED: HTTP {response.status}")
    body = (page.locator("body").inner_text(timeout=3_000) or "").lower()
    if any(marker in body or marker in page.url.lower() for marker in BLOCK_MARKERS):
        raise RuntimeError("BLOCKED: CAPTCHA/접근 제한/HTTP 차단 징후 감지")


def parse_semantic_address_row(label_text: str, row_text: str) -> str:
    """Extract only a semantic 주소 row; never treat route guidance as an address."""
    if normalize_text(label_text) != "주소":
        return ""
    value = re.sub(r"^\s*주소\s*", "", row_text.strip(), count=1)
    if not value or re.search(r"(?:역|출구).*(?:에서|도보)\s*\d+", value):
        return ""
    return value


def parse_address_value_row(label_text: str, row_text: str) -> str:
    """Read one semantic 도로명/지번 row and remove only semantic UI labels."""
    if label_text not in {"도로명", "지번"}:
        return ""
    value = row_text.replace(label_text, "", 1)
    value = value.replace("복사", "").strip()
    return value


def parse_route_value_row(label_text: str, row_text: str) -> str:
    if label_text != "찾아가는길":
        return ""
    return row_text.replace(label_text, "", 1).strip()


def _semantic_address_from_page(page) -> str:
    selectors = (
        "span.place_blind",
        '[aria-label="주소"]',
    )
    for selector in selectors:
        labels = page.locator(selector)
        for index in range(labels.count()):
            label = labels.nth(index)
            try:
                label_text = (
                    label.inner_text(timeout=1000) or label.get_attribute("aria-label") or ""
                )
                for relation in ("xpath=..", "xpath=../..", "xpath=../../.."):
                    row_text = label.locator(relation).inner_text(timeout=1000)
                    value = parse_semantic_address_row(label_text, row_text)
                    if value and any(
                        token in value for token in ("서울", "구", "로", "길", "대로", "동")
                    ):
                        return value
            except Exception:
                continue
    # Text-semantic fallback: find an exact 주소 node, but still read only its row.
    labels = page.get_by_text("주소", exact=True)
    for index in range(labels.count()):
        label = labels.nth(index)
        try:
            for relation in ("xpath=..", "xpath=../..", "xpath=../../.."):
                value = parse_semantic_address_row(
                    "주소", label.locator(relation).inner_text(timeout=1000)
                )
                if value and any(
                    token in value for token in ("서울", "구", "로", "길", "대로", "동")
                ):
                    return value
        except Exception:
            continue
    return ""


def _address_data_from_page(page) -> dict[str, object]:
    """Extract the observed PCMap address section without generic body searching."""
    labels = page.locator("span.place_blind")
    address_label = None
    route_label = None
    for index in range(labels.count()):
        label = labels.nth(index)
        text = (label.inner_text(timeout=1000) or "").strip()
        if text == "주소":
            address_label = label
        elif text == "찾아가는길":
            route_label = label
    if address_label is None:
        return {"status": "NO_DATA", "label_found": False}
    section = address_label.locator("xpath=../..")
    if not section.count():
        return {"status": "PARSE_FAILED", "label_found": True, "section_found": False}
    expand = section.locator('a[role="button"][aria-haspopup="true"]')
    expand_found = bool(expand.count())
    clicked = False
    if expand_found and expand.first.get_attribute("aria-expanded") != "true":
        expand.first.scroll_into_view_if_needed()
        expand.first.click()
        clicked = True

    # Expanding the address inserts new semantic spans, so reacquire the route
    # label instead of retaining an index-based locator from the old DOM.
    route_label = None
    refreshed_labels = page.locator("span.place_blind")
    for index in range(refreshed_labels.count()):
        if (refreshed_labels.nth(index).inner_text(timeout=1000) or "").strip() == "찾아가는길":
            route_label = refreshed_labels.nth(index)
            break

    road = ""
    jibun = ""
    for semantic_label in ("도로명", "지번"):
        value_labels = section.get_by_text(semantic_label, exact=True)
        if value_labels.count():
            row = value_labels.first.locator("xpath=..")
            value = parse_address_value_row(semantic_label, row.inner_text(timeout=1500))
            if semantic_label == "도로명":
                road = value
            else:
                jibun = value
    if not road and expand_found:
        road = parse_address_value_row("도로명", expand.first.inner_text(timeout=1500))
    route = ""
    if route_label is not None:
        route_section = route_label.locator("xpath=../..")
        route = parse_route_value_row("찾아가는길", route_section.inner_text(timeout=1500))
    status = "SUCCESS" if road or jibun else "PARSE_FAILED"
    return {
        "status": status,
        "label_found": True,
        "section_found": True,
        "expand_found": expand_found,
        "clicked": clicked,
        "road": road,
        "jibun": jibun,
        "route": route,
        "road_found": bool(road),
        "jibun_found": bool(jibun),
        "route_found": bool(route),
    }


def _search_ui_response(page, query: str, *, before_navigation=None):
    """Search through the visible Map UI and return its own allSearch response.

    The resolver never constructs or replays the allSearch request.  The response
    is captured only while the page performs the UI search in a normal browser
    session.
    """
    if before_navigation:
        before_navigation()
    page.goto("https://map.naver.com/", wait_until="domcontentloaded", timeout=15_000)
    _check_block(page, None)
    search_input = None
    inputs = page.locator("input.input_search")
    for index in range(inputs.count()):
        candidate = inputs.nth(index)
        if candidate.is_visible():
            search_input = candidate
            break
    if search_input is None:
        raise RuntimeError("ALLSEARCH_RESPONSE_FAILED: visible NAVER search input not found")

    def is_matching_response(response) -> bool:
        if "/api/search/allSearch" not in response.url:
            return False
        request = getattr(response, "request", None)
        if request is not None and getattr(request, "method", "GET") != "GET":
            return False
        observed_query = parse_qs(urlparse(response.url).query).get("query", [""])[0]
        return observed_query == query

    try:
        with page.expect_response(is_matching_response, timeout=15_000) as response_info:
            search_input.fill(query)
            search_input.press("Enter")
        response = response_info.value
        if response.status in {403, 429}:
            raise RuntimeError(f"BLOCKED: HTTP {response.status}")
        payload = response.json()
        result = payload.get("result") if isinstance(payload, dict) else None
        if isinstance(result, dict) and result.get("ncaptcha"):
            raise RuntimeError("BLOCKED: allSearch CAPTCHA 응답")
        response_text = json.dumps(payload, ensure_ascii=False).lower()
        if any(marker in response_text for marker in BLOCK_MARKERS):
            raise RuntimeError("BLOCKED: CAPTCHA/접근 제한/HTTP 차단 징후 감지")
        return response, payload
    except PlaywrightTimeoutError:
        raise RuntimeError(
            "ALLSEARCH_RESPONSE_FAILED: UI allSearch response not observed"
        ) from None
    except RuntimeError:
        raise
    except Exception as error:
        raise RuntimeError(f"ALLSEARCH_RESPONSE_FAILED: {error}") from error


def search_direct(
    page, query: str, reference: RestaurantReference, *, before_navigation=None
) -> tuple[tuple[CandidateDom, ...], int]:
    _response, payload = _search_ui_response(page, query, before_navigation=before_navigation)
    structured = parse_allsearch_candidates(payload)
    candidates = tuple(
        CandidateDom(candidate, None, index, (candidate.place_id,) if candidate.place_id else ())
        for index, candidate in enumerate(structured[:SEARCH_CANDIDATE_LIMIT])
    )
    return candidates, len(structured)


def load_detail_page(page, candidate: PlaceCandidate, *, before_navigation=None) -> DetailData:
    if candidate.place_id is None:
        return DetailData("", "", "", "", "")
    url = f"https://pcmap.place.naver.com/restaurant/{candidate.place_id}/home"
    if before_navigation:
        before_navigation()
    response = page.goto(url, wait_until="commit", timeout=10_000)
    _check_block(page, response)
    page.locator("body").wait_for(state="attached", timeout=5_000)
    lines = [
        line.strip()
        for line in (page.locator("body").inner_text(timeout=3_000) or "").splitlines()
        if line.strip()
    ]
    name = next(
        (line for line in lines if normalize_text(candidate.name) in normalize_text(line)),
        candidate.name,
    )
    address_data = _address_data_from_page(page)
    address = str(address_data.get("road") or "")
    jibun_address = str(address_data.get("jibun") or "")
    category = next((line for line in lines if ">" in line or line.endswith(CATEGORY_TERMS)), "")
    return DetailData(
        page.url,
        name,
        address,
        category,
        jibun_address,
        str(address_data.get("route") or ""),
        bool(address_data.get("label_found")),
        bool(address_data.get("section_found")),
        bool(address_data.get("expand_found")),
        bool(address_data.get("clicked")),
        bool(address_data.get("road_found")),
        bool(address_data.get("jibun_found")),
        bool(address_data.get("route_found")),
        str(address_data.get("status") or "NO_DATA"),
    )


def _empty_result(reference, query, stage, candidates, status, flags, started, **kwargs):
    resolution = Resolution(
        reference, query, kwargs.get("candidate"), status, "UNKNOWN", "UNKNOWN", "UNKNOWN", flags
    )
    return RunResult(
        reference,
        query,
        stage,
        candidates,
        kwargs.get("selected_index"),
        kwargs.get("matcher_source", "NONE"),
        kwargs.get("qwen_used", False),
        kwargs.get("qwen_confidence", ""),
        kwargs.get("qwen_candidate_indices", ()),
        kwargs.get("candidate"),
        kwargs.get("candidate_href_url", ""),
        kwargs.get("place_id"),
        kwargs.get("place_id_source", ""),
        kwargs.get("detail"),
        resolution,
        int((monotonic() - started) * 1000),
        kwargs.get("detail_validation_attempts", 0),
        kwargs.get("original_candidate_count", len(candidates)),
        kwargs.get("filtered_candidate_count", len(candidates)),
        validation_attempts_detail=kwargs.get("validation_attempts_detail", ()),
    )


def _validation_failure_reason(
    resolution: Resolution, detail: DetailData, name_result: str, address_result: str
) -> str:
    if not detail.name:
        return "DETAIL_NAME_MISSING"
    if not detail.address:
        return "DETAIL_ADDRESS_MISSING"
    if not any(token in detail.address for token in ("서울", "구", "로", "길", "대로", "동")):
        return "DETAIL_ADDRESS_PARSE_SUSPECT"
    if name_result == "DIFFERENT" and address_result == "DIFFERENT":
        return "NAME_AND_ADDRESS_MISMATCH"
    if name_result == "DIFFERENT":
        return "NAME_MISMATCH"
    if address_result == "DIFFERENT":
        return "ADDRESS_MISMATCH"
    if "SMALL_SCORE_GAP" in resolution.risk_flags:
        return "SMALL_SCORE_GAP"
    return "DETAIL_EVIDENCE_INSUFFICIENT"


def run_one(
    page, reference, query, stage, matcher: QwenCandidateMatcher | None, *, before_navigation=None
) -> RunResult:
    started = monotonic()
    raw_candidates, original_candidate_count = search_direct(
        page, query, reference, before_navigation=before_navigation
    )
    # allSearch already returns structured place objects.  Candidate identity,
    # category, address and coordinates are semantic evidence for Qwen; no
    # name/address/category business rule runs before ranking.
    rejection_reasons = tuple(
        "CANDIDATE_PLACE_ID_MISSING" if not item.candidate.place_id else ""
        for item in raw_candidates
    )
    candidates = tuple(item for item in raw_candidates if item.candidate.place_id)
    if not candidates:
        reason = (
            "NO_SEARCH_RESULT"
            if original_candidate_count == 0
            else (
                "NON_FOOD"
                if "NON_FOOD_CATEGORY" in rejection_reasons
                else "PLACE_ID_MISSING"
                if "CANDIDATE_PLACE_ID_MISSING" in rejection_reasons
                else "NO_MATCH"
            )
        )
        return _empty_result(
            reference,
            query,
            stage,
            raw_candidates,
            ResolutionStatus.NOT_FOUND,
            (reason,),
            started,
            original_candidate_count=original_candidate_count,
            filtered_candidate_count=0,
        )
    # Evidence ordering is deterministic; Qwen sees a bounded soft-ranked pool.
    ordered = rank_candidates(reference, [item.candidate for item in candidates])
    remaining = list(candidates)
    ordered_dom: list[CandidateDom] = []
    for candidate in ordered:
        match_index = next(
            (index for index, item in enumerate(remaining) if item.candidate == candidate),
            None,
        )
        if match_index is not None:
            ordered_dom.append(remaining.pop(match_index))
    candidates = tuple(ordered_dom[:QWEN_CANDIDATE_LIMIT])
    plain = [item.candidate for item in candidates]
    selected_index = None
    ranked_indices: tuple[int, ...] = ()
    matcher_source = "DETERMINISTIC"
    qwen_used = False
    qwen_confidence = ""
    if candidates and matcher is not None:
        qwen_used = True
        matcher_source = "QWEN"
        try:
            decision = matcher.choose(reference, plain)
            qwen_confidence = decision.confidence
            ranked_indices = decision.candidate_indices
            selected_index = ranked_indices[0]
        except (LlmUnavailable, ValueError) as error:
            return _empty_result(
                reference,
                query,
                stage,
                candidates,
                ResolutionStatus.ERROR,
                ("QWEN_FAILURE", str(error)),
                started,
                matcher_source=matcher_source,
                qwen_used=True,
                qwen_candidate_indices=ranked_indices,
                original_candidate_count=original_candidate_count,
                filtered_candidate_count=len(candidates),
            )
    if selected_index is None or selected_index >= len(candidates):
        status = ResolutionStatus.AMBIGUOUS if candidates else ResolutionStatus.NOT_FOUND
        return _empty_result(
            reference,
            query,
            stage,
            candidates,
            status,
            ("NO_CONFIDENT_CANDIDATE",),
            started,
            matcher_source=matcher_source,
            qwen_used=qwen_used,
            qwen_confidence=qwen_confidence,
            qwen_candidate_indices=ranked_indices,
            original_candidate_count=original_candidate_count,
            filtered_candidate_count=len(candidates),
        )
    attempts = 0
    last_candidate = None
    last_detail = None
    last_resolution = None
    validation_attempts_detail: list[CandidateValidationAttempt] = []
    for candidate_index in ranked_indices[:5]:
        selected = candidates[candidate_index]
        if len(selected.place_ids) != 1:
            continue
        attempts += 1
        candidate = replace(selected.candidate, place_id=selected.place_ids[0])
        try:
            detail = load_detail_page(page, candidate, before_navigation=before_navigation)
        except PlaywrightTimeoutError:
            # A single missing/slow DOM node is a candidate-level validation
            # failure, not a batch-wide failure.  Keep the candidate in the
            # audit trail and continue with the next ranked candidate.
            detail = DetailData(
                getattr(page, "url", ""),
                candidate.name,
                "",
                candidate.category,
                address_status="PARSE_FAILED",
            )
            validation_attempts_detail.append(
                CandidateValidationAttempt(
                    rank=len(validation_attempts_detail) + 1,
                    candidate_name=selected.candidate.name,
                    candidate_address=selected.candidate.address,
                    place_id=candidate.place_id or "",
                    detail_url=getattr(page, "url", ""),
                    detail_name=candidate.name,
                    detail_road_address="",
                    detail_jibun_address="",
                    normalized_source_name=normalize_text(reference.komsco_name),
                    normalized_detail_name=normalize_text(candidate.name),
                    name_comparison="UNKNOWN",
                    normalized_source_address=normalize_text(reference.komsco_address),
                    normalized_detail_road_address="",
                    normalized_detail_jibun_address="",
                    address_comparison="UNKNOWN",
                    validation_result=ResolutionStatus.AMBIGUOUS.value,
                    failure_reason="LOCATOR_TIMEOUT",
                )
            )
            last_candidate, last_detail = candidate, detail
            continue
        verified = replace(
            candidate,
            name=detail.name or candidate.name,
            address=detail.address or candidate.address,
            category=detail.category or candidate.category,
            url=detail.url or candidate.url,
            road_address=detail.address or candidate.road_address,
            jibun_address=detail.jibun_address or candidate.jibun_address,
        )
        name_result, address_result, _, _ = candidate_evidence(reference, verified)
        semantic_decision = ""
        semantic_reason = ""
        entity_match = ""
        business_type = ""
        location_scope = ""
        final_decision = ""
        semantic_error = ""
        attempt_started = monotonic()
        semantic_validator = getattr(matcher, "validate", None) if matcher is not None else None
        if callable(semantic_validator):
            try:
                semantic = semantic_validator(reference, verified)
                entity_match = getattr(semantic, "entity_match", getattr(semantic, "decision", ""))
                semantic_decision = entity_match
                business_type = getattr(semantic, "business_type", "UNKNOWN")
                location_scope = getattr(semantic, "location_scope", "UNKNOWN")
                final_decision = getattr(
                    semantic,
                    "final_decision",
                    {"MATCH": "ACCEPT", "NO_MATCH": "REJECT", "UNCERTAIN": "UNCERTAIN"}.get(
                        entity_match, "UNCERTAIN"
                    ),
                )
                semantic_reason = getattr(semantic, "reason", "")
            except (LlmUnavailable, ValueError) as error:
                semantic_error = str(error)
                validation_attempts_detail.append(
                    CandidateValidationAttempt(
                        rank=len(validation_attempts_detail) + 1,
                        candidate_name=selected.candidate.name,
                        candidate_address=selected.candidate.address,
                        place_id=verified.place_id or "",
                        detail_url=detail.url,
                        detail_name=detail.name,
                        detail_road_address=detail.address,
                        detail_jibun_address=detail.jibun_address,
                        normalized_source_name=normalize_text(reference.komsco_name),
                        normalized_detail_name=normalize_text(detail.name),
                        name_comparison=name_result,
                        normalized_source_address=normalize_text(reference.komsco_address),
                        normalized_detail_road_address=normalize_text(detail.address),
                        normalized_detail_jibun_address=normalize_text(detail.jibun_address),
                        address_comparison=address_result,
                        validation_result=ResolutionStatus.ERROR.value,
                        failure_reason="QWEN_SEMANTIC_FAILURE",
                        category=verified.category,
                        category_values=verified.category_values,
                        candidate_road_address=verified.road_address,
                        candidate_jibun_address=verified.jibun_address,
                        candidate_latitude=verified.latitude,
                        candidate_longitude=verified.longitude,
                        semantic_error=semantic_error,
                        processing_time_ms=int((monotonic() - attempt_started) * 1000),
                    )
                )
                return _empty_result(
                    reference,
                    query,
                    stage,
                    candidates,
                    ResolutionStatus.ERROR,
                    ("QWEN_SEMANTIC_FAILURE", str(error)),
                    started,
                    matcher_source=matcher_source,
                    qwen_used=True,
                    qwen_confidence=qwen_confidence,
                    qwen_candidate_indices=ranked_indices,
                    candidate=verified,
                    place_id=verified.place_id,
                    detail=detail,
                    detail_validation_attempts=attempts,
                    original_candidate_count=original_candidate_count,
                    filtered_candidate_count=len(candidates),
                    validation_attempts_detail=tuple(validation_attempts_detail),
                )
            if final_decision == "ACCEPT":
                resolution = Resolution(
                    reference,
                    query,
                    verified,
                    ResolutionStatus.RESOLVED,
                    name_result,
                    address_result,
                    candidate_evidence(reference, verified)[2],
                    (),
                )
            else:
                resolution = Resolution(
                    reference,
                    query,
                    verified,
                    ResolutionStatus.AMBIGUOUS,
                    name_result,
                    address_result,
                    candidate_evidence(reference, verified)[2],
                    (f"QWEN_{semantic_decision}",),
                )
        else:
            # Test/dry adapters may omit semantic validation; production
            # always supplies QwenCandidateMatcher.validate.
            resolution = replace(resolve_candidate(reference, [verified]), query=query)
        last_candidate, last_detail, last_resolution = verified, detail, resolution
        source_name = reference.komsco_name
        source_address = reference.komsco_address
        validation_attempts_detail.append(
            CandidateValidationAttempt(
                rank=len(validation_attempts_detail) + 1,
                candidate_name=selected.candidate.name,
                candidate_address=selected.candidate.address,
                place_id=verified.place_id or "",
                detail_url=detail.url,
                detail_name=detail.name,
                detail_road_address=detail.address,
                detail_jibun_address=detail.jibun_address,
                normalized_source_name=normalize_text(source_name),
                normalized_detail_name=normalize_text(detail.name),
                name_comparison=name_result,
                normalized_source_address=normalize_text(source_address),
                normalized_detail_road_address=normalize_text(detail.address),
                normalized_detail_jibun_address=normalize_text(detail.jibun_address),
                address_comparison=address_result,
                validation_result=resolution.status.value,
                failure_reason=(
                    "NON_FOOD"
                    if final_decision == "REJECT" and business_type == "NON_FOOD"
                    else "OUT_OF_SCOPE"
                    if final_decision == "REJECT" and location_scope == "OUT_OF_SCOPE"
                    else "QWEN_NO_MATCH"
                    if final_decision == "REJECT"
                    else "QWEN_UNCERTAIN"
                    if final_decision == "UNCERTAIN"
                    else "QWEN_MATCH"
                    if semantic_decision and resolution.status != ResolutionStatus.RESOLVED
                    else _validation_failure_reason(resolution, detail, name_result, address_result)
                ),
                semantic_decision=semantic_decision,
                semantic_reason=semantic_reason,
                fatal_veto="",
                category=verified.category,
                category_values=verified.category_values,
                candidate_road_address=verified.road_address,
                candidate_jibun_address=verified.jibun_address,
                candidate_latitude=verified.latitude,
                candidate_longitude=verified.longitude,
                entity_match=entity_match,
                business_type=business_type,
                location_scope=location_scope,
                final_decision=final_decision,
                semantic_error=semantic_error,
                processing_time_ms=int((monotonic() - attempt_started) * 1000),
            )
        )
        if resolution.status == ResolutionStatus.RESOLVED:
            return RunResult(
                reference,
                query,
                stage,
                candidates,
                candidate_index,
                matcher_source,
                qwen_used,
                qwen_confidence,
                ranked_indices,
                verified,
                selected.candidate.url,
                verified.place_id,
                "DOM_DATA_NLOG",
                detail,
                resolution,
                int((monotonic() - started) * 1000),
                attempts,
                original_candidate_count,
                len(candidates),
                validation_attempts_detail=tuple(validation_attempts_detail),
            )
    if attempts == 0:
        status = ResolutionStatus.NOT_FOUND
        flags = ("PLACE_ID_MISSING",)
    else:
        final_decisions = {
            attempt.final_decision
            for attempt in validation_attempts_detail
            if attempt.final_decision
        }
        if final_decisions and final_decisions <= {"REJECT"}:
            # Existing public enum uses NOT_FOUND for a definitive rejected
            # match; the reason flag preserves the semantic distinction from
            # an empty search result.
            status = ResolutionStatus.NOT_FOUND
            flags = ("NO_MATCH",)
        elif "UNCERTAIN" in final_decisions:
            status = ResolutionStatus.AMBIGUOUS
            flags = ("SEMANTIC_UNCERTAIN",)
        elif any(
            attempt.failure_reason == "LOCATOR_TIMEOUT" for attempt in validation_attempts_detail
        ):
            status = ResolutionStatus.AMBIGUOUS
            flags = ("DETAIL_LOAD_FAILED",)
        else:
            status = ResolutionStatus.AMBIGUOUS
            flags = ("TOP_K_DETAIL_VALIDATION_FAILED",)
    resolution = replace(
        last_resolution
        or Resolution(
            reference, query, last_candidate, status, "UNKNOWN", "UNKNOWN", "UNKNOWN", flags
        ),
        status=status,
        risk_flags=flags,
    )
    return RunResult(
        reference,
        query,
        stage,
        candidates,
        selected_index,
        matcher_source,
        qwen_used,
        qwen_confidence,
        ranked_indices,
        last_candidate,
        last_candidate.url if last_candidate else "",
        last_candidate.place_id if last_candidate else None,
        "DOM_DATA_NLOG" if last_candidate else "",
        last_detail,
        resolution,
        int((monotonic() - started) * 1000),
        attempts,
        original_candidate_count,
        len(candidates),
        tuple(reason for reason in rejection_reasons if reason),
        tuple(validation_attempts_detail),
    )


REPORT_FIELDS = [
    "source_type",
    "restaurant_id",
    "reference_name",
    "query",
    "query_stage",
    "final_status",
    "original_candidate_count",
    "filtered_candidate_count",
    "matcher_source",
    "qwen_ranking",
    "selected_candidate_index",
    "selected_candidate_name",
    "qwen_used",
    "qwen_confidence",
    "candidate_url",
    "place_id",
    "place_id_source",
    "resolved_rank",
    "detail_validation",
    "detail_name",
    "detail_address",
    "detail_category",
    "name_evidence",
    "address_evidence",
    "reason",
    "risk_flags",
    "elapsed_ms",
    "detail_validation_attempts",
    "candidate_rejection_reasons",
    "validation_attempts_json",
]


def result_row(
    result: RunResult,
) -> dict[str, object]:
    status = result.resolution.status.value
    ranking = list(result.qwen_candidate_indices)
    resolved_rank = (
        ranking.index(result.selected_index) + 1
        if status == "RESOLVED" and result.selected_index in ranking
        else ""
    )
    return {
        "source_type": "KOMSCO_ONLY",
        "restaurant_id": result.reference.restaurant_id,
        "reference_name": result.reference.komsco_name,
        "query": result.query,
        "query_stage": result.query_stage,
        "final_status": status,
        "original_candidate_count": result.original_candidate_count,
        "filtered_candidate_count": result.filtered_candidate_count,
        "matcher_source": result.matcher_source,
        "qwen_ranking": ",".join(str(index) for index in ranking),
        "selected_candidate_index": (
            result.selected_index if result.selected_index is not None else ""
        ),
        "selected_candidate_name": result.candidate.name if result.candidate else "",
        "qwen_used": result.qwen_used,
        "qwen_confidence": result.qwen_confidence,
        "candidate_url": result.candidate_href_url,
        "place_id": result.place_id or "",
        "place_id_source": result.place_id_source,
        "resolved_rank": resolved_rank,
        "detail_validation": (
            "PASS"
            if status == "RESOLVED"
            else "NOT_ATTEMPTED"
            if result.detail_validation_attempts == 0
            else "FAIL"
        ),
        "detail_name": result.detail.name if result.detail else "",
        "detail_address": result.detail.address if result.detail else "",
        "detail_category": result.detail.category if result.detail else "",
        "name_evidence": result.resolution.name_evidence,
        "address_evidence": result.resolution.address_evidence,
        "reason": ";".join(result.resolution.risk_flags),
        "risk_flags": ";".join(result.resolution.risk_flags),
        "elapsed_ms": result.elapsed_ms,
        "detail_validation_attempts": result.detail_validation_attempts,
        "candidate_rejection_reasons": ";".join(result.candidate_rejection_reasons),
        "validation_attempts_json": json.dumps(
            [attempt.__dict__ for attempt in result.validation_attempts_detail],
            ensure_ascii=False,
        ),
    }


class ReportWriter:
    """Append-and-fsync writer; the CSV is the resume checkpoint and audit output."""

    def __init__(self, path: Path, resume: bool) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.stream = (
            path.open("a", newline="", encoding="utf-8")
            if resume
            else path.open("w", newline="", encoding="utf-8")
        )
        self.writer = csv.DictWriter(self.stream, fieldnames=REPORT_FIELDS)
        if not resume or path.stat().st_size == 0:
            self.writer.writeheader()
            self.stream.flush()
            os.fsync(self.stream.fileno())

    def completed_ids(self) -> set[int]:
        if not self.path.exists() or self.path.stat().st_size == 0:
            return set()
        with self.path.open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            if "source_type" not in (reader.fieldnames or []):
                raise RuntimeError(
                    "기존 output은 KOMSCO-direct 형식이 아닙니다. 새 output 파일을 사용하세요"
                )
            completed: set[int] = set()
            for row in reader:
                if row.get("source_type") != "KOMSCO_ONLY":
                    raise RuntimeError(
                        "output에 다른 입력 모집단이 섞여 있습니다. 새 output 파일을 사용하세요"
                    )
                if row.get("restaurant_id"):
                    completed.add(int(row["restaurant_id"]))
            return completed

    def append(
        self,
        result: RunResult,
    ) -> None:
        self.writer.writerow(result_row(result))
        self.stream.flush()
        os.fsync(self.stream.fileno())

    def close(self) -> None:
        self.stream.close()


def load_local_env(root: Path) -> None:
    env_path = root / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def preflight(
    root: Path,
    output: Path,
    require_db: bool,
    *,
    require_resolver: bool = True,
) -> None:
    print("=== Place Resolver Preflight ===")
    print(f"[OK] Python {sys.version.split()[0]}")
    if not output.parent.exists():
        output.parent.mkdir(parents=True, exist_ok=True)
    if not os.access(output.parent, os.W_OK):
        raise RuntimeError(f"[FAIL] output directory is not writable: {output.parent}")
    print(f"[OK] output directory writable: {output.parent}")
    if require_resolver:
        try:
            with sync_playwright() as playwright:
                executable = Path(playwright.chromium.executable_path)
                if not executable.exists():
                    raise RuntimeError(
                        "Playwright Chromium이 설치되지 않았습니다: "
                        "poetry run playwright install chromium"
                    )
        except Exception as error:
            raise RuntimeError(f"[FAIL] Playwright Chromium: {error}") from error
        print("[OK] Playwright Chromium")

        ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        model = configured_qwen_model()
        try:
            with urlopen(Request(f"{ollama_url}/api/tags"), timeout=3) as response:
                payload = json.loads(response.read().decode())
            models = {item.get("name") for item in payload.get("models", [])}
            if model not in models:
                raise RuntimeError(f"모델 {model}이 없습니다. ollama pull {model} 실행")
        except Exception as error:
            raise RuntimeError(f"[FAIL] Ollama {ollama_url}: {error}") from error
        print(f"[OK] Ollama {ollama_url} / {model}")
    else:
        print("[SAFE] CSV apply-only mode: resolver network checks disabled")

    host = os.getenv("MYSQL_HOST", "localhost")
    port = int(os.getenv("MYSQL_PORT", "3306"))
    try:
        with socket.create_connection((host, port), timeout=2):
            pass
    except OSError as error:
        if require_db:
            raise RuntimeError(f"[FAIL] MySQL {host}:{port}: {error}") from error
        print(f"[WARN] MySQL {host}:{port} 연결 확인 실패 (CSV-only에서는 DB를 쓰지 않음)")
    else:
        print(f"[OK] MySQL network {host}:{port}")
    if require_db:
        command = _docker_mysql_command("SELECT 1;")
        try:
            completed = subprocess.run(
                command, cwd=root, capture_output=True, text=True, timeout=10
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise RuntimeError(f"[FAIL] MySQL credential check: {error}") from error
        if completed.returncode != 0:
            raise RuntimeError("[FAIL] MySQL credential check failed; verify .env and local MySQL")
        print("[OK] MySQL credentials")
    if not require_db:
        print("[SAFE] DB write disabled (CSV-only mode)")


def _sql_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'").replace("\x00", "")


def _sql_value(value: str | None) -> str:
    if value is None or value == "":
        return "NULL"
    return f"'{_sql_escape(value)}'"


def _existing_pcmap_mapping(root: Path, place_id: str) -> int | None:
    rows = _mysql_rows(
        root,
        "SELECT JSON_OBJECT('restaurant_id', restaurant_id) "
        "FROM restaurant_external_places "
        f"WHERE provider='NAVER' AND external_place_id='{_sql_escape(place_id)}' LIMIT 1",
    )
    if not rows:
        return None
    return int(rows[0]["restaurant_id"])


def _has_restaurant_mapping(root: Path, restaurant_id: int) -> bool:
    rows = _mysql_rows(
        root,
        "SELECT JSON_OBJECT('id', id) FROM restaurant_external_places "
        f"WHERE restaurant_id={int(restaurant_id)} AND provider='NAVER' LIMIT 1",
    )
    return bool(rows)


def _write_place_mapping(
    root: Path,
    restaurant_id: int,
    place_id: str,
    *,
    external_name: str = "",
    category: str = "",
    address: str = "",
    road_address: str = "",
) -> bool:
    if not place_id.isdigit():
        return False
    existing_place_owner = _existing_pcmap_mapping(root, place_id)
    if existing_place_owner is not None and existing_place_owner != restaurant_id:
        raise RuntimeError(
            f"PCMap Place ID {place_id} is already mapped to restaurant "
            f"{existing_place_owner}; refusing remap"
        )
    link = f"https://pcmap.place.naver.com/restaurant/{place_id}/home"
    common = (
        f"external_place_id={_sql_value(place_id)}, "
        f"external_name={_sql_value(external_name)}, "
        f"category={_sql_value(category)}, "
        f"address={_sql_value(address)}, "
        f"road_address={_sql_value(road_address)}, "
        f"link={_sql_value(link)}, match_status='MATCHED', "
        "query_used='PCMAP_PLACE_RESOLVER', matched_at=NOW(6), "
        "last_synced_at=NOW(6), updated_at=NOW(6)"
    )
    if _has_restaurant_mapping(root, restaurant_id):
        sql = (
            "UPDATE restaurant_external_places SET "
            f"{common} "
            f"WHERE restaurant_id={int(restaurant_id)} AND provider='NAVER'; "
            "SELECT 1;"
        )
    else:
        sql = (
            "INSERT INTO restaurant_external_places "
            "(restaurant_id, provider, external_place_id, external_name, category, "
            "address, road_address, link, match_status, match_score, name_score, "
            "address_score, distance_score, category_score, query_used, matched_at, "
            "last_synced_at, created_at, updated_at) VALUES ("
            f"{int(restaurant_id)}, 'NAVER', {_sql_value(place_id)}, "
            f"{_sql_value(external_name)}, {_sql_value(category)}, "
            f"{_sql_value(address)}, {_sql_value(road_address)}, {_sql_value(link)}, "
            "'MATCHED', 0.00, 0.00, 0.00, 0.00, 0.00, "
            "'PCMAP_PLACE_RESOLVER', NOW(6), NOW(6), NOW(6), NOW(6)); "
            "SELECT 1;"
        )
    command = _docker_mysql_command(sql)
    try:
        completed = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(f"DB write command failed: {error}") from error
    if completed.returncode != 0:
        raise RuntimeError(f"DB write failed (exit {completed.returncode})")
    return completed.stdout.strip().splitlines()[-1:] == ["1"]


def write_resolved_to_db(result: RunResult, root: Path) -> bool:
    if (
        result.resolution.status != ResolutionStatus.RESOLVED
        or not result.place_id
        or result.detail_validation_attempts == 0
        or result.detail is None
    ):
        return False
    return _write_place_mapping(
        root,
        result.reference.restaurant_id,
        result.place_id,
        external_name=result.detail.name,
        category=result.detail.category,
        address=result.detail.address,
        road_address=result.detail.address,
    )


def apply_resolved_csv_to_db(path: Path, root: Path) -> tuple[int, int]:
    updated = 0
    missing_external_row = 0
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if "source_type" not in (reader.fieldnames or []):
            raise RuntimeError("KOMSCO-direct CSV만 DB에 반영할 수 있습니다")
        for row in reader:
            if row.get("source_type") != "KOMSCO_ONLY":
                raise RuntimeError("다른 입력 모집단이 섞인 CSV는 DB에 반영할 수 없습니다")
            place_id = row.get("place_id", "")
            if (
                row.get("final_status") != "RESOLVED"
                or row.get("detail_validation") != "PASS"
                or not place_id.isdigit()
            ):
                continue
            if _write_place_mapping(
                root,
                int(row["restaurant_id"]),
                place_id,
                external_name=row.get("detail_name", ""),
                category=row.get("detail_category", ""),
                address=row.get("detail_address", ""),
                road_address=row.get("detail_address", ""),
            ):
                updated += 1
            else:
                missing_external_row += 1
    return updated, missing_external_row


def print_progress(
    index: int, total: int, result: RunResult, counts: dict[str, int], started: float
) -> None:
    elapsed = monotonic() - started
    rate = index / elapsed if elapsed else 0
    eta = (total - index) / rate if rate else 0
    place = result.place_id or "-"
    print(
        f"[{index} / {total}] {index / total:.1%} | Restaurant: "
        f"{result.reference.komsco_name} | "
        f"Status: {result.resolution.status.value} | Place ID: {place} | "
        f"Elapsed: {result.elapsed_ms / 1000:.2f}s | "
        f"Resolved: {counts.get('RESOLVED', 0)} Ambiguous: {counts.get('AMBIGUOUS', 0)} "
        f"NotFound: {counts.get('NOT_FOUND', 0)} Error: {counts.get('ERROR', 0)} "
        f"Blocked: {counts.get('BLOCKED', 0)} | ETA: {time.strftime('%H:%M:%S', time.gmtime(eta))}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--limit", type=int, help="처리할 최대 KOMSCO-direct 대상 수. 생략하면 전체"
    )
    parser.add_argument(
        "--resume", action="store_true", help="기존 output CSV의 완료 restaurant_id를 건너뜀"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="DB를 절대 수정하지 않는 CSV-only 실행(기본 동작)"
    )
    parser.add_argument(
        "--write-db",
        action="store_true",
        help="RESOLVED + PASS + valid place_id 결과만 PCMap mapping에 반영",
    )
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit은 1 이상이어야 합니다")
    if args.dry_run and args.write_db:
        parser.error("--dry-run과 --write-db는 함께 사용할 수 없습니다")
    root = Path(__file__).resolve().parents[2]
    load_local_env(root)
    output = (
        args.output
        or root
        / "ai/build/reports/naver-place-resolver"
        / f"komsco-place-resolver-{datetime.now().strftime('%Y%m%d-%H%M%S')}.csv"
    )
    apply_only = args.resume and args.write_db and output.exists()
    preflight(root, output, args.write_db, require_resolver=not apply_only)
    population = load_komsco_population(root, args.limit)
    refs = list(population.references)
    if args.limit is not None and len(refs) < args.limit:
        raise RuntimeError(f"KOMSCO-only 대상이 {args.limit}건보다 적습니다")
    print(f"KOMSCO-only target: {population.total_count}")
    writer = ReportWriter(output, args.resume)
    completed_ids = writer.completed_ids() if args.resume else set()
    if completed_ids:
        print(f"Loaded previous results: {len(completed_ids)}")
    db_writes = 0
    missing_external_rows = 0
    if apply_only:
        db_writes, missing_external_rows = apply_resolved_csv_to_db(output, root)
        print(
            f"Applied reviewed RESOLVED rows: {db_writes} "
            f"(missing existing PCMap rows: {missing_external_rows})"
        )
        writer.close()
        print("CSV DB apply mode complete; no restaurants were crawled.")
        print(f"CSV: {output}")
        return 0
    pending_refs = [reference for reference in refs if reference.restaurant_id not in completed_ids]
    print(f"Remaining: {len(pending_refs)} / {len(refs)}")
    if not pending_refs:
        writer.close()
        print(f"All selected restaurants are already complete. CSV: {output}")
        print(f"DB writes: {db_writes}")
        return 0
    matcher = QwenCandidateMatcher(OllamaClient())
    stopped = False
    counts = {status.value: 0 for status in ResolutionStatus}
    initial_counts = {status.value: 0 for status in ResolutionStatus}
    run_started = monotonic()
    qwen_calls = 0
    qwen_semantic_calls = 0
    fatal_vetoes = 0
    limiter = NavigationRateLimiter(
        navigation_delay=float(os.getenv("NAVER_NAVIGATION_DELAY_SECONDS", "2.5")),
        restaurant_delay=float(os.getenv("NAVER_RESTAURANT_DELAY_SECONDS", "5")),
    )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_default_timeout(3_000)
        try:
            for index, reference in enumerate(pending_refs, start=1):
                restaurant_started = monotonic()
                result = None
                query = query_for(reference)
                try:
                    result = run_one(
                        page,
                        reference,
                        query,
                        "KOMSCO",
                        matcher,
                        before_navigation=limiter.before_navigation,
                    )
                except RuntimeError as error:
                    if str(error).startswith("BLOCKED:"):
                        result = _empty_result(
                            reference,
                            query,
                            "KOMSCO",
                            (),
                            ResolutionStatus.BLOCKED,
                            (str(error),),
                            monotonic(),
                        )
                        stopped = True
                    else:
                        result = _empty_result(
                            reference,
                            query,
                            "KOMSCO",
                            (),
                            ResolutionStatus.ERROR,
                            ("ALLSEARCH_RESPONSE_FAILED", str(error)),
                            monotonic(),
                        )
                except (PlaywrightTimeoutError, ValueError) as error:
                    result = _empty_result(
                        reference,
                        query,
                        "KOMSCO",
                        (),
                        ResolutionStatus.ERROR,
                        ("TECHNICAL_FAILURE", str(error)),
                        monotonic(),
                    )
                if result:
                    initial_status = result.resolution.status.value
                    initial_counts[initial_status] += 1
                    qwen_calls += int(result.qwen_used)
                    qwen_semantic_calls += sum(
                        1
                        for attempt in result.validation_attempts_detail
                        if attempt.semantic_decision
                    )
                    fatal_vetoes += sum(
                        1 for attempt in result.validation_attempts_detail if attempt.fatal_veto
                    )
                    result = replace(
                        result,
                        elapsed_ms=int((monotonic() - restaurant_started) * 1000),
                    )
                    writer.append(result)
                    counts[result.resolution.status.value] += 1
                    if args.write_db and result.resolution.status == ResolutionStatus.RESOLVED:
                        if write_resolved_to_db(result, root):
                            db_writes += 1
                    print_progress(index, len(pending_refs), result, counts, run_started)
                if stopped:
                    break
                if index < len(pending_refs):
                    limiter.after_restaurant()
        except KeyboardInterrupt:
            stopped = True
            print("\nStopping safely...")
        finally:
            browser.close()
            writer.close()
    processed = sum(counts.values())
    print("=== Place Resolver Summary ===")
    print(f"Processed: {processed} / {len(refs)}")
    print("Initial: " + " ".join(f"{key}: {value}" for key, value in initial_counts.items()))
    print(" ".join(f"{key}: {value}" for key, value in counts.items()))
    print(f"Qwen resolver calls: {qwen_calls}")
    print(f"Qwen semantic validation calls: {qwen_semantic_calls}")
    print(f"Fatal vetoes: {fatal_vetoes}")
    print(f"DB writes: {db_writes}")
    print(f"Total time: {time.strftime('%H:%M:%S', time.gmtime(monotonic() - run_started))}")
    print(f"CSV: {output}")
    if stopped:
        print(
            "Resume with: poetry run python -m app.naver.place_resolver_cli "
            f"--output {output} --resume"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
