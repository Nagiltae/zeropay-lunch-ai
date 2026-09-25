"""HOME/MENU/HOURS/REVIEW section별 완료·부분 완료 판정을 검증한다."""

from datetime import datetime, timedelta

from app.naver.place_detail_enrichment_cli import (
    _collected_sections_complete,
    _missing_sections,
    _pending_detail_rows,
    _section_states,
    _sections_to_persist,
)
from app.naver.place_detail_models import BusinessHour, MenuItem, PlaceDetail
from app.naver.place_detail_persistence import PlaceDetailPersistence


def test_summary_does_not_hide_missing_menu_or_price():
    assert _missing_sections(
        {
            "has_review": "1",
            "has_menu": "0",
            "has_price": "0",
            "has_hours": "1",
        }
    ) == {"review": False, "menu": True, "business_hours": False}
    assert (
        _missing_sections(
            {
                "has_review": "1",
                "has_menu": "1",
                "has_price": "0",
                "has_hours": "1",
            }
        )["menu"]
        is True
    )
    assert _missing_sections(
        {
            "has_review": "1",
            "has_menu": "1",
            "has_price": "1",
            "has_hours": "1",
        }
    ) == {"review": False, "menu": False, "business_hours": False}


def test_db_resume_skips_complete_rows_and_limits_only_incomplete_work():
    complete = {
        "restaurant_id": "1",
        "has_review": "1",
        "has_menu": "1",
        "has_price": "1",
        "has_hours": "1",
    }
    partial = {
        "restaurant_id": "2",
        "has_review": "1",
        "has_menu": "0",
        "has_price": "0",
        "has_hours": "1",
    }
    pending, skipped = _pending_detail_rows(
        [complete, partial, {**partial, "restaurant_id": "3"}], 1
    )
    assert [row["restaurant_id"] for row in pending] == ["2"]
    assert skipped == 1


def test_partial_upsert_only_writes_missing_sections_and_protects_existing_price(tmp_path):
    persistence = PlaceDetailPersistence(tmp_path)
    statements = []
    persistence._run = statements.append
    detail = PlaceDetail(
        place_id="123",
        visitor_reviews_total=10,
        menus=(MenuItem(external_menu_id="dom-1", menu_type=None, name="국밥"),),
        business_hours=(BusinessHour(day="월", description="09:00 - 18:00"),),
    )
    persistence.persist(
        17, "123", detail, sections={"review": False, "menu": True, "business_hours": False}
    )
    sql = statements[0]
    assert "INSERT INTO restaurant_menus" in sql
    assert "INSERT INTO restaurant_review_summaries" not in sql
    assert "INSERT INTO restaurant_business_hours" not in sql
    assert "price_value=COALESCE(VALUES(price_value),price_value)" in sql
    assert "price_text=COALESCE(VALUES(price_text),price_text)" in sql


def test_failed_review_page_never_writes_completion_sentinel():
    missing = {"review": True, "menu": False, "business_hours": False}
    assert _sections_to_persist(missing, False) == {
        "review": False,
        "menu": False,
        "business_hours": False,
    }
    assert _sections_to_persist(missing, True)["review"] is True


def test_crawl_with_missing_menu_or_review_stays_pending():
    missing = {"review": True, "menu": True, "business_hours": False}
    detail = PlaceDetail(
        place_id="123",
        menus=(
            MenuItem(
                external_menu_id="dom-1",
                menu_type=None,
                name="국밥",
            ),
        ),
    )
    assert not _collected_sections_complete(missing, detail, False)
    assert not _collected_sections_complete(missing, detail, True)
    priced = PlaceDetail(
        place_id="123",
        menus=(
            MenuItem(
                external_menu_id="dom-1",
                menu_type=None,
                name="국밥",
                price_value=9000,
            ),
        ),
    )
    assert _collected_sections_complete(missing, priced, True)


def test_complete_detail_becomes_pending_when_a_section_is_stale():
    old = (datetime.now() - timedelta(days=31)).isoformat(sep=" ")
    row = {
        "restaurant_id": "4",
        "has_review": "1",
        "has_menu": "1",
        "has_price": "1",
        "has_hours": "1",
        "review_crawled_at": old,
        "menu_crawled_at": old,
        "hours_crawled_at": datetime.now().isoformat(sep=" "),
    }
    missing = _missing_sections(
        row,
        stale_after_seconds=30 * 24 * 60 * 60,
        now=datetime.now(),
    )
    assert missing == {"review": True, "menu": True, "business_hours": False}
    pending, skipped = _pending_detail_rows(
        [row],
        1,
        stale_after_seconds=30 * 24 * 60 * 60,
        now=datetime.now(),
    )
    assert [item["restaurant_id"] for item in pending] == ["4"]
    assert skipped == 0


def test_force_refresh_marks_complete_sections_for_persistence():
    row = {
        "restaurant_id": "5",
        "has_review": "1",
        "has_menu": "1",
        "has_price": "1",
        "has_hours": "1",
    }
    assert _missing_sections(row, force_refresh=True) == {
        "review": True,
        "menu": True,
        "business_hours": True,
    }


def test_fresh_absent_sections_are_skipped_and_stale_absent_is_rechecked():
    checked = datetime.now().isoformat(sep=" ")
    row = {
        "has_review": "0",
        "has_menu": "0",
        "has_price": "0",
        "has_hours": "0",
        "review_state": "ABSENT_CONFIRMED",
        "menu_state": "ABSENT_CONFIRMED",
        "hours_state": "ABSENT_CONFIRMED",
        "review_checked_at": checked,
        "menu_checked_at": checked,
        "hours_checked_at": checked,
    }
    assert _missing_sections(row, stale_after_seconds=3600, now=datetime.now()) == {
        "review": False,
        "menu": False,
        "business_hours": False,
    }
    old = (datetime.now() - timedelta(days=2)).isoformat(sep=" ")
    stale = {**row, "menu_checked_at": old}
    assert _missing_sections(stale, stale_after_seconds=3600, now=datetime.now())["menu"]


def test_failed_state_remains_pending_without_treating_it_as_absent():
    row = {
        "has_review": "0",
        "has_menu": "0",
        "has_price": "0",
        "has_hours": "0",
        "menu_state": "FAILED",
    }
    assert _missing_sections(row)["menu"]


def test_success_row_with_unstructured_hours_is_still_missing_for_profile_readiness():
    row = {
        "has_review": "1",
        "has_menu": "1",
        "has_price": "1",
        "has_hours": "0",
        "hours_state": "SUCCESS",
    }
    assert _missing_sections(row)["business_hours"] is True


def test_resume_checkpoint_skips_terminal_targets_and_rejects_scope_change(tmp_path):
    import pytest

    from app.naver.place_detail_enrichment_cli import _checkpoint_payload, _save_checkpoint

    path = tmp_path / "group-a.json"
    payload = _checkpoint_payload(path, [9559, 9560], ("business_hours",), "WRITE")
    _save_checkpoint(path, payload, 9559, "SUCCESS")
    resumed = _checkpoint_payload(path, [9559, 9560], ("business_hours",), "WRITE")
    assert resumed["completed"] == {"9559": "SUCCESS"}
    with pytest.raises(ValueError, match="does not match"):
        _checkpoint_payload(path, [9559, 9560], ("menu",), "WRITE")


def test_section_state_mapping_distinguishes_absent_and_success():
    from app.naver.place_dom_detail_crawler import DomCollectedDetail

    absent = DomCollectedDetail(
        True,
        "식당",
        "한식",
        "주소",
        None,
        (),
        (),
        True,
        None,
        (),
        True,
        None,
        None,
        (),
        (),
        (),
        (),
        (),
        True,
        True,
        True,
    )
    states = _section_states(absent, {"menu": True, "business_hours": True, "review": True})
    assert states == {
        "menu": "ABSENT_CONFIRMED",
        "business_hours": "ABSENT_CONFIRMED",
        "review": "ABSENT_CONFIRMED",
    }
