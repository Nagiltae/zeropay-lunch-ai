"""공개 PCMap 상세 화면에서 수집한 음식점 section 모델."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BusinessHour:
    day: str
    open_time: str | None = None
    close_time: str | None = None
    break_hours: str | None = None
    last_order: str | None = None
    description: str | None = None
    regular_closed_day: str | None = None
    irregular_closed_day: str | None = None
    business_status: str | None = None


@dataclass(frozen=True)
class MenuItem:
    external_menu_id: str
    menu_type: str | None
    name: str
    description: str | None = None
    price_value: int | None = None
    price_text: str | None = None
    price_type: str | None = None
    is_set_menu: bool | None = None
    thumbnail_url: str | None = None
    badges: tuple[str, ...] = ()
    labels: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReviewKeyword:
    keyword: str
    count: int | None = None
    kind: str = "theme"


@dataclass(frozen=True)
class ReviewItem:
    review_id: str
    review_text: str
    review_date: str | None = None
    visit_count: int | None = None
    visit_purpose: str | None = None
    selected_keywords: tuple[str, ...] = ()
    rating: float | None = None
    image_urls: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlaceDetail:
    place_id: str
    name: str | None = None
    category: str | None = None
    category_code: str | None = None
    address: str | None = None
    road_address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    phone: str | None = None
    virtual_phone: str | None = None
    conveniences: tuple[str, ...] = ()
    payment_info: tuple[str, ...] = ()
    description: str | None = None
    homepage: str | None = None
    image_url: str | None = None
    visitor_reviews_total: int | None = None
    visitor_reviews_score: float | None = None
    visitor_text_review_total: int | None = None
    cafe_blog_reviews_total: int | None = None
    business_hours: tuple[BusinessHour, ...] = ()
    menus: tuple[MenuItem, ...] = ()
    menu_count: int | None = None
    review_keywords: tuple[ReviewKeyword, ...] = ()
    review_menu_mentions: tuple[ReviewKeyword, ...] = ()
    voted_keywords: tuple[ReviewKeyword, ...] = ()
    representative_reviews: tuple[ReviewItem, ...] = ()
    raw_source: str = "APOLLO"
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def menu_complete(self) -> bool:
        return self.menu_count is not None and len(self.menus) >= self.menu_count
