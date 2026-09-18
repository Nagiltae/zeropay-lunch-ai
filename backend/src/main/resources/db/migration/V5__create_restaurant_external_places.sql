CREATE TABLE restaurant_external_places (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    restaurant_id BIGINT NOT NULL,
    provider VARCHAR(32) NOT NULL,
    external_name VARCHAR(255) NULL,
    category VARCHAR(255) NULL,
    description VARCHAR(1000) NULL,
    link VARCHAR(1000) NULL,
    address VARCHAR(255) NULL,
    road_address VARCHAR(255) NULL,
    latitude DECIMAL(10, 7) NULL,
    longitude DECIMAL(10, 7) NULL,
    match_status VARCHAR(16) NOT NULL,
    match_score DECIMAL(5, 2) NOT NULL,
    match_distance_meters DECIMAL(10, 2) NULL,
    query_used VARCHAR(255) NOT NULL,
    matched_at DATETIME(6) NULL,
    last_synced_at DATETIME(6) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    CONSTRAINT fk_external_places_restaurant
        FOREIGN KEY (restaurant_id) REFERENCES restaurants (id) ON DELETE CASCADE,
    CONSTRAINT uk_external_places_restaurant_provider
        UNIQUE (restaurant_id, provider),
    INDEX idx_external_places_provider_status (provider, match_status)
);
