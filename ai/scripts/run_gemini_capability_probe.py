"""Run a small, staged live capability probe for the frozen Gemini model."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from google import genai
from google.genai import types

from app.gemini_capability_probe import GeminiCapabilityProbe
from app.menu_budget_classifier import (
    MODEL_DEFAULT,
    TIMEOUT_MS,
    GeminiMenuBudgetClassifier,
    MenuBudgetResponseSchema,
    build_menu_classification_prompt,
)

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "AI_Answer/serving_model_v2_pilot_plan.json"
FIXTURE = ROOT / "AI_Answer/menu_budget_classifier_v2_fixture.json"
FIRST_RESULTS = ROOT / "AI_Answer/gemini_menu_budget_pilot_results.json"
RETRY_RESULTS = ROOT / "AI_Answer/gemini_menu_budget_retry_results.json"
PLAN = ROOT / "AI_Answer/gemini_capability_probe_plan.json"
RESULTS = ROOT / "AI_Answer/gemini_capability_probe_results.json"
RUN_ID = "gemini-capability-probe-1"
REQUIRED_SOURCE_SHA = "f02986eb39560164929b7314051324c3a45ec3c7d0742a966314958ae8119eed"
REQUIRED_FIXTURE_SHA = "702ed02da4aa6836553d3d6e271f1cc72eaf6966a7f0ff43769c2dd5f8232145"
MINIMAL_SCHEMA = {
    "type": "OBJECT",
    "properties": {"status": {"type": "STRING", "enum": ["OK"]}},
    "required": ["status"],
}
PLAIN_PROMPT = "Reply with exactly: OK"
STRUCTURED_PROMPT = 'Return exactly this JSON object: {"status":"OK"}'
COHORT = [9617, 9571, 9568, 10042, 9559]
STAGE3_MENU_ID = 8328
STAGE4_MENU_IDS = [8328, 8333, 8738]
STAGE5_MENU_IDS = list(range(8727, 8739))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_bytes(menus: list[dict]) -> int:
    return len(build_menu_classification_prompt(menus).encode("utf-8"))


def stage0_preflight() -> dict:
    import google.genai  # noqa: F401 - intentional import verification

    model = os.getenv("GEMINI_MODEL", MODEL_DEFAULT)
    key_present = bool(os.getenv("GEMINI_API_KEY"))
    google_key_present = bool(os.getenv("GOOGLE_API_KEY"))
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=MINIMAL_SCHEMA,
        temperature=0,
    )
    serialized_config = json.dumps(config.model_dump(mode="json", exclude_none=True))
    schema_valid = json.loads(serialized_config).get("response_schema") == MINIMAL_SCHEMA
    classifier_config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=MenuBudgetResponseSchema,
        temperature=0,
    )
    classifier_schema_valid = (
        json.loads(json.dumps(classifier_config.model_dump(mode="json", exclude_none=True))).get(
            "response_schema"
        )
        == MenuBudgetResponseSchema
    )
    checks = {
        "sdkImport": True,
        "sdkVersion": importlib.metadata.version("google-genai"),
        "model": model,
        "modelValid": model == MODEL_DEFAULT,
        "geminiApiKeyPresent": key_present,
        "googleApiKeyPresent": google_key_present,
        "timeoutMs": TIMEOUT_MS,
        "structuredSchemaSerializable": schema_valid,
        "classifierSchemaSerializable": classifier_schema_valid,
    }
    checks["pass"] = (
        checks["modelValid"]
        and key_present
        and not google_key_present
        and schema_valid
        and classifier_schema_valid
    )
    return checks


def frozen_inputs() -> tuple[dict, dict, list[dict], dict[int, dict]]:
    for artifact in (FIRST_RESULTS, RETRY_RESULTS, FIXTURE):
        if not artifact.is_file():
            raise SystemExit(f"required historical artifact missing: {artifact.name}")
    source_sha = sha256(SOURCE)
    fixture_sha = sha256(FIXTURE)
    first = json.loads(FIRST_RESULTS.read_text(encoding="utf-8"))
    retry = json.loads(RETRY_RESULTS.read_text(encoding="utf-8"))
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    if (
        source_sha != REQUIRED_SOURCE_SHA
        or fixture_sha != REQUIRED_FIXTURE_SHA
        or first.get("sourceArtifactSha256") != source_sha
        or retry.get("sourceArtifactSha256") != source_sha
        or first.get("fixtureArtifactSha256") != fixture_sha
        or retry.get("fixtureArtifactSha256") != fixture_sha
    ):
        raise SystemExit("historical frozen input fingerprint mismatch; no API call permitted")
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    if [int(row["restaurantId"]) for row in source["inputs"]] != COHORT:
        raise SystemExit("frozen five-restaurant input cohort mismatch")
    by_restaurant = {int(item["restaurantId"]): item["menus"] for item in source["inputs"]}
    by_id = {
        int(row["id"]): {**row, "_restaurantId": restaurant_id}
        for restaurant_id, menus in by_restaurant.items()
        for row in menus
    }
    ids = set(by_id)
    expected_ids = set(STAGE4_MENU_IDS + STAGE5_MENU_IDS)
    if STAGE3_MENU_ID not in ids or not expected_ids.issubset(ids):
        raise SystemExit("probe menu IDs do not exist in frozen source")
    if [int(row["id"]) for row in by_restaurant[9617][:12]] != STAGE5_MENU_IDS:
        raise SystemExit("Stage 5 is not the historical 9617 chunk index 0")
    fixture_by_id = {int(case["menuId"]): case for case in fixture["cases"]}
    selected_fixture_ids = set([STAGE3_MENU_ID, *STAGE4_MENU_IDS])
    if not selected_fixture_ids.issubset(fixture_by_id):
        raise SystemExit("probe selected menu lacks a frozen fixture case")
    return source, fixture, [by_id[key] for key in sorted(ids)], fixture_by_id


def create_plan(preflight: dict, inputs: list[dict], fixture_by_id: dict[int, dict]) -> dict:
    menus = {int(row["id"]): row for row in inputs}
    interval = float(os.getenv("GEMINI_PROBE_INTERVAL_SECONDS", "5"))
    if interval < 5:
        raise SystemExit("GEMINI_PROBE_INTERVAL_SECONDS must be at least 5 seconds")
    definitions = [
        {
            "stage": 1,
            "type": "plain_text",
            "maxIndependentRequests": 3,
            "menuIds": [],
            "inputBytes": len(PLAIN_PROMPT.encode("utf-8")),
        },
        {
            "stage": 2,
            "type": "structured_minimal",
            "maxIndependentRequests": 2,
            "menuIds": [],
            "inputBytes": len(STRUCTURED_PROMPT.encode("utf-8")),
        },
        {
            "stage": 3,
            "type": "menu_classifier",
            "maxIndependentRequests": 1,
            "menuIds": [STAGE3_MENU_ID],
        },
        {
            "stage": 4,
            "type": "menu_classifier",
            "maxIndependentRequests": 1,
            "menuIds": STAGE4_MENU_IDS,
        },
        {
            "stage": 5,
            "type": "menu_classifier",
            "maxIndependentRequests": 1,
            "menuIds": STAGE5_MENU_IDS,
        },
    ]
    for stage in definitions[2:]:
        stage["menuCount"] = len(stage["menuIds"])
        stage["inputBytes"] = json_bytes([menus[menu_id] for menu_id in stage["menuIds"]])
        stage["frozenFixture"] = {
            str(menu_id): {
                "kind": fixture_by_id[menu_id]["kind"],
                "expectedEligibility": fixture_by_id[menu_id]["expectedEligibility"],
                "requiredFlags": fixture_by_id[menu_id]["requiredFlags"],
            }
            for menu_id in stage["menuIds"]
            if menu_id in fixture_by_id
        }
    source_sha = sha256(SOURCE)
    fixture_sha = sha256(FIXTURE)
    inputs = json.loads(SOURCE.read_text(encoding="utf-8"))["inputs"]
    return {
        "runId": RUN_ID,
        "createdAt": datetime.now().astimezone().isoformat(),
        "model": MODEL_DEFAULT,
        "provider": "GEMINI",
        "sourceArtifactSha256": source_sha,
        "fixtureArtifactSha256": fixture_sha,
        "restaurantIds": COHORT,
        "sourceMenuCount": sum(len(item["menus"]) for item in inputs),
        "requestIntervalSeconds": interval,
        "payloadBytesDefinition": "UTF-8 byte count of exact contents text; SDK envelope excluded",
        "estimatedNominalRequests": 8,
        "maximumAttemptsWithRetries": 16,
        "retryPolicy": "initial + one retry for network/5xx; no retry for 400/403/429",
        "stages": definitions,
        "stage0": preflight,
        "databaseWrites": 0,
        "qdrantWrites": 0,
        "runtimeGemini": False,
    }


def expected_case(case: dict) -> dict:
    return {
        "budgetEligibility": case["expectedEligibility"],
        "flags": case["requiredFlags"],
    }


def run() -> int:
    key_present = bool(os.getenv("GEMINI_API_KEY"))
    google_key_present = bool(os.getenv("GOOGLE_API_KEY"))
    model = os.getenv("GEMINI_MODEL", MODEL_DEFAULT)
    print(f"GEMINI_API_KEY_PRESENT={str(key_present).lower()}")
    print(f"GOOGLE_API_KEY_PRESENT={str(google_key_present).lower()}")
    print(f"GEMINI_MODEL={model}")
    if PLAN.exists() or RESULTS.exists():
        raise SystemExit("probe artifacts already exist; refusing to overwrite")
    preflight = stage0_preflight()
    _, _, all_menus, fixture_by_id = frozen_inputs()
    menus_by_id = {int(row["id"]): row for row in all_menus}
    plan = create_plan(preflight, all_menus, fixture_by_id)
    PLAN.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not preflight["pass"]:
        final = {
            "runId": RUN_ID,
            "probeStatus": "ENVIRONMENT_BLOCKED",
            "stage0": preflight,
            "stages": {},
            "apiRequestCount": 0,
            "retryCount": 0,
            "databaseWrites": 0,
            "qdrantWrites": 0,
        }
        RESULTS.write_text(json.dumps(final, ensure_ascii=False, indent=2) + "\n")
        return 2

    client = genai.Client(
        api_key=os.environ["GEMINI_API_KEY"],
        http_options=types.HttpOptions(
            timeout=TIMEOUT_MS,
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    )
    classifier = GeminiMenuBudgetClassifier(
        api_key=os.environ["GEMINI_API_KEY"], model=MODEL_DEFAULT, client=client
    )

    def plain_call():
        return client.models.generate_content(model=MODEL_DEFAULT, contents=PLAIN_PROMPT)

    def structured_call():
        return client.models.generate_content(
            model=MODEL_DEFAULT,
            contents=STRUCTURED_PROMPT,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=MINIMAL_SCHEMA,
                temperature=0,
            ),
        )

    def menu_call(selected: list[dict]):
        return classifier.classify(selected)

    stage1_prompt_bytes = len(PLAIN_PROMPT.encode("utf-8"))
    stage2_prompt_bytes = len(STRUCTURED_PROMPT.encode("utf-8"))
    result = GeminiCapabilityProbe(interval_seconds=plan["requestIntervalSeconds"]).run(
        plain_call=plain_call,
        structured_call=structured_call,
        menu_call=menu_call,
        menus_single=[menus_by_id[STAGE3_MENU_ID]],
        menus_three=[menus_by_id[menu_id] for menu_id in STAGE4_MENU_IDS],
        menus_twelve=[menus_by_id[menu_id] for menu_id in STAGE5_MENU_IDS],
        expected_single=expected_case(fixture_by_id[STAGE3_MENU_ID]),
        expected_three={
            menu_id: expected_case(fixture_by_id[menu_id]) for menu_id in STAGE4_MENU_IDS
        },
        expected_twelve={
            menu_id: expected_case(fixture_by_id[menu_id])
            for menu_id in STAGE5_MENU_IDS
            if menu_id in fixture_by_id
        },
        input_bytes=json_bytes,
        structured_input_bytes=len(STRUCTURED_PROMPT.encode("utf-8")),
    )
    result.update(
        {
            "runId": RUN_ID,
            "model": MODEL_DEFAULT,
            "stage0": preflight,
            "requestIntervalSeconds": plan["requestIntervalSeconds"],
            "stage1InputBytes": stage1_prompt_bytes,
            "stage2InputBytes": stage2_prompt_bytes,
            "sourceArtifactSha256": plan["sourceArtifactSha256"],
            "fixtureArtifactSha256": plan["fixtureArtifactSha256"],
            "restaurantIds": COHORT,
        }
    )
    RESULTS.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for stage_id, stage in result["stages"].items():
        print(
            f"stage={stage_id} status={stage['status']} "
            f"requests={stage['independentRequests']} attempts={stage['attempts']}"
        )
    print(f"probe={result['probeStatus']} apiRequests={result['apiRequestCount']}")
    return 0 if result["probeStatus"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(run())
