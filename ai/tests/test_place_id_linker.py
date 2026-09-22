from app.place_allsearch import PlaceCandidate
from app.place_id_linker_cli import _mapping_status_filter, is_exact_match


def test_is_exact_match():
    cand1 = PlaceCandidate(
        place_id="123",
        name="다모아분식",
        address="서울특별시 강남구 논현로150길 41",
        road_address="서울특별시 강남구 논현로150길 41",
        category="",
        latitude=0,
        longitude=0,
        url="",
    )

    # Exact match on address (even with '서울특별시' vs '서울')
    # due to compare_address_pair handling it
    assert (
        is_exact_match(
            cand1, "다모아분식", "서울 강남구 논현동 60-14", "서울 강남구 논현로150길 41"
        )
        is True
    )

    # Non-match on name
    assert (
        is_exact_match(cand1, "다른식당", "서울 강남구 논현동 60-14", "서울 강남구 논현로150길 41")
        is False
    )

    # Non-match on address
    assert (
        is_exact_match(cand1, "다모아분식", "서울 강남구 역삼동 1-1", "서울 강남구 역삼로 1")
        is False
    )

    # Containment match on name
    cand2 = PlaceCandidate(
        place_id="123",
        name="스타벅스 강남점",
        address="서울 강남구 강남대로 123",
        road_address="서울 강남구 강남대로 123",
        category="",
        latitude=0,
        longitude=0,
        url="",
    )
    assert is_exact_match(cand2, "스타벅스", "서울 강남구 강남대로 123", "") is True


def test_place_id_default_retries_unresolved_but_defers_ambiguous():
    default_filter = _mapping_status_filter(False)
    assert "UNRESOLVED" not in default_filter
    assert "<> 'AMBIGUOUS'" in default_filter
    assert _mapping_status_filter(True) == ""
