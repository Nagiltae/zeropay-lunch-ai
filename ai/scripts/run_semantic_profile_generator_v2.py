"""Freeze a read-only three-restaurant cohort and run Generator V2 DRY-RUN."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
AI_ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "AI_Answer"
sys.path.insert(0, str(AI_ROOT))

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

COHORT_PATH = ARTIFACTS / "semantic_profile_generator_v2_cohort.json"
RUN_PATHS = {
    1: ARTIFACTS / "semantic_profile_generator_v2_run1.json",
    2: ARTIFACTS / "semantic_profile_generator_v2_run2.json",
}
METRICS_PATH = ARTIFACTS / "semantic_profile_generator_v2_metrics.json"
PILOT_IDS = (9559, 9603, 9639)
PILOT_REASONS = {
    9559: "Frozen priority cohort: historical tenderness/juiciness and group-context overclaims.",
    9603: (
        "Frozen priority cohort: historical unsupported menu composition and merged "
        "solo/cleanliness claims."
    ),
    9639: "Frozen priority cohort: historical group-to-layout and taste-to-preparation inferences.",
}


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    import hashlib

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
    for ordinal, restaurant_id in enumerate(PILOT_IDS, start=1):
        profile_input, catalog = _live_context(restaurant_id)
        evidence_counts = Counter(item["evidenceType"] for item in catalog["items"])
        restaurants.append(
            {
                "ordinal": ordinal,
                "restaurantId": restaurant_id,
                "name": profile_input["identity"].get("restaurantName"),
                "selectionReason": PILOT_REASONS[restaurant_id],
                "profileReady": profile_input["quality"],
                "inputHash": profile_input["inputHash"],
                "catalogHash": catalog["catalogHash"],
                "evidenceCountsBySourceType": dict(sorted(evidence_counts.items())),
                "evidenceCount": len(catalog["items"]),
            }
        )
        print(
            f"[Cohort Freeze] {ordinal}/3 restaurant={restaurant_id} "
            f"ready=true evidence={len(catalog['items'])}",
            flush=True,
        )
    document = {
        "cohortVersion": "semantic-profile-generator-v2-cohort-v1",
        "createdAt": datetime.now(UTC).isoformat(),
        "source": "current read-only DB input via semantic_profile_shadow.build_input",
        "frozenBeforeGeneratorCalls": True,
        "restaurantIds": list(PILOT_IDS),
        "mysqlSelectQueryCount": len(PILOT_IDS) * 8,
        "restaurants": restaurants,
        "databaseWrites": 0,
    }
    _write_new(COHORT_PATH, document)
    return document


def _prompt_evidence(
    catalog: dict[str, Any], restaurant_id: int
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    evidence_by_id = canonical_evidence(catalog, restaurant_id)
    allowed = [
        item
        for item in evidence_by_id.values()
        if item["evidenceType"] in {"menu", "keyword", "review"}
        and item["status"] == "SUCCESS"
        and item["rawText"]
    ]
    prompt_rows = [
        {
            "evidenceId": item["evidenceId"],
            "sourceType": item["evidenceType"],
            "rawText": item["rawText"],
        }
        for item in allowed
    ]
    return prompt_rows, evidence_by_id


def _call_bounded(
    operation: Callable[[], Any],
    *,
    stage: str,
    stats: dict[str, int],
    correction: Callable[[], Any] | None = None,
) -> tuple[Any | None, str | None]:
    for attempt in range(2):
        stats[f"{stage}Calls"] += 1
        try:
            return (correction() if attempt and correction else operation()), None
        except Exception as error:  # no raw model response is stored
            stats["retries"] += int(attempt == 0)
            if attempt == 1:
                return None, semantic_error_category(error)
    return None, "UNKNOWN_ERROR"


def _generated_claim_input(restaurant_id: int, claim: dict[str, Any]) -> ClaimCandidate:
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


def run_pilot(run_number: int, *, known_overclaim_review: str | None = None) -> dict[str, Any]:
    if run_number not in RUN_PATHS:
        raise ValueError("run number must be 1 or 2")
    if not COHORT_PATH.exists():
        raise RuntimeError("COHORT_NOT_FROZEN")
    output_path = RUN_PATHS[run_number]
    if output_path.exists():
        raise RuntimeError(f"REFUSING_TO_OVERWRITE:{output_path.name}")
    if configured_qwen_model() != "qwen3.5:9b":
        raise RuntimeError("UNEXPECTED_PROFILE_GENERATOR_MODEL")
    cohort = json.loads(COHORT_PATH.read_text(encoding="utf-8"))
    if cohort.get("frozenBeforeGeneratorCalls") is not True or cohort.get("restaurantIds") != list(
        PILOT_IDS
    ):
        raise RuntimeError("COHORT_FREEZE_INVALID")

    previous = None
    if run_number == 2:
        run1_path = RUN_PATHS[1]
        if not run1_path.exists():
            raise RuntimeError("RUN1_REQUIRED_BEFORE_RUN2")
        previous = json.loads(run1_path.read_text(encoding="utf-8"))
        m = previous["metrics"]
        if any(
            m[key]
            for key in (
                "schemaErrorCount",
                "deterministicErrorCount",
                "quoteMismatchCount",
                "knownOverclaimApprovalCount",
            )
        ):
            raise RuntimeError("RUN1_QUALITY_GATE_FAILED_RUN2_BLOCKED")
        if known_overclaim_review != "PASS":
            raise RuntimeError("RUN2_REQUIRES_COMPLETED_KNOWN_OVERCLAIM_REVIEW")

    client = OllamaClient(timeout=180.0, num_predict=4096)
    verifier = OllamaAtomicClaimVerifier(client)
    stats = {
        "generatorCalls": 0,
        "atomicizerCalls": 0,
        "assertionVerifierCalls": 0,
        "retries": 0,
    }
    restaurant_runs: list[dict[str, Any]] = []
    started = time.monotonic()
    try:
        for ordinal, frozen in enumerate(cohort["restaurants"], start=1):
            restaurant_id = frozen["restaurantId"]
            profile_input, catalog = _live_context(restaurant_id)
            if (
                profile_input["inputHash"] != frozen["inputHash"]
                or catalog["catalogHash"] != frozen["catalogHash"]
            ):
                raise RuntimeError(f"FROZEN_SOURCE_DRIFT:{restaurant_id}")
            prompt_rows, evidence_by_id = _prompt_evidence(catalog, restaurant_id)
            raw_output: str | None = None
            generator_error = None
            stats["generatorCalls"] += 1
            try:
                raw_output = client.complete(
                    "/no_think\nYou create atomic evidence-grounded claims. Never infer.",
                    generator_prompt(
                        {"restaurantId": restaurant_id, "name": frozen["name"]}, prompt_rows
                    ),
                    generator_schema(),
                )
                validation = validate_generator_output(
                    raw_output, restaurant_id=restaurant_id, catalog=catalog
                )
            except Exception as error:
                generator_error = semantic_error_category(error)
                validation = {
                    "schemaValid": False,
                    "errors": [{"code": "GENERATOR_ERROR", "category": generator_error}],
                    "claims": [],
                }

            rows = []
            claims = validation.get("claims", [])
            counters = Counter()
            counters["generatedClaimCount"] = len(claims)
            counters["schemaValidCount"] = len(claims) if validation.get("schemaValid") else 0
            counters["deterministicPassCount"] = 0
            counters["exactQuotePassCount"] = 0
            counters["nonAtomicCount"] = 0
            counters["semanticSupportedCount"] = 0
            counters["semanticUnsupportedCount"] = 0
            counters["semanticPartialCount"] = 0
            counters["verifierErrorCount"] = 0
            counters["approvedClaimCount"] = 0
            counters["duplicateCount"] = 0
            counters["provenanceLeakCount"] = 0
            counters["unknownEvidenceIdCount"] = 0
            counters["quoteMismatchCount"] = 0

            for claim_index, checked in enumerate(claims, start=1):
                claim = checked["claim"]
                errors = checked["errors"]
                counters["duplicateCount"] += sum(e["code"] == "DUPLICATE" for e in errors)
                counters["provenanceLeakCount"] += sum(
                    e["code"] == "PROVENANCE_TEXT_IN_CLAIM" for e in errors
                )
                counters["unknownEvidenceIdCount"] += sum(
                    e["code"] == "UNKNOWN_EVIDENCE" for e in errors
                )
                counters["quoteMismatchCount"] += sum(e["code"] == "QUOTE_MISMATCH" for e in errors)
                quote_pass = not any(
                    e["code"]
                    in {
                        "QUOTE_MISMATCH",
                        "SUPPORT_QUOTE_MISSING",
                        "QUOTE_EVIDENCE_MISMATCH",
                        "QUOTE_SOURCE_UNRESOLVED",
                    }
                    for e in errors
                )
                if quote_pass:
                    counters["exactQuotePassCount"] += 1
                if not checked["valid"]:
                    rows.append(
                        {
                            "claim": claim,
                            "rawGeneratedClaim": {
                                k: v
                                for k, v in claim.items()
                                if k not in {"restaurantId", "claimId"}
                            },
                            "deterministicValidation": checked,
                            "atomicAssertions": [],
                            "semanticVerdict": None,
                            "approved": False,
                            "rejectReasons": sorted({e["code"] for e in errors}),
                        }
                    )
                    continue
                counters["deterministicPassCount"] += 1
                verifier_input = _generated_claim_input(restaurant_id, claim)
                atomicization, atomic_error = _call_bounded(
                    lambda c=verifier_input: verifier.decompose(c),
                    stage="atomicizer",
                    stats=stats,
                    correction=lambda c=verifier_input: verifier.decompose(c, correction=True),
                )
                assertions_out = []
                semantic_verdict = None
                reject_reasons: list[str] = []
                verifier_error = None
                if atomic_error:
                    verifier_error = atomic_error
                    counters["verifierErrorCount"] += 1
                    reject_reasons.append("ATOMICIZER_ERROR")
                elif atomicity_rejection(len(atomicization.assertions)):
                    counters["nonAtomicCount"] += 1
                    reject_reasons.append("GENERATOR_NON_ATOMIC")
                    assertions_out = [
                        item.model_dump(mode="json") for item in atomicization.assertions
                    ]
                else:
                    assertion = atomicization.assertions[0]
                    assertion_result, assertion_error = _call_bounded(
                        lambda a=assertion, c=claim, e=checked["resolvedEvidence"]: (
                            verifier.verify_assertion(c["claimType"], a, e)
                        ),
                        stage="assertionVerifier",
                        stats=stats,
                    )
                    assertions_out = [
                        {
                            **assertion.model_dump(mode="json"),
                            "verdict": assertion_result.verdict if assertion_result else None,
                            "supportingEvidenceIds": assertion_result.evidenceIds
                            if assertion_result
                            else [],
                        }
                    ]
                    if assertion_error:
                        verifier_error = assertion_error
                        counters["verifierErrorCount"] += 1
                        reject_reasons.append("VERIFIER_ERROR")
                    else:
                        semantic_verdict = aggregate_assertion_verdicts(
                            atomicization.assertions, [assertion_result]
                        )
                        counters[f"semantic{semantic_verdict.title()}Count"] += 1
                        if semantic_verdict != "SUPPORTED":
                            reject_reasons.append(semantic_verdict)
                approved = (
                    checked["valid"]
                    and len(assertions_out) == 1
                    and semantic_verdict == "SUPPORTED"
                    and verifier_error is None
                )
                if approved:
                    counters["approvedClaimCount"] += 1
                rows.append(
                    {
                        "claim": claim,
                        "rawGeneratedClaim": {
                            k: v for k, v in claim.items() if k not in {"restaurantId", "claimId"}
                        },
                        "deterministicValidation": checked,
                        "atomicAssertions": assertions_out,
                        "semanticVerdict": semantic_verdict,
                        "approved": approved,
                        "verifierError": verifier_error,
                        "rejectReasons": reject_reasons,
                    }
                )
                progress = (
                    f"[Generator V2] restaurant {ordinal}/3={restaurant_id} "
                    f"claim {claim_index}/{len(claims)} "
                    f"atomicizerCalls={stats['atomicizerCalls']} "
                    f"verifierCalls={stats['assertionVerifierCalls']} "
                    f"errors={counters['verifierErrorCount']} "
                    f"elapsed={time.monotonic() - started:.1f}s"
                )
                print(
                    progress,
                    flush=True,
                )

            restaurant_runs.append(
                {
                    "restaurantId": restaurant_id,
                    "name": frozen["name"],
                    "inputHash": frozen["inputHash"],
                    "catalogHash": frozen["catalogHash"],
                    "sourceEvidenceSummary": frozen["evidenceCountsBySourceType"],
                    "generatorError": generator_error,
                    "generatorRawTextPersisted": False,
                    "rawGeneratedClaims": [row["rawGeneratedClaim"] for row in rows],
                    "claimResults": rows,
                    "metrics": dict(counters),
                }
            )
            elapsed = time.monotonic() - started
            eta = max(0, elapsed / ordinal * (3 - ordinal))
            print(
                f"[Generator V2] restaurant {ordinal}/3: {restaurant_id}; "
                f"claims={counters['generatedClaimCount']}, "
                f"validated={counters['deterministicPassCount']}, "
                f"approved={counters['approvedClaimCount']}, "
                f"elapsed={elapsed:.1f}s, ETA~{eta:.1f}s",
                flush=True,
            )
    finally:
        client.close()

    metric_keys = [
        "generatedClaimCount",
        "schemaValidCount",
        "deterministicPassCount",
        "exactQuotePassCount",
        "nonAtomicCount",
        "semanticSupportedCount",
        "semanticUnsupportedCount",
        "semanticPartialCount",
        "verifierErrorCount",
        "approvedClaimCount",
        "duplicateCount",
        "provenanceLeakCount",
        "unknownEvidenceIdCount",
        "quoteMismatchCount",
    ]
    totals = {
        key: sum(row["metrics"].get(key, 0) for row in restaurant_runs) for key in metric_keys
    }
    structural_error_count = sum(
        not row["deterministicValidation"].get("valid", False)
        for restaurant in restaurant_runs
        for row in restaurant["claimResults"]
    )
    totals["deterministicErrorCount"] = structural_error_count
    totals["schemaErrorCount"] = sum(item["generatorError"] is not None for item in restaurant_runs)
    totals["knownOverclaimApprovalCount"] = (
        0 if run_number == 2 and known_overclaim_review == "PASS" else None
    )
    metrics = {
        **totals,
        "restaurantCount": len(restaurant_runs),
        "generatorCalls": stats["generatorCalls"],
        "atomicizerCalls": stats["atomicizerCalls"],
        "assertionVerifierCalls": stats["assertionVerifierCalls"],
        "retries": stats["retries"],
        "elapsedSeconds": round(time.monotonic() - started, 3),
        "mysqlSelectQueryCount": len(restaurant_runs) * 8,
        "model": configured_qwen_model(),
        "knownOverclaimManualReview": (
            "PASS" if run_number == 2 and known_overclaim_review == "PASS" else "PENDING"
        ),
        "temperature": 0,
        "sideEffects": {
            "mysqlReads": len(restaurant_runs) * 8,
            "mysqlWrites": 0,
            "qdrantReads": 0,
            "qdrantWrites": 0,
            "embeddingCalls": 0,
            "embeddingWrites": 0,
            "geminiCalls": 0,
        },
    }
    result = {
        "runVersion": "semantic-profile-generator-v2-dry-run-v1",
        "runNumber": run_number,
        "createdAt": datetime.now(UTC).isoformat(),
        "cohortPath": str(COHORT_PATH.relative_to(ROOT)),
        "cohortHash": _canonical_hash(cohort),
        "model": configured_qwen_model(),
        "generatorSchemaVersion": "atomic-claim-support-quote-v2",
        "runMode": "DRY_RUN",
        "restaurantRuns": restaurant_runs,
        "metrics": metrics,
    }
    _write_new(output_path, result)
    if run_number == 1 and not METRICS_PATH.exists():
        _write_new(
            METRICS_PATH,
            {
                "createdAt": result["createdAt"],
                "runs": [metrics],
                "finalStatus": "PENDING_HUMAN_REVIEW",
            },
        )
    elif run_number == 2:
        metrics_doc = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
        if len(metrics_doc.get("runs", [])) != 1:
            raise RuntimeError("UNEXPECTED_METRICS_RUN_HISTORY")
        metrics_doc["runs"].append(metrics)
        metrics_doc["finalStatus"] = "PENDING_HUMAN_REVIEW"
        METRICS_PATH.write_text(
            json.dumps(metrics_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(f"[Generator V2] wrote {output_path.relative_to(ROOT)}", flush=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze-cohort", "run"))
    parser.add_argument("--run-number", type=int, choices=(1, 2), default=1)
    parser.add_argument("--known-overclaim-review", choices=("PASS",))
    args = parser.parse_args()
    if args.command == "freeze-cohort":
        cohort = freeze_cohort()
        print(
            json.dumps(
                {
                    "path": str(COHORT_PATH.relative_to(ROOT)),
                    "restaurantIds": cohort["restaurantIds"],
                },
                ensure_ascii=False,
            )
        )
    else:
        run_pilot(args.run_number, known_overclaim_review=args.known_overclaim_review)


if __name__ == "__main__":
    main()
