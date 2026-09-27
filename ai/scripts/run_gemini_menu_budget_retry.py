"""Sequential, paced retry run for the frozen Gemini menu-budget pilot."""

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
    MODEL_DEFAULT,
    POLICY_VERSION,
    PROMPT_VERSION,
    ClassificationBatchError,
    RequestPacer,
    classifier_from_environment,
    classify_with_bounded_retry,
)
from scripts.run_gemini_menu_budget_pilot import evaluate_fixtures

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "AI_Answer/serving_model_v2_pilot_plan.json"
FIXTURE = ROOT / "AI_Answer/menu_budget_classifier_v2_fixture.json"
PLAN = ROOT / "AI_Answer/gemini_menu_budget_retry_plan.json"
CHECKPOINT = ROOT / "AI_Answer/gemini_menu_budget_retry_checkpoint.json"
RESULTS = ROOT / "AI_Answer/gemini_menu_budget_retry_results.json"
RUN_ID = "gemini-menu-budget-v2-retry-1"
FROZEN_IDS = [9617, 9571, 9568, 10042, 9559]
EXPECTED_SOURCE_SHA = "f02986eb39560164929b7314051324c3a45ec3c7d0742a966314958ae8119eed"
EXPECTED_FIXTURE_SHA = "702ed02da4aa6836553d3d6e271f1cc72eaf6966a7f0ff43769c2dd5f8232145"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def make_plan() -> tuple[dict, list[dict], dict]:
    model = os.getenv("GEMINI_MODEL", MODEL_DEFAULT)
    if model != MODEL_DEFAULT:
        raise SystemExit("GEMINI_MODEL must be gemini-3.8-flash; no fallback is allowed")
    source_sha, fixture_sha = sha256(SOURCE), sha256(FIXTURE)
    if source_sha != EXPECTED_SOURCE_SHA or fixture_sha != EXPECTED_FIXTURE_SHA:
        raise SystemExit("frozen source/fixture fingerprint drift; refusing external requests")
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    if fixture.get("frozenBeforeGeminiCall") is not True:
        raise SystemExit("fixture is not frozen")
    by_id = {int(row["restaurantId"]): row for row in source["inputs"]}
    if list(by_id) != FROZEN_IDS:
        raise SystemExit("frozen restaurant cohort drift")
    restaurants = []
    for restaurant_id in FROZEN_IDS:
        menus = by_id[restaurant_id]["menus"]
        if len({int(row["id"]) for row in menus}) != len(menus):
            raise SystemExit(f"duplicate source menu ID for restaurant {restaurant_id}")
        restaurants.append(
            {
                "restaurantId": restaurant_id,
                "menuCount": len(menus),
                "chunkCount": (len(menus) + CHUNK_SIZE - 1) // CHUNK_SIZE,
                "menuIds": [int(row["id"]) for row in menus],
            }
        )
    interval = float(os.getenv("GEMINI_REQUEST_INTERVAL_SECONDS", "3"))
    if interval < 0:
        raise SystemExit("GEMINI_REQUEST_INTERVAL_SECONDS must be non-negative")
    plan = {
        "runId": RUN_ID,
        "createdAt": datetime.now().astimezone().isoformat(),
        "status": "FROZEN_BEFORE_MODEL_CALL",
        "provider": "GEMINI",
        "model": model,
        "policyVersion": POLICY_VERSION,
        "promptVersion": PROMPT_VERSION,
        "sourceArtifact": "AI_Answer/serving_model_v2_pilot_plan.json",
        "sourceSha256": source_sha,
        "fixtureArtifact": "AI_Answer/menu_budget_classifier_v2_fixture.json",
        "fixtureSha256": fixture_sha,
        "restaurantIds": FROZEN_IDS,
        "restaurantCount": len(restaurants),
        "menuCount": sum(row["menuCount"] for row in restaurants),
        "chunkSize": CHUNK_SIZE,
        "estimatedApiRequests": sum(row["chunkCount"] for row in restaurants),
        "diagnosticApiRequests": 0,
        "requestIntervalSeconds": interval,
        "sequentialRequests": True,
        "retryPolicy": "initial + one retry for network/5xx; 429/403/400 stop immediately",
        "timeoutMs": 45000,
        "qualityGateFrozenBeforeCall": {
            "completion": "5/5 restaurants and 188/188 assigned menus",
            "criticalFalsePositives": 0,
            "structuralErrors": 0,
            "clearPositiveIncorrect": 0,
            "ambiguousRequiresUnknown": True,
        },
        "databaseWrites": 0,
        "qdrantWrites": 0,
        "restaurants": restaurants,
    }
    return plan, source["inputs"], fixture


def empty_checkpoint(plan: dict) -> dict:
    return {
        "runId": RUN_ID,
        "model": plan["model"],
        "sourceSha256": plan["sourceSha256"],
        "fixtureSha256": plan["fixtureSha256"],
        "restaurantResults": {},
        "requestEvents": [],
        "apiRequestCount": 0,
        "successfulApiRequests": 0,
        "failedApiRequests": 0,
        "retryCount": 0,
        "statusCounts": {"400": 0, "403": 0, "429": 0, "5xx": 0, "network": 0, "timeout": 0},
        "tokenUsage": {},
        "terminalStop": None,
        "lastRequestStartedAt": None,
        "elapsedSeconds": 0.0,
    }


def reusable_chunk(
    checkpoint: dict, restaurant_id: int, chunk_index: int, menu_ids: list[int]
) -> bool:
    """Only skip a resume chunk whose persisted success exactly matches frozen input IDs."""
    saved = (
        checkpoint.get("restaurantResults", {})
        .get(str(restaurant_id), {})
        .get("chunks", {})
        .get(str(chunk_index))
    )
    return bool(
        saved
        and saved.get("status") == "SUCCESS"
        and saved.get("menuIds") == menu_ids
        and len(saved.get("classifications", [])) == len(menu_ids)
        and {item.get("menuId") for item in saved.get("classifications", [])} == set(menu_ids)
    )


def validate_resume_checkpoint(checkpoint: dict, plan: dict) -> None:
    expected = (RUN_ID, plan["model"], plan["sourceSha256"], plan["fixtureSha256"])
    actual = tuple(
        checkpoint.get(key) for key in ("runId", "model", "sourceSha256", "fixtureSha256")
    )
    if actual != expected:
        raise SystemExit("checkpoint belongs to another run/input; refusing resume")
    if checkpoint.get("terminalStop"):
        raise SystemExit("checkpoint is terminal; refusing to send any additional API request")


def fixture_structure_errors(evaluation: dict) -> int:
    return len(evaluation.get("fixtureErrors", []))


def finalize(
    plan: dict, checkpoint: dict, inputs: list[dict], fixture: dict, started: float
) -> dict:
    input_rows = {
        int(menu["id"]): {**menu, "_restaurantId": int(restaurant["restaurantId"])}
        for restaurant in inputs
        for menu in restaurant["menus"]
    }
    classes = {
        int(item["menuId"]): item
        for result in checkpoint["restaurantResults"].values()
        for chunk in result.get("chunks", {}).values()
        if chunk.get("status") == "SUCCESS"
        for item in chunk.get("classifications", [])
    }
    evaluation = evaluate_fixtures(fixture["cases"], input_rows, classes)
    completed = sum(
        result.get("status") == "SUCCESS"
        and sum(
            len(chunk.get("menuIds", []))
            for chunk in result.get("chunks", {}).values()
            if chunk.get("status") == "SUCCESS"
        )
        == len(next(item["menus"] for item in inputs if int(item["restaurantId"]) == int(key)))
        for key, result in checkpoint["restaurantResults"].items()
    )
    assigned = len(classes)
    complete = completed == 5 and assigned == plan["menuCount"]
    critical_fp = evaluation["criticalFalsePositives"]
    semantic_pass = (
        complete
        and critical_fp == 0
        and fixture_structure_errors(evaluation) == 0
        and evaluation["critical"]["incorrect"] == 0
        and evaluation["positive"]["incorrect"] == 0
        and evaluation["ambiguous"]["unacceptable"] == 0
    )
    if checkpoint.get("terminalStop") == 429:
        status = "INCOMPLETE_RATE_LIMIT"
    elif checkpoint.get("terminalStop") == "PROVIDER_AVAILABILITY":
        status = "INCOMPLETE_PROVIDER_AVAILABILITY"
    elif not complete:
        status = "INCOMPLETE_PROVIDER_AVAILABILITY"
    elif semantic_pass:
        status = "GO_FOR_IMPORT_REVIEW"
    else:
        status = "COMPLETE_SEMANTIC_NO_GO"
    events = checkpoint["requestEvents"]
    intervals = [
        (
            datetime.fromisoformat(events[i]["startedAt"])
            - datetime.fromisoformat(events[i - 1]["startedAt"])
        ).total_seconds()
        for i in range(1, len(events))
    ]
    return {
        "runId": RUN_ID,
        "provider": "GEMINI",
        "model": plan["model"],
        "sourceArtifactSha256": plan["sourceSha256"],
        "fixtureArtifactSha256": plan["fixtureSha256"],
        "restaurantIds": FROZEN_IDS,
        "restaurantCount": 5,
        "menuCount": plan["menuCount"],
        "chunkCount": plan["estimatedApiRequests"],
        "pilotStatus": status,
        "completion": "COMPLETE" if complete else "INCOMPLETE",
        "completedRestaurants": completed,
        "classifiedMenuCount": assigned,
        "unknownAssignedMenuCount": sum(
            item["budgetEligibility"] == "UNKNOWN" for item in classes.values()
        ),
        "omittedMenuCount": sum(
            len(chunk.get("omittedMenuIds", []))
            for result in checkpoint["restaurantResults"].values()
            for chunk in result.get("chunks", {}).values()
            if chunk.get("status") == "SUCCESS"
        ),
        "apiRequestCount": checkpoint["apiRequestCount"],
        "diagnosticApiRequestCount": 0,
        "successfulApiRequests": checkpoint["successfulApiRequests"],
        "failedApiRequests": checkpoint["failedApiRequests"],
        "retryCount": checkpoint["retryCount"],
        "statusCounts": checkpoint["statusCounts"],
        "requestIntervalSeconds": plan["requestIntervalSeconds"],
        "observedRequestIntervalSeconds": intervals,
        "meanRequestIntervalSeconds": round(sum(intervals) / len(intervals), 3)
        if intervals
        else None,
        "wallClockElapsedSeconds": round(time.monotonic() - started, 3),
        "requestEvents": events,
        "fixtureEvaluation": evaluation if complete else None,
        "structuralValidation": {
            "successfulChunksValidated": sum(
                chunk.get("status") == "SUCCESS"
                for result in checkpoint["restaurantResults"].values()
                for chunk in result.get("chunks", {}).values()
            ),
            "structuralErrors": 0,
            "evaluationStatus": "COMPLETE" if complete else "NOT_RUN_INCOMPLETE_PILOT",
        },
        "databaseWrites": 0,
        "qdrantWrites": 0,
        "geminiRawOutputPersistedToRuntime": False,
        "springImporterImplemented": False,
        "tokenUsage": checkpoint["tokenUsage"],
        "restaurants": checkpoint["restaurantResults"],
    }


def run() -> int:
    key_present = bool(os.getenv("GEMINI_API_KEY"))
    google_key_present = bool(os.getenv("GOOGLE_API_KEY"))
    print(f"GEMINI_API_KEY_PRESENT={str(key_present).lower()}")
    print(f"GOOGLE_API_KEY_PRESENT={str(google_key_present).lower()}")
    if not key_present or google_key_present:
        raise SystemExit("expected GEMINI_API_KEY only; no external request made")
    plan, inputs, fixture = make_plan()
    if RESULTS.exists():
        raise SystemExit("retry results already exist; refusing to overwrite")
    if PLAN.exists() and not CHECKPOINT.exists():
        raise SystemExit("retry plan exists without checkpoint; refusing ambiguous run")
    if PLAN.exists():
        old_plan = json.loads(PLAN.read_text(encoding="utf-8"))
        for key in (
            "runId",
            "model",
            "sourceSha256",
            "fixtureSha256",
            "restaurantIds",
            "menuCount",
        ):
            if old_plan.get(key) != plan.get(key):
                raise SystemExit("existing retry plan mismatch; refusing resume")
    else:
        write_json(PLAN, plan)
    classifier = classifier_from_environment()
    if classifier.model != MODEL_DEFAULT:
        raise SystemExit("classifier model mismatch; no fallback is allowed")
    checkpoint = (
        json.loads(CHECKPOINT.read_text()) if CHECKPOINT.exists() else empty_checkpoint(plan)
    )
    validate_resume_checkpoint(checkpoint, plan)
    write_json(CHECKPOINT, checkpoint)
    prior_request = checkpoint.get("lastRequestStartedAt")
    elapsed_since_prior = None
    if prior_request:
        elapsed_since_prior = (
            datetime.now().astimezone() - datetime.fromisoformat(prior_request)
        ).total_seconds()
    pacer = RequestPacer(
        plan["requestIntervalSeconds"],
        elapsed_since_last_request=elapsed_since_prior,
    )
    started = time.monotonic()
    source_by_id = {int(row["restaurantId"]): row for row in inputs}
    stop = False

    for restaurant_index, restaurant_id in enumerate(FROZEN_IDS, 1):
        key = str(restaurant_id)
        result = checkpoint["restaurantResults"].setdefault(
            key, {"restaurantId": restaurant_id, "status": "IN_PROGRESS", "chunks": {}}
        )
        menus = source_by_id[restaurant_id]["menus"]
        chunks = result.setdefault("chunks", {})
        for chunk_index, offset in enumerate(range(0, len(menus), CHUNK_SIZE)):
            chunk = menus[offset : offset + CHUNK_SIZE]
            chunk_key = str(chunk_index)
            expected_ids = [int(row["id"]) for row in chunk]
            if reusable_chunk(checkpoint, restaurant_id, chunk_index, expected_ids):
                continue
            context = {"restaurantId": restaurant_id, "chunkIndex": chunk_index}

            def on_attempt(attempt: int, request_context=context) -> None:
                now = datetime.now().astimezone().isoformat()
                checkpoint["apiRequestCount"] += 1
                checkpoint["lastRequestStartedAt"] = now
                event = {
                    "requestOrdinal": checkpoint["apiRequestCount"],
                    "startedAt": now,
                    **request_context,
                    "attempt": attempt,
                }
                checkpoint["requestEvents"].append(event)
                write_json(CHECKPOINT, checkpoint)

            def on_outcome(attempt: int, status_code, diagnostics: dict) -> None:
                event = checkpoint["requestEvents"][-1]
                if status_code is None:
                    checkpoint["successfulApiRequests"] += 1
                    event["outcome"] = "SUCCESS"
                else:
                    checkpoint["failedApiRequests"] += 1
                    event.update(diagnostics)
                    event["statusCode"] = status_code if isinstance(status_code, int) else None
                    event["outcome"] = "FAILED"
                    if status_code == 400:
                        checkpoint["statusCounts"]["400"] += 1
                    elif status_code == 403:
                        checkpoint["statusCounts"]["403"] += 1
                    elif status_code == 429:
                        checkpoint["statusCounts"]["429"] += 1
                    elif isinstance(status_code, int) and 500 <= status_code <= 599:
                        checkpoint["statusCounts"]["5xx"] += 1
                    elif status_code is None:
                        checkpoint["statusCounts"]["network"] += 1
                        if diagnostics.get("safeErrorCategory") == "timeout":
                            checkpoint["statusCounts"]["timeout"] += 1
                write_json(CHECKPOINT, checkpoint)

            try:
                outcome = classify_with_bounded_retry(
                    classifier,
                    chunk,
                    before_request=pacer.before_request,
                    on_attempt=on_attempt,
                    on_outcome=on_outcome,
                )
            except ClassificationBatchError as error:
                checkpoint["retryCount"] += error.retries
                status = error.status_code
                chunks[chunk_key] = {
                    "status": "FAILED",
                    "menuIds": [int(row["id"]) for row in chunk],
                    "safeError": str(error),
                    "statusCode": status,
                    "attempts": error.attempts,
                }
                if status == 429:
                    checkpoint["terminalStop"] = 429
                elif status == 403:
                    checkpoint["terminalStop"] = 403
                elif status == 400 or (status is not None and 400 <= status < 500):
                    checkpoint["terminalStop"] = status
                elif isinstance(status, int) and status >= 500:
                    checkpoint["terminalStop"] = "PROVIDER_AVAILABILITY"
                else:
                    checkpoint["terminalStop"] = "PROVIDER_AVAILABILITY"
                result["status"] = "INCOMPLETE"
                write_json(CHECKPOINT, checkpoint)
                stop = True
                break
            checkpoint["retryCount"] += outcome["retries"]
            for token, count in outcome["usage"].items():
                checkpoint["tokenUsage"][token] = checkpoint["tokenUsage"].get(token, 0) + count
            chunks[chunk_key] = {
                "status": "SUCCESS",
                "menuIds": expected_ids,
                "classifications": outcome["classifications"],
                "omittedMenuIds": outcome["omittedMenuIds"],
                "attempts": outcome["attempts"],
                "latencySeconds": outcome["latencySeconds"],
            }
            write_json(CHECKPOINT, checkpoint)
            done_chunks = sum(item.get("status") == "SUCCESS" for item in chunks.values())
            print(
                f"restaurant {restaurant_index}/5 id={restaurant_id} "
                f"chunk {done_chunks}/{(len(menus) + CHUNK_SIZE - 1) // CHUNK_SIZE} "
                f"requests={checkpoint['apiRequestCount']} retries={checkpoint['retryCount']}"
            )
        if stop:
            break
        result["status"] = (
            "SUCCESS"
            if all(
                chunks.get(str(i), {}).get("status") == "SUCCESS"
                for i in range((len(menus) + CHUNK_SIZE - 1) // CHUNK_SIZE)
            )
            else "IN_PROGRESS"
        )
        write_json(CHECKPOINT, checkpoint)

    plan["status"] = "EXECUTED"
    write_json(PLAN, plan)
    final = finalize(plan, checkpoint, inputs, fixture, started)
    write_json(RESULTS, final)
    print(
        f"pilot={final['pilotStatus']} restaurants={final['completedRestaurants']}/5 "
        f"menus={final['classifiedMenuCount']}/{final['menuCount']} "
        f"requests={final['apiRequestCount']}"
    )
    return 0 if final["pilotStatus"] == "GO_FOR_IMPORT_REVIEW" else 2


if __name__ == "__main__":
    sys.exit(run())
