"""Official Kakao/NAVER Local API candidate retrieval.

This module deliberately stops at provider candidate collection.  It performs
no entity matching, semantic filtering, Playwright navigation, or DB writes.
"""

from __future__ import annotations

import html
import json
import os
import re
from dataclasses import asdict, dataclass
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class ProviderHTTPError(RuntimeError):
    """Safe provider error containing status and documented error fields only."""

    def __init__(self, status: int, detail: str = ""):
        super().__init__(f"HTTP_{status}{(' ' + detail) if detail else ''}")
        self.status = status


@dataclass(frozen=True)
class PlaceSearchCandidate:
    provider: str
    external_place_id: str
    name: str
    category: str
    address: str
    road_address: str
    longitude: float | None
    latitude: float | None
    phone: str
    detail_url: str
    distance: str
    raw_metadata: dict[str, Any]


@dataclass(frozen=True)
class ProviderSearchResult:
    provider: str
    query: str
    candidates: tuple[PlaceSearchCandidate, ...]
    error: str = ""


def _float(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _html_text(value: Any) -> str:
    return re.sub(r"<[^>]+>", "", html.unescape(str(value or "")))


def _request_json(url: str, *, headers: dict[str, str], params: dict[str, Any]) -> dict[str, Any]:
    request = Request(f"{url}?{urlencode(params)}", headers=headers, method="GET")
    try:
        with urlopen(request, timeout=15) as response:  # noqa: S310 - fixed official endpoints
            body = response.read().decode("utf-8")
            payload = json.loads(body)
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")[:1000]
        try:
            error_payload = json.loads(body)
        except json.JSONDecodeError:
            error_payload = {}
        if not isinstance(error_payload, dict):
            error_payload = {}
        code = error_payload.get("code") or error_payload.get("errorCode") or ""
        message = error_payload.get("msg") or error_payload.get("errorMessage") or ""
        detail = " ".join(str(value).replace("\n", " ") for value in (code, message) if value)
        raise ProviderHTTPError(error.code, detail[:300]) from error
    if not isinstance(payload, dict):
        raise ValueError("provider response is not an object")
    return payload


def _safe_error(error: BaseException) -> str:
    """Expose diagnostic class/status only; never include request headers or URLs."""
    if isinstance(error, HTTPError):
        return f"HTTP_{error.code}"
    if isinstance(error, ProviderHTTPError):
        return str(error)
    if isinstance(error, URLError):
        return "NETWORK_ERROR"
    return type(error).__name__


def parse_kakao_candidates(payload: dict[str, Any]) -> tuple[PlaceSearchCandidate, ...]:
    documents = payload.get("documents")
    if not isinstance(documents, list):
        return ()
    result: list[PlaceSearchCandidate] = []
    for row in documents:
        if not isinstance(row, dict):
            continue
        result.append(PlaceSearchCandidate(
            provider="KAKAO",
            external_place_id=str(row.get("id") or ""),
            name=str(row.get("place_name") or ""),
            category=str(row.get("category_name") or ""),
            address=str(row.get("address_name") or ""),
            road_address=str(row.get("road_address_name") or ""),
            longitude=_float(row.get("x")), latitude=_float(row.get("y")),
            phone=str(row.get("phone") or ""),
            detail_url=str(row.get("place_url") or ""),
            distance=str(row.get("distance") or ""),
            raw_metadata=dict(row),
        ))
    return tuple(result)


def parse_naver_candidates(payload: dict[str, Any]) -> tuple[PlaceSearchCandidate, ...]:
    items = payload.get("items")
    if not isinstance(items, list):
        return ()
    result: list[PlaceSearchCandidate] = []
    for row in items:
        if not isinstance(row, dict):
            continue
        mapx, mapy = row.get("mapx"), row.get("mapy")
        longitude = _float(mapx)
        latitude = _float(mapy)
        if longitude is not None and abs(longitude) > 180:
            longitude /= 10_000_000
        if latitude is not None and abs(latitude) > 90:
            latitude /= 10_000_000
        result.append(PlaceSearchCandidate(
            provider="NAVER_LOCAL",
            # The official Local response exposes a link, not a numeric Place ID.
            # Do not invent an ID from the URL; retain it as detail_url below.
            external_place_id="",
            name=_html_text(row.get("title")),
            category=str(row.get("category") or ""),
            address=str(row.get("address") or ""),
            road_address=str(row.get("roadAddress") or ""),
            longitude=longitude, latitude=latitude,
            phone=str(row.get("telephone") or ""),
            detail_url=str(row.get("link") or ""),
            distance="",
            raw_metadata=dict(row),
        ))
    return tuple(result)


class PlaceSearchProvider(Protocol):
    provider: str

    def search(self, query: str, *, longitude: float | None = None,
               latitude: float | None = None) -> ProviderSearchResult: ...


class KakaoPlaceSearchProvider:
    provider = "KAKAO"
    endpoint = "https://dapi.kakao.com/v2/local/search/keyword.json"

    def __init__(self, api_key: str | None = None, *, size: int = 15):
        self.api_key = api_key or os.getenv("KAKAO_REST_API_KEY", "")
        self.size = size

    def search(self, query: str, *, longitude: float | None = None,
               latitude: float | None = None) -> ProviderSearchResult:
        params: dict[str, Any] = {"query": query, "size": self.size}
        if longitude is not None and latitude is not None:
            params.update({"x": longitude, "y": latitude, "sort": "distance"})
        try:
            payload = _request_json(self.endpoint,
                                    headers={"Authorization": f"KakaoAK {self.api_key}"},
                                    params=params)
            return ProviderSearchResult(self.provider, query, parse_kakao_candidates(payload))
        except Exception as error:  # provider errors become report data, not guesses
            return ProviderSearchResult(self.provider, query, (), _safe_error(error))


class NaverPlaceSearchProvider:
    provider = "NAVER_LOCAL"
    endpoint = "https://openapi.naver.com/v1/search/local.json"

    def __init__(self, client_id: str | None = None, client_secret: str | None = None,
                 *, display: int = 5):
        self.client_id = client_id or os.getenv("NAVER_CLIENT_ID", "")
        self.client_secret = client_secret or os.getenv("NAVER_CLIENT_SECRET", "")
        self.display = display

    def search(self, query: str, *, longitude: float | None = None,
               latitude: float | None = None) -> ProviderSearchResult:
        del longitude, latitude  # official endpoint does not expose center coordinates
        try:
            payload = _request_json(
                self.endpoint,
                headers={"X-Naver-Client-Id": self.client_id,
                         "X-Naver-Client-Secret": self.client_secret},
                params={"query": query, "display": self.display, "start": 1, "sort": "random"},
            )
            return ProviderSearchResult(self.provider, query, parse_naver_candidates(payload))
        except Exception as error:
            return ProviderSearchResult(self.provider, query, (), _safe_error(error))


def candidate_json(candidates: tuple[PlaceSearchCandidate, ...]) -> str:
    return json.dumps([asdict(candidate) for candidate in candidates], ensure_ascii=False,
                      separators=(",", ":"))
