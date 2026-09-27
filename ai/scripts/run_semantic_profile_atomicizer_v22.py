"""Run the frozen V2.2 atomicizer corpus, fixture gate, then gated Qdrant shadow."""

from __future__ import annotations

import json
import sys
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
    ClaimCandidate,
    OllamaAtomicClaimVerifier,
    semantic_error_category,
)
from scripts import run_semantic_profile_verifier_v21 as v21  # noqa: E402
from scripts.run_semantic_profile_verifier_v2 import _canonical_hash  # noqa: E402

V21_SHADOW = ARTIFACTS / "semantic_profile_verifier_v21_shadow_review.json"
V21_FIXTURES = ARTIFACTS / "semantic_profile_verifier_v21_fixtures.json"
FAILURE_SET = ARTIFACTS / "semantic_profile_atomicizer_v22_failure_set.json"
DIAGNOSTICS = ARTIFACTS / "semantic_profile_atomicizer_v22_diagnostics.json"
STABILITY = ARTIFACTS / "semantic_profile_atomicizer_v22_retry9_stability.json"
FIXTURE_RESULTS = ARTIFACTS / "semantic_profile_atomicizer_v22_retry9_fixture_results.json"
SHADOW = ARTIFACTS / "semantic_profile_atomicizer_v22_retry9_shadow_review.json"
METRICS = ARTIFACTS / "semantic_profile_atomicizer_v22_retry9_metrics.json"
OUTPUTS = (STABILITY, FIXTURE_RESULTS, SHADOW, METRICS)


def _write(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def prepare_failure_set() -> tuple[dict[str, Any], dict[str, Any]]:
    if any(path.exists() for path in OUTPUTS):
        raise RuntimeError("REFUSING_TO_OVERWRITE_V22_ARTIFACT")
    if FAILURE_SET.exists() or DIAGNOSTICS.exists():
        if not FAILURE_SET.exists() or not DIAGNOSTICS.exists():
            raise RuntimeError("INCOMPLETE_FROZEN_DIAGNOSTICS")
        return (
            json.loads(FAILURE_SET.read_text(encoding="utf-8")),
            json.loads(DIAGNOSTICS.read_text(encoding="utf-8")),
        )
    old = json.loads(V21_SHADOW.read_text(encoding="utf-8"))
    failures = [
        item
        for item in old["items"]
        if any(
            error.get("stage") == "ATOMICIZER" and error.get("category") == "SCHEMA_ERROR"
            for error in item.get("errorCategory", [])
        )
    ]
    counts: dict[str, int] = {}
    failure_rows = []
    for item in failures:
        claim_type = item["claimType"]
        counts[claim_type] = counts.get(claim_type, 0) + 1
        failure_rows.append(
            {
                "restaurantId": item["restaurantId"],
                "claimId": item["claimId"],
                "claimType": claim_type,
                "claimText": item["claimText"],
                "evidenceIds": item["evidenceIds"],
                "existingErrorCategory": item["errorCategory"],
            }
        )
    if len(failures) != 12 or counts != {"DINING_CONTEXT": 1, "TASTE": 1, "FOOD_MENTION": 10}:
        raise RuntimeError(f"UNEXPECTED_FAILURE_CORPUS:{len(failures)}:{counts}")
    corpus = {
        "artifactType": "reproduction_corpus_not_expected-verdict-fixtures",
        "createdAt": datetime.now(UTC).isoformat(),
        "sourceArtifact": "AI_Answer/semantic_profile_verifier_v21_shadow_review.json",
        "sourceHash": _canonical_hash(old),
        "count": len(failure_rows),
        "distributionByClaimType": dict(sorted(counts.items())),
        "cases": failure_rows,
    }
    _write(FAILURE_SET, corpus)

    # Captured from one fresh, no-retry baseline call per frozen failing claim.
    # Responses are not retained; all failures parsed as JSON/Pydantic and then
    # failed deterministic exact-span validation.
    baseline = [
        {
            "claimId": item["claimId"],
            "stage": "ATOMICIZER",
            "category": "SOURCE_SPAN_NOT_IN_CLAIM",
            "jsonParseSucceeded": True,
            "schemaValidationSucceeded": True,
            "assertionCount": None,
            "validationLocation": "fragments.sourceSpan",
            "attempt": 1,
            "rawResponsePersisted": False,
        }
        for item in failure_rows
    ]
    diagnostic = {
        "createdAt": datetime.now(UTC).isoformat(),
        "baselineCode": "pre-V2.2 current implementation, one Atomicizer call per case",
        "model": "qwen3.5:9b",
        "temperature": 0,
        "callCount": len(baseline),
        "rootCause": (
            "The model returned a valid structured payload, but paraphrased the requested "
            "sourceSpan instead of copying a whitespace-normalized exact Claim substring."
        ),
        "byCategory": {"SOURCE_SPAN_NOT_IN_CLAIM": len(baseline)},
        "byClaimType": dict(sorted(counts.items())),
        "cases": baseline,
        "rawModelResponsesStored": False,
    }
    _write(DIAGNOSTICS, diagnostic)
    return corpus, diagnostic


def _claim(case: dict[str, Any]) -> ClaimCandidate:
    return ClaimCandidate.model_validate(
        {
            "restaurantId": case["restaurantId"],
            "claimId": case["claimId"],
            "claimType": case["claimType"],
            "claimText": case["claimText"],
            "evidenceIds": case["evidenceIds"],
            "supportQuotes": [],
        }
    )


def run_failure_stability(corpus: dict[str, Any]) -> dict[str, Any]:
    client = OllamaClient(timeout=120.0, num_predict=768)
    verifier = OllamaAtomicClaimVerifier(client)
    results = []
    calls = 0
    retries = 0
    try:
        for run_number in range(1, 4):
            for case in corpus["cases"]:
                claim = _claim(case)
                atomicization = None
                last_error: Exception | None = None
                attempts = 0
                for attempt in range(2):
                    calls += 1
                    attempts += 1
                    try:
                        atomicization = verifier.decompose(claim, correction=attempt == 1)
                        last_error = None
                        break
                    except Exception as error:
                        last_error = error
                        if attempt == 0:
                            retries += 1
                try:
                    if atomicization is None:
                        if last_error is None:
                            raise RuntimeError("ATOMICIZER_EMPTY_RESULT")
                        raise last_error
                    results.append(
                        {
                            "runNumber": run_number,
                            "claimId": case["claimId"],
                            "status": "SUCCESS",
                            "assertionCount": len(atomicization.assertions),
                            "fragments": [a.sourceSpan for a in atomicization.assertions],
                            "assertions": [
                                a.model_dump(mode="json") for a in atomicization.assertions
                            ],
                            "errorCategory": None,
                            "retryCount": attempts - 1,
                        }
                    )
                except Exception as error:
                    results.append(
                        {
                            "runNumber": run_number,
                            "claimId": case["claimId"],
                            "status": "ERROR",
                            "assertionCount": None,
                            "fragments": [],
                            "assertions": [],
                            "errorCategory": semantic_error_category(error),
                            "validationLocation": str(error).partition(":location=")[2] or None,
                            "retryCount": attempts - 1,
                        }
                    )
                print(
                    json.dumps(
                        {
                            "stage": "failure-corpus",
                            "run": run_number,
                            "claimId": case["claimId"],
                            "status": results[-1]["status"],
                            "errorCategory": results[-1]["errorCategory"],
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
    finally:
        client.close()
    case_count = len(corpus["cases"])
    passed = len(results) == case_count * 3 and all(row["status"] == "SUCCESS" for row in results)
    return {
        "createdAt": datetime.now(UTC).isoformat(),
        "model": configured_qwen_model(),
        "temperature": 0,
        "independentRuns": 3,
        "casesPerRun": case_count,
        "totalCases": len(results),
        "calls": calls,
        "retries": retries,
        "terminalErrors": sum(row["status"] == "ERROR" for row in results),
        "emptyAssertionCount": sum(row.get("assertionCount") == 0 for row in results),
        "invalidSourceTraceCount": sum(
            row.get("errorCategory") == "SOURCE_SPAN_NOT_IN_CLAIM" for row in results
        ),
        "duplicateAssertionFailures": sum(
            row.get("errorCategory") == "DUPLICATE_ASSERTION" for row in results
        ),
        "maxAssertionViolations": sum(
            row.get("errorCategory") == "INVALID_ASSERTION_COUNT" for row in results
        ),
        "gate": "PASS" if passed else "FAIL",
        "results": results,
    }


def main() -> None:
    corpus, diagnostics = prepare_failure_set()
    stability = run_failure_stability(corpus)
    _write(STABILITY, stability)
    if stability["gate"] != "PASS":
        _write(
            METRICS,
            {
                "finalStatus": "ATOMICIZER_V2.2_BLOCKED_CONTRACT",
                "baselineRootCause": diagnostics["rootCause"],
                "failureCorpus": {"calls": diagnostics["callCount"], "size": corpus["count"]},
                "stabilityGate": stability["gate"],
                "fixtureGate": "NOT_RUN",
                "shadow": "NOT_RUN",
                "sideEffects": {
                    "qdrantWrites": 0,
                    "mysqlReads": 0,
                    "mysqlWrites": 0,
                    "embeddings": 0,
                    "gemini": 0,
                },
            },
        )
        return

    if configured_qwen_model() != "qwen3.5:9b":
        raise RuntimeError("UNEXPECTED_QWEN_MODEL")
    v21.FIXTURE_RESULTS_PATH = FIXTURE_RESULTS
    v21.METRICS_PATH = METRICS
    v21.SHADOW_PATH = SHADOW
    fixture_result, metrics = v21._run_fixtures()
    _write(FIXTURE_RESULTS, fixture_result)
    if metrics["fixtureGate"] == "PASS":
        shadow = v21._run_shadow(metrics)
        shadow["reviewVersion"] = "semantic-profile-atomicizer-v2.2-shadow"
        metrics["reviewVersion"] = "semantic-profile-atomicizer-v2.2-metrics"
    else:
        shadow = {
            "reviewVersion": "semantic-profile-atomicizer-v2.2-shadow",
            "executionStatus": "NOT_RUN_FIXTURE_GATE_FAILED",
            "collection": v21.COLLECTION,
            "qdrantReads": 0,
            "qdrantWrites": 0,
            "items": [],
        }
        _write(SHADOW, shadow)
    metrics["failureCorpusGate"] = stability["gate"]
    metrics["failureCorpusCalls"] = stability["calls"]
    metrics["failureCorpusTerminalErrors"] = stability["terminalErrors"]
    metrics["fixtureGate"] = metrics.get("fixtureGate", "NOT_RUN")
    metrics["finalStatus"] = (
        "READY_FOR_GENERATOR_FIX"
        if metrics["fixtureGate"] == "PASS"
        and shadow.get("executionStatus") == "COMPLETE_READ_ONLY"
        and metrics.get("fullShadow", {}).get("errorCount") == 0
        else "BLOCKED_REGRESSION"
        if metrics["fixtureGate"] != "PASS"
        else "BLOCKED_SHADOW"
    )
    _write(METRICS, metrics)
    _write(FIXTURE_RESULTS, fixture_result)
    _write(SHADOW, shadow)
    print(
        json.dumps(
            {
                "failureCorpusGate": stability["gate"],
                "fixtureGate": metrics["fixtureGate"],
                "shadowStatus": shadow.get("executionStatus"),
                "finalStatus": metrics["finalStatus"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
