"""Apply the deterministic source-scope guard to frozen Generator V2.2 results."""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ai"))
from app.semantic_profile_source_scope import evaluate_scoped_claim  # noqa: E402

ARTIFACTS = ROOT / "AI_Answer"
SOURCE_RESULTS = ARTIFACTS / "semantic_profile_generator_v22_fixture_results_v3.json"
RESULTS_PATH = ARTIFACTS / "semantic_profile_source_scope_guard_v1_fixture_results_v2.json"
METRICS_PATH = ARTIFACTS / "semantic_profile_source_scope_guard_v1_metrics_v2.json"


def _quote_valid(checked: dict[str, Any]) -> bool:
    quote_errors = {
        "QUOTE_MISMATCH",
        "QUOTE_EVIDENCE_MISMATCH",
        "QUOTE_SOURCE_UNRESOLVED",
        "SUPPORT_QUOTE_MISSING",
    }
    return not any(error.get("code") in quote_errors for error in checked.get("errors", []))


def evaluate() -> tuple[dict[str, Any], dict[str, Any]]:
    if RESULTS_PATH.exists() or METRICS_PATH.exists():
        raise RuntimeError("REFUSING_TO_OVERWRITE_SCOPE_GUARD_ARTIFACT")
    frozen = json.loads(SOURCE_RESULTS.read_text(encoding="utf-8"))
    if frozen.get("runVersion") != "semantic-profile-generator-v2.2-source-fixture-v1":
        raise RuntimeError("UNEXPECTED_SOURCE_ARTIFACT_VERSION")
    fixture_rows: list[dict[str, Any]] = []
    metrics: Counter[str] = Counter()
    for row in frozen["results"]:
        outcomes = row.get("claims", [])
        if len(outcomes) != 1:
            outcomes = outcomes[:1]
        if not outcomes:
            fixture_rows.append(
                {
                    "fixtureId": row["fixtureId"],
                    "restaurantId": row["restaurantId"],
                    "evidenceId": row["evidenceId"],
                    "observedEvidenceSources": [],
                    "derivedSourceScope": "UNKNOWN",
                    "rawClaimText": None,
                    "safeSearchText": None,
                    "semanticVerdict": None,
                    "atomicAssertionCount": 0,
                    "exactQuoteValid": False,
                    "semanticApproved": False,
                    "indexable": False,
                    "rejectReasons": ["NO_GENERATED_CLAIM", "UNKNOWN_SOURCE_SCOPE"],
                    "humanSafetyReview": "PASS_FAIL_CLOSED_NO_CLAIM",
                }
            )
            metrics["unknownScopeCount"] += 1
            metrics["nonIndexableCount"] += 1
            continue

        outcome = outcomes[0]
        checked = outcome.get("checked", {})
        claim = outcome.get("claim", {})
        evidence = checked.get("resolvedEvidence", [])
        sources = [str(item.get("evidenceType") or "") for item in evidence]
        assertion_count = len(outcome.get("atomicAssertions", []))
        if not assertion_count and outcome.get("rejectReasons") == ["GENERATOR_NON_ATOMIC"]:
            assertion_count = 2
        semantic_verdict = outcome.get("semanticVerdict")
        semantic_approved = semantic_verdict == "SUPPORTED"
        quote_valid = _quote_valid(checked)
        guarded = evaluate_scoped_claim(
            raw_claim_text=claim.get("claimText", ""),
            evidence_sources=sources,
            deterministic_valid=checked.get("valid") is True,
            exact_quote_valid=quote_valid,
            semantic_approved=semantic_approved,
            atomic_assertion_count=assertion_count,
        )
        human_review = (
            "PASS_SCOPED"
            if guarded["sourceScope"] == "LISTING_FACT"
            or (
                guarded["sourceScope"] == "CUSTOMER_REPORTED"
                and guarded["searchText"]
                and guarded["searchText"] != claim.get("claimText")
                and guarded["searchText"].startswith("고객 리뷰 기반 정보: ")
            )
            else "PASS_FAIL_CLOSED" if not guarded["indexable"] else "FAIL_SCOPE_NOT_PRESERVED"
        )
        fixture_rows.append(
            {
                "fixtureId": row["fixtureId"],
                "restaurantId": row["restaurantId"],
                "evidenceId": row["evidenceId"],
                "observedEvidenceSources": sources,
                "derivedSourceScope": guarded["sourceScope"],
                "rawClaimText": claim.get("claimText"),
                "safeSearchText": guarded["searchText"],
                "semanticVerdict": semantic_verdict,
                "atomicAssertionCount": assertion_count,
                "exactQuoteValid": quote_valid,
                "semanticApproved": semantic_approved,
                "indexable": guarded["indexable"],
                "indexText": guarded["indexText"],
                "rejectReasons": guarded["rejectReasons"],
                "humanSafetyReview": human_review,
                "claimType": claim.get("claimType"),
                "fixtureBoundaryPass": row.get("pass"),
            }
        )
        metrics[f"scope{guarded['sourceScope'].title().replace('_', '')}Count"] += 1
        metrics["semanticSupportedCount" if semantic_approved else "semanticRejectedCount"] += 1
        metrics["indexableCount" if guarded["indexable"] else "nonIndexableCount"] += 1
        metrics["exactQuotePassCount" if quote_valid else "quoteMismatchCount"] += 1
        metrics["nonAtomicCount"] += int(assertion_count != 1)
        metrics["verifierErrorCount"] += int(outcome.get("error") is not None)
        metrics["mixedSourceRejectedCount"] += int(
            guarded["sourceScope"] == "MIXED" and not guarded["indexable"]
        )
        metrics["unknownSourceRejectedCount"] += int(
            guarded["sourceScope"] == "UNKNOWN" and not guarded["indexable"]
        )
        if guarded["sourceScope"] == "CUSTOMER_REPORTED" and guarded["indexable"]:
            metrics["customerReportedIndexableCount"] += 1
            metrics["unscopedCustomerTextCount"] += int(
                guarded["searchText"] == claim.get("claimText")
                or not guarded["searchText"].startswith("고객 리뷰 기반 정보: ")
            )
        metrics["sourceScopeFalseAcceptanceCount"] += int(
            human_review == "FAIL_SCOPE_NOT_PRESERVED"
        )
        metrics["officialOrListingPromotionCount"] += int(
            guarded["sourceScope"] == "CUSTOMER_REPORTED"
            and claim.get("claimType") in {"FOOD_TYPE", "MENU_CHARACTERISTIC"}
            and checked.get("valid") is True
        )

    metrics["fixtureCount"] = len(frozen["results"])
    metrics["fixtureEvaluatedCount"] = len(fixture_rows)
    metrics["humanSafetyFailCount"] = sum(
        row["humanSafetyReview"] == "FAIL_SCOPE_NOT_PRESERVED" for row in fixture_rows
    )
    metrics["generatorCalls"] = 0
    metrics["atomicizerCalls"] = 0
    metrics["assertionVerifierCalls"] = 0
    metrics["retries"] = 0
    metrics["mySqlReads"] = 0
    metrics["mySqlWrites"] = 0
    metrics["qdrantReads"] = 0
    metrics["qdrantWrites"] = 0
    metrics["embeddingCalls"] = 0
    metrics["embeddingWrites"] = 0
    metrics["geminiCalls"] = 0
    result_doc = {
        "evaluationVersion": "semantic-profile-source-scope-guard-v1",
        "createdAt": datetime.now(UTC).isoformat(),
        "sourceArtifact": SOURCE_RESULTS.name,
        "sourceArtifactHash": frozen.get("fixtureHash"),
        "reusedGeneratorArtifact": True,
        "results": fixture_rows,
    }
    metric_doc = {
        "evaluationVersion": result_doc["evaluationVersion"],
        "metrics": dict(metrics),
        "scopePolicyTests": "see targeted unit tests; mixed and unknown are fail-closed",
        "sideEffects": {
            "generatorCalls": 0,
            "atomicizerCalls": 0,
            "assertionVerifierCalls": 0,
            "retries": 0,
            "mySqlReads": 0,
            "mySqlWrites": 0,
            "qdrantReads": 0,
            "qdrantWrites": 0,
            "embeddingCalls": 0,
            "embeddingWrites": 0,
            "geminiCalls": 0,
        },
    }
    return result_doc, metric_doc


def main() -> None:
    results, metrics = evaluate()
    RESULTS_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
    METRICS_PATH.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(metrics["metrics"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
