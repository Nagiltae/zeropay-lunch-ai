CREATE TABLE restaurant_naver_verifications (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    restaurant_id BIGINT NOT NULL,
    provider VARCHAR(32) NOT NULL,
    verification_status VARCHAR(16) NOT NULL,
    verification_reason VARCHAR(64) NOT NULL,
    external_place_id VARCHAR(64) NULL,
    model_name VARCHAR(128) NULL,
    verified_at DATETIME(6) NULL,
    last_attempt_at DATETIME(6) NOT NULL,
    CONSTRAINT fk_naver_verifications_restaurant
        FOREIGN KEY (restaurant_id) REFERENCES restaurants (id) ON DELETE CASCADE,
    CONSTRAINT uk_naver_verifications_restaurant_provider
        UNIQUE (restaurant_id, provider),
    INDEX ix_naver_verifications_status (provider, verification_status),
    INDEX ix_naver_verifications_attempt (last_attempt_at)
);
