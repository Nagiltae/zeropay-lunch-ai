import argparse
import sys
import subprocess
from playwright.sync_api import sync_playwright

from app.place_resolver_cli import _search_ui_response
from app.place_allsearch import parse_allsearch_candidates
from app.place_resolver import normalize_text, compare_address_pair
from app.provider_input import load_local_env

def _execute_sql_read(sql: str) -> list[dict[str, str]]:
    command = [
        "docker", "compose", "exec", "-T", "mysql", "sh", "-c",
        f'MYSQL_PWD="zeropay_local" mysql --default-character-set=utf8mb4 --batch -u zeropay zeropay_lunch -e "{sql}"'
    ]
    process = subprocess.run(command, capture_output=True, text=True)
    if process.returncode != 0:
        raise RuntimeError(f"MySQL query failed: {process.stderr}")

    rows = []
    lines = process.stdout.strip().split('\n')
    if len(lines) > 1:
        headers = lines[0].split('\t')
        for line in lines[1:]:
            cols = line.split('\t')
            rows.append(dict(zip(headers, cols)))
    return rows

def _execute_sql_write(sql: str) -> None:
    command = [
        "docker", "compose", "exec", "-T", "mysql", "sh", "-c",
        f'MYSQL_PWD="zeropay_local" mysql --default-character-set=utf8mb4 --batch --raw -u zeropay zeropay_lunch'
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
    parser = argparse.ArgumentParser(description="Step 6 NAVER Place ID Linking")
    parser.add_argument("--limit", type=int, default=3, help="Smoke test limit")
    parser.add_argument("--dry-run", action="store_true", help="Do not write to DB")
    args = parser.parse_args()

    from pathlib import Path
    load_local_env(Path(__file__).resolve().parent.parent.parent)

    print(f"Fetching up to {args.limit} candidates for linking...")
    sql = f"""
    SELECT
        c.restaurant_id,
        c.name,
        c.address,
        COALESCE(e.external_name, c.name) as external_name,
        COALESCE(e.address, c.address) as ext_address,
        COALESCE(e.road_address, c.road_address) as ext_road_address,
        e.external_place_id,
        'NAVER' as provider
    FROM canonical_restaurants c
    LEFT JOIN restaurant_external_places e
        ON c.restaurant_id = e.restaurant_id
        AND e.provider IN ('NAVER', 'NAVER_LOCAL')
    JOIN restaurants r ON c.restaurant_id = r.id
    WHERE (e.external_place_id IS NULL OR e.external_place_id NOT REGEXP '^[0-9]+$')
      AND (e.match_status IS NULL OR e.match_status NOT IN ('MATCHED', 'UNRESOLVED', 'AMBIGUOUS'))
      AND r.recommendation_eligibility = 'ELIGIBLE'
    LIMIT {args.limit};
    """

    rows = _execute_sql_read(sql)
    if not rows:
        print("No candidates found.")
        return

    print(f"Found {len(rows)} candidates.")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_default_timeout(15_000)

        for row in rows:
            restaurant_id = row['restaurant_id']
            provider = row['provider']
            canonical_name = row['name']
            naver_name = row['external_name']
            naver_addr = row['ext_address']
            naver_road = row['ext_road_address']

            target_name = naver_name or canonical_name
            query = f"논현동 {target_name}".strip()
            print(f"[{restaurant_id}] Searching '{query}'...")

            status = "UNRESOLVED"
            new_place_id = None
            try:
                response, payload = _search_ui_response(page, query)
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
            except Exception as e:
                print(f"[{restaurant_id}] Capture failed: {e}")
                status = "UNRESOLVED"

            print(f"[{restaurant_id}] Result: {new_place_id} (Status: {status})")

            if not args.dry_run:
                escaped_query = query.replace("'", "''")
                if new_place_id:
                    sql_write = f"""
                    INSERT INTO restaurant_external_places
                        (restaurant_id, provider, external_place_id, match_status, match_score, query_used, matched_at, updated_at, created_at)
                    VALUES ({restaurant_id}, '{provider}', '{new_place_id}', 'MATCHED', 100.00, '{escaped_query}', NOW(), NOW(), NOW())
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
                        (restaurant_id, provider, match_status, match_score, query_used, updated_at, created_at)
                    VALUES ({restaurant_id}, '{provider}', '{status}', 0.00, '{escaped_query}', NOW(), NOW())
                    ON DUPLICATE KEY UPDATE
                        match_status = '{status}',
                        query_used = '{escaped_query}',
                        updated_at = NOW();
                    """
                _execute_sql_write(sql_write)

        browser.close()

if __name__ == "__main__":
    main()
