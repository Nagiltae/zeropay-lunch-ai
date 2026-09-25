"""Read-only repository-wide Profile readiness audit and backfill planning."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

from app.profile_readiness import assess_profile_readiness, is_source_grounded_hour
from app.semantic_profile_shadow import _mysql

GROUP_A_IDS = (9559, 9560, 9562, 9567, 9569, 9570, 9580)
MENU_ABSENT_EXCLUSIONS = (9654, 9731, 9750)
IDENTITY_REVIEW_EXCLUSIONS = (9582, 9619, 9661, 9695, 9610)
KNOWN_DETAIL_FAILURE_EXCLUSIONS = (9564,)
PRIOR_PROFILE_IDS = (9617, 9731, 9567, 9580, 9568, 9569, 9570, 9571, 9574, 9590)

_AUDIT_SQL = """
WITH scope AS (
  SELECT r.id restaurant_id,r.name,r.active,r.recommendation_eligibility,r.legal_dong_code,
         e.external_place_id,e.match_status
  FROM restaurants r JOIN restaurant_external_places e ON e.restaurant_id=r.id
  WHERE r.active=1 AND r.recommendation_eligibility='ELIGIBLE'
    AND r.legal_dong_code='11680108' AND e.provider='NAVER' AND e.match_status='MATCHED'
    AND e.external_place_id REGEXP '^[0-9]+$'
), menu AS (
  SELECT restaurant_id,external_place_id,COUNT(*) total,
    SUM(price_value IS NOT NULL OR NULLIF(TRIM(price_text),'') IS NOT NULL) priced
  FROM restaurant_menus WHERE provider='NAVER' AND active=1
  GROUP BY restaurant_id,external_place_id
), hours AS (
  SELECT restaurant_id,external_place_id,COUNT(*) total,
    SUM(
      NULLIF(TRIM(open_time),'') IS NOT NULL AND NULLIF(TRIM(close_time),'') IS NOT NULL
    ) structured,
    JSON_ARRAYAGG(JSON_OBJECT('day',day_of_week,'open_time',open_time,
      'close_time',close_time,'description',description)) hour_evidence
  FROM restaurant_business_hours WHERE provider='NAVER' AND active=1
  GROUP BY restaurant_id,external_place_id
), review AS (
  SELECT s.restaurant_id,s.external_place_id,
    (SELECT COUNT(*) FROM restaurant_review_summaries x WHERE x.restaurant_id=s.restaurant_id
      AND x.provider='NAVER' AND x.external_place_id=s.external_place_id) summaries,
    (SELECT COUNT(*) FROM restaurant_review_keywords x WHERE x.restaurant_id=s.restaurant_id
      AND x.provider='NAVER' AND x.external_place_id=s.external_place_id AND x.active=1) keywords,
    (SELECT COUNT(*) FROM restaurant_representative_reviews x WHERE x.restaurant_id=s.restaurant_id
      AND x.provider='NAVER' AND x.external_place_id=s.external_place_id
      AND x.active=1) representative_reviews
  FROM scope s
), state AS (
  SELECT restaurant_id,external_place_id,
    MAX(CASE WHEN section='menu' THEN state END) menu_state,
    MAX(CASE WHEN section='menu' THEN checked_at END) menu_checked,
    MAX(CASE WHEN section='business_hours' THEN state END) hours_state,
    MAX(CASE WHEN section='business_hours' THEN checked_at END) hours_checked,
    MAX(CASE WHEN section='review' THEN state END) review_state,
    MAX(CASE WHEN section='review' THEN checked_at END) review_checked,
    COUNT(DISTINCT section) lifecycle_count
  FROM restaurant_detail_section_states WHERE provider='NAVER'
    AND section IN ('menu','business_hours','review')
  GROUP BY restaurant_id,external_place_id
), verification AS (
  SELECT restaurant_id,external_place_id,verification_status,
    external_place_id verification_place_id,
    ROW_NUMBER() OVER(PARTITION BY restaurant_id ORDER BY last_attempt_at DESC,id DESC) rn
  FROM restaurant_naver_verifications WHERE provider='NAVER'
), owners AS (
  SELECT external_place_id,COUNT(DISTINCT restaurant_id) owner_count
  FROM restaurant_external_places WHERE provider='NAVER' AND match_status='MATCHED'
    AND external_place_id REGEXP '^[0-9]+$' GROUP BY external_place_id
)
SELECT s.restaurant_id,s.name,s.external_place_id,s.active,s.recommendation_eligibility,
  COALESCE(m.total,0) menu_count,COALESCE(m.priced,0) priced_menu_count,
  COALESCE(h.total,0) hours_row_count,COALESCE(h.structured,0) structured_hours_count,
  h.hour_evidence,
  COALESCE(r.summaries,0) review_summary_count,COALESCE(r.keywords,0) review_keyword_count,
  COALESCE(r.representative_reviews,0) representative_review_count,
  st.menu_state,st.menu_checked,st.hours_state,st.hours_checked,st.review_state,st.review_checked,
  COALESCE(st.lifecycle_count,0) lifecycle_count,
  v.verification_status,v.verification_place_id,o.owner_count
FROM scope s
LEFT JOIN menu m ON m.restaurant_id=s.restaurant_id AND m.external_place_id=s.external_place_id
LEFT JOIN hours h ON h.restaurant_id=s.restaurant_id AND h.external_place_id=s.external_place_id
LEFT JOIN review r ON r.restaurant_id=s.restaurant_id AND r.external_place_id=s.external_place_id
LEFT JOIN state st ON st.restaurant_id=s.restaurant_id AND st.external_place_id=s.external_place_id
LEFT JOIN verification v ON v.restaurant_id=s.restaurant_id AND v.rn=1
LEFT JOIN owners o ON o.external_place_id=s.external_place_id
ORDER BY s.restaurant_id
"""


def audit_rows() -> list[dict[str, Any]]:
    raw_rows = _mysql(_AUDIT_SQL)
    result = []
    for raw in raw_rows:
        lifecycle = [
            {
                "section": section,
                "state": raw.get(f"{key}_state"),
                "checkedAt": raw.get(f"{key}_checked"),
            }
            for section, key in (
                ("menu", "menu"),
                ("business_hours", "hours"),
                ("review", "review"),
            )
            if raw.get(f"{key}_state") is not None
        ]
        readiness_record = {
            "active": raw.get("active"),
            "eligibility": raw.get("recommendation_eligibility"),
            "lifecycle": lifecycle,
            "menus": [{"price_value": 1}] if int(raw["priced_menu_count"] or 0) else [],
            "businessHours": json.loads(raw.get("hour_evidence") or "[]"),
            "numericPlaceId": raw.get("external_place_id"),
            "ownerCount": raw.get("owner_count"),
            "verificationStatus": raw.get("verification_status"),
            "verificationPlaceId": raw.get("verification_place_id"),
        }
        readiness = assess_profile_readiness(readiness_record)
        row = {**raw, "readiness": readiness}
        row["restaurant_id"] = int(raw["restaurant_id"])
        for key in (
            "menu_count",
            "priced_menu_count",
            "hours_row_count",
            "structured_hours_count",
            "review_summary_count",
            "review_keyword_count",
            "representative_review_count",
            "lifecycle_count",
            "owner_count",
        ):
            row[key] = int(raw.get(key) or 0)
        row["structured_hours_count"] = sum(
            is_source_grounded_hour(hour)
            for hour in json.loads(raw.get("hour_evidence") or "[]")
        )
        result.append(row)
    return result


def build_coverage_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ready = [row for row in rows if row["readiness"]["ready"]]
    reason_counts: Counter[str] = Counter(
        reason for row in rows for reason in row["readiness"]["reasons"]
    )
    return {
        "population": len(rows),
        "strictReady": len(ready),
        "strictReadyRestaurantIds": [row["restaurant_id"] for row in ready],
        "notReadyReasonCounts": dict(sorted(reason_counts.items())),
    }


def select_backfill_groups(rows: list[dict[str, Any]], group_b_limit: int = 20) -> dict[str, Any]:
    by_id = {row["restaurant_id"]: row for row in rows}
    group_a = []
    for restaurant_id in GROUP_A_IDS:
        row = by_id.get(restaurant_id)
        if row is None:
            continue
        group_a.append(
            {
                "restaurantId": restaurant_id,
                "reason": "only NO_STRUCTURED_HOURS remains"
                if row["readiness"]["reasons"] == ["NO_STRUCTURED_HOURS"]
                else "Group A allowlist; readiness reasons inspected",
                "missingSections": ["business_hours"],
                "placeId": row["external_place_id"],
            }
        )

    legacy = [row for row in rows if row["lifecycle_count"] == 0]
    candidates = []
    for row in legacy:
        rid = row["restaurant_id"]
        if (
            rid in MENU_ABSENT_EXCLUSIONS
            or rid in IDENTITY_REVIEW_EXCLUSIONS
            or rid in KNOWN_DETAIL_FAILURE_EXCLUSIONS
            or "NOT_VERIFIED" in row["readiness"]["reasons"]
        ):
            continue
        if row["readiness"]["reasons"] and any(
            reason in row["readiness"]["reasons"]
            for reason in ("PLACE_ID_CONFLICT", "NO_NUMERIC_PLACE_ID")
        ):
            continue
        signals = {
            "pricedMenu": row["priced_menu_count"] > 0,
            "structuredHours": row["structured_hours_count"] > 0,
            "reviewSummary": row["review_summary_count"] > 0,
            "reviewKeywords": row["review_keyword_count"] > 0,
            "representativeReviews": row["representative_review_count"] > 0,
        }
        score = sum(signals.values())
        candidates.append(
            {
                "restaurantId": rid,
                "placeId": row["external_place_id"],
                "priorityScore": score,
                "signals": signals,
                "existingRows": {
                    "menuCount": row["menu_count"],
                    "pricedMenuCount": row["priced_menu_count"],
                    "structuredHoursCount": row["structured_hours_count"],
                    "reviewKeywordCount": row["review_keyword_count"],
                    "representativeReviewCount": row["representative_review_count"],
                },
                "currentReadinessReasons": row["readiness"]["reasons"],
                "missingSections": ["menu", "business_hours", "review"],
            }
        )
    candidates.sort(
        key=lambda item: (
            -item["priorityScore"],
            -item["existingRows"]["structuredHoursCount"],
            -item["existingRows"]["pricedMenuCount"],
            -item["existingRows"]["reviewKeywordCount"],
            -item["existingRows"]["representativeReviewCount"],
            item["restaurantId"],
        )
    )
    group_b = candidates[:group_b_limit]
    return {
        "groupA": group_a,
        "groupBCandidatePoolCount": len(candidates),
        "groupB": group_b,
        "excludedMenuAbsentConfirmed": list(MENU_ABSENT_EXCLUSIONS),
        "excludedKnownIdentityReview": list(IDENTITY_REVIEW_EXCLUSIONS),
        "excludedKnownDetailFailure": list(KNOWN_DETAIL_FAILURE_EXCLUSIONS),
        "selectedTotal": len(group_a) + len(group_b),
    }
