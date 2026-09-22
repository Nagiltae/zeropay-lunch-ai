from datetime import datetime, timedelta

from app.place_detail_enrichment_cli import (
    _collected_sections_complete,
    _missing_sections,
    _pending_detail_rows,
    _sections_to_persist,
)
from app.place_detail_models import BusinessHour, MenuItem, PlaceDetail
from app.place_detail_persistence import PlaceDetailPersistence


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
