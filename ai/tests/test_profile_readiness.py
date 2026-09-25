from datetime import UTC, datetime, timedelta

from app.profile_readiness import assess_profile_readiness, is_source_grounded_hour
from app.profile_readiness_audit import GROUP_A_IDS, MENU_ABSENT_EXCLUSIONS


def ready_record():
    checked = datetime.now(UTC).isoformat()
    return {
        "active": "1",
        "eligibility": "ELIGIBLE",
        "lifecycle": [
            {"section": "menu", "state": "SUCCESS", "checkedAt": checked},
            {"section": "business_hours", "state": "SUCCESS", "checkedAt": checked},
            {"section": "review", "state": "SUCCESS", "checkedAt": checked},
        ],
        "menus": [{"price_value": 9000}],
        "businessHours": [
            {
                "day": "매일",
                "open_time": "11:00",
                "close_time": "21:00",
                "description": "매일 11:00 - 21:00",
            }
        ],
        "numericPlaceId": "123456",
        "ownerCount": 1,
        "verificationStatus": "VERIFIED",
        "verificationPlaceId": "123456",
    }


def test_all_strict_profile_conditions_ready():
    result = assess_profile_readiness(ready_record())
    assert result["status"] == "READY"
    assert result["reasons"] == []


def test_each_missing_or_untrusted_condition_is_not_ready():
    changes = [
        (
            "menu",
            lambda x: x["lifecycle"].__setitem__(
                0,
                {"section": "menu", "state": "FAILED", "checkedAt": datetime.now(UTC).isoformat()},
            ),
            "NO_MENU_SUCCESS",
        ),
        (
            "review",
            lambda x: x["lifecycle"].__setitem__(
                2,
                {
                    "section": "review",
                    "state": "FAILED",
                    "checkedAt": datetime.now(UTC).isoformat(),
                },
            ),
            "NO_REVIEW_SUCCESS",
        ),
        ("hours", lambda x: x.update(businessHours=[]), "NO_STRUCTURED_HOURS"),
        ("price", lambda x: x.update(menus=[{"name": "정식"}]), "NO_PRICED_MENU"),
        ("owner", lambda x: x.update(ownerCount=2), "PLACE_ID_CONFLICT"),
        ("verification", lambda x: x.update(verificationStatus="UNKNOWN"), "NOT_VERIFIED"),
        ("verification-mismatch", lambda x: x.update(verificationPlaceId="987654"), "NOT_VERIFIED"),
        ("numeric", lambda x: x.update(numericPlaceId="abc"), "NO_NUMERIC_PLACE_ID"),
    ]
    for _, mutate, reason in changes:
        record = ready_record()
        mutate(record)
        result = assess_profile_readiness(record)
        assert result["status"] == "NOT_READY"
        assert reason in result["reasons"]


def test_stale_detail_blocks_readiness():
    old = (datetime.now(UTC) - timedelta(days=31)).isoformat()
    record = ready_record()
    record["lifecycle"][1]["checkedAt"] = old
    result = assess_profile_readiness(record, ttl_seconds=30 * 86400)
    assert result["status"] == "NOT_READY"
    assert "STALE" in result["reasons"]


def test_hours_day_and_range_must_be_adjacent_in_source_description():
    record = ready_record()
    record["businessHours"] = [
        {
            "day": "일",
            "open_time": "14:00",
            "close_time": "23:00",
            "description": "일 정기휴무 월 14:00 - 23:00 화 14:00 - 23:00",
        }
    ]
    result = assess_profile_readiness(record)
    assert result["status"] == "NOT_READY"
    assert "NO_STRUCTURED_HOURS" in result["reasons"]


def test_existing_structured_hour_is_accepted_only_when_source_supports_same_day():
    assert is_source_grounded_hour(
        {
            "day_of_week": "월",
            "open_time": "14:00",
            "close_time": "23:00",
            "description": "일 정기휴무 월 14:00 - 23:00 화 14:00 - 23:00",
        }
    )
    assert not is_source_grounded_hour(
        {
            "day_of_week": "일",
            "open_time": "14:00",
            "close_time": "23:00",
            "description": "일 정기휴무 월 14:00 - 23:00 화 14:00 - 23:00",
        }
    )


def test_group_a_and_menu_absent_exclusions_are_fixed_allowlists():
    assert GROUP_A_IDS == (9559, 9560, 9562, 9567, 9569, 9570, 9580)
    assert MENU_ABSENT_EXCLUSIONS == (9654, 9731, 9750)
