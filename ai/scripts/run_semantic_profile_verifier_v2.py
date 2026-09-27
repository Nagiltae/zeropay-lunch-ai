"""Freeze source-bound verifier fixtures or run a bounded 3x local V2 suite."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
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
from app.semantic_profile_quality_gate import (  # noqa: E402
    AssertionVerdict,
    ClaimCandidate,
    OllamaAtomicClaimVerifier,
    aggregate_assertion_verdicts,
    raw_evidence_text,
    semantic_error_category,
)

FIXTURE_PATH = ARTIFACTS / "semantic_profile_verifier_v2_fixtures.json"
RESULT_PATH = ARTIFACTS / "semantic_profile_verifier_v2_fixture_results.json"
METRICS_PATH = ARTIFACTS / "semantic_profile_verifier_v2_metrics.json"
SHADOW_PATH = ARTIFACTS / "semantic_profile_verifier_v2_shadow_review.json"


def _canonical_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _catalog(path: str, expected_hash: str) -> dict[str, Any]:
    doc = json.loads((ROOT / path).read_text(encoding="utf-8"))
    items = doc.get("items", [])
    actual_hash = _canonical_hash(items)
    if actual_hash != expected_hash or doc.get("catalogHash") != expected_hash:
        raise RuntimeError(f"FROZEN_CATALOG_HASH_MISMATCH:{path}")
    return doc


def freeze_fixtures() -> dict[str, Any]:
    if FIXTURE_PATH.exists():
        raise RuntimeError(f"REFUSING_TO_OVERWRITE:{FIXTURE_PATH.name}")
    v1_doc = json.loads(
        (ARTIFACTS / "semantic_profile_regression_fixtures.json").read_text(encoding="utf-8")
    )
    if v1_doc.get("frozenBeforeVerifierRun") is not True:
        raise RuntimeError("SOURCE_REGRESSION_FIXTURES_NOT_FROZEN")

    sources = [
        {
            "fixtureId": "positive-menu-items-9617",
            "restaurantId": 9617,
            "catalogPath": "AI_Answer/semantic_profile_v1_evidence_catalog_9617.json",
            "catalogHash": "f02c59ad6d64b1b04da1b854875e65cab2ae1e85c128e68b36fd7b4cb77df64a",
            "claimId": "positive:9617:food-type:menu-items",
            "claimType": "FOOD_TYPE",
            "claimText": "메뉴에 마성김밥과 마성떡볶이가 기재되어 있다.",
            "evidenceIds": ["E003", "E011"],
            "supportQuotes": [
                {"evidenceId": "E003", "quote": "마성김밥"},
                {"evidenceId": "E011", "quote": "마성떡볶이"},
            ],
            "expectedFinalVerdict": "SUPPORTED",
            "expectedIndexable": True,
            "polarity": "positive",
        },
        {
            "fixtureId": "positive-solo-and-quick-meal-context-9617",
            "restaurantId": 9617,
            "catalogPath": "AI_Answer/semantic_profile_v1_evidence_catalog_9617.json",
            "catalogHash": "f02c59ad6d64b1b04da1b854875e65cab2ae1e85c128e68b36fd7b4cb77df64a",
            "claimId": "positive:9617:dining-context:solo-quick",
            "claimType": "DINING_CONTEXT",
            "claimText": "혼자 식사하기 좋고 빠른 식사가 가능하다는 이용 맥락이 확인된다.",
            "evidenceIds": ["E023", "E058"],
            "supportQuotes": [
                {
                    "evidenceId": "E023",
                    "quote": '"혼밥하기 좋아요" 이 키워드를 선택한 인원',
                },
                {
                    "evidenceId": "E058",
                    "quote": "빠르게 식사가 필요할 때 들리기에 좋은 것 같아요.",
                },
            ],
            "expectedFinalVerdict": "SUPPORTED",
            "expectedIndexable": True,
            "polarity": "positive",
        },
        {
            "fixtureId": "positive-friendly-review-keyword-9617",
            "restaurantId": 9617,
            "catalogPath": "AI_Answer/semantic_profile_v1_evidence_catalog_9617.json",
            "catalogHash": "f02c59ad6d64b1b04da1b854875e65cab2ae1e85c128e68b36fd7b4cb77df64a",
            "claimId": "positive:9617:taste:friendly-review",
            "claimType": "TASTE",
            "claimText": "고객 keyword에서 친절하다는 평가가 확인된다.",
            "evidenceIds": ["E026"],
            "supportQuotes": [
                {
                    "evidenceId": "E026",
                    "quote": '"친절해요" 이 키워드를 선택한 인원',
                }
            ],
            "expectedFinalVerdict": "SUPPORTED",
            "expectedIndexable": True,
            "polarity": "positive",
        },
    ]

    fixtures = []
    for source in [*v1_doc["fixtures"], *sources]:
        catalog = _catalog(source["catalogPath"], source["catalogHash"])
        by_id = {str(item.get("evidenceId")): item for item in catalog.get("items", [])}
        snapshots = []
        for evidence_id in source["evidenceIds"]:
            item = by_id.get(evidence_id)
            if not item:
                raise RuntimeError(f"FROZEN_EVIDENCE_MISSING:{source['fixtureId']}:{evidence_id}")
            snapshot = {
                "restaurantId": source["restaurantId"],
                "evidenceId": evidence_id,
                "evidenceType": item.get("evidenceType"),
                "sourceField": item.get("sourceField"),
                "status": item.get("status"),
                "rawText": raw_evidence_text(item),
                "rawEvidence": item.get("content"),
            }
            snapshots.append(snapshot)
        quote_map = {q["evidenceId"]: q["quote"] for q in source.get("supportQuotes", [])}
        if set(quote_map) != set(source["evidenceIds"]):
            raise RuntimeError(f"FIXTURE_QUOTE_IDS_MISMATCH:{source['fixtureId']}")
        for snapshot in snapshots:
            quote = quote_map[snapshot["evidenceId"]]
            if " ".join(quote.split()) not in " ".join(snapshot["rawText"].split()):
                raise RuntimeError(f"FIXTURE_QUOTE_NOT_EXACT:{source['fixtureId']}")
        fixture = {
            **source,
            "supportQuotes": [
                {"evidenceId": q["evidenceId"], "quote": q["quote"]}
                for q in source.get("supportQuotes", [])
            ],
            "evidenceSnapshot": snapshots,
            "evidenceSnapshotHash": _canonical_hash(snapshots),
        }
        if "expectedFinalVerdict" not in fixture:
            fixture["expectedFinalVerdict"] = (
                "UNSUPPORTED"
                if fixture["fixtureId"]
                in {
                    "taste-deliciousness-does-not-entail-tenderness-9559",
                    "group-gathering-does-not-entail-corporate-or-family-events-9559",
                }
                else "PARTIAL"
            )
            fixture["expectedIndexable"] = False
            fixture["polarity"] = "negative"
        fixtures.append(fixture)

    document = {
        "fixtureVersion": "semantic-profile-verifier-v2-frozen-1",
        "createdAt": datetime.now(UTC).isoformat(),
        "frozenBeforeVerifierRuns": True,
        "model": "qwen3.5:9b",
        "runsRequired": 3,
        "maxAssertions": 8,
        "retryPolicy": "initial + at most one retry after an atomicizer/verifier call error",
        "source": (
            "Four preserved v1 regressions plus three source-verified v12 positive cases; "
            "Evidence snapshots and catalog hashes included."
        ),
        "fixtures": fixtures,
    }
    FIXTURE_PATH.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n")
    return {"path": str(FIXTURE_PATH), "fixtureCount": len(fixtures)}


def _call_with_one_retry(
    operation: Callable[[], Any],
    stats: dict[str, int],
    stage: str,
    retry_operation: Callable[[], Any] | None = None,
) -> tuple[Any | None, str | None]:
    for attempt in range(2):
        stats["modelCalls"] += 1
        stats[f"{stage}Calls"] += 1
        try:
            retry = attempt == 1 and retry_operation is not None
            return (retry_operation() if retry else operation()), None
        except Exception as error:  # never persist raw output/provider bodies
            category = semantic_error_category(error)
            error_key = f"error:{category}"
            stats[error_key] = stats.get(error_key, 0) + 1
            stats["retries"] += int(attempt == 0)
            if attempt == 1:
                return None, category
    return None, "UNKNOWN_ERROR"


def _run_frozen_suite() -> tuple[dict[str, Any], dict[str, Any]]:
    for path in (RESULT_PATH, METRICS_PATH, SHADOW_PATH):
        if path.exists():
            raise RuntimeError(f"REFUSING_TO_OVERWRITE:{path.name}")
    fixture_doc = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    if fixture_doc.get("frozenBeforeVerifierRuns") is not True:
        raise RuntimeError("FIXTURES_NOT_FROZEN")
    model = configured_qwen_model()
    if model != "qwen3.5:9b":
        raise RuntimeError("UNEXPECTED_QWEN_MODEL")
    client = OllamaClient(timeout=120.0, num_predict=768)
    verifier = OllamaAtomicClaimVerifier(client)
    results = []
    stats: dict[str, int] = {
        "modelCalls": 0,
        "retries": 0,
        "atomicizerCalls": 0,
        "assertionVerifierCalls": 0,
    }
    started = time.monotonic()

    try:
        for run_number in range(1, 4):
            for fixture in fixture_doc["fixtures"]:
                claim = ClaimCandidate.model_validate(
                    {
                        "restaurantId": fixture["restaurantId"],
                        "claimId": fixture["claimId"],
                        "claimType": fixture["claimType"],
                        "claimText": fixture["claimText"],
                        "evidenceIds": fixture["evidenceIds"],
                        "supportQuotes": fixture["supportQuotes"],
                    }
                )
                snapshots = fixture["evidenceSnapshot"]
                if _canonical_hash(snapshots) != fixture["evidenceSnapshotHash"]:
                    raise RuntimeError("FIXTURE_EVIDENCE_SNAPSHOT_HASH_MISMATCH")
                fixture_started = time.monotonic()
                retries_before = stats["retries"]
                atomicization, atomic_error = _call_with_one_retry(
                    lambda claim=claim: verifier.decompose(claim), stats, "atomicizer"
                )
                assertion_rows = []
                final_verdict = "VERIFIER_ERROR"
                errors = []
                if atomic_error:
                    errors.append({"stage": "ATOMICIZER", "category": atomic_error})
                else:
                    assertion_results: list[AssertionVerdict] = []
                    for assertion in atomicization.assertions:
                        assertion_result, assertion_error = _call_with_one_retry(
                            lambda assertion=assertion, claim=claim, snapshots=snapshots: (
                                verifier.verify_assertion(claim.claimType, assertion, snapshots)
                            ),
                            stats,
                            "assertionVerifier",
                        )
                        if assertion_error:
                            errors.append(
                                {
                                    "stage": "ASSERTION_VERIFIER",
                                    "assertionId": assertion.assertionId,
                                    "category": assertion_error,
                                }
                            )
                            break
                        assertion_results.append(assertion_result)
                        assertion_rows.append(
                            {
                                **assertion.model_dump(mode="json"),
                                "verdict": assertion_result.verdict,
                                "evidenceIds": assertion_result.evidenceIds,
                            }
                        )
                    if not errors:
                        try:
                            final_verdict = aggregate_assertion_verdicts(
                                atomicization.assertions, assertion_results
                            )
                        except ValueError:
                            errors.append({"stage": "AGGREGATOR", "category": "UNKNOWN_ERROR"})

                semantic_pass = final_verdict == fixture["expectedFinalVerdict"]
                indexable = bool(semantic_pass and fixture["expectedIndexable"] and not errors)
                result = {
                    "runNumber": run_number,
                    "fixtureId": fixture["fixtureId"],
                    "atomicAssertions": assertion_rows,
                    "atomicizerStatus": "ERROR" if atomic_error else "SUCCESS",
                    "assertionVerdicts": [item["verdict"] for item in assertion_rows],
                    "finalVerdict": final_verdict,
                    "expectedFinalVerdict": fixture["expectedFinalVerdict"],
                    "expectedIndexable": fixture["expectedIndexable"],
                    "indexableUnderContract": indexable,
                    "pass": semantic_pass and not errors,
                    "latencySeconds": round(time.monotonic() - fixture_started, 3),
                    "retryCount": stats["retries"] - retries_before,
                    "errors": errors,
                }
                results.append(result)
                print(
                    json.dumps(
                        {
                            "run": run_number,
                            "fixture": fixture["fixtureId"],
                            "verdict": final_verdict,
                            "pass": result["pass"],
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
    finally:
        client.close()

    fixture_count = len(fixture_doc["fixtures"])
    negatives = [f for f in fixture_doc["fixtures"] if f["polarity"] == "negative"]
    positives = [f for f in fixture_doc["fixtures"] if f["polarity"] == "positive"]
    by_id = {f["fixtureId"]: f for f in fixture_doc["fixtures"]}
    false_acceptances = sum(
        result["finalVerdict"] == "SUPPORTED"
        and by_id[result["fixtureId"]]["polarity"] == "negative"
        for result in results
    )
    metrics = {
        "fixtureCount": fixture_count,
        "fixtureRuns": 3,
        "negativeFixtureCount": len(negatives),
        "positiveFixtureCount": len(positives),
        "falseAcceptanceCount": false_acceptances,
        "positiveFalseRejectionCount": sum(
            result["finalVerdict"] != "SUPPORTED"
            for result in results
            if by_id[result["fixtureId"]]["polarity"] == "positive"
        ),
        "partialExpectedCount": sum(
            f["expectedFinalVerdict"] == "PARTIAL" for f in fixture_doc["fixtures"]
        )
        * 3,
        "partialCorrectCount": sum(
            result["finalVerdict"] == "PARTIAL"
            for result in results
            if by_id[result["fixtureId"]]["expectedFinalVerdict"] == "PARTIAL"
        ),
        "atomicizerErrorCount": sum(
            any(error["stage"] == "ATOMICIZER" for error in result["errors"]) for result in results
        ),
        "verifierErrorCount": sum(bool(result["errors"]) for result in results),
        "model": model,
        "temperature": 0,
        "retryPolicy": fixture_doc["retryPolicy"],
        "atomicizerCalls": stats["atomicizerCalls"],
        "verifierCalls": stats["assertionVerifierCalls"],
        "actualModelCalls": stats["modelCalls"],
        "retries": stats["retries"],
        "errorCategories": {
            key.removeprefix("error:"): value
            for key, value in stats.items()
            if key.startswith("error:")
        },
        "elapsedSeconds": round(time.monotonic() - started, 3),
        "sideEffects": {
            "mysqlReads": 0,
            "mysqlWrites": 0,
            "qdrantReads": 0,
            "qdrantWrites": 0,
            "embeddingCalls": 0,
            "geminiCalls": 0,
            "localQwenCalls": stats["modelCalls"],
        },
    }
    per_fixture = {}
    for fixture in fixture_doc["fixtures"]:
        rows = [r for r in results if r["fixtureId"] == fixture["fixtureId"]]
        per_fixture[fixture["fixtureId"]] = {
            "expected": fixture["expectedFinalVerdict"],
            "observed": [row["finalVerdict"] for row in rows],
            "allThreePass": len(rows) == 3 and all(row["pass"] for row in rows),
        }
    metrics["perFixture"] = per_fixture
    document = {
        "reviewVersion": "semantic-profile-verifier-v2-fixture-suite-v1",
        "createdAt": datetime.now(UTC).isoformat(),
        "fixturesPath": str(FIXTURE_PATH.relative_to(ROOT)),
        "fixtureSnapshotHash": _canonical_hash(fixture_doc),
        "results": results,
    }
    return document, metrics


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze-fixtures", action="store_true")
    args = parser.parse_args()
    if args.freeze_fixtures:
        print(json.dumps(freeze_fixtures(), ensure_ascii=False, indent=2))
        return
    document, metrics = _run_frozen_suite()
    RESULT_PATH.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n")
    METRICS_PATH.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
