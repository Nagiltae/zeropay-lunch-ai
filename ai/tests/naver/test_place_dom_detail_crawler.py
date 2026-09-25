"""PCMap DOM detail parser와 idempotent persistence 호출을 fixture로 검증한다."""

from dataclasses import replace

import pytest

from app.naver import place_detail_persistence
from app.naver.place_detail_models import PlaceDetail
from app.naver.place_detail_persistence import PlaceDetailPersistence
from app.naver.place_dom_detail_crawler import DomCollectedDetail, PlaceDomDetailCrawler


def test_dom_detail_section_statuses_keep_place_and_sections_separate():
    detail = DomCollectedDetail(
        home_success=True,
        name="테스트",
        category="한식",
        address="서울 강남구 테스트길 1",
        phone=None,
        conveniences=(),
        business_hours=("월 10:00 ~ 20:00",),
        menu_page_success=True,
        declared_menu_count=1,
        menus=({"name": "메뉴", "price_text": "6,000원", "price_value": "6000"},),
        review_page_success=True,
        review_total=10,
        blog_review_total=2,
        review_keywords=({"keyword": "맛", "count": 3},),
        review_menu_mentions=(),
        review_themes=(),
        representative_reviews=(),
    )

    assert detail.home_status == "SUCCESS"
    assert detail.menu_status == "SUCCESS"
    assert detail.review_status == "SUCCESS"
    assert detail.status == "SUCCESS"
    assert PlaceDetailPersistence.preview(detail.to_place_detail("123")) == {
        "menu_rows": 1,
        "business_hours_rows": 1,
        "review_summary": True,
        "review_keyword_rows": 1,
        "representative_review_rows": 0,
    }


def test_empty_successful_sections_are_absent_not_failed():
    detail = DomCollectedDetail(
        True, "테스트", "한식", "주소", None, (), (), True, None, (), True, None, None,
        (), (), (), (), (),
    )
    assert detail.menu_status == "ABSENT_CONFIRMED"
    assert detail.hours_status == "ABSENT_CONFIRMED"
    assert detail.review_status == "ABSENT_CONFIRMED"


def test_section_flags_skip_menu_and_review_navigation(monkeypatch):
    class Locator:
        def count(self):
            return 0

        @property
        def first(self):
            return self

        def inner_text(self, timeout=None):
            return "테스트"

        def get_attribute(self, *args, **kwargs):
            return None

        def filter(self, **kwargs):
            return self

        def locator(self, *args, **kwargs):
            return self

    class Page:
        url = "https://pcmap.place.naver.com/restaurant/123/home"

        def locator(self, selector):
            return Locator()

    crawler = PlaceDomDetailCrawler()
    monkeypatch.setattr(crawler, "_menus", lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("fresh MENU must not navigate")
    ))
    monkeypatch.setattr(crawler, "_reviews", lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("fresh REVIEW must not navigate")
    ))
    detail = crawler.collect(Page(), "123", include_menu=False, include_reviews=False)
    assert detail.menu_status == "SKIPPED"
    assert detail.review_status == "SKIPPED"


def test_review_count_parser_accepts_rendered_spacing():
    assert PlaceDomDetailCrawler._number_after("방문자리뷰 378", r"방문자\s*리뷰") == 378
    assert PlaceDomDetailCrawler._number_after("블로그 리뷰 56", r"블로그\s*리뷰") == 56


def test_declared_menu_count_ignores_label_without_numeric_count():
    assert PlaceDomDetailCrawler._declared_menu_count("메뉴, 찾아가는길") is None
    assert PlaceDomDetailCrawler._declared_menu_count("메뉴 12") == 12


def test_business_hour_dom_text_is_structured_without_inventing_schedule():
    detail = DomCollectedDetail(
        True,
        "테스트",
        "한식",
        "주소",
        None,
        (),
        ("영업 전07:00에 영업 시작 매일 07:00 - 20:30 접기",),
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
    )

    hour = detail.to_place_detail("123").business_hours[0]
    assert hour.day == "매일"
    assert hour.open_time == "07:00"
    assert hour.close_time == "20:30"


def test_business_status_without_time_is_not_converted_to_schedule():
    detail = DomCollectedDetail(
        True,
        "테스트",
        "한식",
        "주소",
        None,
        (),
        ("영업 종료, 내일 오전 7시에 영업 시작",),
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
    )

    hour = detail.to_place_detail("123").business_hours[0]
    assert hour.open_time is None
    assert hour.close_time is None
    assert hour.description == "영업 종료, 내일 오전 7시에 영업 시작"


def test_parser_failure_is_not_absent_confirmation():
    detail = DomCollectedDetail(
        True, "식당", "한식", "주소", None, (), (), False, None, (),
        False, None, None, (), (), (), (), ("MENU_PARSE_FAILED",),
    )
    assert detail.menu_status == "FAILED"
    assert detail.review_status == "FAILED"
    assert replace(detail, hours_collection_success=False).hours_status == "FAILED"


def test_hours_without_section_marker_is_parser_failure():
    class Locator:
        def count(self):
            return 0

    class Page:
        def locator(self, selector):
            return Locator()

    with pytest.raises(RuntimeError, match="HOURS_PARSE_FAILED"):
        PlaceDomDetailCrawler()._hours(Page())


def test_persistence_wraps_all_detail_writes_in_transaction(monkeypatch, tmp_path):
    calls = []

    class Result:
        returncode = 0
        stderr = ""
        stdout = ""

    monkeypatch.setattr(
        place_detail_persistence.subprocess,
        "run",
        lambda command, **kwargs: calls.append(command) or Result(),
    )
    PlaceDetailPersistence(tmp_path)._run("INSERT INTO example VALUES (1);")
    sql = calls[0][-1]
    assert "START TRANSACTION;" in sql
    assert "COMMIT;" in sql


def test_persistence_surfaces_database_error(monkeypatch, tmp_path):
    calls = []

    class Result:
        returncode = 1
        stderr = "Duplicate entry 'x' for key 'uk_example'"
        stdout = ""

    monkeypatch.setattr(
        place_detail_persistence.subprocess,
        "run",
        lambda *args, **kwargs: calls.append(args[0][-1]) or Result(),
    )
    try:
        PlaceDetailPersistence(tmp_path)._run("INSERT INTO example VALUES (1);")
    except RuntimeError as error:
        assert "Duplicate entry" in str(error)
        assert "ROLLBACK;" in calls[-1]
    else:
        raise AssertionError("database error was not surfaced")


def test_persistence_bounds_menu_name_to_schema_length():
    assert len(place_detail_persistence._bounded("x" * 300, 255)) == 255


def test_absent_review_snapshot_does_not_overwrite_existing_summary(monkeypatch, tmp_path):
    statements = []
    persistence = PlaceDetailPersistence(tmp_path)
    monkeypatch.setattr(persistence, "_run", statements.append)
    persistence.persist(
        9559,
        "269479759",
        PlaceDetail(place_id="269479759"),
        sections={"review": True, "menu": False, "business_hours": False},
        section_states={"review": "ABSENT_CONFIRMED"},
    )
    assert statements
    assert "restaurant_review_summaries" not in statements[0]


def test_menu_card_parser_separates_name_description_and_price():
    item = PlaceDomDetailCrawler._parse_menu_card_text(
        "이디야 아메리카노\n진한 에스프레소와 부드러운 우유가 어우러진 음료\n4,500원"
    )
    assert item["name"] == "이디야 아메리카노"
    assert item["description"] == "진한 에스프레소와 부드러운 우유가 어우러진 음료"
    assert item["price_value"] == "4500"


@pytest.mark.parametrize("body", ["CAPTCHA", "captcha challenge", "접근이 제한", "비정상적인 접근"])
def test_access_restriction_stops_detail_batch(body):
    with pytest.raises(RuntimeError, match="BLOCKED"):
        PlaceDomDetailCrawler._check_body_access(body)
