from app.canonical_builder import CanonicalRestaurant, build_canonical
from app.place_provider import PlaceSearchCandidate
from app.place_resolver import RestaurantReference


def test_build_canonical_with_provider_name_and_category():
    reference = RestaurantReference(
        restaurant_id=1,
        komsco_name="원조맛집",
        komsco_address="서울 강남구 논현동 1",
        komsco_latitude=37.1,
        komsco_longitude=127.1,
        legal_dong="논현동",
        external_merchant_id="merchant-1",
    )
    candidate = PlaceSearchCandidate(
        provider="NAVER",
        external_place_id="naver-1",
        name="진짜원조맛집",
        category="한식 > 국밥",
        address="서울 강남구 논현동 1-1",
        road_address="서울 강남구 강남대로 123",
        latitude=37.2,
        longitude=127.2,
        phone="",
        detail_url="",
        distance="",
        raw_metadata={},
    )
    
    canonical = build_canonical(reference, candidate)
    assert canonical.restaurant_id == 1
    assert canonical.name == "진짜원조맛집"  # Uses provider name
    assert canonical.category == "한식 > 국밥"  # Uses provider category
    assert canonical.address == "서울 강남구 논현동 1"  # Uses KOMSCO base address
    assert canonical.road_address == "서울 강남구 강남대로 123"  # Uses provider road address
    assert canonical.latitude == 37.2
    assert canonical.longitude == 127.2


def test_build_canonical_fallback_to_komsco():
    reference = RestaurantReference(
        restaurant_id=2,
        komsco_name="KOMSCO Name",
        komsco_address="KOMSCO Address",
        komsco_latitude=37.1,
        komsco_longitude=127.1,
        legal_dong="논현동",
        external_merchant_id="merchant-2",
    )
    candidate = PlaceSearchCandidate(
        provider="KAKAO",
        external_place_id="kakao-2",
        name="",  # Missing name
        category="",
        address="Provider Address",
        road_address="",  # Missing road address
        latitude=None,  # Missing lat
        longitude=None,  # Missing lon
        phone="",
        detail_url="",
        distance="",
        raw_metadata={},
    )
    
    canonical = build_canonical(reference, candidate)
    assert canonical.name == "KOMSCO Name"
    assert canonical.category == ""
    assert canonical.address == "KOMSCO Address"
    assert canonical.road_address == "Provider Address"  # Falls back to candidate.address
    assert canonical.latitude == 37.1
    assert canonical.longitude == 127.1
