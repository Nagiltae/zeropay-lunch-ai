"""PCMap DOM에서 HOME/MENU/HOURS/REVIEW 상세 evidence를 수집한다."""

# ruff: noqa: E501

from __future__ import annotations

import re
from dataclasses import dataclass

from app.naver.place_detail_models import (
    BusinessHour,
    MenuItem,
    PlaceDetail,
    ReviewItem,
    ReviewKeyword,
)
from app.naver.place_dom_parser import _PRICE


_HOUR_RANGE = re.compile(
    r"(?P<day>매일|평일|주말|월|화|수|목|금|토|일)"
    r"[^\d]{0,80}(?P<open>\d{1,2}:\d{2})\s*[-~]\s*(?P<close>\d{1,2}:\d{2})"
)


@dataclass(frozen=True)
class DomCollectedDetail:
    home_success: bool
    name: str | None
    category: str | None
    address: str | None
    phone: str | None
    conveniences: tuple[str, ...]
    business_hours: tuple[str, ...]
    menu_page_success: bool
    declared_menu_count: int | None
    menus: tuple[dict[str, str | None], ...]
    review_page_success: bool
    review_total: int | None
    blog_review_total: int | None
    review_keywords: tuple[dict[str, str | int], ...]
    review_menu_mentions: tuple[dict[str, str | int], ...]
    review_themes: tuple[dict[str, str | int], ...]
    representative_reviews: tuple[dict[str, str], ...]
    warnings: tuple[str, ...] = ()
    menu_requested: bool = True
    review_requested: bool = True
    hours_collection_success: bool = True

    @property
    def home_status(self) -> str:
        return "SUCCESS" if self.home_success else "LOAD_FAILED"

    @property
    def hours_status(self) -> str:
        if not self.hours_collection_success:
            return "FAILED"
        return "SUCCESS" if self.business_hours else "ABSENT_CONFIRMED"

    @property
    def menu_status(self) -> str:
        if not self.menu_requested:
            return "SKIPPED"
        if self.menus:
            return "SUCCESS"
        return "ABSENT_CONFIRMED" if self.menu_page_success else "FAILED"

    @property
    def review_status(self) -> str:
        if not self.review_requested:
            return "SKIPPED"
        if (
            self.review_total is not None
            or self.blog_review_total is not None
            or self.review_keywords
            or self.review_menu_mentions
            or self.review_themes
            or self.representative_reviews
        ):
            return "SUCCESS"
        return "ABSENT_CONFIRMED" if self.review_page_success else "FAILED"

    @property
    def menu_complete(self) -> bool:
        return self.declared_menu_count is not None and len(self.menus) >= self.declared_menu_count

    @property
    def status(self) -> str:
        base = self.home_success and bool(self.name and self.address)
        semantic = bool(self.review_keywords or self.review_menu_mentions or self.review_themes)
        if base and self.menu_complete and self.business_hours and semantic:
            return "SUCCESS"
        if base or self.menu_page_success or self.review_page_success:
            return "PARTIAL"
        return "FAILED"

    def to_place_detail(self, place_id: str) -> PlaceDetail:
        """Map the DOM result to the shared persistence model without Apollo."""
        menus = tuple(
            MenuItem(
                external_menu_id=f"dom-{index}",
                menu_type=None,
                name=str(item.get("name") or ""),
                description=item.get("description"),
                price_value=int(item["price_value"]) if item.get("price_value") else None,
                price_text=item.get("price_text"),
                thumbnail_url=item.get("image_url"),
            )
            for index, item in enumerate(self.menus, 1)
            if item.get("name")
        )
        # DOM 원문을 그대로 day에 넣으면 정상 시간도 open/close가 NULL로 저장된다.
        # 시간 범위가 실제로 보일 때만 구조화하고, 상태 문구만 있는 경우에는
        # 임의의 반복 영업시간을 추론하지 않도록 원문을 description으로 보존한다.
        hours = tuple(
            self._parse_business_hour(raw) for raw in self.business_hours if raw
        )
        keywords = tuple(
            ReviewKeyword(str(item.get("keyword") or ""), item.get("count"), "theme")
            for item in self.review_keywords
            if item.get("keyword")
        )
        mentions = tuple(
            ReviewKeyword(str(item.get("keyword") or ""), item.get("count"), "menu")
            for item in self.review_menu_mentions
            if item.get("keyword")
        )
        themes = tuple(
            ReviewKeyword(str(item.get("keyword") or ""), item.get("count"), "theme")
            for item in self.review_themes
            if item.get("keyword")
        )
        reviews = tuple(
            ReviewItem(f"dom-{index}", str(item.get("text") or ""))
            for index, item in enumerate(self.representative_reviews, 1)
            if item.get("text")
        )
        return PlaceDetail(
            place_id=place_id,
            name=self.name,
            category=self.category,
            address=self.address,
            phone=self.phone,
            conveniences=self.conveniences,
            visitor_reviews_total=self.review_total,
            cafe_blog_reviews_total=self.blog_review_total,
            business_hours=hours,
            menus=menus,
            menu_count=self.declared_menu_count,
            review_keywords=keywords,
            review_menu_mentions=mentions,
            voted_keywords=themes,
            representative_reviews=reviews,
            raw_source="PLAYWRIGHT_DOM",
            warnings=self.warnings,
        )

    @staticmethod
    def _parse_business_hour(raw: str) -> BusinessHour:
        match = _HOUR_RANGE.search(raw)
        if not match:
            return BusinessHour(day=raw[:32], description=raw)
        return BusinessHour(
            day=match.group("day"),
            open_time=match.group("open"),
            close_time=match.group("close"),
            description=raw,
        )


def _text(locator, timeout: int = 1500) -> str:
    try:
        return " ".join((locator.inner_text(timeout=timeout) or "").split())
    except Exception:
        return ""


def _click(locator) -> bool:
    try:
        locator.click(timeout=2500)
        return True
    except Exception:
        return False


def _label_row(page, label: str) -> str:
    labels = page.locator("span.place_blind").filter(has_text=label)
    if not labels.count():
        return ""
    try:
        return _text(labels.first.locator("xpath=.."))
    except Exception:
        return _text(labels.first)


def _pairs(locator) -> tuple[dict[str, str | int], ...]:
    result = []
    for index in range(locator.count()):
        text = _text(locator.nth(index))
        if not text:
            continue
        count_match = re.search(r"([\d,]+)\s*(?:회|명|건)?\s*$", text)
        count = int(count_match.group(1).replace(",", "")) if count_match else None
        key = text[: count_match.start()].strip() if count_match else text
        result.append({"keyword": key, "count": count or 0})
    return tuple(result)


def _semantic_pairs(page, marker: str) -> tuple[dict[str, str | int], ...]:
    """Read keyword rows through their semantic marker, not generated classes."""
    marker_nodes = page.get_by_text(marker, exact=False)
    rows = []
    for index in range(marker_nodes.count()):
        node = marker_nodes.nth(index)
        try:
            row = node.locator("xpath=ancestor::*[@role='listitem' or self::li][1]")
            if not row.count():
                row = node.locator("xpath=..").locator("xpath=..")
            text = _text(row)
        except Exception:
            text = _text(node)
        if text:
            rows.append(text)
    values = []
    for text in dict.fromkeys(rows):
        count_match = re.search(r"([\d,]+)\s*(?:회|명|건)?", text)
        if not count_match:
            continue
        count = int(count_match.group(1).replace(",", ""))
        keyword = text[: count_match.start()].strip(" ·:")
        if keyword and keyword != marker:
            values.append({"keyword": keyword, "count": count})
    return tuple(values)


class PlaceDomDetailCrawler:
    # NAVER 내부 상태가 아니라 사용자에게 렌더링된 DOM contract만 읽어 상세 데이터를 만든다.
    def collect(
        self,
        page,
        place_id: str,
        *,
        include_menu: bool = True,
        include_reviews: bool = True,
        before_navigation=None,
    ) -> DomCollectedDetail:
        warnings: list[str] = []
        home_url = f"https://pcmap.place.naver.com/restaurant/{place_id}/home"
        try:
            if f"/restaurant/{place_id}/home" in page.url:
                home_success = True
            else:
                if before_navigation:
                    before_navigation()
                response = page.goto(home_url, wait_until="domcontentloaded", timeout=15_000)
                self._check_response(response)
                home_success = bool(response and response.ok)
            self._ensure_place(page, place_id)
        except RuntimeError as error:
            if str(error).startswith("BLOCKED:"):
                raise
            return self._failed(f"HOME:{type(error).__name__}")
        except Exception as error:
            return self._failed(f"HOME:{type(error).__name__}")
        body = _text(page.locator("body"), 3000)
        self._check_body_access(body)
        if not body:
            return self._failed("HOME_BLOCKED_OR_EMPTY")
        try:
            name = page.locator('meta[property="og:title"]').get_attribute(
                "content", timeout=1000
            ) or _text(page.locator("h1").first)
            category = page.locator('meta[property="og:description"]').get_attribute(
                "content", timeout=1000
            ) or _label_row(page, "카테고리")
        except Exception:
            name = _text(page.locator("h1").first)
            category = _label_row(page, "카테고리")
        address = _label_row(page, "주소")
        phone = _label_row(page, "전화번호")
        convenience_text = _label_row(page, "편의")
        conveniences = tuple(
            item.strip() for item in re.split(r"[,·]", convenience_text) if item.strip()
        )
        try:
            hours = self._hours(page)
            hours_collection_success = True
        except Exception as error:
            warnings.append(f"HOURS:{type(error).__name__}")
            hours = ()
            hours_collection_success = False
        declared = self._declared_menu_count(body)
        if include_menu:
            try:
                menus, menu_success = self._menus(page, place_id, before_navigation=before_navigation)
            except RuntimeError as error:
                if str(error).startswith("BLOCKED:"):
                    raise
                warnings.append(str(error))
                menus, menu_success = (), False
        else:
            menus, menu_success = (), True
        if include_reviews:
            try:
                review = self._reviews(page, place_id, before_navigation=before_navigation)
            except RuntimeError as error:
                if str(error).startswith("BLOCKED:"):
                    raise
                warnings.append(str(error))
                review = {
                    "success": False,
                    "total": None,
                    "blog": None,
                    "keywords": (),
                    "mentions": (),
                    "themes": (),
                    "representative": (),
            }
        else:
            review = {
                "success": True,
                "total": None,
                "blog": None,
                "keywords": (),
                "mentions": (),
                "themes": (),
                "representative": (),
            }
        return DomCollectedDetail(
            home_success,
            name or None,
            category or None,
            address or None,
            phone or None,
            conveniences,
            hours,
            menu_success,
            declared,
            menus,
            review["success"],
            review["total"],
            review["blog"],
            review["keywords"],
            review["mentions"],
            review["themes"],
            review["representative"],
            tuple(warnings),
            include_menu,
            include_reviews,
            hours_collection_success,
        )

    def _hours(self, page) -> tuple[str, ...]:
        button = page.locator('a[data-nlog-area="plc_btp.bzhour"]')
        body = _text(page.locator("body"), 3000)
        if not button.count() and "영업시간" not in body:
            raise RuntimeError("HOURS_PARSE_FAILED")
        if button.count() and button.first.get_attribute("aria-expanded") != "true":
            _click(button.first)
        expanded = page.locator('a[data-nlog-area="plc_btp.bzhour"]')
        container = expanded.first.locator("xpath=..") if expanded.count() else page.locator("body")
        text = _text(container)
        return tuple(
            line.strip()
            for line in text.split("  ")
            if re.search(r"(?:월|화|수|목|금|토|일|휴무|브레이크|라스트)", line)
        )

    @staticmethod
    def _declared_menu_count(body: str) -> int | None:
        # A bare ``메뉴,`` label is present on some pages; it is not a count.
        match = re.search(r"메뉴\s*(\d[\d,]*)", body)
        return int(match.group(1).replace(",", "")) if match else None

    def _menus(
        self, page, place_id: str, *, before_navigation=None
    ) -> tuple[tuple[dict[str, str | None], ...], bool]:
        # The integrated pipeline uses the stable public menu URL directly.
        # Preview links can lead to booking/ordering pages for some places.
        if before_navigation:
            before_navigation()
        response = page.goto(
            f"https://pcmap.place.naver.com/restaurant/{place_id}/menu/list",
            wait_until="domcontentloaded",
            timeout=15_000,
        )
        self._check_response(response)
        self._ensure_place(page, place_id)
        self._check_body_access(_text(page.locator("body"), 3000))
        try:
            page.locator('a[data-nlog-area="plc_bmv.menu"]').first.wait_for(
                state="visible", timeout=5000
            )
        except Exception:
            # 메뉴 탭/섹션 자체가 확인되지 않으면 DOM 변경 또는 파싱 실패로 본다.
            # 화면에 메뉴 안내가 명시된 경우에만 정상적인 빈 메뉴 snapshot으로 인정한다.
            body = _text(page.locator("body"), 3000)
            return (), bool(re.search(r"(?:메뉴|메뉴판)", body))
        cards = page.locator('a[data-nlog-area="plc_bmv.menu"]')
        menus = []
        for index in range(cards.count()):
            raw = cards.nth(index).inner_text(timeout=1500) or ""
            menus.append(self._parse_menu_card_text(raw))
        return tuple(menus), True

    @staticmethod
    def _parse_menu_card_text(raw: str) -> dict[str, str | None]:
        """Use rendered card line structure so descriptions never become names."""
        lines = [line.strip() for line in raw.splitlines() if line.strip()]

        # Remove known badges that appear as their own line above the name
        if lines and lines[0] in {"대표", "추천", "HIT", "NEW", "BEST", "인기"}:
            lines = lines[1:]

        text = " ".join(lines)
        prices = _PRICE.findall(text)
        price = prices[-1] if prices else None
        non_price = [line for line in lines if not _PRICE.fullmatch(line)]
        name = (
            non_price[0]
            if non_price
            else (text.replace(price or "", "").strip() if price else text)
        )
        description = " ".join(non_price[1:]) or None
        value = str(int(price.replace(",", "").replace("원", ""))) if price else None
        return {"name": name, "description": description, "price_text": price, "price_value": value}

    def _reviews(self, page, place_id: str, *, before_navigation=None) -> dict[str, object]:
        if before_navigation:
            before_navigation()
        response = page.goto(
            f"https://pcmap.place.naver.com/restaurant/{place_id}/review/visitor",
            wait_until="domcontentloaded",
            timeout=15_000,
        )
        self._check_response(response)
        self._ensure_place(page, place_id)
        self._check_body_access(_text(page.locator("body"), 3000))
        visitor = page.locator('a[data-nlog-area="plc_rrv.rrvtab"]')
        if visitor.count() and visitor.first.get_attribute("aria-selected") != "true":
            _click(visitor.first)
        body = _text(page.locator("body"), 3000)
        if not visitor.count() and not re.search(r"(?:방문자\s*리뷰|블로그\s*리뷰)", body):
            return {
                "success": False,
                "total": None,
                "blog": None,
                "keywords": (),
                "mentions": (),
                "themes": (),
                "representative": (),
            }
        try:
            meta_description = (
                page.locator('meta[property="og:description"]').get_attribute(
                    "content", timeout=3000
                )
                or ""
            )
        except Exception:
            meta_description = ""
        total = self._number_after(meta_description or body, "방문자\\s*리뷰")
        blog = self._number_after(meta_description or body, "블로그\\s*리뷰")
        chart = page.locator('a[data-nlog-area="plc_rrv.chartmore"]')
        if chart.count():
            _click(chart.first)
        keywords = _semantic_pairs(page, "이 키워드를 선택한 인원")
        mentions = _pairs(page.locator('a[data-nlog-area="plc_rrv.menufilter"]'))
        themes = _pairs(page.locator('a[data-nlog-area="plc_rrv.filter"]'))
        cards = page.locator("#_review_list [data-pui-click-code=rvshowmore]")
        representative = tuple({"text": _text(cards.nth(i))} for i in range(min(cards.count(), 10)))
        return {
            "success": bool(body),
            "total": total,
            "blog": blog,
            "keywords": keywords,
            "mentions": mentions,
            "themes": themes,
            "representative": representative,
        }

    @staticmethod
    def _number_after(text: str, label: str) -> int | None:
        match = re.search(label + r"\s*([\d,]+)", text)
        return int(match.group(1).replace(",", "")) if match else None

    @staticmethod
    def _failed(reason: str) -> DomCollectedDetail:
        return DomCollectedDetail(
            False,
            None,
            None,
            None,
            None,
            (),
            (),
            False,
            None,
            (),
            False,
            None,
            None,
            (),
            (),
            (),
            (),
            (reason,),
        )

    @staticmethod
    def _ensure_place(page, place_id: str) -> None:
        if f"/restaurant/{place_id}/" not in page.url:
            raise RuntimeError(f"PLACE_ID_URL_MISMATCH:{page.url}")

    @staticmethod
    def _check_response(response) -> None:
        if response is not None and response.status in (403, 429):
            raise RuntimeError(f"BLOCKED: HTTP {response.status}")

    @staticmethod
    def _check_body_access(body: str) -> None:
        if any(marker in body.upper() for marker in ("접근이 제한", "비정상적인 접근", "CAPTCHA")):
            raise RuntimeError("BLOCKED: access restriction")
