"""Public PCMap detail crawler using HTTP and Apollo state only."""

# ruff: noqa: E501

from __future__ import annotations

import time
from dataclasses import dataclass, replace
from urllib.request import Request, urlopen

from app.place_apollo_parser import parse_place_detail, parse_place_detail_state
from app.place_detail_models import PlaceDetail


@dataclass(frozen=True)
class DetailCrawlResult:
    status: str
    detail: PlaceDetail | None
    home_requested: bool = False
    menu_fallback_used: bool = False
    review_requested: bool = False
    warnings: tuple[str, ...] = ()
    access_method: str = "HTTP"
    http_result: str = "NOT_ATTEMPTED"
    playwright_result: str = "NOT_ATTEMPTED"


class PlaceDetailCrawler:
    """Fetches public HTML; it never calls private NAVER APIs."""

    def __init__(self, timeout: float = 15.0, retries: int = 1, delay: float = 0.2):
        self.timeout = timeout
        self.retries = retries
        self.delay = delay

    def crawl(self, place_id: str, *, include_reviews: bool = True) -> DetailCrawlResult:
        try:
            home = self._get(self._url(place_id, "home"))
            detail = parse_place_detail(home, place_id)
            warnings = list(detail.warnings)
            menu_fallback = False
            if detail.menu_count is None or not detail.menu_complete:
                try:
                    menu_html = self._get(self._url(place_id, "menu/list"))
                    menu_detail = parse_place_detail(menu_html, place_id)
                    detail = _merge_detail(detail, menu_detail)
                    menu_fallback = True
                except Exception as error:  # partial detail is still useful
                    warnings.append(f"MENU_FALLBACK_FAILED:{type(error).__name__}")
            review_requested = False
            if include_reviews:
                try:
                    review_html = self._get(self._url(place_id, "review/visitor"))
                    review_detail = parse_place_detail(review_html, place_id)
                    detail = _merge_detail(detail, review_detail)
                    review_requested = True
                except Exception as error:
                    warnings.append(f"REVIEW_FAILED:{type(error).__name__}")
            detail = replace(detail, warnings=tuple(warnings))
            status = "SUCCESS" if not warnings else "PARTIAL"
            return DetailCrawlResult(status, detail, True, menu_fallback, review_requested, tuple(warnings))
        except Exception as error:
            return DetailCrawlResult("FAILED", None, True, False, False, (f"HOME_FAILED:{type(error).__name__}",))

    def crawl_with_page(self, page, place_id: str, *, include_reviews: bool = True) -> DetailCrawlResult:
        """Use the existing Resolver browser/context and read Apollo from page JS."""
        try:
            page.goto(self._url(place_id, "home"), wait_until="domcontentloaded", timeout=15_000)
            state = page.evaluate("() => window.__APOLLO_STATE__ || null")
            if not isinstance(state, dict):
                content = page.content()
                if "__APOLLO_STATE__" not in content:
                    return DetailCrawlResult(
                        "BLOCKED", None, True, False, False,
                        ("APOLLO_STATE_NOT_FOUND",), "PLAYWRIGHT", "APOLLO_STATE_NOT_FOUND", "APOLLO_STATE_NOT_FOUND"
                    )
                return DetailCrawlResult(
                    "FAILED", None, True, False, False,
                    ("APOLLO_STATE_UNREADABLE",), "PLAYWRIGHT", "APOLLO_STATE_UNREADABLE", "APOLLO_STATE_UNREADABLE"
                )
            detail = parse_place_detail_state(state, place_id)
            menu_fallback = False
            warnings: list[str] = list(detail.warnings)
            if not any((detail.name, detail.address, detail.road_address, detail.category)):
                warnings.append("APOLLO_PARSE_ERROR:EMPTY_PLACE_DETAIL")
                return DetailCrawlResult(
                    "FAILED", None, True, False, False, tuple(warnings),
                    "PLAYWRIGHT", "NOT_ATTEMPTED", "APOLLO_PARSE_ERROR"
                )
            if detail.menu_count is None:
                warnings.append("MENU_COUNT_MISSING")
            if detail.menu_count is None or not detail.menu_complete:
                page.goto(self._url(place_id, "menu/list"), wait_until="domcontentloaded", timeout=15_000)
                menu_state = page.evaluate("() => window.__APOLLO_STATE__ || null")
                if isinstance(menu_state, dict):
                    detail = _merge_detail(detail, parse_place_detail_state(menu_state, place_id))
                    menu_fallback = True
                else:
                    warnings.append("MENU_APOLLO_STATE_NOT_FOUND")
            review_requested = False
            if include_reviews:
                page.goto(self._url(place_id, "review/visitor"), wait_until="domcontentloaded", timeout=15_000)
                review_state = page.evaluate("() => window.__APOLLO_STATE__ || null")
                if isinstance(review_state, dict):
                    detail = _merge_detail(detail, parse_place_detail_state(review_state, place_id))
                    review_requested = True
                else:
                    warnings.append("REVIEW_APOLLO_STATE_NOT_FOUND")
            detail = replace(detail, warnings=tuple(warnings))
            return DetailCrawlResult(
                "SUCCESS" if not warnings else "PARTIAL", detail, True, menu_fallback,
                review_requested, tuple(warnings), "PLAYWRIGHT", "NOT_ATTEMPTED", "SUCCESS"
            )
        except Exception as error:
            return DetailCrawlResult(
                "FAILED", None, True, False, False, (f"PLAYWRIGHT_FAILED:{type(error).__name__}",),
                "PLAYWRIGHT", "NOT_ATTEMPTED", "ERROR"
            )

    def _get(self, url: str) -> str:
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urlopen(request, timeout=self.timeout) as response:
                    if response.status in {403, 429}:
                        raise RuntimeError(f"BLOCKED_HTTP_{response.status}")
                    body = response.read().decode("utf-8", errors="replace")
                    lowered = body.lower()
                    if any(marker in lowered for marker in ("captcha", "접근이 제한", "서비스 이용이 제한")):
                        raise RuntimeError("BLOCKED_PAGE")
                    return body
            except Exception as error:
                last = error
                if attempt < self.retries:
                    time.sleep(self.delay * (attempt + 1))
        raise RuntimeError(f"DETAIL_REQUEST_FAILED:{last}") from last

    @staticmethod
    def _url(place_id: str, page: str) -> str:
        if not place_id.isdigit():
            raise ValueError("INVALID_PLACE_ID")
        return f"https://pcmap.place.naver.com/restaurant/{place_id}/{page}"


def _merge_detail(base: PlaceDetail, extra: PlaceDetail) -> PlaceDetail:
    return replace(
        base,
        name=base.name or extra.name,
        category=base.category or extra.category,
        category_code=base.category_code or extra.category_code,
        address=base.address or extra.address,
        road_address=base.road_address or extra.road_address,
        latitude=base.latitude if base.latitude is not None else extra.latitude,
        longitude=base.longitude if base.longitude is not None else extra.longitude,
        phone=base.phone or extra.phone,
        virtual_phone=base.virtual_phone or extra.virtual_phone,
        description=base.description or extra.description,
        homepage=base.homepage or extra.homepage,
        image_url=base.image_url or extra.image_url,
        menus=base.menus or extra.menus,
        menu_count=base.menu_count if base.menu_count is not None else extra.menu_count,
        business_hours=base.business_hours or extra.business_hours,
        review_keywords=base.review_keywords or extra.review_keywords,
        review_menu_mentions=base.review_menu_mentions or extra.review_menu_mentions,
        voted_keywords=base.voted_keywords or extra.voted_keywords,
        representative_reviews=base.representative_reviews or extra.representative_reviews,
        visitor_reviews_total=base.visitor_reviews_total or extra.visitor_reviews_total,
        visitor_reviews_score=base.visitor_reviews_score or extra.visitor_reviews_score,
        visitor_text_review_total=base.visitor_text_review_total or extra.visitor_text_review_total,
        cafe_blog_reviews_total=base.cafe_blog_reviews_total or extra.cafe_blog_reviews_total,
    )
