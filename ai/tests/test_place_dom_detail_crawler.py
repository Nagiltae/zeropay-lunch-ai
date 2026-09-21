from app import place_detail_persistence
from app.place_dom_detail_crawler import DomCollectedDetail, PlaceDomDetailCrawler
from app.place_detail_persistence import PlaceDetailPersistence
import pytest


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


def test_review_count_parser_accepts_rendered_spacing():
    assert PlaceDomDetailCrawler._number_after("방문자리뷰 378", r"방문자\s*리뷰") == 378
    assert PlaceDomDetailCrawler._number_after("블로그 리뷰 56", r"블로그\s*리뷰") == 56


def test_declared_menu_count_ignores_label_without_numeric_count():
    assert PlaceDomDetailCrawler._declared_menu_count("메뉴, 찾아가는길") is None
    assert PlaceDomDetailCrawler._declared_menu_count("메뉴 12") == 12


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
