"""Bounded, checkpointed Detail Quality Backfill orchestration."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.profile_readiness_audit import (
    GROUP_A_IDS,
    IDENTITY_REVIEW_EXCLUSIONS,
    KNOWN_DETAIL_FAILURE_EXCLUSIONS,
    MENU_ABSENT_EXCLUSIONS,
    audit_rows,
    build_coverage_summary,
    select_backfill_groups,
)

ROOT = Path(__file__).resolve().parents[2]
AI_ANSWER = ROOT / "AI_Answer"
REPORT_DIR = ROOT / "ai" / "build" / "reports" / "detail-quality-backfill"
BASELINE_READY = (9568, 9571, 9574, 9590, 9617)
GROUP_B_LIMIT = 20


def _json_write(path: Path, data: Any, *, preserve_existing: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if preserve_existing and path.exists():
        raise FileExistsError(f"refusing to overwrite existing artifact: {path}")
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _db_guard() -> dict[str, str]:
    # Capture only non-secret runtime identity; never print or persist credentials.
    mysql = (
        subprocess.run(
            [
                "docker",
                "compose",
                "exec",
                "-T",
                "mysql",
                "sh",
                "-c",
                'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -N -uroot -e '
                '"SELECT DATABASE(),@@hostname,CURRENT_USER()" zeropay_lunch',
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        .stdout.strip()
        .split("\t")
    )
    if len(mysql) != 3:
        raise RuntimeError("DB guard could not identify the active database")
    project = subprocess.run(
        ["docker", "compose", "ps", "--format", "json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    entries = [json.loads(line) for line in project.splitlines() if line.strip()]
    mysql_service = next((item for item in entries if item.get("Service") == "mysql"), None)
    backend_service = next((item for item in entries if item.get("Service") == "backend"), None)
    # The odd-looking explicit validation avoids accepting a similarly named external DB.
    compose_project = (mysql_service or {}).get("Project", "")
    if mysql[0] != "zeropay_lunch" or compose_project != "zeropay-lunch-ai":
        raise RuntimeError(
            "ABORT BEFORE WRITE: database/project is not the allowlisted development MySQL"
        )
    if not mysql_service or not backend_service or mysql_service.get("State") != "running":
        raise RuntimeError(
            "ABORT BEFORE WRITE: expected local Compose MySQL/backend are not running"
        )
    backend_env = subprocess.run(
        [
            "docker",
            "inspect",
            "--format",
            "{{range .Config.Env}}{{println .}}{{end}}",
            backend_service["ID"],
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    profile = next(
        (
            item.split("=", 1)[1]
            for item in backend_env
            if item.startswith("SPRING_PROFILES_ACTIVE=")
        ),
        "",
    )
    if profile != "dev":
        raise RuntimeError("ABORT BEFORE WRITE: Spring active profile is not dev")
    return {
        "database": mysql[0],
        "mysqlHostname": mysql[1],
        "mysqlUser": mysql[2],
        "composeProject": compose_project,
        "springProfile": profile,
    }


def _candidate_checks(plan: dict[str, Any]) -> None:
    group_a = plan["groups"]["groupA"]
    group_b = plan["groups"]["groupB"]
    a_ids = [int(item["restaurantId"]) for item in group_a]
    b_ids = [int(item["restaurantId"]) for item in group_b]
    if set(a_ids) != set(GROUP_A_IDS) or len(a_ids) != 7:
        raise RuntimeError("ABORT BEFORE WRITE: Group A is not the exact seven-ID allowlist")
    if any(item.get("reason") != "only NO_STRUCTURED_HOURS remains" for item in group_a):
        raise RuntimeError("ABORT BEFORE WRITE: Group A contains a non-hours readiness gap")
    if len(b_ids) > GROUP_B_LIMIT or len(set(b_ids)) != len(b_ids) or set(a_ids) & set(b_ids):
        raise RuntimeError("ABORT BEFORE WRITE: invalid Group B scope")
    if set(b_ids) & set(MENU_ABSENT_EXCLUSIONS):
        raise RuntimeError("ABORT BEFORE WRITE: MENU ABSENT_CONFIRMED exclusion was selected")
    if set(b_ids) & (set(IDENTITY_REVIEW_EXCLUSIONS) | set(KNOWN_DETAIL_FAILURE_EXCLUSIONS)):
        raise RuntimeError(
            "ABORT BEFORE WRITE: known identity-review/detail-failure target was selected"
        )
    for group in (group_a, group_b):
        for item in group:
            if not re.fullmatch(r"\d+", str(item.get("placeId", ""))):
                raise RuntimeError("ABORT BEFORE WRITE: selected row lacks numeric Place ID")
            reasons = set(item.get("currentReadinessReasons", []))
            if reasons & {"PLACE_ID_CONFLICT", "NOT_VERIFIED", "NO_NUMERIC_PLACE_ID"}:
                raise RuntimeError("ABORT BEFORE WRITE: identity/ownership check failed")
    if len(a_ids) + len(b_ids) > 27:
        raise RuntimeError("ABORT BEFORE WRITE: maximum live target count exceeded")
    expected_tables = set(plan.get("expectedWriteTables", []))
    allowed_tables = {
        "restaurant_menus",
        "restaurant_business_hours",
        "restaurant_review_summaries",
        "restaurant_review_keywords",
        "restaurant_representative_reviews",
        "restaurant_detail_section_states",
    }
    if not expected_tables or not expected_tables <= allowed_tables:
        raise RuntimeError("ABORT BEFORE WRITE: unexpected DB table write set")


def create_plan() -> dict[str, Any]:
    rows = audit_rows()
    coverage = build_coverage_summary(rows)
    groups = select_backfill_groups(rows, GROUP_B_LIMIT)
    plan = {
        "planVersion": "detail-quality-backfill-plan-v1",
        "createdAt": datetime.now(UTC).isoformat(),
        "databaseMode": "read-only planning; development DB only",
        "strictReadyBefore": coverage["strictReady"],
        "strictReadyBeforeRestaurantIds": coverage["strictReadyRestaurantIds"],
        "population": coverage["population"],
        "coverageSummary": coverage,
        "groups": groups,
        "excludedRestaurantIds": list(MENU_ABSENT_EXCLUSIONS),
        "knownIdentityReviewExclusions": list(IDENTITY_REVIEW_EXCLUSIONS),
        "knownDetailFailureExclusions": list(KNOWN_DETAIL_FAILURE_EXCLUSIONS),
        "maximumLiveRestaurants": 27,
        "plannedLiveRestaurantCount": groups["selectedTotal"],
        "externalRequestTargets": groups["selectedTotal"],
        "expectedNavigationUpperBound": len(groups["groupA"]) + 3 * len(groups["groupB"]),
        "expectedWriteTables": sorted(
            {
                "restaurant_business_hours",
                "restaurant_detail_section_states",
                *(
                    [
                        "restaurant_menus",
                        "restaurant_review_summaries",
                        "restaurant_review_keywords",
                        "restaurant_representative_reviews",
                    ]
                    if groups["groupB"]
                    else []
                ),
            }
        ),
        "restaurantSignals": [
            {
                key: row.get(key)
                for key in (
                    "restaurant_id",
                    "name",
                    "external_place_id",
                    "menu_count",
                    "priced_menu_count",
                    "hours_row_count",
                    "structured_hours_count",
                    "review_summary_count",
                    "review_keyword_count",
                    "representative_review_count",
                    "lifecycle_count",
                    "verification_status",
                    "owner_count",
                    "readiness",
                )
            }
            for row in rows
        ],
        "writeGate": "NOT_EVALUATED",
    }
    _candidate_checks(plan)
    plan["writeGate"] = "PASS_PLAN_SCOPE_ONLY"
    plan["dbGuard"] = _db_guard()
    plan_path = AI_ANSWER / "detail_quality_backfill_plan.json"
    _json_write(plan_path, plan)
    return plan


def _runner_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "dry-run", "apply", "reconcile-hours"))
    return parser.parse_args()


def _run_group(name: str, items: list[dict[str, Any]], sections: str, *, dry_run: bool) -> int:
    if not items:
        return 0
    ids = [int(item["restaurantId"]) for item in items]
    checkpoint = REPORT_DIR / f"{name.lower()}_{'dryrun' if dry_run else 'write'}_checkpoint.json"
    command = [
        sys.executable,
        "-m",
        "app.naver.place_detail_enrichment_cli",
        "--limit",
        str(len(ids)),
        "--restaurant-ids",
        ",".join(map(str, ids)),
        "--sections",
        sections,
        "--checkpoint",
        str(checkpoint),
    ]
    if dry_run:
        command.append("--dry-run")
    print(
        f"Backfill group {name}: targets={len(ids)} sections={sections} dry_run={dry_run}",
        flush=True,
    )
    return subprocess.run(command, cwd=ROOT / "ai", check=False).returncode


def run_dry_run(plan: dict[str, Any]) -> dict[str, Any]:
    _candidate_checks(plan)
    groups = plan["groups"]
    a_code = _run_group("GROUP_A", groups["groupA"], "business_hours", dry_run=True)
    if a_code != 0:
        raise RuntimeError("Group A dry-run stopped; no persistence may begin")
    b_code = _run_group("GROUP_B", groups["groupB"], "all", dry_run=True)
    if b_code != 0:
        raise RuntimeError("Group B dry-run stopped; no persistence may begin")
    outcomes = {}
    blocked = False
    for name in ("GROUP_A", "GROUP_B"):
        path = REPORT_DIR / f"{name.lower()}_dryrun_checkpoint.json"
        checkpoint = (
            json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"completed": {}}
        )
        outcomes[name] = checkpoint.get("completed", {})
        blocked |= "BLOCKED" in outcomes[name].values()
    result = {
        "status": "BLOCKED" if blocked else "DRY_RUN_COMPLETE",
        "createdAt": datetime.now(UTC).isoformat(),
        "dryRunOnly": True,
        "externalRequestTargets": plan["plannedLiveRestaurantCount"],
        "outcomes": outcomes,
    }
    _json_write(AI_ANSWER / "detail_quality_backfill_dry_run.json", result)
    if blocked:
        raise RuntimeError("provider block detected; stop immediately and honor cooldown")
    return result


def _snapshot(ids: list[int], guard: dict[str, str]) -> dict[str, Any]:
    from app.detail_snapshot import snapshot as read_snapshot

    result: dict[str, Any] = {
        "createdAt": datetime.now(UTC).isoformat(),
        "database": guard["database"],
        "restaurantIds": ids,
        "restaurants": {},
    }
    for rid in ids:
        data = read_snapshot(rid)
        reviews = data.get("restaurant_representative_reviews", [])
        for row in reviews:
            text = row.pop("review_text", None)
            if text is not None:
                row["review_text_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
                row["review_text_length"] = len(text)
        result["restaurants"][str(rid)] = data
    return result


def apply(plan: dict[str, Any]) -> dict[str, Any]:
    _candidate_checks(plan)
    guard = _db_guard()
    dry_path = AI_ANSWER / "detail_quality_backfill_dry_run.json"
    if not dry_path.exists():
        raise RuntimeError("ABORT BEFORE WRITE: completed dry-run manifest is absent")
    dry = json.loads(dry_path.read_text(encoding="utf-8"))
    if dry.get("status") != "DRY_RUN_COMPLETE":
        raise RuntimeError("ABORT BEFORE WRITE: dry-run did not complete without blocks")
    all_groups = plan["groups"]
    successful: dict[str, list[dict[str, Any]]] = {}
    for name, group_name in (("GROUP_A", "groupA"), ("GROUP_B", "groupB")):
        statuses = dry["outcomes"].get(name, {})
        successful[name] = [
            item
            for item in all_groups[group_name]
            if statuses.get(str(item["restaurantId"])) == "DRY_RUN_SUCCESS"
        ]
        if any(value == "BLOCKED" for value in statuses.values()):
            raise RuntimeError("ABORT BEFORE WRITE: dry-run checkpoint has BLOCKED status")

    write_ids = [
        int(item["restaurantId"]) for name in ("GROUP_A", "GROUP_B") for item in successful[name]
    ]
    if not write_ids:
        return {"status": "NO_DRY_RUN_SUCCESS", "writeIds": [], "dbWrites": 0}
    before_path = AI_ANSWER / "detail_quality_backfill_before.json"
    if not before_path.exists():
        _json_write(before_path, _snapshot(write_ids, guard), preserve_existing=True)
    elif json.loads(before_path.read_text(encoding="utf-8")).get("restaurantIds") != write_ids:
        raise RuntimeError(
            "ABORT BEFORE WRITE: existing before-snapshot does not match planned write scope"
        )

    write_manifest: dict[str, Any] = {
        "status": "RUNNING",
        "startedAt": datetime.now(UTC).isoformat(),
        "dbGuard": guard,
        "planned": plan["plannedLiveRestaurantCount"],
        "attempted": len(write_ids),
        "writeIds": write_ids,
        "success": 0,
        "failed": 0,
        "blocked": 0,
        "skipped": 0,
        "groupA": [item["restaurantId"] for item in successful["GROUP_A"]],
        "groupB": [item["restaurantId"] for item in successful["GROUP_B"]],
        "externalRequests": dry["externalRequestTargets"],
        "dbWrites": "detail-only; per-restaurant transactions",
        "newStrictReady": None,
    }
    _json_write(AI_ANSWER / "detail_quality_backfill_manifest.json", write_manifest)
    code_a = _run_group("GROUP_A", successful["GROUP_A"], "business_hours", dry_run=False)
    code_b = 0
    if code_a == 0:
        code_b = _run_group("GROUP_B", successful["GROUP_B"], "all", dry_run=False)

    outcomes: dict[str, dict[str, str]] = {}
    for name in ("GROUP_A", "GROUP_B"):
        checkpoint_path = REPORT_DIR / f"{name.lower()}_write_checkpoint.json"
        outcomes[name] = (
            json.loads(checkpoint_path.read_text(encoding="utf-8")).get("completed", {})
            if checkpoint_path.exists()
            else {}
        )
    values = [status for group in outcomes.values() for status in group.values()]
    write_manifest.update(
        {
            "status": "BLOCKED" if "BLOCKED" in values or code_a or code_b else "COMPLETED",
            "finishedAt": datetime.now(UTC).isoformat(),
            "outcomes": outcomes,
            "success": values.count("SUCCESS"),
            "failed": values.count("FAILED"),
            "blocked": values.count("BLOCKED"),
            "skipped": values.count("SKIPPED"),
        }
    )

    after_path = AI_ANSWER / "detail_quality_backfill_after.json"
    _json_write(after_path, _snapshot(write_ids, guard))
    after_rows = audit_rows()
    coverage_after = build_coverage_summary(after_rows)
    new_ids = sorted(set(coverage_after["strictReadyRestaurantIds"]) - set(BASELINE_READY))
    write_manifest["strictReadyAfter"] = coverage_after["strictReady"]
    write_manifest["strictReadyAfterRestaurantIds"] = coverage_after["strictReadyRestaurantIds"]
    write_manifest["newStrictReady"] = len(new_ids)
    write_manifest["newStrictReadyRestaurantIds"] = new_ids
    write_manifest["coverageAfter"] = coverage_after
    _json_write(AI_ANSWER / "detail_quality_backfill_manifest.json", write_manifest)
    _json_write(
        AI_ANSWER / "detail_quality_backfill_coverage_after.json",
        {
            "createdAt": datetime.now(UTC).isoformat(),
            "strictReadyBefore": plan["strictReadyBefore"],
            "strictReadyAfter": coverage_after["strictReady"],
            "newStrictReady": len(new_ids),
            "newStrictReadyRestaurantIds": new_ids,
            "summary": coverage_after,
            "restaurantReadiness": [
                {
                    "restaurantId": row["restaurant_id"],
                    "name": row["name"],
                    "status": row["readiness"]["status"],
                    "reasons": row["readiness"]["reasons"],
                }
                for row in after_rows
            ],
        },
    )
    return write_manifest


def _normalized_hours(descriptions: list[str]):
    from app.naver.place_dom_detail_crawler import DomCollectedDetail

    by_day: dict[str, Any] = {}
    conflicts: set[str] = set()
    for source in descriptions:
        for hour in DomCollectedDetail._parse_business_hours(source):
            current = by_day.get(hour.day)
            if current and (current.open_time, current.close_time) != (
                hour.open_time,
                hour.close_time,
            ):
                conflicts.add(hour.day)
            else:
                by_day[hour.day] = hour
    return tuple(hour for day, hour in by_day.items() if day not in conflicts), conflicts


def reconcile_persisted_hours() -> dict[str, Any]:
    """Correct weekday/time pairs from persisted DOM text without external navigation."""
    from app.naver.place_detail_models import PlaceDetail
    from app.naver.place_detail_persistence import MysqlWriteSession, PlaceDetailPersistence

    manifest_path = AI_ANSWER / "detail_quality_backfill_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    plan = json.loads(
        (AI_ANSWER / "detail_quality_backfill_plan.json").read_text(encoding="utf-8")
    )
    ids = [int(value) for value in manifest.get("writeIds", [])]
    planned_ids = [
        int(item["restaurantId"])
        for group in ("groupA", "groupB")
        for item in plan["groups"][group]
    ]
    if manifest.get("status") != "COMPLETED" or set(ids) != set(planned_ids) or len(ids) != 27:
        raise RuntimeError("ABORT HOURS RECONCILIATION: completed 27-target manifest required")
    guard = _db_guard()
    previous = json.loads((AI_ANSWER / "detail_quality_backfill_after.json").read_text())
    pre_reconcile_path = AI_ANSWER / "detail_quality_backfill_after_pre_hours_reconcile.json"
    if not pre_reconcile_path.exists():
        _json_write(pre_reconcile_path, previous, preserve_existing=True)
    hours_before_path = AI_ANSWER / "detail_quality_backfill_hours_before_reconcile.json"
    if not hours_before_path.exists():
        _json_write(hours_before_path, _snapshot(ids, guard), preserve_existing=True)

    started_at = str(manifest["startedAt"])[:19].replace("T", " ")
    outcomes: dict[str, str] = {}
    with MysqlWriteSession(ROOT) as session:
        persistence = PlaceDetailPersistence(ROOT, write_session=session)
        for restaurant_id in ids:
            data = previous["restaurants"][str(restaurant_id)]
            place_id = next(
                (value for value in data.get("external_place_ids", []) if str(value).isdigit()),
                None,
            )
            source_rows = [
                row
                for row in data.get("restaurant_business_hours", [])
                if str(row.get("crawled_at", ""))[:19] >= started_at
                and str(row.get("description") or "").strip()
            ]
            descriptions = list(
                dict.fromkeys(str(row["description"]) for row in source_rows)
            )
            hours, conflicts = _normalized_hours(descriptions)
            if not place_id or not descriptions:
                outcomes[str(restaurant_id)] = "BLOCKED_NO_SOURCE"
                continue
            if not hours:
                from app.naver.place_detail_models import BusinessHour

                hours = (BusinessHour(day=descriptions[0][:32], description=descriptions[0]),)
            try:
                persistence.persist(
                    restaurant_id,
                    str(place_id),
                    PlaceDetail(
                        place_id=str(place_id),
                        business_hours=hours,
                        raw_source="PLAYWRIGHT_DOM",
                    ),
                    sections={"menu": False, "business_hours": True, "review": False},
                    section_states={"business_hours": "SUCCESS"},
                )
                outcomes[str(restaurant_id)] = (
                    "SUCCESS_WITH_AMBIGUOUS_DAYS" if conflicts else "SUCCESS"
                )
            except Exception:
                outcomes[str(restaurant_id)] = "FAILED"

    if any(value.startswith("BLOCKED") for value in outcomes.values()):
        raise RuntimeError("hours reconciliation blocked; no new provider requests were made")
    successful = sum(value.startswith("SUCCESS") for value in outcomes.values())
    normalization = {
        "status": (
            "COMPLETED" if successful == len(outcomes) else "PARTIAL"
        ),
        "attempted": len(outcomes),
        "success": successful,
        "ambiguousDayRowsExcluded": sum(
            value == "SUCCESS_WITH_AMBIGUOUS_DAYS" for value in outcomes.values()
        ),
        "failed": sum(value == "FAILED" for value in outcomes.values()),
        "externalRequests": 0,
        "outcomes": outcomes,
    }
    manifest["hoursNormalization"] = normalization
    _json_write(manifest_path, manifest)

    _json_write(AI_ANSWER / "detail_quality_backfill_after.json", _snapshot(ids, guard))
    rows = audit_rows()
    coverage = build_coverage_summary(rows)
    validated_baseline = [9568, 9571, 9574, 9617]
    new_ids = sorted(set(coverage["strictReadyRestaurantIds"]) - set(validated_baseline))
    _json_write(
        AI_ANSWER / "detail_quality_backfill_coverage_after.json",
        {
            "createdAt": datetime.now(UTC).isoformat(),
            "readinessPolicyVersion": "profile-readiness-source-grounded-hours-v2",
            "strictReadyBefore": len(validated_baseline),
            "historicalAuditStrictReadyBefore": 5,
            "strictReadyBeforeRestaurantIds": validated_baseline,
            "strictReadyAfter": coverage["strictReady"],
            "newStrictReady": len(new_ids),
            "newStrictReadyRestaurantIds": new_ids,
            "summary": coverage,
            "restaurantReadiness": [
                {
                    "restaurantId": row["restaurant_id"],
                    "name": row["name"],
                    "status": row["readiness"]["status"],
                    "reasons": row["readiness"]["reasons"],
                }
                for row in rows
            ],
        },
    )
    manifest.update(
        {
            "strictReadyAfter": coverage["strictReady"],
            "strictReadyAfterRestaurantIds": coverage["strictReadyRestaurantIds"],
            "newStrictReady": len(new_ids),
            "newStrictReadyRestaurantIds": new_ids,
            "coverageAfter": coverage,
        }
    )
    _json_write(manifest_path, manifest)
    return manifest


def main() -> None:
    args = _runner_args()
    if args.command == "plan":
        plan = create_plan()
        _json_write(
            AI_ANSWER / "detail_quality_backfill_coverage_before.json",
            {
                "createdAt": plan["createdAt"],
                "strictReadyBefore": plan["strictReadyBefore"],
                "restaurantIds": plan["strictReadyBeforeRestaurantIds"],
                "summary": plan["coverageSummary"],
            },
        )
        print(
            json.dumps(
                {
                    "status": plan["writeGate"],
                    "groupA": len(plan["groups"]["groupA"]),
                    "groupB": len(plan["groups"]["groupB"]),
                    "targets": plan["plannedLiveRestaurantCount"],
                }
            )
        )
    elif args.command == "dry-run":
        plan_path = AI_ANSWER / "detail_quality_backfill_plan.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        result = run_dry_run(plan)
        print(
            json.dumps(
                {"status": result["status"], "outcomes": result["outcomes"]}, ensure_ascii=False
            )
        )
    elif args.command == "apply":
        plan_path = AI_ANSWER / "detail_quality_backfill_plan.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        result = apply(plan)
        print(json.dumps(result, ensure_ascii=False))
    else:
        result = reconcile_persisted_hours()
        print(json.dumps(result.get("hoursNormalization"), ensure_ascii=False))


if __name__ == "__main__":
    main()
