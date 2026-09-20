"""Apollo parser regression fixtures."""

# ruff: noqa: E501

from app.place_apollo_parser import parse_place_detail
from app.place_detail_crawler import PlaceDetailCrawler


def fixture() -> str:
    return '''<script>window.__APOLLO_STATE__ = {
      "PlaceMenuItem:1": {"id":"1","name":"토브버거","price":{"priceType":"NORMAL","displayText":"6,400원"}},
      "PlaceDetailBase:38648810": {
        "name":"토브버거 ,TOV", "category":"햄버거", "categoryCode":"FD6",
        "address":"서울 강남구 논현로 1", "roadAddress":"서울 강남구 논현로 1",
        "latitude":37.51, "longitude":127.02, "phone":"0507-1403-5702",
        "paymentInfo":["제로페이"], "description":"수제버거",
        "newBusinessHours":{"items":[{"day":"월","openTime":"11:00","closeTime":"21:00"}]},
        "placeMenus":{"menuCount":1,"items":[{"__ref":"PlaceMenuItem:1"}]},
        "visitorReviewStats":{"totalCount":378,"avgRating":4.5,
          "analysis":{"themes":[{"keyword":"맛","count":12}],
          "menus":[{"name":"토브버거","count":4}],
          "votedKeyword":{"details":[{"keyword":"가성비가 좋아요","count":9}]}}},
        "visitorReviews":{"items":[{"id":"r1","reviewText":"맛있어요","reviewDate":"2026-09-20"}]},
        "cafeBlogReviewsTotal":56
      },
      "ROOT_QUERY":{"placeDetail":{"__ref":"PlaceDetailBase:38648810"}}
    };</script>'''


def test_apollo_fixture_extracts_basic_menu_hours_and_reviews() -> None:
    detail = parse_place_detail(fixture(), "38648810")
    assert detail.name == "토브버거 ,TOV"
    assert detail.category == "햄버거"
    assert detail.phone == "0507-1403-5702"
    assert "제로페이" in detail.payment_info
    assert detail.menu_count == 1
    assert detail.menu_complete
    assert detail.menus[0].price_value == 6400
    assert detail.business_hours[0].open_time == "11:00"
    assert detail.visitor_reviews_total == 378
    assert detail.cafe_blog_reviews_total == 56
    assert detail.review_keywords[0].keyword == "맛"
    assert detail.review_menu_mentions[0].keyword == "토브버거"
    assert detail.voted_keywords[0].keyword == "가성비가 좋아요"
    assert detail.representative_reviews[0].review_text == "맛있어요"


def test_price_parser_keeps_non_numeric_text() -> None:
    html = fixture().replace("6,400원", "가격 변동")
    detail = parse_place_detail(html, "38648810")
    assert detail.menus[0].price_text == "가격 변동"
    assert detail.menus[0].price_value is None


def test_crawler_only_uses_menu_fallback_when_menu_is_incomplete(monkeypatch) -> None:
    calls = []
    incomplete = fixture().replace('"menuCount":1', '"menuCount":2')

    def fake_get(self, url):
        calls.append(url)
        return incomplete if url.endswith("/home") else fixture()

    monkeypatch.setattr(PlaceDetailCrawler, "_get", fake_get)
    result = PlaceDetailCrawler().crawl("38648810", include_reviews=False)
    assert result.status == "SUCCESS"
    assert result.menu_fallback_used
    assert any(url.endswith("/menu/list") for url in calls)
