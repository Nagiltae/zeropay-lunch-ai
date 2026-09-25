"""Bounded, artifact-only pilot for classifying existing menu rows for lunch budgets.

This module never writes to MySQL or Qdrant. Each restaurant receives at most
one Qwen call; raw responses and validated classifications are checkpointed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.entity_resolution.qwen_candidate_matcher import OllamaClient, configured_qwen_model
from app.semantic_profile_shadow import _mysql, _root

PILOT_IDS = (9617, 9571, 9568, 10042, 9559)
POLICY_VERSION = "menu-budget-role-v1"
ARTIFACT = "menu_budget_classification_pilot.json"
PLAN = "serving_model_v2_pilot_plan.json"
ALLOWED_ROLES = (
    "MEAL_CANDIDATE",
    "SIDE",
    "DRINK",
    "ALCOHOL",
    "MULTI_PERSON",
    "COURSE",
    "WEIGHT_BASED",
    "UNKNOWN",
)


class MenuClassification(BaseModel):
    model_config = ConfigDict(extra="forbid")
    menuId: int
    budgetRole: str
    reason: str = Field(min_length=1, max_length=240)


class ClassificationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    classifications: list[MenuClassification]


def validate_output(raw: str, menus: list[dict[str, Any]]) -> dict[str, Any]:
    parsed = ClassificationOutput.model_validate_json(raw)
    ids = [int(row["id"]) for row in menus]
    allowed_ids = set(ids)
    seen: set[int] = set()
    errors: list[str] = []
    for item in parsed.classifications:
        if item.menuId not in allowed_ids:
            errors.append(f"UNKNOWN_MENU_ID:{item.menuId}")
        if item.menuId in seen:
            errors.append(f"DUPLICATE_MENU_ID:{item.menuId}")
        if item.budgetRole not in ALLOWED_ROLES:
            errors.append(f"INVALID_ROLE:{item.menuId}:{item.budgetRole}")
        seen.add(item.menuId)
    if errors:
        raise ValueError(",".join(errors))
    by_id = {item.menuId: item.model_dump(mode="json") for item in parsed.classifications}
    # Missing rows fail closed, rather than being guessed from another row.
    for menu_id in ids:
        by_id.setdefault(
            menu_id,
            {
                "menuId": menu_id,
                "budgetRole": "UNKNOWN",
                "reason": "MODEL_OMITTED_MENU",
            },
        )
    return {"classifications": [by_id[menu_id] for menu_id in ids]}


def load_pilot_inputs() -> list[dict[str, Any]]:
    result = []
    for restaurant_id in PILOT_IDS:
        rows = _mysql(f"""
            SELECT id, name, description, price_value, price_text
            FROM restaurant_menus
            WHERE restaurant_id={restaurant_id} AND provider='NAVER' AND active=TRUE
            ORDER BY id
        """)
        result.append(
            {
                "restaurantId": restaurant_id,
                "menus": [
                    {
                        "id": int(row["id"]),
                        "name": row["name"],
                        "description": row["description"],
                        "priceValue": int(row["price_value"]) if row["price_value"] else None,
                        "priceText": row["price_text"],
                    }
                    for row in rows
                ],
            }
        )
    return result


def make_plan(inputs: list[dict[str, Any]]) -> dict[str, Any]:
    plan_rows = []
    for item in inputs:
        menus = item["menus"]
        payload = json.dumps(menus, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        plan_rows.append(
            {
                "restaurantId": item["restaurantId"],
                "menuCount": len(menus),
                "pricedMenuCount": sum(
                    menu["priceValue"] is not None and menu["priceValue"] > 0 for menu in menus
                ),
                "menuIds": [menu["id"] for menu in menus],
                "inputBytes": len(payload.encode("utf-8")),
                "inputHash": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
            }
        )
    return {
        "policyVersion": POLICY_VERSION,
        "targetsFrozen": list(PILOT_IDS),
        "plannedQwenCalls": len(PILOT_IDS),
        "retryLimit": 0,
        "databaseWrites": 0,
        "qdrantWrites": 0,
        "restaurants": plan_rows,
    }


def _schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "classifications": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "menuId": {"type": "integer"},
                        "budgetRole": {"type": "string", "enum": list(ALLOWED_ROLES)},
                        "reason": {"type": "string"},
                    },
                    "required": ["menuId", "budgetRole", "reason"],
                },
            }
        },
        "required": ["classifications"],
    }


def classify(inputs: list[dict[str, Any]], *, client: Any, checkpoint_path: Path) -> dict[str, Any]:
    if tuple(item["restaurantId"] for item in inputs) != PILOT_IDS:
        raise ValueError("pilot target IDs/order do not match the frozen allowlist")
    plan = make_plan(inputs)
    checkpoint = (
        json.loads(checkpoint_path.read_text())
        if checkpoint_path.exists()
        else {
            "policyVersion": POLICY_VERSION,
            "model": configured_qwen_model(),
            "calls": 0,
            "restaurants": {},
        }
    )
    if checkpoint.get("policyVersion") != POLICY_VERSION:
        raise ValueError("checkpoint policy mismatch")
    for item in inputs:
        key = str(item["restaurantId"])
        source = next(
            row for row in plan["restaurants"] if row["restaurantId"] == item["restaurantId"]
        )
        prior = checkpoint["restaurants"].get(key)
        if (
            prior
            and prior.get("inputHash") == source["inputHash"]
            and prior.get("status") in {"SUCCESS", "FAILED"}
        ):
            continue
        if prior and prior.get("status") == "CALL_STARTED":
            # A process interruption after request start is ambiguous; never retry.
            checkpoint["restaurants"][key] = {
                **source,
                "status": "BLOCKED_AMBIGUOUS_CALL",
                "qwenCalls": 1,
            }
            _write(checkpoint_path, checkpoint)
            continue
        if checkpoint["calls"] >= len(PILOT_IDS):
            raise ValueError("maximum pilot Qwen calls exceeded")
        checkpoint["restaurants"][key] = {**source, "status": "CALL_STARTED", "qwenCalls": 1}
        checkpoint["calls"] += 1
        _write(checkpoint_path, checkpoint)
        prompt = (
            "Classify whether each listed price is valid for a one-person lunch budget.\n"
            "Do not change or invent menu IDs, names, descriptions, or prices.\n"
            "Use MEAL_CANDIDATE only when the item clearly represents one meal portion.\n"
            "Otherwise choose SIDE, DRINK, ALCOHOL, MULTI_PERSON, COURSE, "
            "WEIGHT_BASED, or UNKNOWN.\n"
            "Use UNKNOWN if uncertain. Return every supplied menuId once.\n"
            + json.dumps(
                {"restaurantId": item["restaurantId"], "menus": item["menus"]}, ensure_ascii=False
            )
        )
        started = time.monotonic()
        try:
            raw = client.complete(
                "You are a constrained menu-role classifier. Classify only supplied rows. "
                "Never infer or create facts.",
                prompt,
                _schema(),
            )
            validated = validate_output(raw, item["menus"])
            checkpoint["restaurants"][key] = {
                **source,
                "status": "SUCCESS",
                "qwenCalls": 1,
                "latencySeconds": round(time.monotonic() - started, 3),
                "rawOutput": raw,
                **validated,
            }
        except Exception as error:  # failure isolation; no retry
            checkpoint["restaurants"][key] = {
                **source,
                "status": "FAILED",
                "qwenCalls": 1,
                "error": type(error).__name__ + ": " + str(error),
            }
        _write(checkpoint_path, checkpoint)
    return checkpoint


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temp.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--classify", action="store_true")
    parser.add_argument("--allow-qwen", action="store_true")
    args = parser.parse_args()
    root = _root()
    out = root / "AI_Answer"
    inputs = load_pilot_inputs()
    plan = make_plan(inputs)
    plan_path = out / PLAN
    if args.plan:
        _write(plan_path, {**plan, "inputs": inputs})
        menu_count = sum(len(item["menus"]) for item in inputs)
        print(f"DRY_RUN restaurants={len(inputs)} menus={menu_count} qwen_calls=0 db_writes=0")
        return
    if not args.classify or not args.allow_qwen:
        parser.error("classification requires --classify --allow-qwen")
    frozen = json.loads(plan_path.read_text())
    if (
        frozen.get("targetsFrozen") != list(PILOT_IDS)
        or frozen.get("restaurants") != plan["restaurants"]
    ):
        raise SystemExit("ABORT: current DB inputs differ from frozen pilot plan")
    client = OllamaClient(timeout=60, num_predict=8192)
    try:
        result = classify(
            inputs,
            client=client,
            checkpoint_path=out / "menu_budget_classification_checkpoint.json",
        )
    finally:
        client.close()
    _write(out / ARTIFACT, result)
    successful = sum(item.get("status") == "SUCCESS" for item in result["restaurants"].values())
    print(f"QWEN calls={result['calls']} success={successful} db_writes=0")


if __name__ == "__main__":
    main()
