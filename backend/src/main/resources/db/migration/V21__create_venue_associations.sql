CREATE TABLE venues (
    id BIGINT NOT NULL AUTO_INCREMENT,
    name VARCHAR(120) NOT NULL,
    address VARCHAR(255) NOT NULL,
    latitude DECIMAL(10, 7) NULL,
    longitude DECIMAL(10, 7) NULL,
    venue_status VARCHAR(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_venues_status (venue_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE restaurant_venue_associations (
    id BIGINT NOT NULL AUTO_INCREMENT,
    restaurant_id BIGINT NOT NULL,
    venue_id BIGINT NOT NULL,
    association_status VARCHAR(16) NOT NULL,
    evidence VARCHAR(1000) NULL,
    verified_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_restaurant_venue_association_restaurant (restaurant_id),
    UNIQUE KEY uk_restaurant_venue_association_pair (restaurant_id, venue_id),
    KEY idx_restaurant_venue_association_venue_status (venue_id, association_status),
    CONSTRAINT fk_restaurant_venue_association_restaurant
        FOREIGN KEY (restaurant_id) REFERENCES restaurants (id),
    CONSTRAINT fk_restaurant_venue_association_venue
        FOREIGN KEY (venue_id) REFERENCES venues (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
