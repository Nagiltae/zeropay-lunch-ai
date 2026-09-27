"""Read-only Qdrant v12 profile quality review with independent local verifier."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
AI_MODULE = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "AI_Answer"
sys.path.insert(0, str(AI_MODULE))

from app.entity_resolution.qwen_candidate_matcher import (  # noqa: E402
    OllamaClient,
    configured_qwen_model,
)
from app.semantic_embedding_qdrant_pilot import _request  # noqa: E402
from app.semantic_profile_quality_gate import (  # noqa: E402
    ClaimCandidate,
    OllamaSemanticVerifier,
    normalize_claim_key,
    raw_evidence_text,
    regression_is_blocked,
    validate_claim,
    verdict_is_indexable,
)

COLLECTION = "zeropay_semantic_claim_pilot_v12"
MANIFEST_PATH = ARTIFACTS / "semantic_retrieval_hybrid_indexing_manifest.json"
RUN_SUFFIX = os.getenv("SEMANTIC_PROFILE_REVIEW_SUFFIX", "_v2")
OUTPUT_PATH = ARTIFACTS / f"semantic_profile_shadow_review{RUN_SUFFIX}.json"
METRICS_PATH = ARTIFACTS / f"semantic_profile_quality_metrics{RUN_SUFFIX}.json"
FIXTURE_PATH = ARTIFACTS / f"semantic_profile_regression_fixtures{RUN_SUFFIX}.json"


def _json_files() -> list[tuple[Path, dict[str, Any]]]:
    documents = []
    for path in ARTIFACTS.rglob("*.json"):
        if path in {OUTPUT_PATH, METRICS_PATH, FIXTURE_PATH}:
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            documents.append((path, value))
    return documents


def _catalog_payload_hash(items: list[dict[str, Any]]) -> str:
    canonical = json.dumps(items, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _load_catalogs(
    documents: list[tuple[Path, dict[str, Any]]],
) -> tuple[dict[str, dict[str, Any]], dict[str, set[int]]]:
    input_owners: dict[str, set[int]] = defaultdict(set)
    for _, document in documents:
        input_hash = document.get("inputHash")
        restaurant_id = document.get("restaurantId")
        if isinstance(input_hash, str) and isinstance(restaurant_id, int):
            input_owners[input_hash].add(restaurant_id)

    catalogs: dict[str, dict[str, Any]] = {}
    for path, document in documents:
        items = document.get("items")
        catalog_hash = document.get("catalogHash")
        input_hash = document.get("inputHash")
        if not isinstance(items, list) or not isinstance(catalog_hash, str):
            continue
        computed = _catalog_payload_hash(items)
        if computed != catalog_hash:
            continue
        catalogs[catalog_hash] = {
            "path": str(path.relative_to(ROOT)),
            "catalog": document,
            "owners": input_owners.get(input_hash, set()),
        }
    return catalogs, input_owners


def _scroll_qdrant(base_url: str) -> list[dict[str, Any]]:
    response = _request(
        base_url,
        f"/collections/{COLLECTION}/points/scroll",
        "POST",
        {"limit": 256, "with_payload": True, "with_vector": False},
    )
    if response.get("status") != "ok":
        raise RuntimeError("QDRANT_SCROLL_FAILED")
    return response.get("result", {}).get("points", [])


def _point_evidence_bindings(
    manifest_points: list[dict[str, Any]],
) -> tuple[dict[str, str], dict[int, str]]:
    restaurant_catalogs: dict[int, set[str]] = defaultdict(set)
    point_hashes: dict[str, str] = {}
    for point in manifest_points:
        catalog_hash = point.get("catalogHash")
        if isinstance(catalog_hash, str):
            point_hashes[str(point["pointId"])] = catalog_hash
            restaurant_catalogs[int(point["restaurantId"])].add(catalog_hash)
    unique_catalogs = {
        restaurant_id: next(iter(hashes))
        for restaurant_id, hashes in restaurant_catalogs.items()
        if len(hashes) == 1
    }
    return point_hashes, unique_catalogs


def _resolved_evidence(
    restaurant_id: int,
    evidence_ids: list[str],
    catalog_hash: str | None,
    catalogs: dict[str, dict[str, Any]],
    owners: dict[str, set[int]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not catalog_hash or catalog_hash not in catalogs:
        return [], {"resolved": False, "reason": "CATALOG_HASH_UNRESOLVED"}
    record = catalogs[catalog_hash]
    owner_set = record["owners"]
    if owner_set != {restaurant_id}:
        return [], {
            "resolved": False,
            "reason": "CATALOG_RESTAURANT_OWNERSHIP_UNVERIFIED",
            "catalogOwners": sorted(owner_set),
        }
    by_id = {str(item.get("evidenceId")): item for item in record["catalog"].get("items", [])}
    result = []
    missing = []
    for evidence_id in evidence_ids:
        source = by_id.get(evidence_id)
        if source is None:
            missing.append(evidence_id)
            continue
        raw_text = raw_evidence_text(source)
        result.append(
            {
                "restaurantId": restaurant_id,
                "evidenceId": evidence_id,
                "evidenceType": source.get("evidenceType"),
                "sourceField": source.get("sourceField"),
                "status": source.get("status"),
                "rawText": raw_text,
                "rawEvidence": source.get("content"),
                "catalogPath": record["path"],
                "catalogHash": catalog_hash,
                "catalogOwnerVerified": owner_set == {restaurant_id},
            }
        )
    return result, {
        "resolved": not missing and len(result) == len(evidence_ids),
        "missingEvidenceIds": missing,
        "catalogPath": record["path"],
        "catalogHash": catalog_hash,
        "catalogOwners": sorted(owner_set),
    }


def _compare_live_points(
    manifest_points: list[dict[str, Any]], live_points: list[dict[str, Any]]
) -> dict[str, Any]:
    manifest_by_id = {str(item.get("pointId")): item for item in manifest_points}
    live_by_id = {str(item.get("id")): item for item in live_points}
    mismatches = []
    for point_id, manifest in manifest_by_id.items():
        live = live_by_id.get(point_id)
        if live is None:
            mismatches.append({"pointId": point_id, "reason": "LIVE_POINT_MISSING"})
            continue
        payload = live.get("payload", {})
        for key in ("restaurantId", "claimId", "claimType", "evidenceIds"):
            if payload.get(key) != manifest.get(key):
                mismatches.append({"pointId": point_id, "reason": f"PAYLOAD_MISMATCH:{key}"})
    for point_id in live_by_id.keys() - manifest_by_id.keys():
        mismatches.append({"pointId": point_id, "reason": "UNMANIFESTED_LIVE_POINT"})
    return {
        "manifestPointCount": len(manifest_points),
        "livePointCount": len(live_points),
        "mismatches": mismatches,
        "consistent": not mismatches and len(manifest_points) == len(live_points),
    }


def _build_metrics(items: list[dict[str, Any]], verifier_calls: int) -> dict[str, Any]:
    total = len(items)
    verdict_counts = Counter(item.get("semanticVerdict") for item in items)
    claim_type: dict[str, Counter[str]] = defaultdict(Counter)
    source_type: dict[str, Counter[str]] = defaultdict(Counter)
    for item in items:
        verdict = item.get("semanticVerdict", "VERIFIER_ERROR")
        claim_type[item.get("claimType", "UNKNOWN")][verdict] += 1
        for source in {e.get("evidenceType") for e in item.get("resolvedEvidence", [])}:
            source_type[str(source)][verdict] += 1
    invalid_evidence = sum(
        not item.get("evidenceResolution", {}).get("resolved")
        or not item.get("deterministicValidation", {}).get("evidenceIntegrityValid")
        for item in items
    )
    quote_valid = sum(
        bool(item.get("deterministicValidation", {}).get("quoteValid")) for item in items
    )
    missing_quote = sum(
        any(
            error.startswith("SUPPORT_QUOTE_MISSING:")
            for error in item.get("deterministicValidation", {}).get("errors", [])
        )
        for item in items
    )
    supported = verdict_counts.get("SUPPORTED", 0)
    overclaims = verdict_counts.get("PARTIAL", 0) + verdict_counts.get("UNSUPPORTED", 0)
    return {
        "totalClaims": total,
        "supportedCount": supported,
        "partialCount": verdict_counts.get("PARTIAL", 0),
        "unsupportedCount": verdict_counts.get("UNSUPPORTED", 0),
        "verifierErrorCount": verdict_counts.get("VERIFIER_ERROR", 0),
        "invalidEvidenceCount": invalid_evidence,
        "missingQuoteCount": missing_quote,
        "exactQuoteValidationPassCount": quote_valid,
        "approvalRate": supported / total if total else 0.0,
        "overclaimRate": overclaims / total if total else 0.0,
        "indexableCount": sum(bool(item.get("indexableUnderNewPolicy")) for item in items),
        "indexableRate": sum(bool(item.get("indexableUnderNewPolicy")) for item in items) / total
        if total
        else 0.0,
        "verifierCalls": verifier_calls,
        "byClaimType": {key: dict(value) for key, value in sorted(claim_type.items())},
        "bySourceType": {
            key: {"claimsByVerdict": dict(value), "denominatorOverlapping": True}
            for key, value in sorted(source_type.items())
        },
    }


def _run_regression_fixtures(
    verifier: OllamaSemanticVerifier,
    catalogs: dict[str, dict[str, Any]],
    input_owners: dict[str, set[int]],
) -> tuple[list[dict[str, Any]], int]:
    fixture_document = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    if fixture_document.get("frozenBeforeVerifierRun") is not True:
        raise RuntimeError("REGRESSION_FIXTURES_NOT_FROZEN")
    results = []
    calls = 0
    for fixture in fixture_document.get("fixtures", []):
        restaurant_id = int(fixture["restaurantId"])
        claim_data = {
            key: fixture[key]
            for key in (
                "restaurantId",
                "claimId",
                "claimType",
                "claimText",
                "evidenceIds",
                "supportQuotes",
            )
        }
        evidence, resolution = _resolved_evidence(
            restaurant_id,
            claim_data["evidenceIds"],
            fixture.get("catalogHash"),
            catalogs,
            input_owners,
        )
        deterministic = validate_claim(
            claim_data,
            {item["evidenceId"]: item for item in evidence},
            expected_restaurant_id=restaurant_id,
        )
        verdict_name = "VERIFIER_ERROR"
        supported = ""
        unsupported = ""
        error_code = None
        if resolution.get("resolved") and deterministic.get("evidenceIntegrityValid"):
            calls += 1
            try:
                verdict = verifier.verify(ClaimCandidate.model_validate(claim_data), evidence)
                verdict_name = verdict.verdict
                supported = verdict.supportedPortion
                unsupported = verdict.unsupportedPortion
            except Exception as error:
                error_code = type(error).__name__
        allowed = fixture.get("expectedVerdicts", [])
        indexable = (
            verdict_name == "SUPPORTED"
            and deterministic.get("valid")
            and deterministic.get("quoteValid")
        )
        results.append(
            {
                "fixtureId": fixture["fixtureId"],
                "claimId": fixture["claimId"],
                "evidenceResolution": resolution,
                "deterministicValidation": deterministic,
                "semanticVerdict": verdict_name,
                "supportedPortion": supported,
                "unsupportedPortion": unsupported,
                "indexableUnderNewPolicy": bool(indexable),
                "expectedVerdicts": allowed,
                "regressionBlocked": regression_is_blocked(verdict_name, allowed, bool(indexable)),
                "verifierErrorCode": error_code,
            }
        )
    return results, calls


def _preflight_all_evidence(
    manifest_points: list[dict[str, Any]],
    catalogs: dict[str, dict[str, Any]],
    point_hashes: dict[str, str],
    restaurant_hashes: dict[int, str],
) -> None:
    unresolved = []
    for point in manifest_points:
        restaurant_id = int(point["restaurantId"])
        catalog_hash = point_hashes.get(str(point["pointId"])) or restaurant_hashes.get(
            restaurant_id
        )
        _, resolution = _resolved_evidence(
            restaurant_id,
            list(point.get("evidenceIds", [])),
            catalog_hash,
            catalogs,
            {},
        )
        if not resolution.get("resolved"):
            unresolved.append({"claimId": point.get("claimId"), "resolution": resolution})
    if unresolved:
        raise RuntimeError(f"EVIDENCE_PREFLIGHT_FAILED:{len(unresolved)}")


def run() -> dict[str, Any]:
    for path in (OUTPUT_PATH, METRICS_PATH):
        if path.exists():
            raise RuntimeError(f"REFUSING_TO_OVERWRITE:{path.name}")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest.get("collection") != COLLECTION:
        raise RuntimeError("MANIFEST_COLLECTION_MISMATCH")
    manifest_points = manifest.get("points", [])
    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    live_points = _scroll_qdrant(qdrant_url)
    live_consistency = _compare_live_points(manifest_points, live_points)
    if not live_consistency["consistent"]:
        raise RuntimeError("LIVE_COLLECTION_MANIFEST_MISMATCH")

    documents = _json_files()
    catalogs, input_owners = _load_catalogs(documents)
    point_hashes, restaurant_hashes = _point_evidence_bindings(manifest_points)
    _preflight_all_evidence(manifest_points, catalogs, point_hashes, restaurant_hashes)
    claim_ids_seen: set[str] = set()
    duplicate_keys: set[tuple[int, str, str]] = set()
    items: list[dict[str, Any]] = []
    verifier = OllamaSemanticVerifier(
        OllamaClient(
            timeout=float(os.getenv("PROFILE_VERIFIER_TIMEOUT_SECONDS", "120")),
            num_predict=512,
        )
    )
    verifier_calls = 0
    started = time.monotonic()
    regression_results: list[dict[str, Any]] = []
    regression_calls = 0
    try:
        for ordinal, point in enumerate(manifest_points, start=1):
            claim_id = str(point["claimId"])
            if claim_id in claim_ids_seen:
                raise RuntimeError("DUPLICATE_CLAIM_ID_IN_MANIFEST")
            claim_ids_seen.add(claim_id)
            restaurant_id = int(point["restaurantId"])
            catalog_hash = point_hashes.get(str(point["pointId"])) or restaurant_hashes.get(
                restaurant_id
            )
            resolved, resolution = _resolved_evidence(
                restaurant_id,
                list(point.get("evidenceIds", [])),
                catalog_hash,
                catalogs,
                input_owners,
            )
            claim = {
                "restaurantId": restaurant_id,
                "claimId": claim_id,
                "claimType": point.get("claimType", ""),
                "claimText": point.get("normalizedClaimText") or point.get("originalClaimText", ""),
                "evidenceIds": point.get("evidenceIds", []),
                # Legacy v12 does not persist supportQuotes; do not invent them.
                "supportQuotes": [],
            }
            key = normalize_claim_key(ClaimCandidate.model_validate(claim))
            duplicate = key in duplicate_keys
            duplicate_keys.add(key)
            evidence_by_id = {entry["evidenceId"]: entry for entry in resolved}
            deterministic = validate_claim(
                claim,
                evidence_by_id,
                expected_restaurant_id=restaurant_id,
                duplicate=duplicate,
            )
            semantic_verdict = "VERIFIER_ERROR"
            supported_portion = ""
            unsupported_portion = ""
            verifier_status = "SKIPPED_INVALID_EVIDENCE"
            verifier_latency_ms = None
            verifier_error_code = None
            if resolution.get("resolved") and deterministic.get("evidenceIntegrityValid"):
                verifier_calls += 1
                call_started = time.monotonic()
                try:
                    verdict = verifier.verify(ClaimCandidate.model_validate(claim), resolved)
                    semantic_verdict = verdict.verdict
                    supported_portion = verdict.supportedPortion
                    unsupported_portion = verdict.unsupportedPortion
                    verifier_status = "SUCCESS"
                except Exception as error:  # fail closed; omit provider response/body
                    verifier_status = "ERROR"
                    verifier_error_code = type(error).__name__
                verifier_latency_ms = round((time.monotonic() - call_started) * 1000)
            verdict_obj = None
            if verifier_status == "SUCCESS":
                verdict_obj = verdict
            indexable = bool(verdict_obj and verdict_is_indexable(deterministic, verdict_obj))
            items.append(
                {
                    "ordinal": ordinal,
                    "restaurantId": restaurant_id,
                    "claimId": claim_id,
                    "claimType": claim.get("claimType"),
                    "claimText": claim.get("claimText"),
                    "evidenceIds": claim.get("evidenceIds"),
                    "oldStatus": "IN_QDRANT_V12",
                    "resolvedEvidence": resolved,
                    "evidenceResolution": resolution,
                    "supportQuotes": [],
                    "deterministicValidation": deterministic,
                    "semanticVerdict": semantic_verdict,
                    "supportedPortion": supported_portion,
                    "unsupportedPortion": unsupported_portion,
                    "verifierStatus": verifier_status,
                    "verifierErrorCode": verifier_error_code,
                    "verifierLatencyMs": verifier_latency_ms,
                    "indexableUnderNewPolicy": indexable,
                }
            )
            print(
                json.dumps(
                    {
                        "progress": f"{ordinal}/{len(manifest_points)}",
                        "restaurantId": restaurant_id,
                        "claimId": claim_id,
                        "verdict": semantic_verdict,
                        "verifierStatus": verifier_status,
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
        regression_results, regression_calls = _run_regression_fixtures(
            verifier, catalogs, input_owners
        )
    finally:
        verifier._client.close()

    metrics = _build_metrics(items, verifier_calls)
    metrics["regressionFixtureCount"] = len(regression_results)
    metrics["regressionFixtureVerifierCalls"] = regression_calls
    metrics["regressionBlockedCount"] = sum(
        bool(item.get("regressionBlocked")) for item in regression_results
    )
    result = {
        "reviewVersion": "semantic-profile-shadow-review-v1",
        "createdAt": datetime.now(UTC).isoformat(),
        "collection": COLLECTION,
        "readOnly": True,
        "liveCollectionConsistency": live_consistency,
        "model": configured_qwen_model(),
        "verifierPromptVersion": "evidence-entailment-verifier-v1",
        "verifierCalls": verifier_calls,
        "regressionFixtureVerifierCalls": regression_calls,
        "regressionResults": regression_results,
        "elapsedSeconds": round(time.monotonic() - started, 3),
        "items": items,
    }
    OUTPUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    METRICS_PATH.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n")
    return {"result": str(OUTPUT_PATH), "metrics": str(METRICS_PATH), **metrics}


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
