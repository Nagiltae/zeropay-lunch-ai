"""Run the frozen five-restaurant, offline Gemini menu-budget classification pilot."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from app.menu_budget_classifier import (
    CHUNK_SIZE,
    POLICY_VERSION,
    PROMPT_VERSION,
    ClassificationBatchError,
    classifier_from_environment,
    classify_with_bounded_retry,
)

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "AI_Answer/serving_model_v2_pilot_plan.json"
FIXTURE = ROOT / "AI_Answer/menu_budget_classifier_v2_fixture.json"
OUTPUT = ROOT / "AI_Answer/gemini_menu_budget_pilot_results.json"
CHECKPOINT = ROOT / "AI_Answer/gemini_menu_budget_pilot_checkpoint.json"
PLAN = ROOT / "AI_Answer/gemini_menu_budget_pilot_plan.json"
FROZEN_IDS = [9617, 9571, 9568, 10042, 9559]
REQUIRED_MODEL = "gemini-3.8-flash"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def freeze_plan() -> tuple[dict, list[dict]]:
    configured_model = os.getenv("GEMINI_MODEL", REQUIRED_MODEL)
    if configured_model != REQUIRED_MODEL:
        raise SystemExit("pilot requires GEMINI_MODEL=gemini-3.8-flash")
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    if fixture.get("frozenBeforeGeminiCall") is not True:
        raise SystemExit("fixture is not frozen")
    by_id = {int(row["restaurantId"]): row for row in source["inputs"]}
    if list(by_id) != FROZEN_IDS:
        raise SystemExit("frozen restaurant cohort mismatch")
    restaurants = []
    estimated_requests = 0
    for restaurant_id in FROZEN_IDS:
        menus = by_id[restaurant_id]["menus"]
        if not menus or any(not row.get("name") or row.get("priceValue") is None for row in menus):
            raise SystemExit(f"source rows incomplete for frozen restaurant {restaurant_id}")
        if len({int(row["id"]) for row in menus}) != len(menus):
            raise SystemExit(f"duplicate source menu id for frozen restaurant {restaurant_id}")
        requests = (len(menus) + CHUNK_SIZE - 1) // CHUNK_SIZE
        estimated_requests += requests
        restaurants.append(
            {
                "restaurantId": restaurant_id,
                "menuCount": len(menus),
                "chunkCount": requests,
                "menuIds": [int(row["id"]) for row in menus],
            }
        )
    plan = {
        "createdAt": datetime.now().astimezone().isoformat(),
        "status": "FROZEN_BEFORE_MODEL_CALL",
        "provider": "GEMINI",
        "model": configured_model,
        "policyVersion": POLICY_VERSION,
        "promptVersion": PROMPT_VERSION,
        "sourceArtifact": "AI_Answer/serving_model_v2_pilot_plan.json",
        "sourceSha256": sha256(SOURCE),
        "fixtureArtifact": "AI_Answer/menu_budget_classifier_v2_fixture.json",
        "fixtureSha256": sha256(FIXTURE),
        "restaurantIds": FROZEN_IDS,
        "restaurantCount": len(restaurants),
        "menuCount": sum(row["menuCount"] for row in restaurants),
        "chunkSize": CHUNK_SIZE,
        "estimatedApiRequests": estimated_requests,
        "retryPolicy": "one retry for network/5xx; project safety stops immediately on 429/403",
        "timeoutMs": 45000,
        "databaseWrites": 0,
        "qdrantWrites": 0,
        "restaurants": restaurants,
    }
    write_json(PLAN, plan)
    return plan, source["inputs"]


def run() -> int:
    key_present = bool(os.getenv("GEMINI_API_KEY"))
    google_key_present = bool(os.getenv("GOOGLE_API_KEY"))
    print(f"GEMINI_API_KEY_PRESENT={str(key_present).lower()}")
    print(f"GOOGLE_API_KEY_PRESENT={str(google_key_present).lower()}")
    if not key_present:
        raise SystemExit("GEMINI_API_KEY missing; no external call made")

    plan, inputs = freeze_plan()
    classifier = classifier_from_environment()
    if classifier.model != plan["model"]:
        raise SystemExit("classifier model does not match the frozen pilot plan")
    checkpoint = (
        json.loads(CHECKPOINT.read_text(encoding="utf-8"))
        if CHECKPOINT.exists()
        else {
            "provider": "GEMINI",
            "model": classifier.model,
            "restaurantResults": {},
            "requestCount": 0,
            "successfulRequests": 0,
            "failedRequests": 0,
            "retryCount": 0,
            "timeoutCount": 0,
            "rateLimitCount": 0,
            "serverErrorCount": 0,
            "elapsedSeconds": 0.0,
            "tokenUsage": {},
        }
    )
    checkpoint.setdefault("diagnosticApiRequests", 0)
    if checkpoint["model"] != classifier.model:
        raise SystemExit("checkpoint model mismatch; refusing to resume with different model")

    started_all = time.monotonic()
    source_by_id = {int(item["restaurantId"]): item for item in inputs}
    stopped_on_rate_limit = False
    stopped_on_client_error = False
    for target_index, restaurant_id in enumerate(FROZEN_IDS, start=1):
        target_key = str(restaurant_id)
        prior = checkpoint["restaurantResults"].get(target_key)
        if prior and prior.get("status") == "SUCCESS":
            print(f"{target_index}/{len(FROZEN_IDS)} restaurant={restaurant_id} SKIPPED_SUCCESS")
            continue
        menus = source_by_id[restaurant_id]["menus"]
        result = prior or {
            "restaurantId": restaurant_id,
            "status": "IN_PROGRESS",
            "classifications": [],
        }
        result["status"] = "IN_PROGRESS"
        result.setdefault("classifications", [])
        result.setdefault("chunks", {})
        for start in range(0, len(menus), CHUNK_SIZE):
            chunk = menus[start : start + CHUNK_SIZE]
            chunk_index = start // CHUNK_SIZE
            saved_chunks = result.setdefault("chunks", {})
            saved_chunk = saved_chunks.get(str(chunk_index))
            if saved_chunk and saved_chunk.get("status") == "SUCCESS":
                continue
            try:
                outcome = classify_with_bounded_retry(classifier, chunk)
                checkpoint["requestCount"] += outcome["attempts"]
                checkpoint["successfulRequests"] += 1
                checkpoint["retryCount"] += outcome["retries"]
                for token_name, count in outcome["usage"].items():
                    checkpoint["tokenUsage"][token_name] = (
                        checkpoint["tokenUsage"].get(token_name, 0) + count
                    )
                saved_chunks[str(chunk_index)] = {
                    "status": "SUCCESS",
                    "menuIds": [int(row["id"]) for row in chunk],
                    "classifications": outcome["classifications"],
                    "latencySeconds": outcome["latencySeconds"],
                    "attempts": outcome["attempts"],
                }
                result["classifications"].extend(outcome["classifications"])
            except ClassificationBatchError as error:
                message = str(error)
                checkpoint["failedRequests"] += 1
                checkpoint["requestCount"] += error.attempts
                checkpoint["retryCount"] += error.retries
                if "timeout" in message.lower():
                    checkpoint["timeoutCount"] += 1
                if error.status_code == 429:
                    checkpoint["rateLimitCount"] += 1
                    stopped_on_rate_limit = True
                elif isinstance(error.status_code, int) and 400 <= error.status_code < 500:
                    stopped_on_client_error = True
                if isinstance(error.status_code, int) and 500 <= error.status_code <= 599:
                    checkpoint["serverErrorCount"] += 1
                saved_chunks[str(chunk_index)] = {
                    "status": "FAILED",
                    "menuIds": [int(row["id"]) for row in chunk],
                    "errorCode": message[:120],
                }
                result["status"] = "FAILED"
                break
            checkpoint["restaurantResults"][target_key] = result
            checkpoint["elapsedSeconds"] = round(time.monotonic() - started_all, 3)
            write_json(CHECKPOINT, checkpoint)
            print(
                f"{target_index}/{len(FROZEN_IDS)} restaurant={restaurant_id} "
                f"chunk={chunk_index + 1}/{(len(menus) + CHUNK_SIZE - 1) // CHUNK_SIZE} "
                f"requests={checkpoint['requestCount']} retries={checkpoint['retryCount']}"
            )
            if stopped_on_rate_limit or stopped_on_client_error:
                break
        else:
            result["status"] = "SUCCESS"
        checkpoint["restaurantResults"][target_key] = result
        write_json(CHECKPOINT, checkpoint)
        if stopped_on_rate_limit or stopped_on_client_error:
            break

    plan["status"] = "EXECUTED"
    write_json(PLAN, plan)
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    all_rows = {
        int(row["id"]): {**row, "_restaurantId": int(item["restaurantId"])}
        for item in inputs
        for row in item["menus"]
    }
    all_classes = {
        int(row["menuId"]): row
        for result in checkpoint["restaurantResults"].values()
        for row in result.get("classifications", [])
    }
    evaluation = evaluate_fixtures(fixture["cases"], all_rows, all_classes)
    completed_restaurants = sum(
        result.get("status") == "SUCCESS"
        for result in checkpoint["restaurantResults"].values()
    )
    classified_menu_count = len(all_classes)
    complete = (
        completed_restaurants == len(FROZEN_IDS)
        and classified_menu_count == plan["menuCount"]
    )
    pilot_status = (
        "GO_FOR_IMPORT_REVIEW"
        if complete
        and evaluation["criticalFalsePositives"] == 0
        and not evaluation["fixtureErrors"]
        and evaluation["critical"]["incorrect"] == 0
        and evaluation["positive"]["incorrect"] == 0
        and evaluation["ambiguous"]["unacceptable"] == 0
        else "NO_GO"
    )
    final = {
        "provider": "GEMINI",
        "model": classifier.model,
        "policyVersion": POLICY_VERSION,
        "promptVersion": PROMPT_VERSION,
        "sourceArtifactSha256": plan["sourceSha256"],
        "fixtureArtifactSha256": plan["fixtureSha256"],
        "restaurantIds": FROZEN_IDS,
        "restaurantCount": len(FROZEN_IDS),
        "menuCount": plan["menuCount"],
        "pilotStatus": pilot_status,
        "completion": "COMPLETE" if complete else "INCOMPLETE",
        "completedRestaurants": completed_restaurants,
        "restaurantsWithAnyClassification": sum(
            bool(result.get("classifications"))
            for result in checkpoint["restaurantResults"].values()
        ),
        "classifiedMenuCount": classified_menu_count,
        "apiRequestCount": checkpoint["requestCount"],
        "diagnosticApiRequests": checkpoint["diagnosticApiRequests"],
        "successfulApiRequests": checkpoint["successfulRequests"],
        "failedApiAttempts": max(0, checkpoint["requestCount"] - checkpoint["successfulRequests"]),
        "successfulRequests": checkpoint["successfulRequests"],
        "failedRequests": checkpoint["failedRequests"],
        "retryCount": checkpoint["retryCount"],
        "timeoutCount": checkpoint["timeoutCount"],
        "rateLimitCount": checkpoint["rateLimitCount"],
        "serverErrorCount": checkpoint["serverErrorCount"],
        "elapsedSeconds": checkpoint["elapsedSeconds"],
        "tokenUsage": checkpoint["tokenUsage"],
        "restaurants": checkpoint["restaurantResults"],
        "fixtureEvaluation": evaluation,
        "databaseWrites": 0,
        "qdrantWrites": 0,
        "stoppedOnRateLimit": stopped_on_rate_limit,
        "stoppedOnClientError": stopped_on_client_error,
    }
    write_json(OUTPUT, final)
    print(f"Pilot artifact written: {OUTPUT.relative_to(ROOT)}")
    print(f"Fixture critical false positives: {evaluation['criticalFalsePositives']}")
    return 0 if not stopped_on_rate_limit else 2


def evaluate_fixtures(
    cases: list[dict], input_rows: dict[int, dict], outputs: dict[int, dict]
) -> dict:
    outcomes = {
        "critical": {"total": 0, "correct": 0, "incorrect": 0, "unknown": 0},
        "positive": {"total": 0, "correct": 0, "incorrect": 0, "unknown": 0},
        "ambiguous": {"total": 0, "acceptable": 0, "unacceptable": 0},
        "criticalFalsePositives": 0,
        "fixtureErrors": [],
    }
    for case in cases:
        menu_id = int(case["menuId"])
        row = input_rows.get(menu_id)
        output = outputs.get(menu_id)
        if row is None or output is None:
            outcomes["fixtureErrors"].append({"menuId": menu_id, "issue": "missing input/output"})
            continue
        if int(case["restaurantId"]) != row["_restaurantId"]:
            outcomes["fixtureErrors"].append({"menuId": menu_id, "issue": "restaurant mismatch"})
            continue
        eligibility = output["budgetEligibility"]
        flags = set(output["flags"])
        kind = case["kind"]
        if kind == "ambiguous":
            outcomes["ambiguous"]["total"] += 1
            if eligibility == "UNKNOWN":
                outcomes["ambiguous"]["acceptable"] += 1
            else:
                outcomes["ambiguous"]["unacceptable"] += 1
            continue
        bucket = outcomes["critical" if kind == "critical_negative" else "positive"]
        bucket["total"] += 1
        expected = case["expectedEligibility"]
        is_correct = eligibility == expected and set(case["requiredFlags"]).issubset(flags)
        bucket["correct" if is_correct else "incorrect"] += 1
        if eligibility == "UNKNOWN":
            bucket["unknown"] += 1
        if kind == "critical_negative" and eligibility == "ELIGIBLE":
            outcomes["criticalFalsePositives"] += 1
    for bucket in (outcomes["critical"], outcomes["positive"]):
        bucket["accuracy"] = bucket["correct"] / bucket["total"] if bucket["total"] else None
    return outcomes


if __name__ == "__main__":
    sys.exit(run())
