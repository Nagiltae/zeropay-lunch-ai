"""CLI to persist Canonical Restaurants from evaluation CSV."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


from app.canonical_builder import build_canonical
from app.place_provider import PlaceSearchCandidate
from app.place_resolver import RestaurantReference
from app.provider_input import load_local_env


import subprocess

def _execute_sql(root: Path, sql: str) -> None:
    script = f'MYSQL_PWD="zeropay_password" mysql --batch --raw -u zeropay -h 127.0.0.1 -P 3306 zeropay_lunch'
    # Use docker compose exec -T mysql
    command = [
        "docker", "compose", "exec", "-T", "mysql", "sh", "-c",
        f'MYSQL_PWD="zeropay_password" mysql --batch --raw -u zeropay zeropay_lunch'
    ]
    process = subprocess.run(command, input=sql.encode("utf-8"), cwd=str(root), capture_output=True)
    if process.returncode != 0:
        raise RuntimeError(f"MySQL execution failed: {process.stderr.decode('utf-8')}")


def process_csv(path: Path, root: Path, dry_run: bool = False) -> tuple[int, int]:
    created = 0
    skipped = 0
    all_sql = []

    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        for row in reader:
            decision = row.get("decision", "")
            if decision != "ACCEPT":
                skipped += 1
                continue

            kakao_idx_str = row.get("kakao_selected_index", "")
            naver_idx_str = row.get("naver_selected_index", "")

            if not kakao_idx_str and not naver_idx_str:
                skipped += 1
                continue

            candidates_json = row.get("candidates_json", "[]")
            try:
                candidates_data = json.loads(candidates_json)
            except json.JSONDecodeError:
                skipped += 1
                continue

            accepted_candidates = []

            def parse_candidate(idx_str):
                if not idx_str:
                    return None
                try:
                    selected_data = candidates_data[int(idx_str)]
                    return PlaceSearchCandidate(
                        provider=selected_data.get("provider", ""),
                        external_place_id=selected_data.get("external_place_id", ""),
                        name=selected_data.get("name", ""),
                        category=selected_data.get("category", ""),
                        address=selected_data.get("address", ""),
                        road_address=selected_data.get("road_address", ""),
                        latitude=float(selected_data["latitude"]) if selected_data.get("latitude") else None,
                        longitude=float(selected_data["longitude"]) if selected_data.get("longitude") else None,
                        phone=selected_data.get("phone", ""),
                        detail_url=selected_data.get("detail_url", ""),
                        distance=selected_data.get("distance", ""),
                        raw_metadata=selected_data.get("raw_metadata", {}),
                    )
                except (IndexError, KeyError, ValueError):
                    return None

            naver_candidate = parse_candidate(naver_idx_str)
            kakao_candidate = parse_candidate(kakao_idx_str)

            if naver_candidate:
                accepted_candidates.append(naver_candidate)
            if kakao_candidate:
                accepted_candidates.append(kakao_candidate)

            if not accepted_candidates:
                skipped += 1
                continue

            reference = RestaurantReference(
                restaurant_id=int(row["restaurant_id"]),
                komsco_name=row["komsco_name"],
                komsco_address=row["komsco_address"],
                komsco_latitude=None,
                komsco_longitude=None,
                legal_dong="논현동",
                external_merchant_id=row["external_merchant_id"],
            )

            # Use NAVER as primary for canonical fields if available, else KAKAO
            primary_candidate = naver_candidate if naver_candidate else kakao_candidate
            canonical = build_canonical(reference, primary_candidate)

            from app.canonical_builder import generate_canonical_sql
            all_sql.append(generate_canonical_sql(canonical, accepted_candidates))
            created += 1

    if not dry_run and all_sql:
        _execute_sql(root, "\n".join(all_sql))

    return created, skipped


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    load_local_env(root)

    created, skipped = process_csv(args.csv, root, dry_run=args.dry_run)
    print(f"Canonical restaurants: created={created}, skipped={skipped} (dry_run={args.dry_run})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
