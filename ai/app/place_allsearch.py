"""Structured candidate extraction for NAVER Map allSearch responses."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from app.place_resolver import PlaceCandidate

_ID_KEYS = ("placeId", "place_id", "businessId", "business_id", "sid", "id")
_NAME_KEYS = ("name", "placeName", "businessName", "title")
_CATEGORY_KEYS = ("category", "categoryName", "bizcategory", "businessCategory")
_ROAD_KEYS = ("roadAddress", "road_address")
_JIBUN_KEYS = ("jibunAddress", "jibun_address", "address")


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return " > ".join(item.strip() for item in value if item.strip())
    return ""


def _first_text(item: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = _text(item.get(key))
        if value:
            return value
    return ""


def _category_values(item: dict[str, Any]) -> tuple[str, ...]:
    for key in _CATEGORY_KEYS:
        value = item.get(key)
        if isinstance(value, list) and all(isinstance(entry, str) for entry in value):
            values = tuple(entry.strip() for entry in value if entry.strip())
            if values:
                return values
        text = _text(value)
        if text:
            return (text,)
    return ()


def _place_id(item: dict[str, Any]) -> str:
    for key in _ID_KEYS:
        value = item.get(key)
        if isinstance(value, int) and value > 0:
            return str(value)
        if isinstance(value, str) and value.isdigit():
            return value
    return ""


def _coordinate(item: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = item.get(key)
        try:
            if value not in (None, ""):
                return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _walk(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def parse_allsearch_candidates(payload: Any) -> tuple[PlaceCandidate, ...]:
    """Convert only structured place objects into candidates.

    Unknown/missing fields remain empty or ``None``; no DOM text or suffix
    inference is performed here.
    """
    result: list[PlaceCandidate] = []
    seen: set[str] = set()
    for item in _walk(payload):
        place_id = _place_id(item)
        name = _first_text(item, _NAME_KEYS)
        if not name or (place_id and place_id in seen):
            continue
        road = _first_text(item, _ROAD_KEYS)
        jibun = _first_text(item, _JIBUN_KEYS)
        address = road or jibun
        url = _first_text(item, ("url", "placeUrl", "place_url"))
        if not url and place_id:
            url = f"https://pcmap.place.naver.com/restaurant/{place_id}/home"
        if not place_id and not (road or jibun or _first_text(item, _CATEGORY_KEYS)):
            continue
        result.append(
            PlaceCandidate(
                name=name,
                address=address,
                category=_first_text(item, _CATEGORY_KEYS) or "UNKNOWN",
                url=url,
                place_id=place_id or None,
                latitude=_coordinate(item, ("latitude", "lat", "y")),
                longitude=_coordinate(item, ("longitude", "lng", "lon", "x")),
                road_address=road,
                jibun_address=jibun,
                category_values=_category_values(item),
            )
        )
        if place_id:
            seen.add(place_id)
    return tuple(result)
