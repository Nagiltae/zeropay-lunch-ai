"""Bounded, resumable Semantic Profile expansion for strict-ready restaurants.

MySQL access is delegated to the existing SELECT-only profile input helpers.
Generated artifacts live in a versioned shadow directory; this module never
persists profiles or writes to an existing Qdrant collection.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.entity_resolution.qwen_candidate_matcher import OllamaClient, configured_qwen_model
from app.profile_readiness_audit import audit_rows, build_coverage_summary
from app.semantic_profile_shadow import (
    EVIDENCE_OUTPUT_VERSION,
    _evidence_prompt,
    _evidence_schema,
    _profile_system_prompt,
    benchmark_eligible_claims,
    build_compact_input,
    build_evidence_catalog,
    build_input,
    classify_claims,
    validate_evidence_output,
)

REPO = Path(__file__).resolve().parents[2]
ARTIFACT_ROOT = REPO / "AI_Answer"
RUN_DIR = ARTIFACT_ROOT / "semantic_profile_expansion_v2"
PLAN_PATH = ARTIFACT_ROOT / "semantic_profile_expansion_plan.json"
MANIFEST_PATH = ARTIFACT_ROOT / "semantic_profile_expansion_batch_manifest.json"
CHECKPOINT_PATH = RUN_DIR / "checkpoint.json"
MAX_INPUT_BYTES = 64_000

# Known historical artifacts only. They are read-only and never rewritten.
EXISTING_ARTIFACTS: dict[int, tuple[str, str | None]] = {
    9568: (
        "semantic_profile_post_persistence_9568/semantic_profile_v1_shadow_results.json",
        "semantic_profile_post_persistence_9568/semantic_profile_v1_evidence_catalog_9568.json",
    ),
    9569: (
        "semantic_profile_post_persistence_9569/semantic_profile_v1_shadow_results.json",
        "semantic_profile_post_persistence_9569/semantic_profile_v1_evidence_catalog_9569.json",
    ),
    9570: (
        "semantic_profile_benchmark_9570/semantic_profile_v1_shadow_results.json",
        "semantic_profile_benchmark_9570/semantic_profile_v1_evidence_catalog_9570.json",
    ),
    9571: (
        "semantic_profile_benchmark_9571/semantic_profile_v1_shadow_results.json",
        "semantic_profile_benchmark_9571/semantic_profile_v1_evidence_catalog_9571.json",
    ),
    9574: (
        "semantic_profile_benchmark_9574/semantic_profile_v1_shadow_results.json",
        "semantic_profile_benchmark_9574/semantic_profile_v1_evidence_catalog_9574.json",
    ),
    9580: (
        "semantic_profile_pilot_9580/semantic_profile_v1_shadow_results.json",
        "semantic_profile_pilot_9580/semantic_profile_v1_evidence_catalog_9580.json",
    ),
    9617: (
        "semantic_profile_v1_approved_9617.json",
        "semantic_profile_v1_evidence_catalog_9617.json",
    ),
}


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def _current_material(restaurant_id: int) -> tuple[dict[str, Any], dict[str, Any]]:
    profile_input = build_compact_input(build_input(restaurant_id))
    catalog = build_evidence_catalog(profile_input)
    return profile_input, catalog


def evidence_compatible(
    evidence_ids: list[str], old_catalog: dict[str, Any], current_catalog: dict[str, Any]
) -> bool:
    """Require every cited source value/type/section to remain identical and successful."""
    old_by_id = {item.get("evidenceId"): item for item in old_catalog.get("items", [])}
    current_by_id = {item.get("evidenceId"): item for item in current_catalog.get("items", [])}
    if not evidence_ids:
        return False
    for evidence_id in evidence_ids:
        old = old_by_id.get(evidence_id)
        current = current_by_id.get(evidence_id)
        if not old or not current or current.get("status") != "SUCCESS":
            return False
        if any(
            old.get(key) != current.get(key)
            for key in ("sourceField", "content", "section", "evidenceType")
        ):
            return False
    return True


def _existing_claims(
    restaurant_id: int, catalog: dict[str, Any], profile_input: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    spec = EXISTING_ARTIFACTS.get(restaurant_id)
    if not spec:
        return [], {"found": False}
    result_path = ARTIFACT_ROOT / spec[0]
    if not result_path.is_file():
        return [], {"found": False, "missingArtifact": spec[0]}
    result = json.loads(result_path.read_text())
    old_catalog = None
    if spec[1] and (ARTIFACT_ROOT / spec[1]).is_file():
        old_catalog = json.loads((ARTIFACT_ROOT / spec[1]).read_text())
    if restaurant_id == 9617:
        raw_claims = [
            {key: claim[key] for key in ("claimType", "text", "confidence", "evidenceIds")}
            for claim in result.get("claims", [])
        ]
    else:
        calls = result.get("calls", [])
        valid_calls = [
            call
            for call in calls
            if call.get("status") == "ok"
            and isinstance(call.get("validation", {}).get("parsed"), dict)
        ]
        if not valid_calls:
            return [], {"found": True, "source": spec[0], "reason": "no parsed output"}
        raw_claims = valid_calls[-1]["validation"]["parsed"].get("claims", [])
    classifications = classify_claims({"claims": raw_claims}, catalog, profile_input)
    eligible, reason = benchmark_eligible_claims(classifications, catalog, profile_input)
    # A current source catalog revalidation is required before rebasing provenance.
    preserved = []
    incompatible_claims = 0
    for item in eligible:
        claim = item["claim"]
        if old_catalog is None or not evidence_compatible(
            claim.get("evidenceIds", []), old_catalog, catalog
        ):
            incompatible_claims += 1
            continue
        preserved.append(claim)
    detail = {
        "found": True,
        "source": spec[0],
        "sourceInputHash": result.get("inputHash"),
        "currentInputHash": profile_input["inputHash"],
        "sourceCatalogHash": result.get("catalogHash"),
        "currentCatalogHash": catalog["catalogHash"],
        "revalidatedAutoApprovedClaims": len(preserved),
        "incompatibleCitedEvidenceClaims": incompatible_claims,
        "claimValidationErrorsAreLocal": len(preserved) > 0,
        "eligibilityReason": reason,
    }
    return preserved, detail


def build_plan() -> tuple[dict[str, Any], dict[int, tuple[dict[str, Any], dict[str, Any]]]]:
    rows = audit_rows()
    coverage = build_coverage_summary(rows)
    ready_ids = coverage["strictReadyRestaurantIds"]
    row_by_id = {row["restaurant_id"]: row for row in rows}
    materials: dict[int, tuple[dict[str, Any], dict[str, Any]]] = {}
    entries = []
    for rid in ready_ids:
        profile_input, catalog = _current_material(rid)
        materials[rid] = (profile_input, catalog)
        compact_bytes = len(json.dumps(profile_input, ensure_ascii=False).encode("utf-8"))
        catalog_bytes = len(json.dumps(catalog, ensure_ascii=False).encode("utf-8"))
        estimated_prompt_bytes = catalog_bytes + 600
        previous, prior_info = _existing_claims(rid, catalog, profile_input)
        if prior_info.get("found") and previous:
            action = "REUSE_EXISTING"
        elif prior_info.get("found"):
            action = "NEEDS_REVIEW"
        else:
            action = "GENERATE_NEW"
        row = row_by_id[rid]
        entries.append(
            {
                "restaurantId": rid,
                "name": row["name"],
                "placeId": row["external_place_id"],
                "readiness": row["readiness"],
                "action": action,
                "existingArtifact": prior_info,
                "existingRevalidatedAutoClaims": len(previous),
                "menuCount": len(profile_input["sections"]["menu"]["items"]),
                "pricedMenuCount": row["priced_menu_count"],
                "structuredHoursCount": row["structured_hours_count"],
                "reviewSummaryCount": row["review_summary_count"],
                "reviewKeywordCount": len(profile_input["sections"]["review"]["keywords"]),
                "representativeReviewCount": len(
                    profile_input["sections"]["review"]["representativeReviews"]
                ),
                "evidenceCatalogItems": len(catalog["items"]),
                "inputBytes": compact_bytes,
                "catalogBytes": catalog_bytes,
                "estimatedPromptBytes": estimated_prompt_bytes,
                "inputChars": len(json.dumps(profile_input, ensure_ascii=False)),
                "inputHash": profile_input["inputHash"],
                "catalogHash": catalog["catalogHash"],
                "strictProfileReady": profile_input["quality"]["strictProfileReady"],
                "profileArtifactExpected": prior_info.get("found", False),
            }
        )
    new_ids = [item["restaurantId"] for item in entries if item["action"] == "GENERATE_NEW"]
    plan = {
        "planVersion": "semantic-profile-expansion-plan-v2",
        "createdAt": datetime.now(UTC).isoformat(),
        "readOnlyAudit": True,
        "readinessPolicyVersion": "profile-readiness-source-grounded-hours-v2",
        "coverage": coverage,
        "readyRestaurantIds": ready_ids,
        "actions": {
            key: [item["restaurantId"] for item in entries if item["action"] == key]
            for key in ("REUSE_EXISTING", "GENERATE_NEW", "NEEDS_REVIEW")
        },
        "plannedQwenCalls": len(new_ids),
        "modelConfigured": configured_qwen_model(),
        "maxInputBytes": MAX_INPUT_BYTES,
        "inputSizeGatePass": all(
            max(item["inputBytes"], item["estimatedPromptBytes"]) <= MAX_INPUT_BYTES
            for item in entries
        ),
        "mySqlWrites": 0,
        "existingV12Writes": 0,
        "restaurants": entries,
    }
    return plan, materials


def _prior_batch_state() -> dict[str, Any]:
    if not CHECKPOINT_PATH.exists():
        return {"version": 1, "outcomes": {}}
    return json.loads(CHECKPOINT_PATH.read_text())


def _save_checkpoint(state: dict[str, Any]) -> None:
    temporary = CHECKPOINT_PATH.with_suffix(".tmp")
    _write_json(temporary, state)
    temporary.replace(CHECKPOINT_PATH)


def run_generation(
    plan: dict[str, Any], materials: dict[int, tuple[dict[str, Any], dict[str, Any]]]
) -> dict[str, Any]:
    if not plan["inputSizeGatePass"]:
        raise RuntimeError("input size gate failed; refusing Qwen calls")
    if any(not row["strictProfileReady"] for row in plan["restaurants"]):
        raise RuntimeError("NOT_READY present in plan; refusing Qwen calls")
    if PLAN_PATH.exists() and json.loads(PLAN_PATH.read_text()) != plan:
        raise RuntimeError("plan artifact exists and differs; refusing to overwrite")
    state = _prior_batch_state()
    outcomes: dict[str, Any] = state.setdefault("outcomes", {})
    # Reuse only claims revalidated against the freshly-built current catalog.
    # The source artifacts remain untouched; current provenance is recorded in
    # this separate expansion run directory.
    for rid in plan["actions"]["REUSE_EXISTING"]:
        profile_input, catalog = materials[rid]
        claims, source = _existing_claims(rid, catalog, profile_input)
        out_dir = RUN_DIR / str(rid)
        _write_json(out_dir / "compact_input.json", profile_input)
        _write_json(out_dir / "evidence_catalog.json", catalog)
        by_id = {item["evidenceId"]: item for item in catalog["items"]}
        attached = [
            {**claim, "evidence": [by_id[eid] for eid in claim["evidenceIds"]]} for claim in claims
        ]
        final = {
            "profileVersion": EVIDENCE_OUTPUT_VERSION,
            "inputVersion": profile_input["inputVersion"],
            "inputHash": profile_input["inputHash"],
            "catalogVersion": catalog["catalogVersion"],
            "catalogHash": catalog["catalogHash"],
            "restaurantId": rid,
            "venueId": profile_input["venueId"],
            "profileStatus": "READY" if attached else "PARTIAL",
            "claims": attached,
            "reusedFrom": source["source"],
            "sourceInputHash": source.get("sourceInputHash"),
            "sourceCatalogHash": source.get("sourceCatalogHash"),
            "revalidatedAgainstCurrentInput": True,
        }
        _write_json(out_dir / "approved_profile.json", final)
        _write_json(
            out_dir / "claim_validation.json",
            {
                "valid": bool(attached),
                "strictProfileReady": True,
                "reused": True,
                "sourceArtifact": source,
                "approvedClaimCount": len(attached),
            },
        )
    generate_ids = plan["actions"]["GENERATE_NEW"]
    total = len(generate_ids)
    consecutive_quality_failures = 0
    quality_stop = False
    for index, rid in enumerate(generate_ids, start=1):
        key = str(rid)
        material = materials[rid]
        profile_input, catalog = material
        current = outcomes.get(key)
        if (
            current
            and current.get("inputHash") == profile_input["inputHash"]
            and current.get("terminal")
        ):
            print(f"[{index}/{total}] {rid} SKIPPED checkpoint={current['status']}", flush=True)
            if current.get("status") in {"FAILED_VALIDATION", "NO_APPROVED_CLAIMS"}:
                consecutive_quality_failures += 1
            else:
                consecutive_quality_failures = 0
            if consecutive_quality_failures >= 3:
                quality_stop = True
                break
            continue
        out_dir = RUN_DIR / str(rid)
        _write_json(out_dir / "compact_input.json", profile_input)
        _write_json(out_dir / "evidence_catalog.json", catalog)
        started = time.perf_counter()
        record: dict[str, Any] = {
            "restaurantId": rid,
            "inputHash": profile_input["inputHash"],
            "catalogHash": catalog["catalogHash"],
            "terminal": True,
            "qwenCalls": 1,
        }
        client = OllamaClient(timeout=120.0)
        try:
            raw_text = client.complete(
                _profile_system_prompt(),
                _evidence_prompt(profile_input, catalog),
                _evidence_schema(),
            )
            raw = json.loads(raw_text)
            _write_json(out_dir / "qwen_raw_output.json", raw)
            validation = validate_evidence_output(raw, catalog, profile_input)
            classifications = (
                classify_claims(raw, catalog, profile_input) if "claims" in raw else []
            )
            eligible, eligibility_reason = benchmark_eligible_claims(
                classifications, catalog, profile_input
            )
            approved = [item["claim"] for item in eligible if item["status"] == "AUTO_APPROVED"]
            if not validation.get("valid"):
                status = "FAILED_VALIDATION"
            elif not approved:
                status = "NO_APPROVED_CLAIMS"
            else:
                status = "SUCCESS"
                by_id = {item["evidenceId"]: item for item in catalog["items"]}
                final = {
                    "profileVersion": EVIDENCE_OUTPUT_VERSION,
                    "inputVersion": profile_input["inputVersion"],
                    "inputHash": profile_input["inputHash"],
                    "catalogVersion": catalog["catalogVersion"],
                    "catalogHash": catalog["catalogHash"],
                    "restaurantId": rid,
                    "venueId": profile_input["venueId"],
                    "profileStatus": raw["profileStatus"],
                    "claims": [
                        {**item, "evidence": [by_id[eid] for eid in item["evidenceIds"]]}
                        for item in approved
                    ],
                }
                _write_json(
                    out_dir / "claim_validation.json",
                    {
                        "valid": validation["valid"],
                        "errors": validation.get("errors", []),
                        "strictProfileReady": profile_input["quality"]["strictProfileReady"],
                        "classifications": classifications,
                        "benchmarkEligibilityReason": eligibility_reason,
                    },
                )
                _write_json(out_dir / "approved_profile.json", final)
            if status != "SUCCESS":
                _write_json(
                    out_dir / "claim_validation.json",
                    {
                        "valid": validation.get("valid", False),
                        "errors": validation.get("errors", []),
                        "classifications": classifications,
                        "benchmarkEligibilityReason": eligibility_reason,
                    },
                )
            record.update(
                {
                    "status": status,
                    "validation": validation,
                    "claimCounts": dict(Counter(item["status"] for item in classifications)),
                    "approvedClaimCount": len(approved),
                    "elapsedMs": round((time.perf_counter() - started) * 1000),
                    "profilePath": str(out_dir / "approved_profile.json")
                    if status == "SUCCESS"
                    else None,
                }
            )
        except Exception as error:  # one bounded call; fail this Restaurant only
            record.update(
                {
                    "status": "FAILED_CALL",
                    "error": f"{type(error).__name__}: {error}",
                    "elapsedMs": round((time.perf_counter() - started) * 1000),
                }
            )
            _write_json(out_dir / "call_error.json", record)
        finally:
            client.close()
        outcomes[key] = record
        _save_checkpoint(state)
        print(
            f"[{index}/{total}] {rid} {record['status']} "
            f"approved={record.get('approvedClaimCount', 0)} "
            f"elapsed={record.get('elapsedMs')}ms",
            flush=True,
        )
        if record["status"] in {"FAILED_VALIDATION", "NO_APPROVED_CLAIMS"}:
            consecutive_quality_failures += 1
        else:
            consecutive_quality_failures = 0
        if consecutive_quality_failures >= 3:
            quality_stop = True
            print(
                "[STOP] three consecutive profile quality failures; remaining batch deferred",
                flush=True,
            )
            break
    state["updatedAt"] = datetime.now(UTC).isoformat()
    state["qualityStop"] = quality_stop
    state["pendingRestaurantIds"] = [
        rid
        for rid in generate_ids
        if str(rid) not in outcomes or not outcomes[str(rid)].get("terminal")
    ]
    _save_checkpoint(state)
    return state


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--generate",
        action="store_true",
        help="perform one bounded Qwen call per new READY restaurant",
    )
    parser.add_argument(
        "--refresh-plan",
        action="store_true",
        help="replace only this turn's v2 plan after policy-compatible artifact revalidation",
    )
    args = parser.parse_args()
    if PLAN_PATH.exists() and not args.refresh_plan:
        raise SystemExit(f"refusing to overwrite existing plan artifact: {PLAN_PATH}")
    if PLAN_PATH.exists() and args.refresh_plan:
        existing_plan = json.loads(PLAN_PATH.read_text())
        if existing_plan.get("planVersion") != "semantic-profile-expansion-plan-v2":
            raise SystemExit("refusing to overwrite a plan not created by this v2 task")
    plan, materials = build_plan()
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    _write_json(PLAN_PATH, plan)
    print(
        json.dumps(
            {
                "plan": str(PLAN_PATH),
                "strictReady": len(plan["readyRestaurantIds"]),
                "reuse": len(plan["actions"]["REUSE_EXISTING"]),
                "generate": len(plan["actions"]["GENERATE_NEW"]),
                "needsReview": len(plan["actions"]["NEEDS_REVIEW"]),
                "qwenCallsPlanned": plan["plannedQwenCalls"],
                "inputSizeGatePass": plan["inputSizeGatePass"],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    if not args.generate:
        return
    if MANIFEST_PATH.exists():
        raise SystemExit(f"refusing to overwrite existing batch manifest: {MANIFEST_PATH}")
    if plan["plannedQwenCalls"] > len(plan["readyRestaurantIds"]):
        raise SystemExit("write/call gate failed: planned calls exceed ready cohort")
    state = run_generation(plan, materials)
    counts = Counter(item.get("status", "UNKNOWN") for item in state["outcomes"].values())
    manifest = {
        "manifestVersion": "semantic-profile-expansion-batch-v2",
        "status": "PAUSED_QUALITY_FAILURE"
        if state.get("qualityStop")
        else "INCOMPLETE"
        if state.get("pendingRestaurantIds")
        else "COMPLETED"
        if not counts.get("FAILED_CALL") and not counts.get("FAILED_VALIDATION")
        else "COMPLETED_WITH_FAILURES",
        "readyRestaurantIds": plan["readyRestaurantIds"],
        "reuseExisting": plan["actions"]["REUSE_EXISTING"],
        "generateNew": plan["actions"]["GENERATE_NEW"],
        "needsReview": plan["actions"]["NEEDS_REVIEW"],
        "pendingRestaurantIds": state.get("pendingRestaurantIds", []),
        "outcomes": dict(counts),
        "generation": {
            "profileLlmCalls": sum(item.get("qwenCalls", 0) for item in state["outcomes"].values()),
            "successfulProfiles": counts.get("SUCCESS", 0),
            "failedProfiles": counts.get("FAILED_CALL", 0) + counts.get("FAILED_VALIDATION", 0),
            "noApprovedClaims": counts.get("NO_APPROVED_CLAIMS", 0),
            "reusedProfiles": len(plan["actions"]["REUSE_EXISTING"]),
            "embeddingCalls": 0,
        },
        "checkpoint": str(CHECKPOINT_PATH.relative_to(REPO)),
        "inputHashes": {
            str(item["restaurantId"]): item["inputHash"] for item in plan["restaurants"]
        },
        "profileArtifactsRoot": str(RUN_DIR.relative_to(REPO)),
        "mySqlWrites": 0,
        "v12Writes": 0,
    }
    _write_json(MANIFEST_PATH, manifest)
    print(
        json.dumps(
            {
                "manifest": str(MANIFEST_PATH),
                "status": manifest["status"],
                "generation": manifest["generation"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
