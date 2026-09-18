ALTER TABLE restaurants
    MODIFY COLUMN category VARCHAR(40);
ALTER TABLE restaurants
    MODIFY COLUMN representative_menu VARCHAR(120);
ALTER TABLE restaurants
    MODIFY COLUMN average_price INT;
ALTER TABLE restaurants
    MODIFY COLUMN location_id VARCHAR(32);

ALTER TABLE restaurants
    ADD COLUMN recommendation_ready BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE restaurants
    ADD COLUMN external_merchant_id VARCHAR(255);
ALTER TABLE restaurants
    ADD COLUMN detail_address VARCHAR(255);
ALTER TABLE restaurants
    ADD COLUMN postal_code VARCHAR(20);
ALTER TABLE restaurants
    ADD COLUMN legal_dong_code VARCHAR(16);
ALTER TABLE restaurants
    ADD COLUMN legal_dong_name VARCHAR(80);
ALTER TABLE restaurants
    ADD COLUMN industry_code VARCHAR(20);
ALTER TABLE restaurants
    ADD COLUMN industry_name VARCHAR(255);
ALTER TABLE restaurants
    ADD COLUMN provider_institution_code VARCHAR(20);
ALTER TABLE restaurants
    ADD COLUMN business_status_code VARCHAR(20);
ALTER TABLE restaurants
    ADD COLUMN business_status_name VARCHAR(80);
ALTER TABLE restaurants
    ADD COLUMN source_reference_date DATE;
ALTER TABLE restaurants
    ADD COLUMN source_provider VARCHAR(32);
ALTER TABLE restaurants
    ADD COLUMN last_synced_at DATETIME(6);

ALTER TABLE restaurants
    ADD CONSTRAINT uk_restaurants_source_merchant
        UNIQUE (source_provider, external_merchant_id);

CREATE INDEX idx_restaurants_source_status
    ON restaurants (source_provider, legal_dong_code, business_status_name);
