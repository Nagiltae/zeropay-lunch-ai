"""Read-only row-level snapshot helper for bounded detail persistence checks."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def rows(sql: str) -> list[dict[str, str | None]]:
    command = [
        "docker", "compose", "exec", "-T", "mysql", "mysql",
        "-uroot", "-proot_local", "zeropay_lunch", "--default-character-set=utf8mb4", "--batch", "--raw", "-e", sql,
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    lines = result.stdout.rstrip("\n").splitlines()
    if len(lines) < 2:
        return []
    headers = lines[0].split("\t")
    return [
        {header: (None if value == "\\N" else value) for header, value in zip(headers, line.split("\t"), strict=True)}
        for line in lines[1:]
    ]


def snapshot(restaurant_id: int) -> dict[str, object]:
    external = rows(f"SELECT external_place_id FROM restaurant_external_places WHERE restaurant_id={restaurant_id} AND provider='NAVER'")
    tables = {
        "restaurants": f"SELECT * FROM restaurants WHERE id={restaurant_id}",
        "restaurant_external_places": f"SELECT * FROM restaurant_external_places WHERE restaurant_id={restaurant_id}",
        "restaurant_naver_verifications": f"SELECT * FROM restaurant_naver_verifications WHERE restaurant_id={restaurant_id}",
        "restaurant_menus": f"SELECT * FROM restaurant_menus WHERE restaurant_id={restaurant_id}",
        "restaurant_business_hours": f"SELECT * FROM restaurant_business_hours WHERE restaurant_id={restaurant_id}",
        "restaurant_review_summaries": f"SELECT * FROM restaurant_review_summaries WHERE restaurant_id={restaurant_id}",
        "restaurant_review_keywords": f"SELECT * FROM restaurant_review_keywords WHERE restaurant_id={restaurant_id}",
        "restaurant_representative_reviews": f"SELECT * FROM restaurant_representative_reviews WHERE restaurant_id={restaurant_id}",
        "restaurant_detail_section_states": f"SELECT * FROM restaurant_detail_section_states WHERE restaurant_id={restaurant_id}",
    }
    data = {table: rows(sql) for table, sql in tables.items()}
    data["external_place_ids"] = [row["external_place_id"] for row in external]
    data["snapshotAt"] = datetime.now(timezone.utc).isoformat()
    data["restaurantId"] = restaurant_id
    return data


if __name__ == "__main__":
    rid = int(sys.argv[1])
    output = Path(sys.argv[2])
    output.write_text(json.dumps(snapshot(rid), ensure_ascii=False, indent=2) + "\n")
