CREATE TABLE canonical_restaurants (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    restaurant_id BIGINT NOT NULL,
    name VARCHAR(120) NOT NULL,
    category VARCHAR(255) NULL,
    address VARCHAR(255) NOT NULL,
    road_address VARCHAR(255) NULL,
    latitude DECIMAL(10, 7) NULL,
    longitude DECIMAL(10, 7) NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    CONSTRAINT fk_canonical_restaurants_restaurant
        FOREIGN KEY (restaurant_id) REFERENCES restaurants (id) ON DELETE CASCADE,
    UNIQUE KEY uk_canonical_restaurants_restaurant (restaurant_id)
);
