"""Freeze and execute a read-only Korean/source-diverse Generator V2.1 pilot."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter, deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ai"))

from app.entity_resolution.qwen_candidate_matcher import (  # noqa: E402
    OllamaClient,
    configured_qwen_model,
)
from app.semantic_profile_generator_v2 import (  # noqa: E402
    atomicity_rejection,
    canonical_evidence,
    generator_prompt,
    generator_schema,
    validate_generator_output,
)
from app.semantic_profile_quality_gate import (  # noqa: E402
    ClaimCandidate,
    OllamaAtomicClaimVerifier,
    aggregate_assertion_verdicts,
    semantic_error_category,
)
from app.semantic_profile_shadow import (  # noqa: E402
    build_compact_input,
    build_evidence_catalog,
    build_input,
)

ARTIFACTS = ROOT / "AI_Answer"
COHORT_PATH = ARTIFACTS / "semantic_profile_generator_v21_cohort.json"
RUN_PATHS = {
    1: ARTIFACTS / "semantic_profile_generator_v21_run1.json",
    2: ARTIFACTS / "semantic_profile_generator_v21_run2.json",
}
METRICS_PATH = ARTIFACTS / "semantic_profile_generator_v21_metrics.json"
RESTAURANT_IDS = (9568, 9569, 9570, 9574, 9580, 9659, 9801, 10042)
EXCLUDED_PRIOR_PILOT = {9559, 9603, 9639}
MAX_CLAIMS = 8
SOURCE_TYPES = ("menu", "keyword", "review")


def _hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def _write_new(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        raise RuntimeError(f"REFUSING_TO_OVERWRITE:{path.name}")
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _live_context(restaurant_id: int) -> tuple[dict[str, Any], dict[str, Any]]:
    profile_input = build_compact_input(build_input(restaurant_id))
    catalog = build_evidence_catalog(profile_input)
    if not profile_input.get("quality", {}).get("strictProfileReady"):
        raise RuntimeError(f"NOT_PROFILE_READY:{restaurant_id}")
    if catalog.get("inputHash") != profile_input.get("inputHash"):
        raise RuntimeError(f"CATALOG_INPUT_HASH_MISMATCH:{restaurant_id}")
    return profile_input, catalog


def freeze_cohort() -> dict[str, Any]:
    if COHORT_PATH.exists():
        raise RuntimeError(f"REFUSING_TO_OVERWRITE:{COHORT_PATH.name}")
    restaurants = []
    for ordinal, restaurant_id in enumerate(RESTAURANT_IDS, start=1):
        if restaurant_id in EXCLUDED_PRIOR_PILOT:
            raise RuntimeError("PRIOR_PILOT_RESTAURANT_IN_COHORT")
        profile_input, catalog = _live_context(restaurant_id)
        counts = Counter(item["evidenceType"] for item in catalog["items"])
        restaurants.append(
            {
                "ordinal": ordinal,
                "restaurantId": restaurant_id,
                "name": profile_input["identity"].get("restaurantName"),
                "selectionReason": (
                    "Current strict ProfileReady cohort; selected before generation to combine "
                    "verified menu data with available review keywords and representative reviews."
                ),
                "profileReady": profile_input["quality"],
                "inputHash": profile_input["inputHash"],
                "catalogHash": catalog["catalogHash"],
                "sourceEvidenceCounts": dict(sorted(counts.items())),
                "menuCount": counts.get("menu", 0),
                "keywordCount": counts.get("keyword", 0),
                "reviewCount": counts.get("review", 0),
                "evidenceCount": len(catalog["items"]),
            }
        )
        print(
            f"[Cohort Freeze] {ordinal}/8 restaurant={restaurant_id} "
            f"ready=true menu={counts.get('menu', 0)} keyword={counts.get('keyword', 0)} "
            f"review={counts.get('review', 0)}",
            flush=True,
        )
    document = {
        "cohortVersion": "semantic-profile-generator-v2.1-cohort-v1",
        "createdAt": datetime.now(UTC).isoformat(),
        "source": "current read-only DB via semantic_profile_shadow.build_input",
        "frozenBeforeGeneratorCalls": True,
        "restaurantIds": list(RESTAURANT_IDS),
        "excludedPriorPilotIds": sorted(EXCLUDED_PRIOR_PILOT),
        "mysqlSelectQueryCount": len(RESTAURANT_IDS) * 8,
        "restaurants": restaurants,
        "databaseWrites": 0,
    }
    _write_new(COHORT_PATH, document)
    return document


def _prompt_evidence(
    catalog: dict[str, Any], restaurant_id: int
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    evidence_by_id = canonical_evidence(catalog, restaurant_id)
    queues: dict[str, deque[dict[str, Any]]] = {
        source: deque(
            {
                "evidenceId": item["evidenceId"],
                "sourceType": source,
                "rawText": item["rawText"],
            }
            for item in evidence_by_id.values()
            if item["evidenceType"] == source and item["status"] == "SUCCESS" and item["rawText"]
        )
        for source in SOURCE_TYPES
    }
    interleaved = []
    while any(queues.values()):
        for source in SOURCE_TYPES:
            if queues[source]:
                interleaved.append(queues[source].popleft())
    return interleaved, evidence_by_id


def _claim_candidate(restaurant_id: int, claim: dict[str, Any]) -> ClaimCandidate:
    return ClaimCandidate.model_validate(
        {
            "restaurantId": restaurant_id,
            "claimId": claim["claimId"],
            "claimType": claim["claimType"],
            "claimText": claim["claimText"],
            "evidenceIds": claim["evidenceIds"],
            "supportQuotes": claim["supportQuotes"],
        }
    )


def _verify_claim(
    verifier: OllamaAtomicClaimVerifier,
    restaurant_id: int,
    checked: dict[str, Any],
    stats: Counter[str],
) -> dict[str, Any]:
    claim = checked["claim"]
    if not checked["valid"]:
        return {
            "claim": claim,
            "deterministicValidation": checked,
            "atomicAssertions": [],
            "semanticVerdict": None,
            "approved": False,
            "rejectReasons": sorted({error["code"] for error in checked["errors"]}),
        }
    candidate = _claim_candidate(restaurant_id, claim)
    atomicization = None
    error_category = None
    for attempt in range(2):
        stats["atomicizerCalls"] += 1
        try:
            atomicization = verifier.decompose(candidate, correction=bool(attempt))
            break
        except Exception as error:  # noqa: BLE001 - bounded fail-closed model boundary
            stats["retries"] += int(attempt == 0)
            if attempt:
                error_category = semantic_error_category(error)
    if atomicization is None:
        stats["verifierErrorCount"] += 1
        return {
            "claim": claim,
            "deterministicValidation": checked,
            "atomicAssertions": [],
            "semanticVerdict": None,
            "approved": False,
            "verifierError": error_category,
            "rejectReasons": ["ATOMICIZER_ERROR"],
        }
    assertion_rows = [item.model_dump(mode="json") for item in atomicization.assertions]
    if atomicity_rejection(len(atomicization.assertions)):
        stats["nonAtomicCount"] += 1
        return {
            "claim": claim,
            "deterministicValidation": checked,
            "atomicAssertions": assertion_rows,
            "semanticVerdict": None,
            "approved": False,
            "rejectReasons": ["GENERATOR_NON_ATOMIC"],
        }
    assertion = atomicization.assertions[0]
    result = None
    error_category = None
    for attempt in range(2):
        stats["assertionVerifierCalls"] += 1
        try:
            result = verifier.verify_assertion(
                claim["claimType"], assertion, checked["resolvedEvidence"]
            )
            break
        except Exception as error:  # noqa: BLE001 - bounded fail-closed model boundary
            stats["retries"] += int(attempt == 0)
            if attempt:
                error_category = semantic_error_category(error)
    if result is None:
        stats["verifierErrorCount"] += 1
        return {
            "claim": claim,
            "deterministicValidation": checked,
            "atomicAssertions": assertion_rows,
            "semanticVerdict": None,
            "approved": False,
            "verifierError": error_category,
            "rejectReasons": ["VERIFIER_ERROR"],
        }
    verdict = aggregate_assertion_verdicts(atomicization.assertions, [result])
    assertion_rows[0] |= {
        "verdict": result.verdict,
        "supportingEvidenceIds": result.evidenceIds,
    }
    stats[f"semantic{verdict.title()}Count"] += 1
    approved = verdict == "SUPPORTED"
    return {
        "claim": claim,
        "deterministicValidation": checked,
        "atomicAssertions": assertion_rows,
        "semanticVerdict": verdict,
        "approved": approved,
        "rejectReasons": [] if approved else [verdict],
    }


def run_pilot(run_number: int, *, human_review_pass: bool = False) -> dict[str, Any]:
    output_path = RUN_PATHS[run_number]
    if output_path.exists():
        raise RuntimeError(f"REFUSING_TO_OVERWRITE:{output_path.name}")
    if not COHORT_PATH.exists():
        raise RuntimeError("COHORT_NOT_FROZEN")
    if configured_qwen_model() != "qwen3.5:9b":
        raise RuntimeError("UNEXPECTED_PROFILE_GENERATOR_MODEL")
    cohort = json.loads(COHORT_PATH.read_text(encoding="utf-8"))
    if cohort.get("frozenBeforeGeneratorCalls") is not True or cohort.get("restaurantIds") != list(
        RESTAURANT_IDS
    ):
        raise RuntimeError("COHORT_FREEZE_INVALID")
    if run_number == 2:
        run1 = json.loads(RUN_PATHS[1].read_text(encoding="utf-8"))
        m = run1["metrics"]
        blockers = (
            "schemaErrorCount",
            "deterministicErrorCount",
            "quoteMismatchCount",
            "unknownEvidenceIdCount",
            "verifierErrorCount",
        )
        if any(m.get(key, 0) for key in blockers):
            raise RuntimeError("RUN1_QUALITY_GATE_FAILED_RUN2_BLOCKED")
        if not m.get("nonMenuApprovedRestaurantCount") or not human_review_pass:
            raise RuntimeError("RUN2_REQUIRES_NON_MENU_AND_HUMAN_REVIEW_PASS")

    client = OllamaClient(timeout=180.0, num_predict=6144)
    verifier = OllamaAtomicClaimVerifier(client)
    stats: Counter[str] = Counter()
    restaurant_results = []
    started = time.monotonic()
    try:
        for ordinal, frozen in enumerate(cohort["restaurants"], start=1):
            rid = frozen["restaurantId"]
            profile_input, catalog = _live_context(rid)
            if (
                profile_input["inputHash"] != frozen["inputHash"]
                or catalog["catalogHash"] != frozen["catalogHash"]
            ):
                raise RuntimeError(f"FROZEN_SOURCE_DRIFT:{rid}")
            prompt_rows, _ = _prompt_evidence(catalog, rid)
            stats["generatorCalls"] += 1
            generated_raw = None
            generator_error = None
            try:
                system_prompt = (
                    "/no_think\n당신은 원문 Evidence에 근거한 원자적 Claim을 만듭니다. "
                    "추론하지 마세요."
                )
                generated_raw = client.complete(
                    system_prompt,
                    generator_prompt(
                        {"restaurantId": rid, "name": frozen["name"]},
                        prompt_rows,
                        max_claims=MAX_CLAIMS,
                        korean=True,
                    ),
                    generator_schema(max_claims=MAX_CLAIMS),
                )
                validation = validate_generator_output(
                    generated_raw, restaurant_id=rid, catalog=catalog
                )
            except Exception as error:  # noqa: BLE001 - model/client boundary
                generator_error = semantic_error_category(error)
                validation = {
                    "schemaValid": False,
                    "errors": [{"code": "GENERATOR_ERROR", "category": generator_error}],
                    "claims": [],
                }
            claims = validation.get("claims", [])
            stats["schemaErrorCount"] += int(not validation.get("schemaValid"))
            stats["generatedClaimCount"] += len(claims)
            claim_results = []
            for claim_idx, checked in enumerate(claims, start=1):
                stats["schemaValidCount"] += 1
                for error in checked["errors"]:
                    code = error["code"]
                    if code == "UNKNOWN_EVIDENCE":
                        stats["unknownEvidenceIdCount"] += 1
                    elif code == "QUOTE_MISMATCH":
                        stats["quoteMismatchCount"] += 1
                    elif code == "PROVENANCE_TEXT_IN_CLAIM":
                        stats["provenanceLeakCount"] += 1
                    elif code == "DUPLICATE":
                        stats["duplicateCount"] += 1
                stats["koreanClaimCount"] += int(
                    not any(
                        error["code"] == "CLAIM_NOT_KOREAN_DOMINANT" for error in checked["errors"]
                    )
                )
                stats["deterministicPassCount"] += int(checked["valid"])
                stats["exactQuotePassCount"] += int(
                    not any(
                        error["code"] in {"QUOTE_MISMATCH", "SUPPORT_QUOTE_MISSING"}
                        for error in checked["errors"]
                    )
                )
                result = _verify_claim(verifier, rid, checked, stats)
                if result["approved"]:
                    stats["approvedClaimCount"] += 1
                    source_types = sorted(
                        {item["evidenceType"] for item in checked["resolvedEvidence"]}
                    )
                    for source in source_types:
                        stats[f"approvedSource:{source}"] += 1
                else:
                    stats[f"rejected:{','.join(result['rejectReasons']) or 'UNKNOWN'}"] += 1
                result["sourceTypes"] = sorted(
                    {item["evidenceType"] for item in checked["resolvedEvidence"]}
                )
                claim_results.append(result)
                elapsed = time.monotonic() - started
                print(
                    f"[Generator V2.1] restaurant {ordinal}/8={rid} claim "
                    f"{claim_idx}/{len(claims)} generated={stats['generatedClaimCount']} "
                    f"approved={stats['approvedClaimCount']} elapsed={elapsed:.1f}s",
                    flush=True,
                )
            approved_sources = Counter(
                source
                for item in claim_results
                if item["approved"]
                for source in item["sourceTypes"]
            )
            approved_claim_types = Counter(
                item["claim"]["claimType"] for item in claim_results if item["approved"]
            )
            restaurant_results.append(
                {
                    "restaurantId": rid,
                    "name": frozen["name"],
                    "inputHash": frozen["inputHash"],
                    "catalogHash": frozen["catalogHash"],
                    "sourceEvidenceSummary": frozen["sourceEvidenceCounts"],
                    "promptEvidenceOrder": [row["sourceType"] for row in prompt_rows],
                    "generatorError": generator_error,
                    "generatorValidationErrors": validation.get("errors", []),
                    "generatorRawTextPersisted": False,
                    "rawGeneratedClaims": [item["claim"] for item in claim_results],
                    "claimResults": claim_results,
                    "approvedByEvidenceSource": dict(approved_sources),
                    "approvedByClaimType": dict(approved_claim_types),
                }
            )
            elapsed = time.monotonic() - started
            eta = elapsed / ordinal * (len(cohort["restaurants"]) - ordinal)
            print(
                f"[Generator V2.1] restaurant {ordinal}/8: generated={len(claims)} "
                f"approved={sum(x['approved'] for x in claim_results)} "
                f"menu/keyword/review={approved_sources['menu']}/"
                f"{approved_sources['keyword']}/{approved_sources['review']} "
                f"elapsed={elapsed:.1f}s ETA~{eta:.1f}s (approximate)",
                flush=True,
            )
    finally:
        client.close()

    stats["nonMenuApprovedRestaurantCount"] = len(
        {
            restaurant["restaurantId"]
            for restaurant in restaurant_results
            if any(
                item["approved"] and set(item["sourceTypes"]) & {"keyword", "review"}
                for item in restaurant["claimResults"]
            )
        }
    )
    stats["englishDominantClaimCount"] = sum(
        any(
            error["code"] == "CLAIM_NOT_KOREAN_DOMINANT"
            for error in item["deterministicValidation"]["errors"]
        )
        for restaurant in restaurant_results
        for item in restaurant["claimResults"]
    )
    stats["deterministicErrorCount"] = sum(
        not item["deterministicValidation"]["valid"]
        for restaurant in restaurant_results
        for item in restaurant["claimResults"]
    )
    stats["koreanClaimRate"] = (
        round(stats["koreanClaimCount"] / stats["generatedClaimCount"], 4)
        if stats["generatedClaimCount"]
        else 0
    )
    metrics = {
        **dict(stats),
        "restaurantCount": len(restaurant_results),
        "model": configured_qwen_model(),
        "temperature": 0,
        "maxClaimsPerRestaurant": MAX_CLAIMS,
        "elapsedSeconds": round(time.monotonic() - started, 3),
        "multiSourceCountsAreOverlapping": True,
        "knownOverclaimApprovalCount": 0 if run_number == 2 and human_review_pass else None,
        "knownOverclaimManualReview": (
            "PASS" if run_number == 2 and human_review_pass else "PENDING"
        ),
        "sideEffects": {
            "mysqlReads": len(restaurant_results) * 8,
            "mysqlWrites": 0,
            "qdrantReads": 0,
            "qdrantWrites": 0,
            "embeddingCalls": 0,
            "embeddingWrites": 0,
            "geminiCalls": 0,
        },
    }
    result = {
        "runVersion": "semantic-profile-generator-v2.1-dry-run-v1",
        "runNumber": run_number,
        "createdAt": datetime.now(UTC).isoformat(),
        "cohortPath": str(COHORT_PATH.relative_to(ROOT)),
        "cohortHash": _hash(cohort),
        "model": configured_qwen_model(),
        "runMode": "DRY_RUN",
        "generatorSchemaVersion": "atomic-claim-support-quote-v2.1-korean",
        "restaurantRuns": restaurant_results,
        "metrics": metrics,
    }
    _write_new(output_path, result)
    if run_number == 1:
        _write_new(METRICS_PATH, {"createdAt": result["createdAt"], "run1": metrics})
    print(f"[Generator V2.1] wrote {output_path.relative_to(ROOT)}", flush=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze-cohort", "run"))
    parser.add_argument("--run-number", type=int, choices=(1, 2), default=1)
    parser.add_argument("--human-review-pass", action="store_true")
    args = parser.parse_args()
    if args.command == "freeze-cohort":
        document = freeze_cohort()
        print(
            json.dumps(
                {
                    "path": str(COHORT_PATH.relative_to(ROOT)),
                    "restaurantIds": document["restaurantIds"],
                },
                ensure_ascii=False,
            )
        )
    else:
        run_pilot(args.run_number, human_review_pass=args.human_review_pass)


if __name__ == "__main__":
    main()
