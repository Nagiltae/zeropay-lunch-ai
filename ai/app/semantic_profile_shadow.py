"""Read-only Semantic Profile v1 input and shadow evaluation helpers.

This module deliberately does not share the Entity Resolution prompt or write
to the application database.  It is a bounded experiment for an already
validated detail record.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.entity_resolution.qwen_candidate_matcher import OllamaClient, configured_qwen_model

INPUT_VERSION = "semantic-profile-input-v1"
PROMPT_VERSION = "semantic-profile-prompt-v1"
OUTPUT_VERSION = "semantic-profile-output-v1"
COMPACT_INPUT_VERSION = "semantic-profile-input-v1-compact-1"
EVIDENCE_CATALOG_VERSION = "semantic-profile-evidence-catalog-v1"
EVIDENCE_OUTPUT_VERSION = "semantic-profile-output-v2-evidence"


class ProfileClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claimType: str
    text: str = Field(min_length=1)
    confidence: Literal["HIGH", "MEDIUM", "LOW", "UNKNOWN"]
    sourceFields: list[str] = Field(min_length=1)
    evidence: str = Field(min_length=1)


class ProfileOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profileStatus: Literal["READY", "PARTIAL", "UNKNOWN"]
    claims: list[ProfileClaim]
    sectionEvidence: dict[str, list[str]]
    inputVersion: str
    promptVersion: str
    inputHash: str


class ProfileInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    inputVersion: str
    restaurantId: int
    venueId: int | None
    source: dict[str, Any]
    identity: dict[str, Any]
    sections: dict[str, Any]
    quality: dict[str, Any]
    inputHash: str
    sourceTrace: dict[str, Any] | None = None


class EvidenceClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claimType: str
    text: str = Field(min_length=1)
    confidence: Literal["HIGH", "MEDIUM", "LOW", "UNKNOWN"]
    evidenceIds: list[str] = Field(min_length=1)


class EvidenceOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profileStatus: Literal["READY", "PARTIAL", "UNKNOWN"]
    claims: list[EvidenceClaim]


def _mysql(sql: str) -> list[dict[str, str | None]]:
    command = [
        "docker",
        "compose",
        "exec",
        "-T",
        "mysql",
        "sh",
        "-c",
        'MYSQL_PWD="zeropay_local" mysql --default-character-set=utf8mb4 '
        f'--batch --raw -u zeropay zeropay_lunch -e "{sql}"',
    ]
    result = subprocess.run(command, capture_output=True, text=True, cwd=_root())
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "read-only MySQL query failed")
    lines = result.stdout.rstrip("\n").splitlines()
    if len(lines) < 2:
        return []
    headers = lines[0].split("\t")
    rows = []
    for line in lines[1:]:
        values = line.split("\t")
        rows.append(
            {
                key: (None if value in {"\\N", "NULL"} else value)
                for key, value in zip(headers, values, strict=True)
            }
        )
    return rows


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def _rows(sql: str, restaurant_id: int) -> list[dict[str, str | None]]:
    return _mysql(sql.replace(":restaurant_id", str(int(restaurant_id))))


def _as_number(value: str | None) -> int | float | str | None:
    if value is None:
        return None
    try:
        return float(value) if "." in value else int(value)
    except ValueError:
        return value


def build_input(restaurant_id: int) -> dict[str, Any]:
    base = _rows(
        """
        SELECT r.id, r.name, r.address, r.category, r.latitude, r.longitude,
               r.source_provider, r.last_synced_at,
               c.name AS canonical_name, c.address AS canonical_address,
               c.road_address AS canonical_road_address,
               e.external_place_id, e.provider AS external_provider,
               e.match_status, e.last_synced_at AS external_synced_at
        FROM restaurants r
        LEFT JOIN canonical_restaurants c ON c.restaurant_id=r.id
        LEFT JOIN restaurant_external_places e ON e.restaurant_id=r.id
          AND e.provider='NAVER'
        WHERE r.id=:restaurant_id
    """,
        restaurant_id,
    )
    if not base:
        raise ValueError(f"restaurant_id={restaurant_id} not found")
    row = base[0]
    venue = _rows(
        """
        SELECT v.id FROM restaurant_venue_associations a
        JOIN venues v ON v.id=a.venue_id
        WHERE a.restaurant_id=:restaurant_id
          AND a.association_status='CONFIRMED' AND v.venue_status='ACTIVE'
    """,
        restaurant_id,
    )
    menu = _rows(
        """
        SELECT name, description, price_value, price_text, price_type,
               external_menu_id, crawled_at
        FROM restaurant_menus
        WHERE restaurant_id=:restaurant_id AND active=1
        ORDER BY id
    """,
        restaurant_id,
    )
    hours = _rows(
        """
        SELECT day_of_week, open_time, close_time, break_hours, last_order,
               regular_closed_day, irregular_closed_day, business_status,
               crawled_at
        FROM restaurant_business_hours
        WHERE restaurant_id=:restaurant_id AND active=1
        ORDER BY id
    """,
        restaurant_id,
    )
    summary = _rows(
        """
        SELECT visitor_reviews_total, visitor_reviews_score,
               visitor_text_review_total, cafe_blog_reviews_total, crawled_at
        FROM restaurant_review_summaries WHERE restaurant_id=:restaurant_id
        ORDER BY id DESC LIMIT 1
    """,
        restaurant_id,
    )
    keywords = _rows(
        """
        SELECT keyword_kind, keyword, mention_count, crawled_at
        FROM restaurant_review_keywords WHERE restaurant_id=:restaurant_id AND active=1
        ORDER BY id
    """,
        restaurant_id,
    )
    reviews = _rows(
        """
        SELECT review_id, review_text, review_date, rating, crawled_at
        FROM restaurant_representative_reviews
        WHERE restaurant_id=:restaurant_id AND active=1 ORDER BY id
    """,
        restaurant_id,
    )
    states = _rows(
        """
        SELECT section, state, checked_at, error_code
        FROM restaurant_detail_section_states
        WHERE restaurant_id=:restaurant_id ORDER BY section
    """,
        restaurant_id,
    )

    def clean(items: list[dict[str, str | None]]) -> list[dict[str, Any]]:
        return [
            {
                key: _as_number(value)
                if key.endswith(("_value", "_count", "_score", "rating"))
                else value
                for key, value in item.items()
            }
            for item in items
        ]

    lifecycle = clean(states)
    lifecycle_map = {item["section"]: item for item in lifecycle}
    strict_ready = (
        all(
            lifecycle_map.get(section, {}).get("state") == "SUCCESS"
            for section in ("menu", "business_hours", "review")
        )
        and any(
            item.get("price_value") is not None or str(item.get("price_text") or "").strip()
            for item in menu
        )
        and any(item.get("open_time") and item.get("close_time") for item in hours)
    )
    payload: dict[str, Any] = {
        "inputVersion": INPUT_VERSION,
        "restaurantId": restaurant_id,
        "venueId": int(venue[0]["id"]) if venue else None,
        "source": {
            "provider": row.get("source_provider"),
            "lastSyncedAt": row.get("last_synced_at"),
        },
        "identity": {
            "restaurantName": row.get("name"),
            "restaurantAddress": row.get("address"),
            "category": row.get("category"),
            "latitude": _as_number(row.get("latitude")),
            "longitude": _as_number(row.get("longitude")),
            "canonicalName": row.get("canonical_name"),
            "canonicalAddress": row.get("canonical_address"),
            "canonicalRoadAddress": row.get("canonical_road_address"),
            "provider": row.get("external_provider"),
            "numericPlaceId": row.get("external_place_id"),
            "matchStatus": row.get("match_status"),
            "mappingSyncedAt": row.get("external_synced_at"),
        },
        "sections": {
            "menu": {"items": clean(menu)},
            "businessHours": {"items": clean(hours)},
            "review": {
                "summary": clean(summary),
                "keywords": clean(keywords),
                "representativeReviews": clean(reviews),
            },
            "lifecycle": lifecycle,
        },
        "quality": {
            "strictProfileReady": strict_ready,
            "lifecyclePresent": bool(lifecycle),
            "missingSections": [
                s for s in ("menu", "business_hours", "review") if s not in lifecycle_map
            ],
        },
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload["inputHash"] = hashlib.sha256(canonical.encode()).hexdigest()
    ProfileInput.model_validate(payload)
    return payload


def validate_output(raw: dict[str, Any], profile_input: dict[str, Any]) -> dict[str, Any]:
    try:
        output = ProfileOutput.model_validate(raw)
    except ValidationError as error:
        return {"valid": False, "errors": [str(error)]}
    paths = _source_paths(profile_input)
    errors = []
    for claim in output.claims:
        errors.extend(
            f"unknown sourceField: {path}"
            for path in claim.sourceFields
            if path not in paths
        )
        if (
            any(path.startswith("sections.menu") for path in claim.sourceFields)
            and not profile_input["sections"]["menu"]["items"]
        ):
            errors.append("menu claim cites absent menu")
    if (
        output.inputVersion != profile_input.get("inputVersion", INPUT_VERSION)
        or output.promptVersion != PROMPT_VERSION
        or output.inputHash != profile_input["inputHash"]
    ):
        errors.append("version or input hash mismatch")
    return {"valid": not errors, "errors": errors, "parsed": output.model_dump(mode="json")}


def build_compact_input(profile_input: dict[str, Any]) -> dict[str, Any]:
    """Deduplicate low-value repetition without discarding evidence identifiers."""
    compact = json.loads(json.dumps(profile_input, ensure_ascii=False))
    compact["inputVersion"] = COMPACT_INPUT_VERSION
    menu = compact["sections"]["menu"]["items"]
    unique_menu: list[dict[str, Any]] = []
    seen_menu: dict[tuple[str, Any], int] = {}
    for index, item in enumerate(menu):
        key = (str(item.get("name") or "").strip().casefold(), item.get("price_value"))
        source = f"sections.menu.items[{index}]"
        if key in seen_menu:
            unique_menu[seen_menu[key]]["sourceFields"].append(source)
            continue
        copied = {
            key: value for key, value in item.items() if key not in {"description", "crawled_at"}
        }
        copied["sourceFields"] = [
            f"{source}.{field}" for field in ("name", "price_value", "price_text")
        ]
        seen_menu[key] = len(unique_menu)
        unique_menu.append(copied)
    compact["sections"]["menu"]["items"] = unique_menu

    keywords = compact["sections"]["review"]["keywords"]
    unique_keywords: list[dict[str, Any]] = []
    seen_keywords: set[str] = set()
    for item in keywords:
        keyword = str(item.get("keyword") or "").strip().casefold()
        if keyword and keyword not in seen_keywords:
            seen_keywords.add(keyword)
            unique_keywords.append(
                {
                    "keyword": item.get("keyword"),
                    "keyword_kind": item.get("keyword_kind"),
                    "mention_count": item.get("mention_count"),
                }
            )
    compact["sections"]["review"]["keywords"] = unique_keywords

    reviews = compact["sections"]["review"]["representativeReviews"]
    informative = [
        item
        for item in reviews
        if len(str(item.get("review_text") or "").strip()) >= 20
        and item.get("review_text") != "더보기"
    ]
    selected = sorted(
        informative, key=lambda item: len(str(item.get("review_text") or "")), reverse=True
    )[:4]
    compact["sections"]["review"]["representativeReviews"] = [
        {
            "review_id": item.get("review_id"),
            "review_text": str(item.get("review_text") or "")[:800],
            "review_date": item.get("review_date"),
        }
        for item in selected
    ]
    compact["sourceTrace"] = {
        "menuDeduplicated": True,
        "reviewSelection": "informative_max_6",
        "originalInputHash": profile_input["inputHash"],
    }
    compact_json = json.dumps(compact, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    compact["inputHash"] = hashlib.sha256(compact_json.encode()).hexdigest()
    ProfileInput.model_validate(compact)
    return compact


def build_evidence_catalog(profile_input: dict[str, Any]) -> dict[str, Any]:
    catalog: list[dict[str, Any]] = []

    def add(evidence_type: str, source_field: str, content: Any, section: str) -> None:
        catalog.append(
            {
                "evidenceId": f"E{len(catalog) + 1:03d}",
                "sourceField": source_field,
                "content": content,
                "section": section,
                "status": _section_state(profile_input, section),
                "evidenceType": evidence_type,
            }
        )

    identity = profile_input["identity"]
    add("identity", "identity.restaurantName", identity.get("restaurantName"), "identity")
    add("identity", "identity.restaurantAddress", identity.get("restaurantAddress"), "identity")
    for index, item in enumerate(profile_input["sections"]["menu"]["items"]):
        add(
            "menu",
            f"sections.menu.items[{index}]",
            {"name": item.get("name"), "price": item.get("price_value")},
            "menu",
        )
    for index, item in enumerate(profile_input["sections"]["review"]["keywords"]):
        add(
            "keyword",
            f"sections.review.keywords[{index}]",
            {"keyword": item.get("keyword"), "mentionCount": item.get("mention_count")},
            "review",
        )
    for index, item in enumerate(profile_input["sections"]["review"]["representativeReviews"]):
        add(
            "review",
            f"sections.review.representativeReviews[{index}]",
            {"reviewId": item.get("review_id"), "text": item.get("review_text")},
            "review",
        )
    for index, item in enumerate(profile_input["sections"]["businessHours"]["items"]):
        add("business_hours", f"sections.businessHours.items[{index}]", item, "business_hours")
    canonical = json.dumps(catalog, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "catalogVersion": EVIDENCE_CATALOG_VERSION,
        "inputHash": profile_input["inputHash"],
        "items": catalog,
        "catalogHash": hashlib.sha256(canonical.encode()).hexdigest(),
    }


def _section_state(profile_input: dict[str, Any], section: str) -> str | None:
    name = "business_hours" if section == "business_hours" else section
    for item in profile_input["sections"].get("lifecycle", []):
        if item.get("section") == name:
            return item.get("state")
    return None


def validate_evidence_output(
    raw: dict[str, Any], catalog: dict[str, Any], profile_input: dict[str, Any]
) -> dict[str, Any]:
    try:
        output = EvidenceOutput.model_validate(raw)
    except ValidationError as error:
        return {"valid": False, "errors": [str(error)]}
    by_id = {item["evidenceId"]: item for item in catalog["items"]}
    allowed = {
        "FOOD_TYPE": {"menu", "keyword"},
        "MENU_CHARACTERISTIC": {"menu"},
        "TASTE": {"keyword", "review"},
        "DINING_CONTEXT": {"keyword", "review"},
        "VENUE_CHARACTERISTIC": {"keyword", "review"},
    }
    errors: list[str] = []
    for claim in output.claims:
        if claim.claimType not in allowed:
            errors.append(f"unsupported claimType: {claim.claimType}")
            continue
        for evidence_id in claim.evidenceIds:
            evidence = by_id.get(evidence_id)
            if evidence is None:
                errors.append(f"unknown evidenceId: {evidence_id}")
            elif evidence["evidenceType"] not in allowed[claim.claimType]:
                errors.append(
                    f"evidence type not allowed: {claim.claimType}/{evidence['evidenceType']}"
                )
            elif evidence["status"] != "SUCCESS":
                errors.append(f"evidence section not SUCCESS: {evidence_id}")
    return {
        "valid": not errors,
        "errors": errors,
        "parsed": output.model_dump(mode="json"),
        "strictProfileReady": profile_input["quality"]["strictProfileReady"],
    }


def classify_claims(
    raw: dict[str, Any], catalog: dict[str, Any], profile_input: dict[str, Any]
) -> list[dict[str, Any]]:
    """Classify claims conservatively without changing the Qwen semantic policy."""
    by_id = {item["evidenceId"]: item for item in catalog["items"]}
    allowed = {
        "FOOD_TYPE": {"menu", "keyword"},
        "MENU_CHARACTERISTIC": {"menu"},
        "TASTE": {"keyword", "review"},
        "DINING_CONTEXT": {"keyword", "review"},
        "VENUE_CHARACTERISTIC": {"keyword", "review"},
    }
    result = []
    for claim in raw.get("claims", []):
        evidence = [
            by_id[evidence_id]
            for evidence_id in claim.get("evidenceIds", [])
            if evidence_id in by_id
        ]
        reasons: list[str] = []
        missing = [
            evidence_id
            for evidence_id in claim.get("evidenceIds", [])
            if evidence_id not in by_id
        ]
        if missing:
            reasons.append(f"unknown evidenceId: {','.join(missing)}")
        if claim.get("claimType") not in allowed:
            reasons.append(f"unsupported claimType: {claim.get('claimType')}")
        if not evidence:
            reasons.append("claim has no valid evidence")
        if reasons and any(
            "unknown evidenceId" in reason or "unsupported" in reason for reason in reasons
        ):
            result.append(
                {"claim": claim, "status": "REJECTED", "reasons": reasons, "evidence": evidence}
            )
            continue
        for item in evidence:
            if item["evidenceType"] not in allowed[claim["claimType"]]:
                reasons.append(
                    f"evidence type not allowed: {claim['claimType']}/{item['evidenceType']}"
                )
        if claim["claimType"] == "FOOD_TYPE" and any(
            item["evidenceType"] != "menu" for item in evidence
        ):
            reasons.append("food type from review/keyword is not an official menu fact")
        if claim["claimType"] == "MENU_CHARACTERISTIC" and any(
            item["evidenceType"] != "menu" for item in evidence
        ):
            reasons.append("menu characteristic lacks direct menu evidence")
        if any(item["status"] != "SUCCESS" for item in evidence):
            reasons.append("evidence section is not SUCCESS")
        if any(item["evidenceType"] == "review" for item in evidence):
            reasons.append("representative review requires semantic review")
        if any(
            item["evidenceType"] == "keyword"
            and (item["content"].get("mentionCount") or 0) < 3
            for item in evidence
        ):
            reasons.append("low keyword mention count")
        if reasons:
            status = (
                "REJECTED"
                if any(
                    "lacks direct" in reason or "not an official" in reason
                    for reason in reasons
                )
                else "REVIEW_REQUIRED"
            )
        else:
            status = "AUTO_APPROVED"
        result.append({"claim": claim, "status": status, "reasons": reasons, "evidence": evidence})
    return result


def benchmark_eligible_claims(
    classifications: list[dict[str, Any]],
    catalog: dict[str, Any],
    profile_input: dict[str, Any],
) -> tuple[list[dict[str, Any]], str]:
    """Return only locally verifiable AUTO claims for shadow retrieval.

    A profile-wide validation error may be local to another claim.  It must not
    promote that claim, but it also must not discard an unrelated AUTO claim.
    Identity/provenance/lifecycle failures remain a hard stop for all claims.
    """
    quality = profile_input.get("quality", {})
    if not quality.get("lifecyclePresent"):
        return [], "section lifecycle is unavailable"
    if quality.get("identityConflict") or quality.get("placeIdOwnershipConflict"):
        return [], "identity or Place ID ownership conflict"
    by_id = {item["evidenceId"]: item for item in catalog.get("items", [])}
    eligible: list[dict[str, Any]] = []
    for item in classifications:
        if item.get("status") != "AUTO_APPROVED":
            continue
        evidence = item.get("evidence", [])
        if not evidence or any(
            by_id.get(e.get("evidenceId"), {}).get("status") != "SUCCESS" for e in evidence
        ):
            continue
        eligible.append(item)
    return eligible, "AUTO_APPROVED with SUCCESS evidence; unrelated local claim errors excluded"


def _source_paths(value: Any, prefix: str = "") -> set[str]:
    """Return only paths that are present in this concrete input."""
    paths = {prefix} if prefix else set()
    if isinstance(value, dict):
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else key
            paths.update(_source_paths(child, child_prefix))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            paths.update(_source_paths(child, f"{prefix}[{index}]"))
    return paths


def _prompt(profile_input: dict[str, Any]) -> str:
    return (
        "Generate a conservative semantic profile from the JSON below. Do not infer facts "
        "from names alone. Every claim must cite an existing sourceFields path; "
        "omit unsupported claims. Return at most 5 short claims and keep evidence concise. "
        f"Return only the {OUTPUT_VERSION} JSON contract.\n"
        + json.dumps(profile_input, ensure_ascii=False)
    )


def _evidence_prompt(profile_input: dict[str, Any], catalog: dict[str, Any]) -> str:
    return (
        "Return only JSON with profileStatus and claims. Each claim must use only evidenceId "
        "values from the catalog. Do not output versions, hashes, source paths, prices, hours, "
        "or metadata. "
        "Use only these claim types: FOOD_TYPE, MENU_CHARACTERISTIC, TASTE, DINING_CONTEXT, "
        "VENUE_CHARACTERISTIC. Do not generalize one review into a universal fact. "
        "At most 5 concise claims.\nCATALOG:\n"
        + json.dumps(catalog, ensure_ascii=False)
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only Semantic Profile v1 shadow evaluation")
    parser.add_argument("--restaurant-id", type=int, default=9617)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument(
        "--compact", action="store_true", help="Use the bounded compact profile input"
    )
    parser.add_argument("--once", action="store_true", help="Use one bounded inference call")
    parser.add_argument("--evidence", action="store_true", help="Use Evidence ID output contract")
    args = parser.parse_args()
    started = time.perf_counter()
    profile_input = build_input(args.restaurant_id)
    original_hash = profile_input["inputHash"]
    if args.compact:
        profile_input = build_compact_input(profile_input)
    catalog = build_evidence_catalog(profile_input) if args.evidence else None
    out_dir = Path(args.output_dir) if args.output_dir else _root() / "AI_Answer"
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = "_compact" if args.compact else ""
    input_path = out_dir / f"semantic_profile_v1_input_{args.restaurant_id}{suffix}.json"
    input_path.write_text(json.dumps(profile_input, ensure_ascii=False, indent=2) + "\n")
    if catalog is not None:
        (out_dir / f"semantic_profile_v1_evidence_catalog_{args.restaurant_id}.json").write_text(
            json.dumps(catalog, ensure_ascii=False, indent=2) + "\n"
        )
    result: dict[str, Any] = {
        "restaurantId": args.restaurant_id,
        "inputPath": str(input_path),
        "inputHash": profile_input["inputHash"],
        "inputVersion": INPUT_VERSION,
        "promptVersion": PROMPT_VERSION,
        "modelConfigured": configured_qwen_model(),
        "calls": [],
        "quality": profile_input["quality"],
        "originalInputHash": original_hash,
    }
    client = OllamaClient(timeout=120.0 if args.compact else 30.0)
    try:
        for attempt in range(1 if args.once else 2):
            call_started = time.perf_counter()
            try:
                prompt = (
                    _evidence_prompt(profile_input, catalog)
                    if catalog
                    else _prompt(profile_input)
                )
                response_schema = _evidence_schema() if catalog else _schema()
                raw_text = client.complete(_profile_system_prompt(), prompt, response_schema)
                parsed = json.loads(raw_text)
                checked = (
                    validate_evidence_output(parsed, catalog, profile_input)
                    if catalog
                    else validate_output(parsed, profile_input)
                )
                if catalog and checked.get("parsed"):
                    checked["claimClassifications"] = classify_claims(
                        parsed, catalog, profile_input
                    )
                result["calls"].append(
                    {
                        "attempt": attempt + 1,
                        "status": "ok",
                        "latencyMs": round((time.perf_counter() - call_started) * 1000),
                        "validation": checked,
                    }
                )
            except Exception as error:  # bounded shadow experiment; preserve exact failure class
                result["calls"].append(
                    {
                        "attempt": attempt + 1,
                        "status": "error",
                        "latencyMs": round((time.perf_counter() - call_started) * 1000),
                        "error": type(error).__name__ + ": " + str(error),
                    }
                )
    finally:
        client.close()
    result["elapsedMs"] = round((time.perf_counter() - started) * 1000)
    if catalog is not None:
        result["catalogPath"] = str(
            out_dir / f"semantic_profile_v1_evidence_catalog_{args.restaurant_id}.json"
        )
        successful = next(
            (
                item["validation"]["parsed"]
                for item in result["calls"]
                if item.get("status") == "ok" and item.get("validation", {}).get("valid")
            ),
            None,
        )
        if successful is not None:
            by_id = {item["evidenceId"]: item for item in catalog["items"]}
            classifications = next(
                item["validation"].get("claimClassifications", [])
                for item in result["calls"]
                if item.get("status") == "ok"
            )
            result["finalProfile"] = {
                "profileVersion": EVIDENCE_OUTPUT_VERSION,
                "inputVersion": profile_input["inputVersion"],
                "inputHash": profile_input["inputHash"],
                "catalogVersion": catalog["catalogVersion"],
                "catalogHash": catalog["catalogHash"],
                "restaurantId": profile_input["restaurantId"],
                "venueId": profile_input["venueId"],
                "profileStatus": successful["profileStatus"],
                "claims": [
                    {
                        **item["claim"],
                        "evidence": [
                            by_id[evidence_id] for evidence_id in item["claim"]["evidenceIds"]
                        ],
                    }
                    for item in classifications
                    if item["status"] == "AUTO_APPROVED"
                ],
            }
            (out_dir / f"semantic_profile_v1_final_{args.restaurant_id}.json").write_text(
                json.dumps(result["finalProfile"], ensure_ascii=False, indent=2) + "\n"
            )
    result_path = out_dir / "semantic_profile_v1_shadow_results.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "input": str(input_path),
                "results": str(result_path),
                "calls": len(result["calls"]),
                "model": result["modelConfigured"],
            },
            ensure_ascii=False,
        )
    )


def _profile_system_prompt() -> str:
    return (
        "/no_think\nYou are a conservative restaurant semantic profile extractor. "
        "Never invent facts."
    )


def _schema() -> dict[str, Any]:
    claim = {
        "type": "object",
        "properties": {
            "claimType": {"type": "string"},
            "text": {"type": "string"},
            "confidence": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW", "UNKNOWN"]},
            "sourceFields": {"type": "array", "items": {"type": "string"}},
            "evidence": {"type": "string"},
        },
        "required": ["claimType", "text", "confidence", "sourceFields", "evidence"],
    }
    return {
        "type": "object",
        "properties": {
            "profileStatus": {"type": "string", "enum": ["READY", "PARTIAL", "UNKNOWN"]},
            "claims": {"type": "array", "items": claim},
            "sectionEvidence": {
                "type": "object",
                "additionalProperties": {"type": "array", "items": {"type": "string"}},
            },
            "inputVersion": {"type": "string"},
            "promptVersion": {"type": "string"},
            "inputHash": {"type": "string"},
        },
        "required": [
            "profileStatus",
            "claims",
            "sectionEvidence",
            "inputVersion",
            "promptVersion",
            "inputHash",
        ],
    }


def _evidence_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "profileStatus": {"type": "string", "enum": ["READY", "PARTIAL", "UNKNOWN"]},
            "claims": {
                "type": "array",
                "maxItems": 5,
                "items": {
                    "type": "object",
                    "properties": {
                        "claimType": {"type": "string"},
                        "text": {"type": "string"},
                        "confidence": {
                            "type": "string",
                            "enum": ["HIGH", "MEDIUM", "LOW", "UNKNOWN"],
                        },
                        "evidenceIds": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["claimType", "text", "confidence", "evidenceIds"],
                },
            },
        },
        "required": ["profileStatus", "claims"],
    }


if __name__ == "__main__":
    main()
