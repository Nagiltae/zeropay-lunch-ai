from app.place_provider import parse_kakao_candidates, parse_naver_candidates


def test_kakao_candidate_mapping_preserves_structured_fields():
    rows = parse_kakao_candidates({"documents": [{
        "id": "123", "place_name": "모우리", "category_name": "음식점 > 한식",
        "address_name": "서울 강남구 논현동", "road_address_name": "서울 강남구 학동로 1",
        "x": "127.01", "y": "37.51", "place_url": "https://place.map.kakao.com/123",
    }]})
    assert rows[0].provider == "KAKAO"
    assert rows[0].external_place_id == "123"
    assert rows[0].category == "음식점 > 한식"
    assert rows[0].longitude == 127.01
    assert rows[0].latitude == 37.51


def test_naver_candidate_mapping_strips_display_html_and_scales_coordinates():
    rows = parse_naver_candidates({"items": [{
        "title": "<b>모우리</b>", "category": "한식",
        "address": "서울 강남구 논현동", "roadAddress": "서울 강남구 학동로 1",
        "mapx": "1270100000", "mapy": "375100000", "link": "https://example.test/1",
    }]})
    assert rows[0].provider == "NAVER_LOCAL"
    assert rows[0].name == "모우리"
    assert rows[0].longitude == 127.01
    assert rows[0].latitude == 37.51


def test_optional_provider_fields_are_empty_or_none():
    kakao = parse_kakao_candidates({"documents": [{"id": "1", "place_name": "x"}]})[0]
    naver = parse_naver_candidates({"items": [{"title": "x"}]})[0]
    assert kakao.road_address == "" and kakao.latitude is None
    assert naver.category == "" and naver.longitude is None
