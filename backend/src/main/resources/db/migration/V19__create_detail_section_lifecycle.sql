CREATE TABLE restaurant_detail_section_states (
    restaurant_id BIGINT NOT NULL,
    provider VARCHAR(32) NOT NULL,
    external_place_id VARCHAR(64) NOT NULL,
    section VARCHAR(32) NOT NULL,
    state VARCHAR(32) NOT NULL,
    checked_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    error_code VARCHAR(128) NULL,
    PRIMARY KEY (provider, external_place_id, section),
    CONSTRAINT fk_detail_section_state_restaurant
        FOREIGN KEY (restaurant_id) REFERENCES restaurants(id)
);

ALTER TABLE restaurant_business_hours
    ADD COLUMN active BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE restaurant_review_keywords
    ADD COLUMN active BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE restaurant_representative_reviews
    ADD COLUMN active BOOLEAN NOT NULL DEFAULT TRUE;
