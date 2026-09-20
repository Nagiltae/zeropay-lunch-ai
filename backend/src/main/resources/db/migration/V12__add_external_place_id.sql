ALTER TABLE restaurant_external_places
    ADD COLUMN external_place_id VARCHAR(64) NULL AFTER provider;

CREATE UNIQUE INDEX uk_external_places_provider_place_id
    ON restaurant_external_places (provider, external_place_id);
