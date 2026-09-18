ALTER TABLE restaurants
    ADD COLUMN recommendation_eligibility VARCHAR(16) NOT NULL DEFAULT 'UNKNOWN';

UPDATE restaurants
SET recommendation_eligibility = 'ELIGIBLE'
WHERE sample_data = TRUE;

CREATE INDEX idx_restaurants_recommendation_eligibility
    ON restaurants (
        active,
        recommendation_ready,
        recommendation_eligibility,
        zero_pay_available
    );
