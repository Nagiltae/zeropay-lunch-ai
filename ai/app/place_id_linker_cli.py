import argparse
import os
import subprocess
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from app.batch_progress import BatchProgress
from app.place_allsearch import parse_allsearch_candidates
from app.place_request_limiter import NavigationRateLimiter, TransientRetryPolicy
from app.place_resolver import compare_address_pair, normalize_text
from app.place_resolver_cli import _search_ui_response
from app.playwright_lifecycle import PlaywrightLifecycle, is_playwright_lifecycle_error
from app.provider_input import load_local_env


def _is_blocked_error(error: Exception) -> bool:
    message = str(error).upper()
    return any(token in message for token in ("403", "429", "CAPTCHA", "BLOCKED"))


def _mapping_status_filter(force_retry: bool) -> str:
    if force_retry:
        return ""
    return """
      AND (e.match_status IS NULL OR e.match_status <> 'AMBIGUOUS')
      AND (n.match_status IS NULL OR n.match_status <> 'AMBIGUOUS')
    """


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


def _execute_sql_write(sql: str) -> None:
    command = [
        "docker",
        "compose",
        "exec",
        "-T",
        "mysql",
        "sh",
        "-c",
        'MYSQL_PWD="zeropay_local" mysql --default-character-set=utf8mb4 --batch '
        '--raw -u zeropay zeropay_lunch',
    ]
    process = subprocess.run(command, input=sql.encode("utf-8"), capture_output=True)
    if process.returncode != 0:
        raise RuntimeError(f"MySQL write failed: {process.stderr.decode('utf-8')}")


def is_exact_match(candidate, naver_external_name, naver_address, naver_road_address):
    norm_cand_name = normalize_text(candidate.name)
    norm_db_name = normalize_text(naver_external_name)

    if norm_cand_name != norm_db_name:
        if norm_db_name not in norm_cand_name and norm_cand_name not in norm_db_name:
            return False

    c_addr = candidate.address or ""
    c_road = candidate.road_address or ""

    db_addresses = [a for a in (naver_address, naver_road_address) if a]
    cand_addresses = [a for a in (c_addr, c_road) if a]

    for db_a in db_addresses:
        for c_a in cand_addresses:
            evidence = compare_address_pair(db_a, c_a)
            if evidence in ("EXACT", "STRONG_MATCH"):
                return True

    return False


def main():
    # 공식 Local evidence와 numeric Place ID 연결은 별도 상태이므로
    # 이 단계에서만 UI 검색을 수행한다.
    parser = argparse.ArgumentParser(description="Step 6 NAVER Place ID Linking")
    parser.add_argument("--limit", type=int, default=3, help="Smoke test limit")
    parser.add_argument(
        "--restaurant-ids", help="Comma-separated restaurant IDs for a bounded preflight"
    )
    parser.add_argument("--dry-run", action="store_true", help="Do not write to DB")
    parser.add_argument(
        "--force-retry",
        action="store_true",
        help="Explicitly retry non-numeric AMBIGUOUS and other pending mappings",
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
    status_filter = _mapping_status_filter(args.force_retry)

    root = Path(__file__).resolve().parent.parent.parent
    load_local_env(root)

    print(f"Fetching up to {args.limit} candidates for linking...")
    sql = f"""
    SELECT
        c.restaurant_id,
        c.name,
        c.address,
        COALESCE(e.external_name, c.name) as external_name,
        COALESCE(e.address, c.address) as ext_address,
        COALESCE(e.road_address, c.road_address) as ext_road_address,
        e.match_status,
        n.match_status AS naver_match_status,
        n.external_place_id,
        'NAVER' as provider
    FROM canonical_restaurants c
    LEFT JOIN restaurant_external_places e
        ON c.restaurant_id = e.restaurant_id
        AND e.provider = 'NAVER_LOCAL'
        LEFT JOIN restaurant_external_places n
        ON c.restaurant_id = n.restaurant_id AND n.provider = 'NAVER'
    JOIN restaurants r ON c.restaurant_id = r.id
    WHERE (n.external_place_id IS NULL OR n.external_place_id NOT REGEXP '^[0-9]+$')
      AND r.recommendation_eligibility = 'ELIGIBLE'
      {status_filter}
      {id_filter}
    ORDER BY c.restaurant_id
    LIMIT {args.limit};
    """

    rows = _execute_sql_read(sql)
    completed_sql = f"""
    SELECT COUNT(*) AS completed_count
    FROM canonical_restaurants c
    JOIN restaurants r ON r.id = c.restaurant_id
    JOIN restaurant_external_places n ON n.restaurant_id = c.restaurant_id
      AND n.provider = 'NAVER'
    WHERE r.recommendation_eligibility = 'ELIGIBLE'
      AND n.match_status = 'MATCHED'
      AND n.external_place_id REGEXP '^[0-9]+$'
      {id_filter};
    """
    completed_rows = _execute_sql_read(completed_sql)
    already_complete = int(completed_rows[0]["completed_count"])
    print(f"Found {len(rows)} candidates; numeric Place ID already complete: {already_complete}.")
    report_dir = root / "ai/build/reports/naver-place-pipeline/e2e"
    BatchProgress.enforce_cooldown(report_dir, "Place ID")
    progress = BatchProgress(
        "Place ID",
        len(rows),
        {"matched": "MATCHED", "unresolved": "UNRESOLVED", "ambiguous": "AMBIGUOUS"},
        report_dir=report_dir,
    )
    progress.skip_preexisting(already_complete)
    progress.record_reason("PLACE_ID_SKIPPED", already_complete)
    if not rows:
        progress.finish()
        return
    limiter = NavigationRateLimiter(
        navigation_delay=float(os.environ.get("NAVER_NAVIGATION_DELAY_SECONDS", "2.5")),
        restaurant_delay=float(os.environ.get("NAVER_RESTAURANT_DELAY_SECONDS", "3.0")),
    )
    retry_policy = TransientRetryPolicy.from_env()

    run_status = "DRY_RUN" if args.dry_run else "COMPLETED"
    stop_reason = None
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
                restaurant_id = row["restaurant_id"]
                current_id = restaurant_id
                provider = row["provider"]
                canonical_name = row["name"]
                naver_name = row["external_name"]
                naver_addr = row["ext_address"]
                naver_road = row["ext_road_address"]

                prior_statuses = {row.get("match_status", ""), row.get("naver_match_status", "")}
                if args.force_retry and "AMBIGUOUS" in prior_statuses:
                    progress.record_reason("AMBIGUOUS_FORCE_RETRY")
                elif "UNRESOLVED" in prior_statuses:
                    progress.record_reason("UNRESOLVED_RETRY")
                else:
                    progress.record_reason("PLACE_ID_PENDING")

                target_name = naver_name or canonical_name
                query = f"논현동 {target_name}".strip()
                progress.current(restaurant_id, target_name)
                print(f"[{restaurant_id}] Searching '{query}'...", flush=True)

                status = "UNRESOLVED"
                new_place_id = None
                for attempt in range(retry_policy.max_retries + 1):
                    try:
                        response, payload = _search_ui_response(
                            session.page,
                            query,
                            before_navigation=limiter.before_navigation,
                        )
                        candidates = parse_allsearch_candidates(payload)

                        matches = []
                        for cand in candidates:
                            if not cand.place_id or not cand.place_id.isdigit():
                                continue
                            if is_exact_match(cand, target_name, naver_addr, naver_road):
                                matches.append(cand)

                        if len(matches) == 1:
                            new_place_id = matches[0].place_id
                            status = "MATCHED"
                        elif len(matches) > 1:
                            status = "AMBIGUOUS"
                        else:
                            status = "UNRESOLVED"
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
                        progress.error(restaurant_id, f"Capture failed: {error}")
                        status = "UNRESOLVED"
                        if is_playwright_lifecycle_error(error):
                            session.recover_after(error)

                print(f"[{restaurant_id}] Result: {new_place_id} (Status: {status})", flush=True)

                if not args.dry_run:
                    escaped_query = query.replace("'", "''")
                    if new_place_id:
                        sql_write = f"""
                    INSERT INTO restaurant_external_places
                        (restaurant_id, provider, external_place_id, match_status, match_score,
                         query_used, matched_at, updated_at, created_at)
                    VALUES ({restaurant_id}, '{provider}', '{new_place_id}', 'MATCHED', 100.00,
                            '{escaped_query}', NOW(), NOW(), NOW())
                    ON DUPLICATE KEY UPDATE
                        external_place_id = '{new_place_id}',
                        match_status = 'MATCHED',
                        match_score = 100.00,
                        query_used = '{escaped_query}',
                        matched_at = NOW(),
                        updated_at = NOW();
                    """
                    else:
                        sql_write = f"""
                    INSERT INTO restaurant_external_places
                        (restaurant_id, provider, match_status, match_score, query_used,
                         updated_at, created_at)
                    VALUES ({restaurant_id}, '{provider}', '{status}', 0.00,
                            '{escaped_query}', NOW(), NOW(), NOW())
                    ON DUPLICATE KEY UPDATE
                        match_status = '{status}',
                        query_used = '{escaped_query}',
                        updated_at = NOW();
                    """
                    _execute_sql_write(sql_write)

                progress.record(
                    "success" if status == "MATCHED" else "failed",
                    restaurant_id,
                    matched=int(status == "MATCHED"),
                    unresolved=int(status == "UNRESOLVED"),
                    ambiguous=int(status == "AMBIGUOUS"),
                )
                # Record the committed item before a possible Ctrl+C during pacing.
                limiter.after_restaurant()

            session.close()
    except BaseException as error:
        run_status = (
            "BLOCKED"
            if isinstance(error, Exception) and _is_blocked_error(error)
            else ("INTERRUPTED" if isinstance(error, KeyboardInterrupt) else "FAILED")
        )
        stop_reason = str(error) or type(error).__name__
        if current_id is not None and current_id not in (
            progress.last_success_restaurant_id,
            progress.last_failure_restaurant_id,
        ):
            progress.last_failure_restaurant_id = current_id
        raise
    finally:
        if "session" in locals():
            session.close()
        if progress.failed and run_status in {"COMPLETED", "DRY_RUN"}:
            run_status = "PARTIAL" if run_status == "COMPLETED" else "DRY_RUN_PARTIAL"
        progress.finish(run_status, stop_reason)


if __name__ == "__main__":
    main()
