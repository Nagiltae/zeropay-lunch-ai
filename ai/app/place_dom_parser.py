"""DOM 상세 수집에서 메뉴 가격 문자열을 보수적으로 해석하는 공통 parser."""

# ruff: noqa: E501

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class DomDetailEvidence:
    name: str | None
    category: str | None
    address: str | None
    phone: str | None
    menu_count: int
    priced_menu_count: int
    hours_count: int
    review_total: int | None
    blog_review_total: int | None
    review_keyword_count: int
    representative_review_count: int
    sections: tuple[str, ...]
    selector_strategy: str = "semantic-text/role/aria"

    @property
    def base_available(self) -> bool:
        return bool(self.name and (self.address or self.category))


_PRICE = re.compile(r"(?:₩|￦)?\d[\d,]*\s*원")
_REVIEW = re.compile(r"방문자\s*리뷰\s*([\d,]+)")
_BLOG = re.compile(r"블로그\s*리뷰\s*([\d,]+)")
_PHONE = re.compile(r"(?:0\d{1,2}[- .])\d{3,4}[- .]\d{4}")
_ADDRESS = re.compile(r"(?:서울(?:특별시)?|서울시)\s+강남구\s+[^\n]+")


def parse_rendered_text(text: str) -> DomDetailEvidence:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    sections = tuple(
        heading for heading in ("메뉴", "영업시간", "방문자 리뷰", "편의", "리뷰")
        if any(heading in line for line in lines)
    )
    name = lines[0] if lines else None
    category = next((line for line in lines if ">" in line or "음식점" in line), None)
    address_match = _ADDRESS.search(text)
    phone_match = _PHONE.search(text)
    prices = _PRICE.findall(text)
    menu_lines = 0
    for index, line in enumerate(lines):
        if _PRICE.search(line) and index:
            menu_lines += 1
    review_match = _REVIEW.search(text)
    blog_match = _BLOG.search(text)
    keyword_count = sum(1 for line in lines if any(token in line for token in ("맛", "서비스", "분위기", "가성비")))
    review_count = sum(1 for line in lines if len(line) >= 20 and "리뷰" not in line)
    hours_count = sum(1 for line in lines if re.search(r"(?:월|화|수|목|금|토|일).*(?:\d{1,2}:\d{2})", line))
    return DomDetailEvidence(
        name=name,
        category=category,
        address=address_match.group(0) if address_match else None,
        phone=phone_match.group(0) if phone_match else None,
        menu_count=menu_lines,
        priced_menu_count=len(prices),
        hours_count=hours_count,
        review_total=int(review_match.group(1).replace(",", "")) if review_match else None,
        blog_review_total=int(blog_match.group(1).replace(",", "")) if blog_match else None,
        review_keyword_count=keyword_count,
        representative_review_count=review_count if "방문자 리뷰" in sections else 0,
        sections=sections,
    )


def parse_page(page) -> DomDetailEvidence:
    return parse_rendered_text(page.locator("body").inner_text(timeout=5_000) or "")
