"""Deterministic, review-first NAVER Map Place ID resolver PoC.

This module only reads browser-rendered search results. It does not call NAVER's
private APIs, write to MySQL, or infer an ID when a URL has no explicit place
path. The resolver intentionally prefers an unresolved result to a false
positive.
"""

from __future__ import annotations

import html
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from math import asin, cos, radians, sin, sqrt
from urllib.parse import urlparse


class ResolutionStatus(StrEnum):
    RESOLVED = "RESOLVED"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_FOUND = "NOT_FOUND"
    BLOCKED = "BLOCKED"
    ERROR = "ERROR"


@dataclass(frozen=True)
class RestaurantReference:
    restaurant_id: int
    komsco_name: str
    komsco_address: str
    komsco_latitude: float | None
    komsco_longitude: float | None
    legal_dong: str


@dataclass(frozen=True)
class PlaceCandidate:
    name: str
    address: str
    category: str
    url: str
    place_id: str | None
    latitude: float | None = None
    longitude: float | None = None


@dataclass(frozen=True)
class Resolution:
    reference: RestaurantReference
    query: str
    candidate: PlaceCandidate | None
    status: ResolutionStatus
    name_evidence: str
    address_evidence: str
    distance_evidence: str
    risk_flags: tuple[str, ...]


PLACE_PATH = re.compile(r"/(?:entry/)?place/(\d+)(?:[/?#]|$)|/restaurant/(\d+)(?:[/?#]|$)")
HTML_TAG = re.compile(r"<[^>]+>")
NON_TEXT = re.compile(r"[^0-9a-z가-힣]")
NON_FOOD_TERMS = (
    "약국", "병원", "의원", "치과", "복지", "사회복지", "소프트웨어", "세무사",
    "법률", "부동산", "자동차정비", "여행사", "광고", "공방",
)
ADDRESS_EVIDENCE_ORDER = {
    "DIFFERENT": 0,
    "UNKNOWN": 1,
    "PARTIAL": 2,
    "STRONG_MATCH": 3,
    "EXACT": 4,
}


def extract_place_ids_from_nlog_params(value: str | None) -> tuple[str, ...]:
    """Parse numeric place_id values from one data-nlog-params attribute."""
    if not value:
        return ()
    decoded = html.unescape(value)
    try:
        payload = json.loads(decoded)
    except json.JSONDecodeError:
        return ()
    place_id = payload.get("place_id") if isinstance(payload, dict) else None
    if isinstance(place_id, int):
        place_id = str(place_id)
    if isinstance(place_id, str) and place_id.isdigit():
        return (place_id,)
    return ()


def extract_candidate_place_ids(attributes: Iterable[str | None]) -> tuple[str, ...]:
    """Return unique IDs scoped to one candidate DOM subtree.

    More than one distinct ID is treated as unsafe and returned as an empty tuple;
    callers must not mix IDs from separate candidates.
    """
    values = {
        place_id
        for attribute in attributes
        for place_id in extract_place_ids_from_nlog_params(attribute)
    }
    return tuple(sorted(values)) if len(values) == 1 else ()


def normalize_text(value: str | None) -> str:
    value = html.unescape(value or "")
    value = HTML_TAG.sub("", value).lower().strip()
    return NON_TEXT.sub("", value)


def extract_place_id(url: str) -> str | None:
    """Extract only an explicit numeric NAVER place or restaurant URL path."""
    parsed = urlparse(url)
    if "/restaurant/" in parsed.path and parsed.netloc and parsed.netloc != "pcmap.place.naver.com":
        return None
    match = PLACE_PATH.search(parsed.path)
    return next((group for group in match.groups() if group), None) if match else None


def distance_meters(
    first_latitude: float | None,
    first_longitude: float | None,
    second_latitude: float | None,
    second_longitude: float | None,
) -> float | None:
    if None in (first_latitude, first_longitude, second_latitude, second_longitude):
        return None
    latitude_delta = radians(second_latitude - first_latitude)
    longitude_delta = radians(second_longitude - first_longitude)
    first_latitude_radians = radians(first_latitude)
    second_latitude_radians = radians(second_latitude)
    haversine = (
        sin(latitude_delta / 2) ** 2
        + cos(first_latitude_radians) * cos(second_latitude_radians) * sin(longitude_delta / 2) ** 2
    )
    return 2 * 6_371_000 * asin(sqrt(haversine))


def _name_evidence(reference: RestaurantReference, candidate: PlaceCandidate) -> str:
    expected = normalize_text(reference.komsco_name)
    actual = normalize_text(candidate.name)
    if not expected or not actual:
        return "UNKNOWN"
    if expected == actual:
        return "EXACT"
    if expected in actual or actual in expected:
        return "CONTAINED"
    return "DIFFERENT"


def compare_address_pair(source: str, detail: str) -> str:
    """Compare one source/detail address pair, ignoring trailing descriptions."""
    expected = normalize_text(source)
    actual = normalize_text(detail)
    source_spaced = re.sub(r"[^0-9a-z가-힣]+", " ", html.unescape(source).lower()).strip()
    detail_spaced = re.sub(r"[^0-9a-z가-힣]+", " ", html.unescape(detail).lower()).strip()
    if not expected or not actual:
        return "UNKNOWN"
    if expected == actual:
        return "EXACT"
    expected_tokens = set(re.findall(r"[가-힣]+|\d+", expected))
    actual_tokens = set(re.findall(r"[가-힣]+|\d+", actual))
    expected_numbers = set(re.findall(r"\d+", expected))
    actual_numbers = set(re.findall(r"\d+", actual))
    building_pattern = r"(?:대로\d*길|로\d*길|길|로|대로)\s*(\d+)"
    expected_buildings = set(re.findall(building_pattern, source_spaced))
    actual_buildings = set(re.findall(building_pattern, detail_spaced))
    if expected_buildings and actual_buildings and not expected_buildings & actual_buildings:
        return "DIFFERENT"

    # Road address: district + road name + building number are strong evidence.
    road_pattern = r"([가-힣]+(?:대로|로|길)\d*(?:길)?)"
    expected_roads = re.findall(road_pattern, expected)
    actual_roads = re.findall(road_pattern, actual)

    def road_key(value: str) -> str:
        suffixes = list(re.finditer(r"대로|로|길", value))
        if not suffixes:
            return ""
        return value[: suffixes[-1].end()].rsplit("구", 1)[-1]

    expected_road = road_key(expected_roads[-1]) if expected_roads else ""
    actual_road = road_key(actual_roads[-1]) if actual_roads else ""
    if (
        expected_road
        and actual_road
        and expected_road == actual_road
        and (
            expected_buildings & actual_buildings
            or expected_numbers & actual_numbers
        )
        and any(token in expected and token in actual for token in ("구", "시", "도"))
    ):
        return "STRONG_MATCH"

    # Jibun address: dong and main/sub-lot numbers are strong evidence.
    expected_dong = set(re.findall(r"[가-힣]+동", expected))
    actual_dong = set(re.findall(r"[가-힣]+동", actual))
    if expected_dong & actual_dong and expected_numbers & actual_numbers:
        return "STRONG_MATCH"
    if expected_tokens and len(expected_tokens & actual_tokens) / len(expected_tokens) >= 0.5:
        return "PARTIAL"
    return "DIFFERENT"


def best_address_evidence(source_addresses: Iterable[str], detail_addresses: Iterable[str]) -> str:
    """Use the strongest available source/detail address pair; missing is UNKNOWN."""
    sources = tuple(source_addresses)
    details = tuple(detail_addresses)
    if not any(normalize_text(value) for value in sources) or not any(
        normalize_text(value) for value in details
    ):
        return "UNKNOWN"
    results = [
        compare_address_pair(source, detail)
        for source in sources
        for detail in details
        if normalize_text(source) and normalize_text(detail)
    ]
    return max(results, key=lambda result: ADDRESS_EVIDENCE_ORDER[result], default="UNKNOWN")


def _address_evidence(reference: RestaurantReference, candidate: PlaceCandidate) -> str:
    return best_address_evidence(
        (reference.komsco_address,),
        (candidate.address,),
    )


def candidate_evidence(
    reference: RestaurantReference, candidate: PlaceCandidate
) -> tuple[str, str, str, int]:
    """Return comparable evidence without treating absent optional fields as conflicts."""
    name = _name_evidence(reference, candidate)
    address = _address_evidence(reference, candidate)
    distance = distance_meters(
        reference.komsco_latitude,
        reference.komsco_longitude,
        candidate.latitude,
        candidate.longitude,
    )
    distance_evidence = "UNKNOWN" if distance is None else "NEAR" if distance <= 300 else "FAR"
    score = (50 if name == "EXACT" else 25 if name == "CONTAINED" else 0) + (
        35 if address == "EXACT" else 30 if address == "STRONG_MATCH" else 15 if address == "PARTIAL" else 0
    )
    if distance is not None:
        score += 15 if distance <= 50 else 5 if distance <= 300 else 0
    return name, address, distance_evidence, score


def hard_rejection_reason(reference: RestaurantReference, candidate: PlaceCandidate) -> str | None:
    """Reject only evidence of an unambiguous wrong candidate.

    Missing category/address/coordinates are unknown evidence, not mismatches.
    """
    if not candidate.place_id or not candidate.place_id.isdigit():
        return "CANDIDATE_PLACE_ID_MISSING"
    category = normalize_text(candidate.category)
    if category and any(term in category for term in NON_FOOD_TERMS):
        return "NON_FOOD_CATEGORY"
    name, address, _, _ = candidate_evidence(reference, candidate)
    if name == "DIFFERENT" and address == "DIFFERENT":
        return "NAME_AND_ADDRESS_MISMATCH"
    return None


def rank_candidates(
    reference: RestaurantReference, candidates: Iterable[PlaceCandidate]
) -> tuple[PlaceCandidate, ...]:
    """Stable deterministic ordering used to form the Qwen Top-5 input."""
    values = list(candidates)
    scored = [(candidate_evidence(reference, candidate)[3], index, candidate) for index, candidate in enumerate(values)]
    scored.sort(key=lambda item: (-item[0], item[2].place_id or "", item[1]))
    return tuple(candidate for _, _, candidate in scored)


def resolve_candidate(
    reference: RestaurantReference,
    candidates: Iterable[PlaceCandidate],
) -> Resolution:
    """Apply conservative evidence gates to browser candidates."""
    ranked: list[tuple[int, PlaceCandidate, str, str, str]] = []
    for candidate in candidates:
        name, address, distance_evidence, score = candidate_evidence(reference, candidate)
        ranked.append((score, candidate, name, address, distance_evidence))

    if not ranked:
        return Resolution(
            reference, "", None, ResolutionStatus.NOT_FOUND, "UNKNOWN", "UNKNOWN", "UNKNOWN", ()
        )
    ranked.sort(key=lambda item: (-item[0], item[1].place_id or ""))
    best = ranked[0]
    second_score = ranked[1][0] if len(ranked) > 1 else None
    risk_flags: list[str] = []
    if best[2] == "DIFFERENT":
        risk_flags.append("NAME_MISMATCH")
    if best[3] == "DIFFERENT":
        risk_flags.append("ADDRESS_MISMATCH")
    if best[4] == "FAR":
        risk_flags.append("FAR_COORDINATE")
    if second_score is not None and best[0] - second_score < 15:
        risk_flags.append("SMALL_SCORE_GAP")

    strong = best[2] in {"EXACT", "CONTAINED"} and best[3] in {"EXACT", "STRONG_MATCH", "PARTIAL"}
    if best[1].place_id is None:
        status = ResolutionStatus.NOT_FOUND
    elif best[2] == "DIFFERENT" and best[3] == "DIFFERENT":
        status = ResolutionStatus.NOT_FOUND
    elif not strong:
        status = ResolutionStatus.AMBIGUOUS
    elif second_score is not None and best[0] - second_score < 15:
        status = ResolutionStatus.AMBIGUOUS
    else:
        status = ResolutionStatus.RESOLVED
    return Resolution(
        reference,
        "",
        best[1],
        status,
        best[2],
        best[3],
        best[4],
        tuple(risk_flags),
    )


def deterministic_fast_path(
    reference: RestaurantReference,
    candidates: Iterable[PlaceCandidate],
) -> PlaceCandidate | None:
    """Select only a single candidate with strong, independent evidence.

    This deliberately does not lower the general matcher thresholds: one exact
    normalized name, meaningful address evidence, and an explicit food category
    are required. Multiple candidates always remain eligible for Qwen ranking.
    """
    values = list(candidates)
    if len(values) != 1:
        return None
    candidate = values[0]
    if _name_evidence(reference, candidate) != "EXACT":
        return None
    if _address_evidence(reference, candidate) not in {"EXACT", "PARTIAL"}:
        return None
    category = normalize_text(candidate.category)
    if not category or not any(
        term in category
        for term in ("한식", "일식", "중식", "양식", "분식", "음식점", "식당", "카페", "술집")
    ):
        return None
    return candidate


def query_for(reference: RestaurantReference) -> str:
    """Build the PCMap query from KOMSCO fields only."""
    return f"{reference.legal_dong} {reference.komsco_name}".strip()
