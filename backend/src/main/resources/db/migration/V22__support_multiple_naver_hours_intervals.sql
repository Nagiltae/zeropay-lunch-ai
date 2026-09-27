ALTER TABLE restaurant_business_hours
    ADD COLUMN interval_index INT NOT NULL DEFAULT 0 AFTER day_of_week;

ALTER TABLE restaurant_business_hours
    DROP INDEX uk_restaurant_hours_external;

ALTER TABLE restaurant_business_hours
    ADD CONSTRAINT uk_restaurant_hours_external
        UNIQUE (provider, external_place_id, day_of_week, interval_index);
