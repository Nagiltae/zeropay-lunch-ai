"""Canonical restaurant data builder and persistence."""

from dataclasses import dataclass
from datetime import datetime

from app.place_provider import PlaceSearchCandidate
from app.place_resolver import RestaurantReference

@dataclass
class CanonicalRestaurant:
    restaurant_id: int
    name: str
    category: str
    address: str
    road_address: str
    latitude: float | None
    longitude: float | None

def build_canonical(reference: RestaurantReference, candidate: PlaceSearchCandidate) -> CanonicalRestaurant:
    """Merge KOMSCO reference and provider candidate deterministically."""
    name = candidate.name if candidate.name else reference.komsco_name
    category = candidate.category if candidate.category else ""
    # Keep original KOMSCO address as base address, use candidate's road_address if available.
    address = reference.komsco_address
    road_address = candidate.road_address if candidate.road_address else (candidate.address or "")
    latitude = candidate.latitude if candidate.latitude else reference.komsco_latitude
    longitude = candidate.longitude if candidate.longitude else reference.komsco_longitude

    return CanonicalRestaurant(
        restaurant_id=reference.restaurant_id,
        name=name,
        category=category,
        address=address,
        road_address=road_address,
        latitude=latitude,
        longitude=longitude,
    )

def _sql_value(value: str | float | None) -> str:
    if value is None or value == "":
        return "NULL"
    if isinstance(value, float):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"

def generate_mapping_sql(restaurant_id: int, candidate: PlaceSearchCandidate) -> str:
    """Generate SQL to save external place mapping for a specific provider."""
    return f"""
        INSERT INTO restaurant_external_places
        (restaurant_id, provider, external_place_id, external_name, category, link, address, road_address, latitude, longitude,
         match_status, match_score, query_used, matched_at, last_synced_at, created_at, updated_at)
        VALUES ({restaurant_id}, {_sql_value(candidate.provider)}, {_sql_value(candidate.external_place_id)}, {_sql_value(candidate.name)}, {_sql_value(candidate.category)}, {_sql_value(candidate.detail_url)}, {_sql_value(candidate.address)}, {_sql_value(candidate.road_address)}, {_sql_value(candidate.latitude)}, {_sql_value(candidate.longitude)}, 'MATCHED', 100.00, 'QWEN_ENTITY_RESOLUTION', NOW(), NOW(), NOW(), NOW())
        ON DUPLICATE KEY UPDATE
        external_place_id = VALUES(external_place_id),
        external_name = VALUES(external_name),
        category = VALUES(category),
        link = VALUES(link),
        address = VALUES(address),
        road_address = VALUES(road_address),
        latitude = VALUES(latitude),
        longitude = VALUES(longitude),
        match_status = 'MATCHED',
        match_score = 100.00,
        query_used = 'QWEN_ENTITY_RESOLUTION',
        matched_at = NOW(),
        last_synced_at = NOW(),
        updated_at = NOW();
    """

def generate_canonical_sql(canonical: CanonicalRestaurant, candidates: list[PlaceSearchCandidate]) -> str:
    """Generate SQL to idempotently save canonical restaurant data and external place mappings."""
    sql_canonical = f"""
        INSERT INTO canonical_restaurants
        (restaurant_id, name, category, address, road_address, latitude, longitude, created_at, updated_at)
        VALUES ({canonical.restaurant_id}, {_sql_value(canonical.name)}, {_sql_value(canonical.category)}, {_sql_value(canonical.address)}, {_sql_value(canonical.road_address)}, {_sql_value(canonical.latitude)}, {_sql_value(canonical.longitude)}, NOW(), NOW())
        ON DUPLICATE KEY UPDATE
        name = VALUES(name),
        category = VALUES(category),
        address = VALUES(address),
        road_address = VALUES(road_address),
        latitude = VALUES(latitude),
        longitude = VALUES(longitude),
        updated_at = NOW();
    """

    mapping_sqls = [generate_mapping_sql(canonical.restaurant_id, c) for c in candidates]
    return sql_canonical + "\n" + "\n".join(mapping_sqls)

