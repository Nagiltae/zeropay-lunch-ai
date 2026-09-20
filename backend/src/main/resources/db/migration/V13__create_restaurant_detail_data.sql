CREATE TABLE restaurant_menus (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    restaurant_id BIGINT NOT NULL,
    provider VARCHAR(32) NOT NULL,
    external_place_id VARCHAR(64) NOT NULL,
    external_menu_id VARCHAR(128) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT NULL,
    price_value INT NULL,
    price_text VARCHAR(255) NULL,
    price_type VARCHAR(64) NULL,
    menu_type VARCHAR(64) NULL,
    is_set_menu BOOLEAN NULL,
    thumbnail_url VARCHAR(1000) NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    source_updated_at DATETIME(6) NULL,
    crawled_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_restaurant_menus_restaurant FOREIGN KEY (restaurant_id) REFERENCES restaurants(id),
    CONSTRAINT uk_restaurant_menus_external UNIQUE (provider, external_place_id, external_menu_id)
);

CREATE INDEX ix_restaurant_menus_restaurant ON restaurant_menus (restaurant_id, active);

CREATE TABLE restaurant_business_hours (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    restaurant_id BIGINT NOT NULL,
    provider VARCHAR(32) NOT NULL,
    external_place_id VARCHAR(64) NOT NULL,
    day_of_week VARCHAR(32) NOT NULL,
    open_time VARCHAR(32) NULL,
    close_time VARCHAR(32) NULL,
    break_hours VARCHAR(255) NULL,
    last_order VARCHAR(255) NULL,
    description VARCHAR(1000) NULL,
    regular_closed_day VARCHAR(255) NULL,
    irregular_closed_day VARCHAR(255) NULL,
    business_status VARCHAR(255) NULL,
    crawled_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_restaurant_hours_restaurant FOREIGN KEY (restaurant_id) REFERENCES restaurants(id),
    CONSTRAINT uk_restaurant_hours_external UNIQUE (provider, external_place_id, day_of_week)
);

CREATE TABLE restaurant_review_summaries (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    restaurant_id BIGINT NOT NULL,
    provider VARCHAR(32) NOT NULL,
    external_place_id VARCHAR(64) NOT NULL,
    visitor_reviews_total INT NULL,
    visitor_reviews_score DECIMAL(4,2) NULL,
    visitor_text_review_total INT NULL,
    cafe_blog_reviews_total INT NULL,
    crawled_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_restaurant_review_summary_restaurant FOREIGN KEY (restaurant_id) REFERENCES restaurants(id),
    CONSTRAINT uk_restaurant_review_summary_external UNIQUE (provider, external_place_id)
);

CREATE TABLE restaurant_review_keywords (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    restaurant_id BIGINT NOT NULL,
    provider VARCHAR(32) NOT NULL,
    external_place_id VARCHAR(64) NOT NULL,
    keyword_kind VARCHAR(32) NOT NULL,
    keyword VARCHAR(255) NOT NULL,
    mention_count INT NULL,
    crawled_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_restaurant_review_keywords_restaurant FOREIGN KEY (restaurant_id) REFERENCES restaurants(id),
    CONSTRAINT uk_restaurant_review_keyword UNIQUE (provider, external_place_id, keyword_kind, keyword)
);

CREATE TABLE restaurant_representative_reviews (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    restaurant_id BIGINT NOT NULL,
    provider VARCHAR(32) NOT NULL,
    external_place_id VARCHAR(64) NOT NULL,
    review_id VARCHAR(128) NOT NULL,
    review_text TEXT NOT NULL,
    review_date VARCHAR(64) NULL,
    rating DECIMAL(4,2) NULL,
    crawled_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_restaurant_reviews_restaurant FOREIGN KEY (restaurant_id) REFERENCES restaurants(id),
    CONSTRAINT uk_restaurant_review_external UNIQUE (provider, external_place_id, review_id)
);
