"""Parser for the public ``window.__APOLLO_STATE__`` embedded in PCMap HTML."""

# The parser contains long field-mapping expressions that mirror the external payload.
# ruff: noqa: E501

from __future__ import annotations

import html
import json
import re
from typing import Any

from app.place_detail_models import (
    BusinessHour,
    MenuItem,
    PlaceDetail,
    ReviewItem,
    ReviewKeyword,
)

_APOLLO_MARKER = "window.__APOLLO_STATE__"
_PRICE_NUMBER = re.compile(r"\d[\d,]*")


def extract_apollo_state(document: str) -> dict[str, Any]:
    """Extract the balanced JSON object assigned to ``window.__APOLLO_STATE__``."""
    marker = document.find(_APOLLO_MARKER)
    if marker < 0:
        raise ValueError("APOLLO_STATE_NOT_FOUND")
    start = document.find("{", marker)
    if start < 0:
        raise ValueError("APOLLO_STATE_JSON_NOT_FOUND")
    end = _balanced_json_end(document, start)
    try:
        value = json.loads(html.unescape(document[start:end]))
    except json.JSONDecodeError as error:
        raise ValueError("APOLLO_STATE_INVALID_JSON") from error
    if not isinstance(value, dict):
        raise ValueError("APOLLO_STATE_NOT_OBJECT")
    return value


def _balanced_json_end(value: str, start: int) -> int:
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(value)):
        char = value[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index + 1
    raise ValueError("APOLLO_STATE_UNBALANCED_JSON")


class ApolloResolver:
    def __init__(self, state: dict[str, Any]):
        self.state = state

    def resolve(self, value: Any, seen: frozenset[str] = frozenset()) -> Any:
        if isinstance(value, dict) and set(value) == {"__ref"}:
            key = value["__ref"]
            if not isinstance(key, str) or key in seen:
                return None
            return self.resolve(self.state.get(key), seen | {key})
        if isinstance(value, list):
            return [self.resolve(item, seen) for item in value]
        if isinstance(value, dict):
            return {key: self.resolve(item, seen) for key, item in value.items()}
        return value

    def place_detail(self, place_id: str) -> dict[str, Any]:
        candidates = [
            self.state.get(f"PlaceDetailBase:{place_id}"),
            self.state.get(f"PlaceDetail:{place_id}"),
        ]
        root = self.state.get("ROOT_QUERY")
        if isinstance(root, dict):
            candidates.extend(value for key, value in root.items() if "placeDetail" in key)
        for candidate in candidates:
            resolved = self.resolve(candidate)
            if isinstance(resolved, dict):
                return resolved
        raise ValueError(f"PLACE_DETAIL_NOT_FOUND:{place_id}")


def parse_place_detail(document: str, place_id: str) -> PlaceDetail:
    state = extract_apollo_state(document)
    return parse_place_detail_state(state, place_id)


def parse_place_detail_state(state: dict[str, Any], place_id: str) -> PlaceDetail:
    resolver = ApolloResolver(state)
    detail = resolver.place_detail(place_id)
    return _detail_from_dict(detail, place_id, resolver)


def _detail_from_dict(value: dict[str, Any], place_id: str, resolver: ApolloResolver) -> PlaceDetail:
    hours = _hours(value.get("newBusinessHours") or value.get("businessHours"))
    menu_container = value.get("placeMenus") or {}
    menu_count = _int(_first(menu_container, "menuCount", "totalCount"))
    menu_values = _list_value(menu_container, "items")
    menus = tuple(_menu(item, resolver) for item in menu_values if isinstance(item, dict))
    stats = value.get("visitorReviewStats") or value.get("visitorReviews") or {}
    stats = stats if isinstance(stats, dict) else {}
    analysis = stats.get("analysis") if isinstance(stats.get("analysis"), dict) else {}
    reviews = _reviews(value.get("reviews") or value.get("visitorReviews"))
    return PlaceDetail(
        place_id=place_id,
        name=_str(_first(value, "name", "businessName")),
        category=_str(_first(value, "category", "categoryName")),
        category_code=_str(_first(value, "categoryCode", "category_code")),
        address=_str(_first(value, "address", "parcelAddress")),
        road_address=_str(_first(value, "roadAddress", "road_address")),
        latitude=_float(_first(value, "latitude", "lat")),
        longitude=_float(_first(value, "longitude", "lng", "lon")),
        phone=_str(_first(value, "phone", "telephone")),
        virtual_phone=_str(_first(value, "virtualPhone", "virtual_phone")),
        conveniences=_strings(_first(value, "conveniences", "convenience")),
        payment_info=_strings(_first(value, "paymentInfo", "payment_info")),
        description=_str(_first(value, "description", "desc")),
        homepage=_str(_first(value, "homepage", "homePage")),
        image_url=_str(_first(value, "imageUrl", "image", "representativeImage")),
        visitor_reviews_total=_int(_first(stats, "totalCount", "visitorReviewsTotal")),
        visitor_reviews_score=_float(_first(stats, "avgRating", "score")),
        visitor_text_review_total=_int(_first(stats, "textReviewTotal", "textReviewCount")),
        cafe_blog_reviews_total=_int(_first(value, "cafeBlogReviewsTotal", "blogReviewsTotal")),
        business_hours=hours,
        menus=menus,
        menu_count=menu_count,
        review_keywords=_keywords(analysis.get("themes"), "theme"),
        review_menu_mentions=_keywords(analysis.get("menus"), "menu"),
        voted_keywords=_keywords(
            (analysis.get("votedKeyword") or {}).get("details")
            if isinstance(analysis.get("votedKeyword"), dict) else None,
            "voted",
        ),
        representative_reviews=reviews,
    )


def _hours(value: Any) -> tuple[BusinessHour, ...]:
    items = value.get("items") if isinstance(value, dict) else value
    return tuple(
        BusinessHour(
            day=_str(_first(item, "day", "dayOfWeek")) or "",
            open_time=_str(_first(item, "openTime", "open_time")),
            close_time=_str(_first(item, "closeTime", "close_time")),
            break_hours=_str(_first(item, "breakHours", "break_hours")),
            last_order=_str(_first(item, "lastOrder", "last_order")),
            description=_str(_first(item, "description", "desc")),
            regular_closed_day=_str(_first(item, "regularClosedDay", "regular_closed_day")),
            irregular_closed_day=_str(_first(item, "irregularClosedDay", "irregular_closed_day")),
            business_status=_str(_first(item, "businessStatus", "status")),
        )
        for item in (items or []) if isinstance(item, dict)
    )


def _menu(value: dict[str, Any], resolver: ApolloResolver) -> MenuItem:
    if "__ref" in value:
        resolved = resolver.resolve(value)
        if isinstance(resolved, dict):
            value = resolved
    price = value.get("price") if isinstance(value.get("price"), dict) else {}
    price_text = _str(_first(price, "displayText", "text"))
    return MenuItem(
        external_menu_id=_str(_first(value, "id", "menuId", "externalMenuId")) or "",
        menu_type=_str(_first(value, "type", "menuType")),
        name=_str(_first(value, "name", "menuName")) or "",
        description=_str(_first(value, "description", "desc")),
        price_value=_price_value(price_text),
        price_text=price_text,
        price_type=_str(price.get("priceType")),
        is_set_menu=_bool(_first(value, "isSetMenu", "setMenu")),
        thumbnail_url=_str(_first(value, "thumbnailUrl", "imageUrl")),
        badges=_strings(value.get("badges")),
        labels=_strings(value.get("labels")),
    )


def _keywords(value: Any, kind: str) -> tuple[ReviewKeyword, ...]:
    if not isinstance(value, list):
        return ()
    result = []
    for item in value:
        if isinstance(item, str):
            result.append(ReviewKeyword(item, None, kind))
        elif isinstance(item, dict):
            keyword = _str(_first(item, "keyword", "name", "text", "label"))
            if keyword:
                result.append(ReviewKeyword(keyword, _int(_first(item, "count", "value")), kind))
    return tuple(result)


def _reviews(value: Any) -> tuple[ReviewItem, ...]:
    items = value.get("items") if isinstance(value, dict) else value
    if not isinstance(items, list):
        return ()
    result: list[ReviewItem] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        review_id = _str(_first(item, "id", "reviewId"))
        text = _str(_first(item, "text", "reviewText", "content"))
        if not review_id or not text:
            continue
        result.append(
            ReviewItem(
                review_id=review_id,
                review_text=text,
                review_date=_str(_first(item, "date", "reviewDate")),
                visit_count=_int(_first(item, "visitCount")),
                visit_purpose=_str(_first(item, "visitPurpose")),
                selected_keywords=_strings(_first(item, "keywords", "selectedKeywords")),
                rating=_float(_first(item, "rating", "score")),
                image_urls=_strings(_first(item, "imageUrls", "images")),
            )
        )
    return tuple(result)


def _list_value(value: Any, key: str) -> list[Any]:
    if isinstance(value, dict) and isinstance(value.get(key), list):
        return value[key]
    return value if isinstance(value, list) else []


def _first(value: Any, *keys: str) -> Any:
    return next((value[key] for key in keys if isinstance(value, dict) and value.get(key) is not None), None)


def _str(value: Any) -> str | None:
    return str(value).strip() if value is not None and str(value).strip() else None


def _int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _strings(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if not isinstance(value, list):
        return ()
    return tuple(item if isinstance(item, str) else str(item.get("name") or item.get("label"))
                 for item in value if isinstance(item, str) or isinstance(item, dict))


def _price_value(value: str | None) -> int | None:
    if not value:
        return None
    match = _PRICE_NUMBER.search(value.replace(" ", ""))
    return int(match.group().replace(",", "")) if match else None
