import argparse
import subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright

from app.provider_input import load_local_env
from app.place_dom_detail_crawler import PlaceDomDetailCrawler
from app.place_detail_persistence import PlaceDetailPersistence

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

def main():
    parser = argparse.ArgumentParser(description="Step 7 NAVER Detail Enrichment")
    parser.add_argument("--limit", type=int, default=3, help="Smoke test limit")
    parser.add_argument("--dry-run", action="store_true", help="Do not write to DB")
    args = parser.parse_args()
    
    root = Path(__file__).resolve().parent.parent.parent
    load_local_env(root)

    print(f"Fetching up to {args.limit} candidates for detail enrichment...")
    sql = f"""
    SELECT c.restaurant_id, c.name, e.external_place_id, e.provider
    FROM canonical_restaurants c
    JOIN restaurant_external_places e ON c.restaurant_id = e.restaurant_id
    WHERE e.provider IN ('NAVER', 'NAVER_LOCAL')
      AND e.match_status = 'MATCHED'
      AND e.external_place_id REGEXP '^[0-9]+$'
    LIMIT {args.limit};
    """
    
    rows = _execute_sql_read(sql)
    if not rows:
        print("No candidates found.")
        return

    print(f"Found {len(rows)} candidates.")
    
    dom_crawler = PlaceDomDetailCrawler()
    persistence = PlaceDetailPersistence(root) if not args.dry_run else None
    
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_default_timeout(15_000)
        
        for row in rows:
            restaurant_id = int(row['restaurant_id'])
            place_id = row['external_place_id']
            canonical_name = row['name']
            
            print(f"[{restaurant_id}] Enriching details for '{canonical_name}' (Place ID: {place_id})...")
            
            try:
                dom_detail = dom_crawler.collect(page, place_id, include_reviews=True)
            except Exception as e:
                print(f"[{restaurant_id}] Crawler threw exception: {e}")
                continue
                
            if not dom_detail.home_success:
                warnings = ", ".join(dom_detail.warnings)
                print(f"[{restaurant_id}] Detail collection failed (home_success=False). Warnings: {warnings}. Skipping persistence to protect existing data.")
                continue
                
            print(f"[{restaurant_id}] Collected DOM successfully:")
            print(f"  - Name: {dom_detail.name}")
            print(f"  - Menus: {len(dom_detail.menus)} items")
            print(f"  - Business Hours: {len(dom_detail.business_hours)} rows")
            print(f"  - Reviews: {dom_detail.review_total} visitor, {dom_detail.blog_review_total} blog")
            
            if persistence:
                try:
                    place_detail = dom_detail.to_place_detail(place_id)
                    persistence.persist(restaurant_id, place_id, place_detail)
                    print(f"[{restaurant_id}] Successfully persisted details to DB.")
                except Exception as e:
                    print(f"[{restaurant_id}] Persistence failed: {e}")
                    
        browser.close()

if __name__ == "__main__":
    main()
