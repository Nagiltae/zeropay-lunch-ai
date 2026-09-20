"""Run DOM-only detail collection for already verified Place IDs."""

# ruff: noqa: E501

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from time import monotonic

from playwright.sync_api import sync_playwright

from app.place_dom_detail_crawler import PlaceDomDetailCrawler
from app.place_resolver_cli import load_local_env, load_verified_checkpoint, preflight

FIELDS = [
    "restaurant_id", "place_id", "resolved_name", "home", "hours", "menu_page",
    "menu_cards", "menu_status", "visitor_total", "blog_total", "keyword_count",
    "menu_mention_count", "theme_count", "representative_count", "review_status",
    "detail_status", "diagnostics", "elapsed_ms",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    load_local_env(root)
    checkpoint = args.checkpoint or root / "ai/build/reports/naver-place-pipeline/verified-place-ids.csv"
    preflight(root, args.output, False, require_resolver=True)
    rows = list(load_verified_checkpoint(checkpoint).values())[: args.limit]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    crawler = PlaceDomDetailCrawler()
    with args.output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_default_timeout(3_000)
            try:
                for index, row in enumerate(rows, 1):
                    started = monotonic()
                    detail = crawler.collect(page, row["place_id"])
                    diagnostics = {
                        "url": page.url,
                        "body_length": len(page.locator("body").inner_text(timeout=3000) or ""),
                        "visitor_text": "방문자리뷰" in (page.locator("body").inner_text(timeout=3000) or ""),
                        "blog_text": "블로그리뷰" in (page.locator("body").inner_text(timeout=3000) or ""),
                        "keyword_heading": "이런 점이 좋았어요" in (page.locator("body").inner_text(timeout=3000) or ""),
                        "chartmore": page.locator('a[data-nlog-area="plc_rrv.chartmore"]').count(),
                        "menufilter": page.locator('a[data-nlog-area="plc_rrv.menufilter"]').count(),
                        "filter": page.locator('a[data-nlog-area="plc_rrv.filter"]').count(),
                        "review_list": page.locator("#_review_list").count(),
                        "rvshowmore": page.locator('[data-pui-click-code="rvshowmore"]').count(),
                    }
                    body_text = page.locator("body").inner_text(timeout=3000) or ""
                    menu_status = (
                        "SUCCESS" if detail.menus else
                        "PARSE_FAILED" if any(token in body_text for token in ("원", "메뉴")) else
                        "NO_DATA"
                    )
                    review_status = (
                        "SUCCESS" if detail.review_total is not None or detail.review_keywords or detail.representative_reviews else
                        "PARSE_FAILED" if diagnostics["keyword_heading"] or diagnostics["review_list"] else
                        "NO_DATA"
                    )
                    writer.writerow({
                        "restaurant_id": row["restaurant_id"], "place_id": row["place_id"],
                        "resolved_name": row.get("resolved_name", ""), "home": detail.home_success,
                        "hours": "SUCCESS" if detail.business_hours else "NO_DATA",
                        "menu_page": detail.menu_page_success, "menu_cards": len(detail.menus),
                        "menu_status": menu_status,
                        "visitor_total": detail.review_total or "", "blog_total": detail.blog_review_total or "",
                        "keyword_count": len(detail.review_keywords), "menu_mention_count": len(detail.review_menu_mentions),
                        "theme_count": len(detail.review_themes), "representative_count": len(detail.representative_reviews),
                        "review_status": review_status,
                        "detail_status": detail.status, "diagnostics": diagnostics,
                        "elapsed_ms": int((monotonic() - started) * 1000),
                    })
                    stream.flush()
                    print(f"[{index}/{len(rows)}] {row.get('resolved_name')} {detail.status}")
            finally:
                browser.close()
    print(f"CSV: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
