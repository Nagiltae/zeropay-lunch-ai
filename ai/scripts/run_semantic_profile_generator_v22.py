"""Bounded V2.2 source-semantics fixture and 3-Restaurant DRY-RUN."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter
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
from app.semantic_profile_source_scope import evaluate_scoped_claim  # noqa: E402
from scripts.run_semantic_profile_generator_v21 import _prompt_evidence  # noqa: E402

ARTIFACTS = ROOT / "AI_Answer"
FIXTURE_PATH = ARTIFACTS / "semantic_profile_generator_v22_source_fixtures.json"
FIXTURE_RESULTS_PATH = ARTIFACTS / "semantic_profile_generator_v22_fixture_results.json"
COHORT_PATH = ARTIFACTS / "semantic_profile_generator_v22_cohort.json"
RUN_PATH = ARTIFACTS / "semantic_profile_generator_v22_run1.json"
METRICS_PATH = ARTIFACTS / "semantic_profile_generator_v22_metrics.json"
FIXTURE_V2_PATH = ARTIFACTS / "semantic_profile_generator_v22_source_fixtures_v2.json"
FIXTURE_V2_RESULTS_PATH = ARTIFACTS / "semantic_profile_generator_v22_fixture_results_v2.json"
METRICS_V2_PATH = ARTIFACTS / "semantic_profile_generator_v22_metrics_v2.json"
FIXTURE_V3_PATH = ARTIFACTS / "semantic_profile_generator_v22_source_fixtures_v3.json"
FIXTURE_V3_RESULTS_PATH = ARTIFACTS / "semantic_profile_generator_v22_fixture_results_v3.json"
METRICS_V3_PATH = ARTIFACTS / "semantic_profile_generator_v22_metrics_v3.json"
COHORT_IDS = (9568, 9569, 10042)
FIXTURE_SPECS = (
    (
        "menu-9568-1",
        9568,
        "E003",
        "MENU",
        ["listed menu item"],
        ["customer opinion as official fact"],
    ),
    (
        "menu-9569-1",
        9569,
        "E003",
        "MENU",
        ["listed menu item"],
        ["customer opinion as official fact"],
    ),
    (
        "menu-10042-1",
        10042,
        "E004",
        "MENU",
        ["listed menu item"],
        ["customer opinion as official fact"],
    ),
    (
        "keyword-food-mention",
        9569,
        "E023",
        "REVIEW_KEYWORD",
        ["customer review mentions a food term"],
        ["official sale or representative menu"],
    ),
    (
        "keyword-solo-9568",
        9568,
        "E029",
        "REVIEW_KEYWORD",
        ["customer evaluation of dining context"],
        ["official restaurant classification"],
    ),
    (
        "keyword-service-9568",
        9568,
        "E026",
        "REVIEW_KEYWORD",
        ["customer evaluation"],
        ["official service policy or training level"],
    ),
    (
        "keyword-solo-10042",
        10042,
        "E075",
        "REVIEW_KEYWORD",
        ["customer evaluation of dining context"],
        ["official restaurant classification"],
    ),
    (
        "review-food-experience",
        9569,
        "E049",
        "REVIEW",
        ["customer food experience or evaluation"],
        ["official menu status beyond the review"],
    ),
    (
        "review-venue-context",
        9569,
        "E050",
        "REVIEW",
        ["customer-described venue or dining experience"],
        ["unmentioned facility or policy"],
    ),
    (
        "review-taste-9568",
        9568,
        "E059",
        "REVIEW",
        ["customer taste evaluation"],
        ["texture or preparation facts not stated"],
    ),
    (
        "review-quick-meal",
        10042,
        "E109",
        "REVIEW",
        ["customer-reported quick service or meal experience"],
        ["guaranteed service speed or official policy"],
    ),
)


def _hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def _write_new(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        raise RuntimeError(f"REFUSING_TO_OVERWRITE:{path.name}")
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _live(rid: int) -> tuple[dict[str, Any], dict[str, Any]]:
    profile = build_compact_input(build_input(rid))
    catalog = build_evidence_catalog(profile)
    if profile.get("quality", {}).get("strictProfileReady") is not True:
        raise RuntimeError(f"NOT_PROFILE_READY:{rid}")
    if profile["inputHash"] != catalog["inputHash"]:
        raise RuntimeError(f"INPUT_CATALOG_HASH_MISMATCH:{rid}")
    return profile, catalog


def freeze() -> None:
    if FIXTURE_PATH.exists() or COHORT_PATH.exists():
        raise RuntimeError("REFUSING_TO_OVERWRITE_V22_FREEZE_ARTIFACT")
    live: dict[int, tuple[dict[str, Any], dict[str, Any]]] = {}
    prior = json.loads(
        (ARTIFACTS / "semantic_profile_generator_v21_cohort.json").read_text(encoding="utf-8")
    )
    prior_by_id = {row["restaurantId"]: row for row in prior["restaurants"]}
    cohort_rows = []
    for ordinal, rid in enumerate(COHORT_IDS, start=1):
        profile, catalog = _live(rid)
        previous = prior_by_id.get(rid)
        if (
            previous is None
            or profile["inputHash"] != previous["inputHash"]
            or catalog["catalogHash"] != previous["catalogHash"]
        ):
            raise RuntimeError(f"V21_FROZEN_SOURCE_DRIFT:{rid}")
        live[rid] = (profile, catalog)
        counts = Counter(item["evidenceType"] for item in catalog["items"])
        cohort_rows.append(
            {
                "ordinal": ordinal,
                "restaurantId": rid,
                "name": profile["identity"].get("restaurantName"),
                "selectionReason": (
                    "Selected before V2.2 generation from the existing frozen 8-Restaurant "
                    "cohort; has successful MENU, REVIEW_KEYWORD and REVIEW evidence."
                ),
                "profileReady": profile["quality"],
                "inputHash": profile["inputHash"],
                "catalogHash": catalog["catalogHash"],
                "sourceEvidenceCounts": dict(sorted(counts.items())),
            }
        )
        print(f"[V2.2 Freeze] restaurant {ordinal}/3 id={rid} ready=true", flush=True)

    fixtures = []
    for fixture_id, rid, evidence_id, source_type, may, must_not in FIXTURE_SPECS:
        profile, catalog = live[rid]
        evidence = next(
            (item for item in catalog["items"] if item["evidenceId"] == evidence_id), None
        )
        expected_type = {"MENU": "menu", "REVIEW_KEYWORD": "keyword", "REVIEW": "review"}[
            source_type
        ]
        if (
            evidence is None
            or evidence["status"] != "SUCCESS"
            or evidence["evidenceType"] != expected_type
        ):
            raise RuntimeError(f"FIXTURE_SOURCE_INVALID:{fixture_id}")
        fixtures.append(
            {
                "fixtureId": fixture_id,
                "restaurantId": rid,
                "sourceType": source_type,
                "evidenceId": evidence_id,
                "rawEvidence": evidence,
                "resolvedRawText": canonical_evidence(catalog, rid)[evidence_id]["rawText"],
                "inputHash": profile["inputHash"],
                "catalogHash": catalog["catalogHash"],
                "rawEvidenceHash": _hash(evidence),
                "semanticBoundary": {"mayExpress": may, "mustNotExpress": must_not},
            }
        )
    fixture_doc = {
        "fixtureVersion": "semantic-profile-generator-v2.2-source-contract-v1",
        "createdAt": datetime.now(UTC).isoformat(),
        "frozenBeforeGeneratorCalls": True,
        "caseCount": len(fixtures),
        "sourceCounts": dict(Counter(row["sourceType"] for row in fixtures)),
        "fixtures": fixtures,
        "databaseWrites": 0,
    }
    cohort_doc = {
        "cohortVersion": "semantic-profile-generator-v2.2-cohort-v1",
        "createdAt": fixture_doc["createdAt"],
        "frozenBeforeGeneratorCalls": True,
        "restaurantIds": list(COHORT_IDS),
        "restaurants": cohort_rows,
        "mysqlSelectQueryCount": len(COHORT_IDS) * 8,
        "databaseWrites": 0,
    }
    _write_new(FIXTURE_PATH, fixture_doc)
    _write_new(COHORT_PATH, cohort_doc)
    print(
        f"[V2.2 Freeze] frozen {len(fixtures)} source fixtures and cohort {COHORT_IDS}", flush=True
    )


def _candidate(rid: int, claim: dict[str, Any]) -> ClaimCandidate:
    return ClaimCandidate.model_validate(
        {
            "restaurantId": rid,
            "claimId": claim["claimId"],
            "claimType": claim["claimType"],
            "claimText": claim["claimText"],
            "evidenceIds": claim["evidenceIds"],
            "supportQuotes": claim["supportQuotes"],
        }
    )


def _quality(
    checked: dict[str, Any], verifier: OllamaAtomicClaimVerifier, stats: Counter[str]
) -> dict[str, Any]:
    def scoped(outcome: dict[str, Any], assertion_count: int) -> dict[str, Any]:
        claim_row = checked.get("claim", {})
        resolved = checked.get("resolvedEvidence", [])
        quote_errors = {
            "QUOTE_MISMATCH",
            "QUOTE_EVIDENCE_MISMATCH",
            "QUOTE_SOURCE_UNRESOLVED",
            "SUPPORT_QUOTE_MISSING",
        }
        scope = evaluate_scoped_claim(
            raw_claim_text=claim_row.get("claimText", ""),
            evidence_sources=[str(item.get("evidenceType") or "") for item in resolved],
            deterministic_valid=checked.get("valid") is True,
            exact_quote_valid=not any(
                error.get("code") in quote_errors for error in checked.get("errors", [])
            ),
            semantic_approved=outcome.get("semanticVerdict") == "SUPPORTED",
            atomic_assertion_count=assertion_count,
        )
        outcome.update(scope)
        return outcome

    claim = checked["claim"]
    if not checked["valid"]:
        return scoped({
            "checked": checked,
            "approved": False,
            "rejectReasons": sorted({e["code"] for e in checked["errors"]}),
        }, 0)
    result = None
    error_category = None
    atomicization = None
    for attempt in range(2):
        stats["atomicizerCalls"] += 1
        try:
            atomicization = verifier.decompose(
                _candidate(claim["restaurantId"], claim), correction=bool(attempt)
            )
            break
        except Exception as error:  # noqa: BLE001 - bounded model boundary
            stats["retries"] += int(attempt == 0)
            if attempt:
                error_category = semantic_error_category(error)
    if atomicization is None:
        stats["verifierErrorCount"] += 1
        return scoped({
            "checked": checked,
            "approved": False,
            "error": error_category,
            "rejectReasons": ["ATOMICIZER_ERROR"],
        }, 0)
    assertion_rows = [item.model_dump(mode="json") for item in atomicization.assertions]
    if atomicity_rejection(len(atomicization.assertions)):
        stats["nonAtomicCount"] += 1
        return scoped({
            "checked": checked,
            "atomicAssertions": assertion_rows,
            "approved": False,
            "rejectReasons": ["GENERATOR_NON_ATOMIC"],
        }, len(atomicization.assertions))
    assertion = atomicization.assertions[0]
    for attempt in range(2):
        stats["assertionVerifierCalls"] += 1
        try:
            result = verifier.verify_assertion(
                claim["claimType"], assertion, checked["resolvedEvidence"]
            )
            break
        except Exception as error:  # noqa: BLE001 - bounded model boundary
            stats["retries"] += int(attempt == 0)
            if attempt:
                error_category = semantic_error_category(error)
    if result is None:
        stats["verifierErrorCount"] += 1
        return scoped({
            "checked": checked,
            "atomicAssertions": assertion_rows,
            "approved": False,
            "error": error_category,
            "rejectReasons": ["VERIFIER_ERROR"],
        }, len(atomicization.assertions))
    verdict = aggregate_assertion_verdicts(atomicization.assertions, [result])
    assertion_rows[0] |= {"verdict": result.verdict, "supportingEvidenceIds": result.evidenceIds}
    return scoped({
        "checked": checked,
        "atomicAssertions": assertion_rows,
        "semanticVerdict": verdict,
        "approved": verdict == "SUPPORTED",
        "rejectReasons": [] if verdict == "SUPPORTED" else [verdict],
    }, len(atomicization.assertions))


def _one_call(
    client: OllamaClient, rid: int, rows: list[dict[str, Any]], max_claims: int
) -> dict[str, Any]:
    prompt_rows = [
        {key: value for key, value in row.items() if key != "catalogItem"} for row in rows
    ]
    return validate_generator_output(
        client.complete(
            "/no_think\n당신은 source 의미 경계를 지키는 한국어 Claim 생성기입니다.",
            generator_prompt(
                {},
                prompt_rows,
                max_claims=max_claims,
                korean=True,
                source_contract_v22=True,
            ),
            generator_schema(max_claims=max_claims),
        ),
        restaurant_id=rid,
        catalog={"items": [row["catalogItem"] for row in rows if "catalogItem" in row]},
    )


def run_fixtures() -> None:
    if FIXTURE_RESULTS_PATH.exists():
        raise RuntimeError("REFUSING_TO_OVERWRITE:fixture_results")
    if not FIXTURE_PATH.exists() or not COHORT_PATH.exists():
        raise RuntimeError("FREEZE_REQUIRED")
    fixtures_doc = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    if fixtures_doc.get("frozenBeforeGeneratorCalls") is not True:
        raise RuntimeError("FIXTURE_NOT_FROZEN")
    client = OllamaClient(timeout=180.0, num_predict=2048)
    verifier = OllamaAtomicClaimVerifier(client)
    stats: Counter[str] = Counter()
    results = []
    started = time.monotonic()
    try:
        for index, fixture in enumerate(fixtures_doc["fixtures"], start=1):
            item = fixture["rawEvidence"]
            evidence = canonical_evidence({"items": [item]}, fixture["restaurantId"])[
                fixture["evidenceId"]
            ]
            prompt_row = {
                "evidenceId": fixture["evidenceId"],
                "sourceType": fixture["sourceType"],
                "rawText": evidence["rawText"],
                "catalogItem": item,
            }
            stats["generatorCalls"] += 1
            try:
                validation = _one_call(client, fixture["restaurantId"], [prompt_row], 1)
                generator_error = None
            except Exception as error:  # noqa: BLE001 - model boundary
                generator_error = semantic_error_category(error)
                validation = {
                    "schemaValid": False,
                    "errors": [{"code": "GENERATOR_ERROR", "category": generator_error}],
                    "claims": [],
                }
            checked_results = []
            for checked in validation.get("claims", []):
                stats["generatedClaimCount"] += 1
                outcome = _quality(checked, verifier, stats)
                claim = checked["claim"]
                observed_types = {
                    evidence["evidenceType"] for evidence in checked["resolvedEvidence"]
                }
                if not checked["valid"]:
                    stats["sourceTypeMismatchCount"] += sum(
                        e["code"] == "EVIDENCE_SOURCE_TYPE_NOT_ALLOWED" for e in checked["errors"]
                    )
                    stats["quoteMismatchCount"] += sum(
                        e["code"] == "QUOTE_MISMATCH" for e in checked["errors"]
                    )
                    stats["unknownEvidenceCount"] += sum(
                        e["code"] == "UNKNOWN_EVIDENCE" for e in checked["errors"]
                    )
                    stats["provenanceLeakCount"] += sum(
                        e["code"] == "PROVENANCE_TEXT_IN_CLAIM" for e in checked["errors"]
                    )
                if outcome.get("approved"):
                    stats[f"approvedSource:{fixture['sourceType'].lower()}"] += 1
                    stats[f"approvedClaimType:{claim['claimType']}"] += 1
                outcome["claim"] = claim
                outcome["observedSourceTypes"] = sorted(observed_types)
                checked_results.append(outcome)
            fixture_pass = (
                validation.get("schemaValid") is True
                and len(checked_results) == 1
                and checked_results[0].get("approved") is True
                and checked_results[0]["claim"]["claimType"]
                in fixture.get("allowedClaimTypes", [])
            )
            if checked_results and checked_results[0]["claim"]["claimType"] not in fixture.get(
                "allowedClaimTypes", []
            ):
                checked_results[0]["rejectReasons"].append("FIXTURE_CLAIM_TYPE_MISMATCH")
            stats["fixturePassCount"] += int(fixture_pass)
            stats["fixtureFailCount"] += int(not fixture_pass)
            results.append(
                {
                    "fixtureId": fixture["fixtureId"],
                    "restaurantId": fixture["restaurantId"],
                    "sourceType": fixture["sourceType"],
                    "evidenceId": fixture["evidenceId"],
                    "semanticBoundary": fixture["semanticBoundary"],
                    "generatorError": generator_error,
                    "schemaErrors": validation.get("errors", []),
                    "claims": checked_results,
                    "pass": fixture_pass,
                }
            )
            print(
                f"[Source Fixture] case {index}/{len(fixtures_doc['fixtures'])} "
                f"source={fixture['sourceType']} result={'PASS' if fixture_pass else 'FAIL'} "
                f"elapsed={time.monotonic() - started:.1f}s",
                flush=True,
            )
    finally:
        client.close()
    stats["fixtureCount"] = len(results)
    stats["officialFactPromotionCount"] = None  # set only after human semantic review
    doc = {
        "runVersion": "semantic-profile-generator-v2.2-source-fixture-v1",
        "createdAt": datetime.now(UTC).isoformat(),
        "model": configured_qwen_model(),
        "temperature": 0,
        "fixtureHash": _hash(fixtures_doc),
        "results": results,
        "metrics": {
            **dict(stats),
            "elapsedSeconds": round(time.monotonic() - started, 3),
            "sideEffects": {
                "mysqlWrites": 0,
                "qdrantReads": 0,
                "qdrantWrites": 0,
                "embeddingCalls": 0,
                "embeddingWrites": 0,
                "geminiCalls": 0,
            },
        },
    }
    doc["status"] = "PASS_PENDING_HUMAN_SOURCE_REVIEW" if stats["fixtureFailCount"] == 0 else "FAIL"
    _write_new(FIXTURE_RESULTS_PATH, doc)
    _write_new(
        METRICS_PATH,
        {"fixtureMetrics": doc["metrics"], "restaurantMetrics": None, "humanReview": "PENDING"},
    )


def freeze_fixtures_v2() -> None:
    """Freeze source-semantic ClaimType boundaries without changing source snapshots."""
    if FIXTURE_V2_PATH.exists():
        raise RuntimeError("REFUSING_TO_OVERWRITE:fixture_v2")
    original = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    allowed_types = {
        "menu-9568-1": ["FOOD_TYPE", "MENU_CHARACTERISTIC"],
        "menu-9569-1": ["FOOD_TYPE", "MENU_CHARACTERISTIC"],
        "menu-10042-1": ["FOOD_TYPE", "MENU_CHARACTERISTIC"],
        "keyword-food-mention": ["FOOD_MENTION"],
        "keyword-solo-9568": ["DINING_CONTEXT"],
        "keyword-service-9568": ["VENUE_CHARACTERISTIC"],
        "keyword-solo-10042": ["DINING_CONTEXT"],
        "review-food-experience": ["TASTE"],
        "review-venue-context": ["VENUE_CHARACTERISTIC"],
        "review-taste-9568": ["TASTE"],
        "review-quick-meal": ["DINING_CONTEXT"],
    }
    for fixture in original["fixtures"]:
        fixture["allowedClaimTypes"] = allowed_types[fixture["fixtureId"]]
        fixture["expectationBasis"] = (
            "Frozen from source type and the existing documented ClaimType meanings, before "
            "the v2 fixture generator run; this is an evaluation boundary, not runtime logic."
        )
    doc = {
        **original,
        "fixtureVersion": "semantic-profile-generator-v2.2-source-contract-v2",
        "supersedesForEvaluation": original["fixtureVersion"],
        "frozenBeforeGeneratorCalls": True,
        "createdAt": datetime.now(UTC).isoformat(),
        "claimTypeBoundaryPolicy": "source semantics + existing ClaimType definitions",
        "fixtureHashV1": _hash(original),
    }
    _write_new(FIXTURE_V2_PATH, doc)
    print(
        f"[Source Fixture V2 Freeze] {len(doc['fixtures'])} cases frozen before model calls",
        flush=True,
    )


def run_fixtures_v2() -> None:
    if FIXTURE_V2_RESULTS_PATH.exists() or METRICS_V2_PATH.exists():
        raise RuntimeError("REFUSING_TO_OVERWRITE:fixture_v2_results")
    original_path = FIXTURE_PATH
    original_results_path = FIXTURE_RESULTS_PATH
    original_metrics_path = METRICS_PATH
    try:
        globals()["FIXTURE_PATH"] = FIXTURE_V2_PATH
        globals()["FIXTURE_RESULTS_PATH"] = FIXTURE_V2_RESULTS_PATH
        globals()["METRICS_PATH"] = METRICS_V2_PATH
        run_fixtures()
    finally:
        globals()["FIXTURE_PATH"] = original_path
        globals()["FIXTURE_RESULTS_PATH"] = original_results_path
        globals()["METRICS_PATH"] = original_metrics_path


def freeze_fixtures_v3() -> None:
    if FIXTURE_V3_PATH.exists():
        raise RuntimeError("REFUSING_TO_OVERWRITE:fixture_v3")
    previous = json.loads(FIXTURE_V2_PATH.read_text(encoding="utf-8"))
    doc = {
        **previous,
        "fixtureVersion": "semantic-profile-generator-v2.2-source-contract-v3",
        "supersedesForEvaluation": previous["fixtureVersion"],
        "createdAt": datetime.now(UTC).isoformat(),
        "frozenBeforeGeneratorCalls": True,
        "fixtureHashPrevious": _hash(previous),
        "promptPolicyRevision": (
            "Preserve explicit review evaluation under its existing ClaimType and keep "
            "independently verifiable propositions separate."
        ),
    }
    _write_new(FIXTURE_V3_PATH, doc)
    print(
        f"[Source Fixture V3 Freeze] {len(doc['fixtures'])} cases frozen before model calls",
        flush=True,
    )


def run_fixtures_v3() -> None:
    if FIXTURE_V3_RESULTS_PATH.exists() or METRICS_V3_PATH.exists():
        raise RuntimeError("REFUSING_TO_OVERWRITE:fixture_v3_results")
    original_path = FIXTURE_PATH
    original_results_path = FIXTURE_RESULTS_PATH
    original_metrics_path = METRICS_PATH
    try:
        globals()["FIXTURE_PATH"] = FIXTURE_V3_PATH
        globals()["FIXTURE_RESULTS_PATH"] = FIXTURE_V3_RESULTS_PATH
        globals()["METRICS_PATH"] = METRICS_V3_PATH
        run_fixtures()
    finally:
        globals()["FIXTURE_PATH"] = original_path
        globals()["FIXTURE_RESULTS_PATH"] = original_results_path
        globals()["METRICS_PATH"] = original_metrics_path


def freeze_cohort() -> None:
    if not FIXTURE_RESULTS_PATH.exists():
        raise RuntimeError("FIXTURE_RUN_REQUIRED")
    fixture_results = json.loads(FIXTURE_RESULTS_PATH.read_text(encoding="utf-8"))
    if fixture_results.get("status") != "PASS_PENDING_HUMAN_SOURCE_REVIEW":
        raise RuntimeError("FIXTURE_GATE_FAILED")
    cohort = json.loads(COHORT_PATH.read_text(encoding="utf-8"))
    # The cohort was frozen before the fixture calls; this command is a gate acknowledgement.
    if cohort.get("frozenBeforeGeneratorCalls") is not True:
        raise RuntimeError("COHORT_NOT_FROZEN")
    print(
        "[Restaurant Gate] cohort already frozen; fixture pass requires human source-boundary "
        "review before running restaurants"
    )


def run_restaurants(*, human_fixture_review_pass: bool) -> None:
    if RUN_PATH.exists():
        raise RuntimeError("REFUSING_TO_OVERWRITE_RESTAURANT_RUN")
    fixture_results_path = (
        FIXTURE_V2_RESULTS_PATH if FIXTURE_V2_RESULTS_PATH.exists() else FIXTURE_RESULTS_PATH
    )
    fixture_results = json.loads(fixture_results_path.read_text(encoding="utf-8"))
    if (
        fixture_results.get("status") != "PASS_PENDING_HUMAN_SOURCE_REVIEW"
        or not human_fixture_review_pass
    ):
        raise RuntimeError("FIXTURE_GATE_NOT_APPROVED")
    cohort = json.loads(COHORT_PATH.read_text(encoding="utf-8"))
    client = OllamaClient(timeout=180.0, num_predict=6144)
    verifier = OllamaAtomicClaimVerifier(client)
    stats: Counter[str] = Counter()
    restaurant_results = []
    started = time.monotonic()
    try:
        for ordinal, frozen in enumerate(cohort["restaurants"], start=1):
            rid = frozen["restaurantId"]
            profile, catalog = _live(rid)
            if (
                profile["inputHash"] != frozen["inputHash"]
                or catalog["catalogHash"] != frozen["catalogHash"]
            ):
                raise RuntimeError(f"FROZEN_SOURCE_DRIFT:{rid}")
            prompt_rows, _ = _prompt_evidence(catalog, rid)
            # Do not expose Restaurant name to claim generation; identity is metadata.
            prompt_rows = [
                dict(
                    row,
                    catalogItem=next(
                        x for x in catalog["items"] if x["evidenceId"] == row["evidenceId"]
                    ),
                )
                for row in prompt_rows
            ]
            stats["generatorCalls"] += 1
            try:
                validation = _one_call(client, rid, prompt_rows, 6)
                generator_error = None
            except Exception as error:  # noqa: BLE001 - model boundary
                generator_error = semantic_error_category(error)
                validation = {
                    "schemaValid": False,
                    "errors": [{"code": "GENERATOR_ERROR", "category": generator_error}],
                    "claims": [],
                }
            claims = []
            for checked in validation.get("claims", []):
                stats["generatedClaimCount"] += 1
                for error in checked["errors"]:
                    code = error["code"]
                    stats[
                        {
                            "EVIDENCE_SOURCE_TYPE_NOT_ALLOWED": "sourceTypeMismatchCount",
                            "QUOTE_MISMATCH": "quoteMismatchCount",
                            "UNKNOWN_EVIDENCE": "unknownEvidenceCount",
                            "PROVENANCE_TEXT_IN_CLAIM": "provenanceLeakCount",
                        }.get(code, f"reject:{code}")
                    ] += 1
                stats["koreanClaimCount"] += int(
                    not any(e["code"] == "CLAIM_NOT_KOREAN_DOMINANT" for e in checked["errors"])
                )
                outcome = _quality(checked, verifier, stats)
                outcome["claim"] = checked["claim"]
                outcome["sourceTypes"] = sorted(
                    {e["evidenceType"] for e in checked["resolvedEvidence"]}
                )
                if outcome.get("approved"):
                    stats["approvedClaimCount"] += 1
                    for source in outcome["sourceTypes"]:
                        stats[f"approvedSource:{source}"] += 1
                    stats[f"approvedClaimType:{checked['claim']['claimType']}"] += 1
                claims.append(outcome)
                print(
                    f"[Restaurant Evaluation] restaurant {ordinal}/3 id={rid} "
                    f"claim={len(claims)}/{len(validation.get('claims', []))} "
                    f"approved={stats['approvedClaimCount']} "
                    f"elapsed={time.monotonic() - started:.1f}s",
                    flush=True,
                )
            restaurant_results.append(
                {
                    "restaurantId": rid,
                    "name": frozen["name"],
                    "inputHash": frozen["inputHash"],
                    "catalogHash": frozen["catalogHash"],
                    "sourceEvidenceCounts": frozen["sourceEvidenceCounts"],
                    "claims": claims,
                    "generatorError": generator_error,
                }
            )
            print(
                f"[Restaurant Evaluation] restaurant {ordinal}/3 "
                f"generated={len(claims)} "
                f"approved={sum(x.get('approved', False) for x in claims)} "
                f"elapsed={time.monotonic() - started:.1f}s "
                f"ETA~{(time.monotonic() - started) / ordinal * (3 - ordinal):.1f}s "
                "(approximate)",
                flush=True,
            )
    finally:
        client.close()
    stats["restaurantCount"] = len(restaurant_results)
    stats["fixturePassCount"] = fixture_results["metrics"]["fixturePassCount"]
    stats["fixtureFailCount"] = fixture_results["metrics"]["fixtureFailCount"]
    stats["fixtureCount"] = fixture_results["metrics"]["fixtureCount"]
    stats["officialFactPromotionCount"] = None  # manual review required
    stats["knownOverclaimApprovalCount"] = None  # manual review required
    stats["koreanClaimRate"] = (
        round(stats["koreanClaimCount"] / stats["generatedClaimCount"], 4)
        if stats["generatedClaimCount"]
        else 0
    )
    metrics = {
        **dict(stats),
        "model": configured_qwen_model(),
        "temperature": 0,
        "elapsedSeconds": round(time.monotonic() - started, 3),
        "multiSourceCountsAreOverlapping": True,
        "sideEffects": {
            "mysqlReads": len(COHORT_IDS) * 8,
            "mysqlWrites": 0,
            "qdrantReads": 0,
            "qdrantWrites": 0,
            "embeddingCalls": 0,
            "embeddingWrites": 0,
            "geminiCalls": 0,
        },
    }
    run_doc = {
        "runVersion": "semantic-profile-generator-v2.2-dry-run-v1",
        "createdAt": datetime.now(UTC).isoformat(),
        "runMode": "DRY_RUN",
        "model": configured_qwen_model(),
        "restaurantRuns": restaurant_results,
        "metrics": metrics,
    }
    _write_new(RUN_PATH, run_doc)
    metric_doc = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
    metric_doc["restaurantMetrics"] = metrics
    METRICS_PATH.write_text(
        json.dumps(metric_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "freeze",
            "fixtures",
            "freeze-fixtures-v2",
            "fixtures-v2",
            "freeze-fixtures-v3",
            "fixtures-v3",
            "freeze-cohort",
            "restaurants",
        ),
    )
    parser.add_argument("--human-fixture-review-pass", action="store_true")
    args = parser.parse_args()
    if configured_qwen_model() != "qwen3.5:9b":
        raise RuntimeError("UNEXPECTED_MODEL")
    if args.command == "freeze":
        freeze()
    elif args.command == "fixtures":
        run_fixtures()
    elif args.command == "freeze-fixtures-v2":
        freeze_fixtures_v2()
    elif args.command == "fixtures-v2":
        run_fixtures_v2()
    elif args.command == "freeze-fixtures-v3":
        freeze_fixtures_v3()
    elif args.command == "fixtures-v3":
        run_fixtures_v3()
    elif args.command == "freeze-cohort":
        freeze_cohort()
    else:
        run_restaurants(human_fixture_review_pass=args.human_fixture_review_pass)


if __name__ == "__main__":
    main()
