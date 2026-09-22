"""Entity Resolution CSV의 검증·Canonical·provider mapping을 MySQL에 반영한다.

음식점 하나의 관련 SQL을 하나의 트랜잭션으로 실행해 부분 persistence를 막는다.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from pathlib import Path

from app.batch.batch_progress import BatchProgress
from app.canonical.canonical_builder import build_canonical
from app.entity_resolution.qwen_candidate_matcher import configured_qwen_model
from app.naver.place_detail_persistence import PlaceDetailPersistence
from app.naver.place_resolver import RestaurantReference
from app.providers.place_provider import PlaceSearchCandidate
from app.providers.provider_input import load_local_env


def verification_metadata(row: dict[str, str]) -> tuple[str, str, str]:
    # UNKNOWN은 확정된 거절이 아니므로 ERROR로 저장하되 eligibility=UNKNOWN과
    # reason code를 함께 보존해 기술 실패와 semantic 불확실을 다음 배치에서 재검증한다.
    decision = row.get("decision", "")
    status = (
        "VERIFIED" if decision == "ACCEPT" else ("REJECTED" if decision == "REJECT" else "ERROR")
    )
    reason = row.get("verification_reason", "")
    if len(reason) > 64:
        reason = (
            "NON_FOOD"
            if row.get("qwen_business_type") == "NON_FOOD"
            else "OUT_OF_SCOPE"
            if row.get("qwen_location_scope") == "OUT_OF_SCOPE"
            else "MATCHED"
            if decision == "ACCEPT"
            else "NO_MATCH"
            if decision == "REJECT"
            else "SEMANTIC_UNCERTAIN"
        )
    return status, reason, row.get("qwen_model") or configured_qwen_model()


def _execute_sql(root: Path, sql: str) -> None:
    # 한 음식점의 Canonical·mapping·verification을 하나의 transaction으로 묶는다.
    transactional_sql = f"START TRANSACTION;\n{sql}\nCOMMIT;"
    command = [
        "docker",
        "compose",
        "exec",
        "-T",
        "mysql",
        "sh",
        "-c",
        'MYSQL_PWD="zeropay_local" mysql --default-character-set=utf8mb4 --batch '
        '--skip-reconnect '
        '--raw -u zeropay zeropay_lunch',
    ]
    # --force를 사용하지 않으므로 batch SQL 오류에서 mysql client가 실패하고
    # COMMIT까지 진행하지 않는다. 연결 종료 시 열린 InnoDB transaction도 rollback된다.
    process = subprocess.run(
        command,
        input=transactional_sql.encode("utf-8"),
        cwd=str(root),
        capture_output=True,
    )
    if process.returncode != 0:
        raise RuntimeError(f"MySQL execution failed: {process.stderr.decode('utf-8')}")


def process_csv(path: Path, root: Path, dry_run: bool = False) -> tuple[int, int]:
    created = 0
    skipped = 0
    verification_rows: list[dict[str, str]] = []

    persistence = PlaceDetailPersistence(root)
    with path.open(newline="", encoding="utf-8") as stream:
        verification_rows = list(csv.DictReader(stream))
        progress = BatchProgress(
            "Canonical Prepare",
            len(verification_rows),
            {"accept": "ACCEPT", "skipped": "REJECT/UNKNOWN"},
        )
        for row in verification_rows:
            decision = row.get("decision", "")
            progress.current(row["restaurant_id"], row.get("komsco_name", ""))

            transaction_sql = ""
            if decision == "ACCEPT":
                kakao_idx_str = row.get("kakao_selected_index", "")
                naver_idx_str = row.get("naver_selected_index", "")

                if not kakao_idx_str and not naver_idx_str:
                    raise ValueError(f"ACCEPT row {row['restaurant_id']} has no selected candidate")

                candidates_json = row.get("candidates_json", "[]")
                try:
                    candidates_data = json.loads(candidates_json)
                except json.JSONDecodeError as error:
                    raise ValueError(
                        f"ACCEPT row {row['restaurant_id']} has invalid candidates"
                    ) from error

                accepted_candidates = []

                def parse_candidate(idx_str, candidate_rows=candidates_data):
                    if not idx_str:
                        return None
                    try:
                        selected_data = candidate_rows[int(idx_str)]
                        return PlaceSearchCandidate(
                            provider=selected_data.get("provider", ""),
                            external_place_id=selected_data.get("external_place_id", ""),
                            name=selected_data.get("name", ""),
                            category=selected_data.get("category", ""),
                            address=selected_data.get("address", ""),
                            road_address=selected_data.get("road_address", ""),
                            latitude=float(selected_data["latitude"])
                            if selected_data.get("latitude")
                            else None,
                            longitude=float(selected_data["longitude"])
                            if selected_data.get("longitude")
                            else None,
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
                    raise ValueError(f"ACCEPT row {row['restaurant_id']} has no usable candidate")

                reference = RestaurantReference(
                    restaurant_id=int(row["restaurant_id"]),
                    komsco_name=row["komsco_name"],
                    komsco_address=row["komsco_address"],
                    komsco_latitude=None,
                    komsco_longitude=None,
                    legal_dong="논현동",
                    external_merchant_id=row["external_merchant_id"],
                )

                # Canonical은 NAVER evidence를 우선하고 없으면 KAKAO evidence를 사용한다.
                primary_candidate = naver_candidate if naver_candidate else kakao_candidate
                canonical = build_canonical(reference, primary_candidate)

                from app.canonical.canonical_builder import generate_canonical_sql

                transaction_sql = generate_canonical_sql(canonical, accepted_candidates)
                created += 1
            else:
                skipped += 1

            ver_status, ver_reason, model_name = verification_metadata(row)
            transaction_sql += persistence.verification_sql(
                restaurant_id=int(row["restaurant_id"]),
                status=ver_status,
                reason=ver_reason,
                place_id=None,
                model_name=model_name,
                source_fingerprint_value=row.get("source_fingerprint") or None,
                eligibility=row.get("recommendation_eligibility") or None,
            )

            if not dry_run:
                try:
                    _execute_sql(root, transaction_sql)
                except Exception as error:
                    progress.error(row["restaurant_id"], str(error))
                    raise RuntimeError(
                        f"Failed to persist canonical/verification for {row['restaurant_id']}"
                    ) from error

            progress.complete(accept=int(decision == "ACCEPT"), skipped=int(decision != "ACCEPT"))

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
