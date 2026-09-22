"""확정된 numeric Place ID의 HOME/MENU/HOURS/REVIEW를 보완 수집하는 CLI.

section별 완료 상태를 독립적으로 확인하며 403/429/CAPTCHA/BLOCKED는 우회하지
않고 중단한다. 기존 정상 section은 persistence 단계에서 보호한다.
"""

import argparse
import os
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

from playwright.sync_api import sync_playwright

from app.batch.batch_progress import BatchProgress
from app.batch.place_request_limiter import NavigationRateLimiter, TransientRetryPolicy
from app.naver.place_detail_models import PlaceDetail
from app.naver.place_detail_persistence import PlaceDetailPersistence
from app.naver.place_dom_detail_crawler import PlaceDomDetailCrawler
from app.naver.playwright_lifecycle import PlaywrightLifecycle, is_playwright_lifecycle_error
from app.providers.provider_input import load_local_env


def _is_blocked_error(error: Exception) -> bool:
    message = str(error).upper()
    return any(token in message for token in ("403", "429", "CAPTCHA", "BLOCKED"))


def _timestamp_is_stale(
    value: str | None,
    stale_after_seconds: float | None,
    now: datetime,
) -> bool:
    if stale_after_seconds is None:
        return False
    if not value or value in {"NULL", "None"}:
        return True
    try:
        crawled_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return True
    if crawled_at.tzinfo is not None and now.tzinfo is None:
        now = now.replace(tzinfo=crawled_at.tzinfo)
    elif crawled_at.tzinfo is None and now.tzinfo is not None:
        crawled_at = crawled_at.replace(tzinfo=now.tzinfo)
    return now - crawled_at > timedelta(seconds=stale_after_seconds)


def _missing_sections(
    row: dict[str, str],
    *,
    stale_after_seconds: float | None = None,
    now: datetime | None = None,
    force_refresh: bool = False,
) -> dict[str, bool]:
    """A summary proves HOME succeeded, but not that MENU or hours were collected."""
    now = now or datetime.now()
    review_missing = row["has_review"] == "0"
    menu_missing = row["has_menu"] == "0" or row["has_price"] == "0"
    hours_missing = row["has_hours"] == "0"
    if force_refresh:
        return {"review": True, "menu": True, "business_hours": True}
    return {
        "review": review_missing
        or (
            not review_missing
            and _timestamp_is_stale(
                row.get("review_crawled_at"),
                stale_after_seconds,
                now,
            )
        ),
        "menu": menu_missing
        or (
            not menu_missing
            and _timestamp_is_stale(
                row.get("menu_crawled_at"),
                stale_after_seconds,
                now,
            )
        ),
        "business_hours": hours_missing
        or (
            not hours_missing
            and _timestamp_is_stale(
                row.get("hours_crawled_at"),
                stale_after_seconds,
                now,
            )
        ),
    }


def _sections_to_persist(missing: dict[str, bool], review_page_success: bool) -> dict[str, bool]:
    return {**missing, "review": missing["review"] and review_page_success}


def _pending_detail_rows(
    rows: list[dict[str, str]],
    limit: int,
    *,
    stale_after_seconds: float | None = None,
    now: datetime | None = None,
    force_refresh: bool = False,
) -> tuple[list[dict[str, str]], int]:
    pending = [
        row
        for row in rows
        if any(
            _missing_sections(
                row,
                stale_after_seconds=stale_after_seconds,
                now=now,
                force_refresh=force_refresh,
            ).values()
        )
    ]
    return pending[:limit], len(rows) - len(pending)


def _detail_stale_after_seconds() -> float | None:
    raw = os.environ.get("NAVER_DETAIL_STALE_AFTER_SECONDS", "2592000").strip().lower()
    if raw in {"", "off", "none", "disabled"}:
        return None
    try:
        value = float(raw)
    except ValueError as error:
        raise ValueError("NAVER_DETAIL_STALE_AFTER_SECONDS must be numeric or off") from error
    return value if value > 0 else None


def _collected_sections_complete(
    missing: dict[str, bool],
    detail: PlaceDetail | None,
    review_page_success: bool,
) -> bool:
    if detail is None:
        return False
    priced_menu = any(
        (item.price_value is not None and item.price_value > 0)
        or bool(item.price_text and item.price_text.strip())
        for item in detail.menus
    )
    return (
        (not missing["review"] or review_page_success)
        and (not missing["menu"] or priced_menu)
        and (not missing["business_hours"] or bool(detail.business_hours))
    )


def _execute_sql_read(sql: str) -> list[dict[str, str]]:
    command = [
        "docker",
        "compose",
        "exec",
        "-T",
        "mysql",
        "sh",
        "-c",
        f'MYSQL_PWD="zeropay_local" mysql --default-character-set=utf8mb4 '
        f'--batch -u zeropay zeropay_lunch -e "{sql}"',
    ]
    process = subprocess.run(command, capture_output=True, text=True)
    if process.returncode != 0:
        raise RuntimeError(f"MySQL query failed: {process.stderr}")

    rows = []
    lines = process.stdout.strip().split("\n")
    if len(lines) > 1:
        headers = lines[0].split("\t")
        for line in lines[1:]:
            cols = line.split("\t")
            rows.append(dict(zip(headers, cols, strict=True)))
    return rows


def main():
    # Place ID가 확정된 음식점만 section별로 보완하며, 429/차단은 우회하지 않고 안전하게 중단한다.
    parser = argparse.ArgumentParser(description="Step 7 NAVER Detail Enrichment")
    parser.add_argument("--limit", type=int, default=3, help="Smoke test limit")
    parser.add_argument(
        "--restaurant-ids", help="Comma-separated restaurant IDs for a bounded preflight"
    )
    parser.add_argument("--dry-run", action="store_true", help="Do not write to DB")
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Refresh all eligible detail sections, including fresh complete rows",
    )
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")
    id_filter = ""
    if args.restaurant_ids:
        try:
            ids = [int(value) for value in args.restaurant_ids.split(",")]
        except ValueError:
            parser.error("--restaurant-ids must contain only integers")
        if not ids or any(value < 1 for value in ids) or len(ids) > args.limit:
            parser.error("--restaurant-ids requires 1..limit positive IDs")
        id_filter = f"AND c.restaurant_id IN ({','.join(map(str, ids))})"

    root = Path(__file__).resolve().parent.parent.parent
    load_local_env(root)
    stale_after_seconds = _detail_stale_after_seconds()
    now = datetime.now()

    print(f"Fetching up to {args.limit} candidates for detail enrichment...")
    sql = f"""
    SELECT c.restaurant_id, c.name, e.external_place_id, e.provider,
           IF(h.id IS NULL, 0, 1) AS has_review,
           h.crawled_at AS review_crawled_at,
           IF(m.restaurant_id IS NULL, 0, 1) AS has_menu,
           COALESCE(m.has_price, 0) AS has_price,
           m.crawled_at AS menu_crawled_at,
           IF(b.restaurant_id IS NULL, 0, 1) AS has_hours
           ,b.crawled_at AS hours_crawled_at
    FROM canonical_restaurants c
    JOIN restaurant_external_places e ON c.restaurant_id = e.restaurant_id
    JOIN restaurants r ON c.restaurant_id = r.id
    LEFT JOIN restaurant_review_summaries h ON c.restaurant_id = h.restaurant_id
      AND h.provider = e.provider AND h.external_place_id = e.external_place_id
    LEFT JOIN (
        SELECT restaurant_id, provider, external_place_id,
               MAX(price_value > 0 OR
                   (price_text IS NOT NULL AND TRIM(price_text) <> '')) AS has_price
               ,MAX(crawled_at) AS crawled_at
        FROM restaurant_menus WHERE active = 1
        GROUP BY restaurant_id, provider, external_place_id
    ) m ON m.restaurant_id = c.restaurant_id AND m.provider = e.provider
      AND m.external_place_id = e.external_place_id
    LEFT JOIN (
        SELECT restaurant_id, provider, external_place_id
               ,MAX(crawled_at) AS crawled_at
        FROM restaurant_business_hours
        GROUP BY restaurant_id, provider, external_place_id
    ) b ON b.restaurant_id = c.restaurant_id AND b.provider = e.provider
      AND b.external_place_id = e.external_place_id
    WHERE e.provider = 'NAVER'
      AND e.match_status = 'MATCHED'
      AND e.external_place_id REGEXP '^[0-9]+$'
      AND r.recommendation_eligibility = 'ELIGIBLE'
      {id_filter}
    ORDER BY c.restaurant_id
    """

    eligible_rows = _execute_sql_read(sql)
    rows, already_complete = _pending_detail_rows(
        eligible_rows,
        args.limit,
        stale_after_seconds=stale_after_seconds,
        now=now,
        force_refresh=args.force_refresh,
    )
    print(
        f"Found {len(rows)} candidates; complete/fresh skipped: {already_complete}; "
        f"stale_after_seconds={stale_after_seconds or 'off'}; force_refresh={args.force_refresh}."
    )
    report_dir = root / "ai/build/reports/naver-place-pipeline/e2e"
    BatchProgress.enforce_cooldown(report_dir, "Detail")
    progress = BatchProgress(
        "Detail",
        len(rows),
        {"success": "success", "failure": "failure"},
        report_dir=report_dir,
    )
    progress.skip_preexisting(already_complete)
    progress.record_reason("DETAIL_COMPLETE_SKIPPED", already_complete)
    if not rows:
        progress.finish()
        return

    dom_crawler = PlaceDomDetailCrawler()
    persistence = PlaceDetailPersistence(root) if not args.dry_run else None
    limiter = NavigationRateLimiter(
        navigation_delay=float(os.environ.get("NAVER_NAVIGATION_DELAY_SECONDS", "2.5")),
        restaurant_delay=float(os.environ.get("NAVER_RESTAURANT_DELAY_SECONDS", "5.0")),
    )
    retry_policy = TransientRetryPolicy.from_env()

    status = "DRY_RUN" if args.dry_run else "COMPLETED"
    reason = None
    current_id = None
    try:
        with sync_playwright() as playwright:
            session = PlaywrightLifecycle(
                playwright,
                on_event=lambda event: progress.record_browser_lifecycle(
                    browser_starts=int(event == "browser_start"),
                    browser_restarts=int(event == "browser_restart"),
                    page_recreates=int(event == "page_recreate"),
                ),
            )
            session.start()
            for row in rows:
                restaurant_id = int(row["restaurant_id"])
                current_id = restaurant_id
                place_id = row["external_place_id"]
                canonical_name = row["name"]
                missing = _missing_sections(
                    row,
                    stale_after_seconds=stale_after_seconds,
                    now=now,
                    force_refresh=args.force_refresh,
                )
                has_any_detail = any(
                    row[key] == "1" for key in ("has_review", "has_menu", "has_hours")
                )
                if args.force_refresh and has_any_detail:
                    progress.record_reason("DETAIL_FORCE_REFRESH")
                elif any(
                    row.get(f"{section}_crawled_at")
                    and _timestamp_is_stale(
                        row.get(f"{section}_crawled_at"),
                        stale_after_seconds,
                        now,
                    )
                    for section in ("review", "menu", "hours")
                ):
                    progress.record_reason("DETAIL_STALE")
                else:
                    progress.record_reason("DETAIL_PARTIAL")

                progress.current(restaurant_id, canonical_name)
                print(
                    f"[{restaurant_id}] Enriching {','.join(k for k, v in missing.items() if v)} "
                    f"for '{canonical_name}' (Place ID: {place_id})...",
                    flush=True,
                )

                dom_detail = None
                for attempt in range(retry_policy.max_retries + 1):
                    try:
                        dom_detail = dom_crawler.collect(
                            session.page,
                            place_id,
                            include_reviews=True,
                            before_navigation=limiter.before_navigation,
                        )
                        break
                    except Exception as error:
                        if _is_blocked_error(error):
                            progress.block(restaurant_id, error)
                            raise
                        if attempt < retry_policy.max_retries and retry_policy.is_retryable(error):
                            delay = retry_policy.delay(attempt)
                            progress.retry(restaurant_id, delay, error)
                            time.sleep(delay)
                            continue
                        progress.error(restaurant_id, f"Crawler threw exception: {error}")
                        if is_playwright_lifecycle_error(error):
                            session.recover_after(error)
                if dom_detail is None:
                    progress.record("failed", restaurant_id, failure=1)
                    if not session.is_usable():
                        session.recover_if_unusable()
                    limiter.after_restaurant()
                    continue

                if not dom_detail.home_success:
                    warnings = ", ".join(dom_detail.warnings)
                    print(
                        f"[{restaurant_id}] Detail collection failed (home_success=False). "
                        f"Warnings: {warnings}. Skipping persistence to protect existing data."
                    )
                    progress.record("failed", restaurant_id, failure=1)
                    if not session.is_usable():
                        session.recover_if_unusable()
                    limiter.after_restaurant()
                    continue

                if not session.is_usable():
                    session.recover_if_unusable()

                print(f"[{restaurant_id}] Collected DOM successfully:")
                print(f"  - Name: {dom_detail.name}")
                print(f"  - Menus: {len(dom_detail.menus)} items")
                print(f"  - Business Hours: {len(dom_detail.business_hours)} rows")
                print(
                    f"  - Reviews: {dom_detail.review_total} visitor, "
                    f"{dom_detail.blog_review_total} blog"
                )

                place_detail = None
                persisted = True
                write_sections = _sections_to_persist(missing, dom_detail.review_page_success)
                try:
                    place_detail = dom_detail.to_place_detail(place_id)
                    if persistence:
                        persistence.persist(
                            restaurant_id, place_id, place_detail, sections=write_sections
                        )
                except Exception as error:
                    persisted = False
                    progress.error(restaurant_id, f"Persistence failed: {error}")

                # A legitimate missing online menu remains pending without deleting old sections.
                available = _collected_sections_complete(
                    missing,
                    place_detail,
                    dom_detail.review_page_success,
                )
                if persisted and not available:
                    progress.error(
                        restaurant_id,
                        "Incomplete REVIEW, MENU/price or BUSINESS HOURS; remains pending",
                    )
                succeeded = persisted and available
                if succeeded and persistence:
                    print(f"[{restaurant_id}] Successfully persisted details to DB.", flush=True)
                progress.record(
                    "success" if succeeded else "failed",
                    restaurant_id,
                    success=int(succeeded),
                    failure=int(not succeeded),
                )
                limiter.after_restaurant()

            session.close()
    except BaseException as error:
        status = (
            "BLOCKED"
            if isinstance(error, Exception) and _is_blocked_error(error)
            else ("INTERRUPTED" if isinstance(error, KeyboardInterrupt) else "FAILED")
        )
        reason = str(error) or type(error).__name__
        if current_id is not None and current_id not in (
            progress.last_success_restaurant_id,
            progress.last_failure_restaurant_id,
        ):
            progress.last_failure_restaurant_id = current_id
        raise
    finally:
        if "session" in locals():
            session.close()
        if progress.failed and status in {"COMPLETED", "DRY_RUN"}:
            status = "PARTIAL" if status == "COMPLETED" else "DRY_RUN_PARTIAL"
        progress.finish(status, reason)


if __name__ == "__main__":
    main()
