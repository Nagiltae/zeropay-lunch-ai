"""Freeze and run the V2.1 fixture gate; run the Qdrant shadow only on a full pass."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter, defaultdict
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
from app.semantic_profile_quality_gate import (  # noqa: E402
    AssertionVerdict,
    ClaimCandidate,
    OllamaAtomicClaimVerifier,
    aggregate_assertion_verdicts,
    normalize_claim_key,
    validate_claim,
)
from scripts.run_semantic_profile_shadow_review import (  # noqa: E402
    COLLECTION,
    MANIFEST_PATH,
    _compare_live_points,
    _load_catalogs,
    _point_evidence_bindings,
    _resolved_evidence,
    _scroll_qdrant,
)
from scripts.run_semantic_profile_verifier_v2 import (  # noqa: E402
    _call_with_one_retry,
    _canonical_hash,
)

FIXTURE_PATH = ARTIFACTS / "semantic_profile_verifier_v21_fixtures.json"
FIXTURE_RESULTS_PATH = ARTIFACTS / "semantic_profile_verifier_v21_fixture_results.json"
METRICS_PATH = ARTIFACTS / "semantic_profile_verifier_v21_metrics.json"
SHADOW_PATH = ARTIFACTS / "semantic_profile_verifier_v21_shadow_review.json"
V2_FIXTURE_PATH = ARTIFACTS / "semantic_profile_verifier_v2_fixtures.json"
V2_RESULT_PATH = ARTIFACTS / "semantic_profile_verifier_v2_fixture_results.json"
V1_SHADOW_PATH = ARTIFACTS / "semantic_profile_shadow_review.json"


def freeze_v21_fixtures() -> dict[str, Any]:
    if FIXTURE_PATH.exists():
        raise RuntimeError(f"REFUSING_TO_OVERWRITE:{FIXTURE_PATH.name}")
    previous = json.loads(V2_FIXTURE_PATH.read_text(encoding="utf-8"))
    if previous.get("frozenBeforeVerifierRuns") is not True:
        raise RuntimeError("SOURCE_FIXTURES_NOT_FROZEN")

    fixtures = json.loads(json.dumps(previous["fixtures"], ensure_ascii=False))
    old_9571 = next(
        item
        for item in fixtures
        if item["fixtureId"] == "menu-evidence-does-not-entail-chicken-topping-9571"
    )
    old_9571["previousExpectedFinalVerdict"] = old_9571["expectedFinalVerdict"]
    old_9571["expectedFinalVerdict"] = "UNSUPPORTED"
    old_9571["expectedIndexable"] = False
    old_9571["polarity"] = "negative"
    old_9571["expectationCorrection"] = (
        "MENU names prove only listed item names. The claim adds a topping/ingredient assertion, "
        "which these titles do not directly establish. Corrected by the pre-run policy audit."
    )

    source = old_9571["evidenceSnapshot"]
    by_id = {item["evidenceId"]: item for item in source}
    mixed_claim = {
        "fixtureId": "listed-menu-items-with-one-unsubstantiated-item-9571",
        "restaurantId": 9571,
        "catalogPath": old_9571["catalogPath"],
        "catalogHash": old_9571["catalogHash"],
        "claimId": "mixed:9571:menu-items:bulgogi-vegetable-chicken",
        "claimType": "FOOD_TYPE",
        "claimText": "메뉴에 불고기피자, 야채퀘사디아피자, 닭고기피자 항목이 있다.",
        "evidenceIds": ["E015", "E024"],
        "supportQuotes": [
            {"evidenceId": "E015", "quote": "불고기피자"},
            {"evidenceId": "E024", "quote": "야채퀘사디아피자"},
        ],
        "expectedFinalVerdict": "PARTIAL",
        "expectedIndexable": False,
        "polarity": "mixed",
        "evidenceSnapshot": [by_id["E015"], by_id["E024"]],
    }
    mixed_claim["evidenceSnapshotHash"] = _canonical_hash(mixed_claim["evidenceSnapshot"])
    for quote in mixed_claim["supportQuotes"]:
        evidence = by_id[quote["evidenceId"]]
        if quote["quote"] not in evidence["rawText"]:
            raise RuntimeError("MIXED_FIXTURE_QUOTE_NOT_EXACT")
    fixtures.append(mixed_claim)

    document = {
        "fixtureVersion": "semantic-profile-verifier-v2-frozen-2",
        "createdAt": datetime.now(UTC).isoformat(),
        "frozenBeforeVerifierRuns": True,
        "supersedesFixtureVersion": previous["fixtureVersion"],
        "model": "qwen3.5:9b",
        "temperature": 0,
        "runsRequired": 3,
        "maxAssertions": 8,
        "retryPolicy": "initial + at most one retry per atomicizer/assertion call",
        "policyAudit": "AI_Answer/semantic_profile_verifier_v21_fixture_audit.md",
        "source": (
            "Preserved V2 snapshots; corrected the 9571 topping expectation before V2.1 calls "
            "and added one literal menu-entry mixed fixture."
        ),
        "fixtures": fixtures,
    }
    FIXTURE_PATH.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n")
    return {"path": str(FIXTURE_PATH), "fixtureCount": len(fixtures)}


def _fixture_claim(fixture: dict[str, Any]) -> ClaimCandidate:
    snapshot = fixture["evidenceSnapshot"]
    if _canonical_hash(snapshot) != fixture["evidenceSnapshotHash"]:
        raise RuntimeError(f"FIXTURE_SNAPSHOT_HASH_MISMATCH:{fixture['fixtureId']}")
    return ClaimCandidate.model_validate(
        {
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
    )


def _run_fixtures() -> tuple[dict[str, Any], dict[str, Any]]:
    for path in (FIXTURE_RESULTS_PATH, METRICS_PATH, SHADOW_PATH):
        if path.exists():
            raise RuntimeError(f"REFUSING_TO_OVERWRITE:{path.name}")
    document = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    if document.get("frozenBeforeVerifierRuns") is not True:
        raise RuntimeError("FIXTURES_NOT_FROZEN")
    if configured_qwen_model() != "qwen3.5:9b":
        raise RuntimeError("UNEXPECTED_QWEN_MODEL")

    client = OllamaClient(timeout=120.0, num_predict=768)
    verifier = OllamaAtomicClaimVerifier(client)
    stats: dict[str, int] = {
        "modelCalls": 0,
        "retries": 0,
        "atomicizerCalls": 0,
        "assertionVerifierCalls": 0,
    }
    rows: list[dict[str, Any]] = []
    started = time.monotonic()
    try:
        for run_number in range(1, 4):
            for fixture in document["fixtures"]:
                claim = _fixture_claim(fixture)
                before_retries = stats["retries"]
                started_one = time.monotonic()
                atomicization, error = _call_with_one_retry(
                    lambda claim=claim: verifier.decompose(claim),
                    stats,
                    "atomicizer",
                    retry_operation=lambda claim=claim: verifier.decompose(claim, correction=True),
                )
                assertions_out = []
                errors = []
                final_verdict = "VERIFIER_ERROR"
                if error:
                    errors.append({"stage": "ATOMICIZER", "category": error})
                else:
                    assertion_results: list[AssertionVerdict] = []
                    for assertion in atomicization.assertions:
                        result, error = _call_with_one_retry(
                            lambda assertion=assertion, claim=claim, fixture=fixture: (
                                verifier.verify_assertion(
                                    claim.claimType, assertion, fixture["evidenceSnapshot"]
                                )
                            ),
                            stats,
                            "assertionVerifier",
                        )
                        if error:
                            errors.append(
                                {
                                    "stage": "ASSERTION_VERIFIER",
                                    "assertionId": assertion.assertionId,
                                    "category": error,
                                }
                            )
                            break
                        assertion_results.append(result)
                        assertions_out.append(
                            {
                                **assertion.model_dump(mode="json"),
                                "verdict": result.verdict,
                                "supportingEvidenceIds": result.evidenceIds,
                            }
                        )
                    if not errors:
                        try:
                            final_verdict = aggregate_assertion_verdicts(
                                atomicization.assertions, assertion_results
                            )
                        except ValueError:
                            errors.append({"stage": "AGGREGATOR", "category": "UNKNOWN_ERROR"})
                expected = fixture["expectedFinalVerdict"]
                rows.append(
                    {
                        "runNumber": run_number,
                        "fixtureId": fixture["fixtureId"],
                        "atomicAssertions": assertions_out,
                        "assertionVerdicts": [item["verdict"] for item in assertions_out],
                        "finalVerdict": final_verdict,
                        "expectedFinalVerdict": expected,
                        "expectedIndexable": fixture["expectedIndexable"],
                        "indexableUnderCurrentPolicy": False,
                        "pass": final_verdict == expected and not errors,
                        "latencySeconds": round(time.monotonic() - started_one, 3),
                        "retryCount": stats["retries"] - before_retries,
                        "errors": errors,
                    }
                )
                print(
                    json.dumps(
                        {
                            "run": run_number,
                            "fixture": fixture["fixtureId"],
                            "verdict": final_verdict,
                            "pass": rows[-1]["pass"],
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
    finally:
        client.close()

    by_fixture = {f["fixtureId"]: f for f in document["fixtures"]}
    per_fixture = {}
    for fixture in document["fixtures"]:
        runs = [row for row in rows if row["fixtureId"] == fixture["fixtureId"]]
        per_fixture[fixture["fixtureId"]] = {
            "polarity": fixture["polarity"],
            "expected": fixture["expectedFinalVerdict"],
            "observed": [row["finalVerdict"] for row in runs],
            "allThreePass": len(runs) == 3 and all(row["pass"] for row in runs),
        }
    false_acceptance = sum(
        row["finalVerdict"] == "SUPPORTED"
        for row in rows
        if by_fixture[row["fixtureId"]]["polarity"] in {"negative", "mixed"}
    )
    positive_false_rejection = sum(
        row["finalVerdict"] != "SUPPORTED"
        for row in rows
        if by_fixture[row["fixtureId"]]["polarity"] == "positive"
    )
    partial_expected = sum(f["expectedFinalVerdict"] == "PARTIAL" for f in document["fixtures"]) * 3
    partial_correct = sum(
        row["finalVerdict"] == "PARTIAL" for row in rows if row["expectedFinalVerdict"] == "PARTIAL"
    )
    gate_pass = (
        all(item["allThreePass"] for item in per_fixture.values())
        and false_acceptance == 0
        and positive_false_rejection == 0
        and not any(row["errors"] for row in rows)
        and partial_correct == partial_expected
    )
    metrics = {
        "fixtureCount": len(document["fixtures"]),
        "fixtureRuns": 3,
        "negativeFixtureCount": sum(f["polarity"] == "negative" for f in document["fixtures"]),
        "mixedFixtureCount": sum(f["polarity"] == "mixed" for f in document["fixtures"]),
        "positiveFixtureCount": sum(f["polarity"] == "positive" for f in document["fixtures"]),
        "falseAcceptanceCount": false_acceptance,
        "positiveFalseRejectionCount": positive_false_rejection,
        "partialExpectedCount": partial_expected,
        "partialCorrectCount": partial_correct,
        "atomicizerErrorCount": sum(
            any(e["stage"] == "ATOMICIZER" for e in row["errors"]) for row in rows
        ),
        "verifierErrorCount": sum(bool(row["errors"]) for row in rows),
        "model": configured_qwen_model(),
        "temperature": 0,
        "retryPolicy": document["retryPolicy"],
        "atomicizerCalls": stats["atomicizerCalls"],
        "assertionVerifierCalls": stats["assertionVerifierCalls"],
        "actualModelCalls": stats["modelCalls"],
        "retries": stats["retries"],
        "errorCategories": {
            key.removeprefix("error:"): value
            for key, value in stats.items()
            if key.startswith("error:")
        },
        "elapsedSeconds": round(time.monotonic() - started, 3),
        "fixtureGate": "PASS" if gate_pass else "FAIL",
        "fullShadowRunStatus": "PENDING_GATE" if gate_pass else "NOT_RUN_REGRESSION_GATE_FAILED",
        "sideEffects": {
            "localQwenCalls": stats["modelCalls"],
            "qdrantReads": 0,
            "qdrantWrites": 0,
            "mysqlReads": 0,
            "mysqlWrites": 0,
            "embeddingCalls": 0,
            "geminiCalls": 0,
        },
        "perFixture": per_fixture,
    }
    result_doc = {
        "reviewVersion": "semantic-profile-verifier-v2.1-fixture-suite",
        "createdAt": datetime.now(UTC).isoformat(),
        "fixturePath": str(FIXTURE_PATH.relative_to(ROOT)),
        "fixtureHash": _canonical_hash(document),
        "results": rows,
    }
    return result_doc, metrics


def _run_shadow(metrics: dict[str, Any]) -> dict[str, Any]:
    if metrics["fixtureGate"] != "PASS":
        skipped = {
            "reviewVersion": "semantic-profile-verifier-v2.1-shadow",
            "executionStatus": "NOT_RUN_REGRESSION_GATE_FAILED",
            "collection": COLLECTION,
            "plannedPointCount": 40,
            "qdrantReads": 0,
            "qdrantWrites": 0,
            "v1ToV21TransitionCounts": "NOT_COMPUTED",
            "items": [],
        }
        SHADOW_PATH.write_text(json.dumps(skipped, ensure_ascii=False, indent=2) + "\n")
        return skipped

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    points = manifest.get("points", [])
    live_points = _scroll_qdrant(os.getenv("QDRANT_URL", "http://localhost:6333"))
    consistency = _compare_live_points(points, live_points)
    if not consistency["consistent"] or len(points) != 40:
        raise RuntimeError("QDRANT_V12_MANIFEST_OR_COUNT_MISMATCH")

    documents = []
    for path in ARTIFACTS.rglob("*.json"):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            documents.append((path, value))
    catalogs, owners = _load_catalogs(documents)
    point_hashes, restaurant_hashes = _point_evidence_bindings(points)
    old_shadow = json.loads(V1_SHADOW_PATH.read_text(encoding="utf-8"))
    old_by_id = {str(item["claimId"]): item for item in old_shadow.get("items", [])}
    client = OllamaClient(timeout=120.0, num_predict=768)
    verifier = OllamaAtomicClaimVerifier(client)
    stats: dict[str, int] = {
        "modelCalls": 0,
        "retries": 0,
        "atomicizerCalls": 0,
        "assertionVerifierCalls": 0,
    }
    seen: set[tuple[int, str, str]] = set()
    rows = []
    try:
        for point in points:
            restaurant_id = int(point["restaurantId"])
            claim_data = {
                "restaurantId": restaurant_id,
                "claimId": str(point["claimId"]),
                "claimType": point["claimType"],
                "claimText": point.get("normalizedClaimText") or point.get("originalClaimText", ""),
                "evidenceIds": point["evidenceIds"],
                "supportQuotes": [],
            }
            claim = ClaimCandidate.model_validate(claim_data)
            duplicate = normalize_claim_key(claim) in seen
            seen.add(normalize_claim_key(claim))
            catalog_hash = point_hashes.get(str(point["pointId"])) or restaurant_hashes.get(
                restaurant_id
            )
            evidence, resolution = _resolved_evidence(
                restaurant_id, claim.evidenceIds, catalog_hash, catalogs, owners
            )
            deterministic = validate_claim(
                claim_data,
                {item["evidenceId"]: item for item in evidence},
                expected_restaurant_id=restaurant_id,
                duplicate=duplicate,
            )
            verdict = "VERIFIER_ERROR"
            assertions_out = []
            errors = []
            if not resolution.get("resolved") or not deterministic.get("evidenceIntegrityValid"):
                errors.append({"stage": "EVIDENCE", "category": "INVALID_EVIDENCE"})
            else:
                atomicization, error = _call_with_one_retry(
                    lambda claim=claim: verifier.decompose(claim),
                    stats,
                    "atomicizer",
                    retry_operation=lambda claim=claim: verifier.decompose(claim, correction=True),
                )
                if error:
                    errors.append({"stage": "ATOMICIZER", "category": error})
                else:
                    assertion_results = []
                    for assertion in atomicization.assertions:
                        result, error = _call_with_one_retry(
                            lambda assertion=assertion, claim=claim, evidence=evidence: (
                                verifier.verify_assertion(claim.claimType, assertion, evidence)
                            ),
                            stats,
                            "assertionVerifier",
                        )
                        if error:
                            errors.append(
                                {
                                    "stage": "ASSERTION_VERIFIER",
                                    "assertionId": assertion.assertionId,
                                    "category": error,
                                }
                            )
                            break
                        assertion_results.append(result)
                        assertions_out.append(
                            {
                                **assertion.model_dump(mode="json"),
                                "verdict": result.verdict,
                                "supportingEvidenceIds": result.evidenceIds,
                            }
                        )
                    if not errors:
                        try:
                            verdict = aggregate_assertion_verdicts(
                                atomicization.assertions, assertion_results
                            )
                        except ValueError:
                            errors.append({"stage": "AGGREGATOR", "category": "UNKNOWN_ERROR"})
            if errors:
                verdict = "ERROR"
            rows.append(
                {
                    **claim_data,
                    "resolvedEvidence": evidence,
                    "evidenceResolution": resolution,
                    "deterministicValidation": deterministic,
                    "atomicAssertions": assertions_out,
                    "atomicizerStatus": "ERROR"
                    if errors and errors[0]["stage"] == "ATOMICIZER"
                    else "SUCCESS",
                    "verifierStatus": "ERROR" if errors else "SUCCESS",
                    "errorCategory": errors,
                    "v1VerifierVerdict": old_by_id.get(claim.claimId, {}).get(
                        "semanticVerdict", "ERROR"
                    ),
                    "v21VerifierVerdict": verdict,
                    "finalSemanticVerdict": verdict,
                    "indexableUnderCurrentPolicy": False,
                }
            )
    finally:
        client.close()

    transitions: Counter[str] = Counter()
    by_type: dict[str, Counter[str]] = defaultdict(Counter)
    by_source: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        old = row["v1VerifierVerdict"]
        new = row["v21VerifierVerdict"]
        old = "ERROR" if old in {"ERROR", "VERIFIER_ERROR", None} else old
        transitions[f"{old} -> {new}"] += 1
        by_type[row["claimType"]][new] += 1
        for source in {item["evidenceType"] for item in row["resolvedEvidence"]}:
            by_source[str(source)][new] += 1
    shadow = {
        "reviewVersion": "semantic-profile-verifier-v2.1-shadow",
        "createdAt": datetime.now(UTC).isoformat(),
        "executionStatus": "COMPLETE_READ_ONLY",
        "collection": COLLECTION,
        "liveCollectionConsistency": consistency,
        "model": configured_qwen_model(),
        "items": rows,
    }
    metrics["fullShadow"] = {
        "pointCount": len(rows),
        "supportedCount": sum(row["v21VerifierVerdict"] == "SUPPORTED" for row in rows),
        "partialCount": sum(row["v21VerifierVerdict"] == "PARTIAL" for row in rows),
        "unsupportedCount": sum(row["v21VerifierVerdict"] == "UNSUPPORTED" for row in rows),
        "errorCount": sum(row["v21VerifierVerdict"] == "ERROR" for row in rows),
        "v1ToV21TransitionCounts": dict(sorted(transitions.items())),
        "byClaimType": {key: dict(value) for key, value in sorted(by_type.items())},
        "bySourceType": {
            key: {"counts": dict(value), "denominatorOverlapping": True}
            for key, value in sorted(by_source.items())
        },
        "atomicizerCalls": stats["atomicizerCalls"],
        "assertionVerifierCalls": stats["assertionVerifierCalls"],
        "retries": stats["retries"],
        "verifierErrors": sum(row["v21VerifierVerdict"] == "ERROR" for row in rows),
        "sideEffects": {
            "qdrantReads": len(live_points),
            "qdrantWrites": 0,
            "mysqlReads": 0,
            "mysqlWrites": 0,
            "embeddingCalls": 0,
            "geminiCalls": 0,
            "localQwenCalls": stats["modelCalls"],
        },
    }
    metrics["fullShadowRunStatus"] = "COMPLETE_READ_ONLY"
    SHADOW_PATH.write_text(json.dumps(shadow, ensure_ascii=False, indent=2) + "\n")
    return shadow


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze-fixtures", action="store_true")
    args = parser.parse_args()
    if args.freeze_fixtures:
        print(json.dumps(freeze_v21_fixtures(), ensure_ascii=False, indent=2))
        return
    fixture_result, metrics = _run_fixtures()
    FIXTURE_RESULTS_PATH.write_text(json.dumps(fixture_result, ensure_ascii=False, indent=2) + "\n")
    shadow = _run_shadow(metrics)
    METRICS_PATH.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "fixtureMetrics": metrics,
                "shadowStatus": shadow["executionStatus"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
