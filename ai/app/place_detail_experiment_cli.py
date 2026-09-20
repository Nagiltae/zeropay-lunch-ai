"""Compare Apollo and rendered DOM extraction on a deterministic MATCHED sample."""

# ruff: noqa: E501

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from time import monotonic

from playwright.sync_api import sync_playwright

from app.place_apollo_parser import parse_place_detail_state
from app.place_dom_detail_crawler import PlaceDomDetailCrawler
from app.place_resolver import ResolutionStatus, query_for
from app.place_resolver_cli import (
    load_komsco_population,
    load_local_env,
    preflight,
    run_one,
)
from app.qwen_candidate_matcher import OllamaClient, QwenCandidateMatcher

FIELDS = [
    "restaurant_id", "name", "place_id", "resolve_status", "matcher_source", "qwen_used",
    "apollo_state", "apollo_entities", "apollo_place_entities", "apollo_menu_entities",
    "apollo_review_entities", "apollo_hours_entities", "apollo_base", "apollo_menu",
    "apollo_hours", "apollo_review_stats", "apollo_keywords", "dom_base", "dom_menu",
    "dom_hours", "dom_review_stats", "dom_keywords", "dom_reviews", "dom_sections",
    "apollo_ms", "dom_ms", "dom_status", "dom_declared_menu_count", "dom_menu_count",
    "dom_hours_count", "dom_keyword_count", "dom_menu_mention_count", "dom_theme_count",
    "dom_representative_count", "reason",
]


def _entity_counts(state: object) -> tuple[int, int, int, int, int]:
    if not isinstance(state, dict):
        return 0, 0, 0, 0, 0
    keys = list(state)
    return (
        len(keys),
        sum("PlaceDetail" in key for key in keys),
        sum("Menu" in key for key in keys),
        sum("Review" in key or "review" in key for key in keys),
        sum("Business" in key or "business" in key for key in keys),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    load_local_env(root)
    preflight(root, args.output, False, require_resolver=True)
    population = load_komsco_population(root, args.limit)
    refs = list(population.references)[: args.limit]
    matcher = QwenCandidateMatcher(OllamaClient())
    dom_crawler = PlaceDomDetailCrawler()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    started = monotonic()
    with args.output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_default_timeout(3_000)
            try:
                for index, reference in enumerate(refs, 1):
                    query = query_for(reference)
                    result = run_one(page, reference, query, "KOMSCO", matcher)
                    assert result is not None
                    row = {field: "" for field in FIELDS}
                    row.update(
                        restaurant_id=reference.restaurant_id,
                        name=reference.komsco_name,
                        place_id=result.place_id or "",
                        resolve_status=result.resolution.status.value,
                        matcher_source=result.matcher_source,
                        qwen_used=result.qwen_used,
                        reason=";".join(result.resolution.risk_flags),
                    )
                    if result.place_id and result.resolution.status == ResolutionStatus.RESOLVED:
                        page.goto(
                            f"https://pcmap.place.naver.com/restaurant/{result.place_id}/home",
                            wait_until="domcontentloaded",
                            timeout=15_000,
                        )
                        apollo_started = monotonic()
                        state = page.evaluate("() => window.__APOLLO_STATE__ || null")
                        row["apollo_ms"] = int((monotonic() - apollo_started) * 1000)
                        entities = _entity_counts(state)
                        for key, value in zip(
                            ("apollo_entities", "apollo_place_entities", "apollo_menu_entities", "apollo_review_entities", "apollo_hours_entities"),
                            entities,
                            strict=True,
                        ):
                            row[key] = value
                        row["apollo_state"] = bool(isinstance(state, dict))
                        if isinstance(state, dict):
                            try:
                                detail = parse_place_detail_state(state, result.place_id)
                                row.update(
                                    apollo_base=detail.name is not None and detail.address is not None,
                                    apollo_menu=bool(detail.menus),
                                    apollo_hours=bool(detail.business_hours),
                                    apollo_review_stats=detail.visitor_reviews_total is not None,
                                    apollo_keywords=bool(detail.review_keywords or detail.voted_keywords),
                                )
                            except Exception as error:
                                row["reason"] = f"{row['reason']};APOLLO:{type(error).__name__}"
                        dom_started = monotonic()
                        dom = dom_crawler.collect(page, result.place_id)
                        row["dom_ms"] = int((monotonic() - dom_started) * 1000)
                        row.update(
                            dom_status=dom.status,
                            dom_base=dom.home_success and bool(dom.name and dom.address),
                            dom_menu=bool(dom.menus),
                            dom_hours=bool(dom.business_hours),
                            dom_review_stats=dom.review_total is not None,
                            dom_keywords=bool(dom.review_keywords),
                            dom_reviews=bool(dom.representative_reviews),
                            dom_declared_menu_count=dom.declared_menu_count or "",
                            dom_menu_count=len(dom.menus),
                            dom_hours_count=len(dom.business_hours),
                            dom_keyword_count=len(dom.review_keywords),
                            dom_menu_mention_count=len(dom.review_menu_mentions),
                            dom_theme_count=len(dom.review_themes),
                            dom_representative_count=len(dom.representative_reviews),
                        )
                    writer.writerow(row)
                    stream.flush()
                    print(f"[{index}/{len(refs)}] {reference.komsco_name} {result.resolution.status.value}")
            finally:
                browser.close()
    print(f"Experiment complete: {len(refs)} rows in {monotonic() - started:.1f}s")
    print(f"CSV: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
