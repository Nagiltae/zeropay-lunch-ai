ALTER TABLE restaurant_external_places
    MODIFY COLUMN last_synced_at DATETIME(6) NULL;

ALTER TABLE restaurant_external_places
    ADD COLUMN name_score DECIMAL(5, 2) NOT NULL DEFAULT 0.00;
ALTER TABLE restaurant_external_places
    ADD COLUMN address_score DECIMAL(5, 2) NOT NULL DEFAULT 0.00;
ALTER TABLE restaurant_external_places
    ADD COLUMN distance_score DECIMAL(5, 2) NOT NULL DEFAULT 0.00;
ALTER TABLE restaurant_external_places
    ADD COLUMN category_score DECIMAL(5, 2) NOT NULL DEFAULT 0.00;
ALTER TABLE restaurant_external_places
    ADD COLUMN runner_up_score DECIMAL(5, 2) NULL;
ALTER TABLE restaurant_external_places
    ADD COLUMN score_gap DECIMAL(5, 2) NULL;
ALTER TABLE restaurant_external_places
    ADD COLUMN source_content_hash VARCHAR(64) NULL;
ALTER TABLE restaurant_external_places
    ADD COLUMN last_attempt_status VARCHAR(16) NULL;
ALTER TABLE restaurant_external_places
    ADD COLUMN last_match_attempt_at DATETIME(6) NULL;
ALTER TABLE restaurant_external_places
    ADD COLUMN next_retry_at DATETIME(6) NULL;

CREATE INDEX idx_external_places_incremental_retry
    ON restaurant_external_places (provider, last_attempt_status, next_retry_at);

CREATE INDEX idx_external_places_incremental_refresh
    ON restaurant_external_places (provider, match_status, last_synced_at);
