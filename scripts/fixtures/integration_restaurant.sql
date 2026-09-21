-- Idempotent, harness-only restaurant in the current Nonhyeon-dong scope.
INSERT INTO restaurants (
    id, name, category, representative_menu, average_price, address, location_id,
    latitude, longitude, zero_pay_available, sample_data, active,
    recommendation_eligibility, legal_dong_code, created_at, updated_at
)
SELECT
    1004, '논현 통합검사 국밥집', 'KOREAN_SOUP', '돼지국밥', 10000,
    '서울특별시 강남구 논현동 1', 'gangnam',
    37.5110000, 127.0280000, TRUE, TRUE, TRUE,
    'ELIGIBLE', '11680108', CURRENT_TIMESTAMP(6), CURRENT_TIMESTAMP(6)
WHERE NOT EXISTS (SELECT 1 FROM restaurants WHERE id = 1004);

INSERT INTO restaurant_schedules (id, restaurant_id, name)
SELECT 2004, 1004, '통합검사 매일 영업'
WHERE NOT EXISTS (SELECT 1 FROM restaurant_schedules WHERE id = 2004);

INSERT INTO restaurant_operating_days (schedule_id, day_of_week)
SELECT 2004, day_value
FROM (
    SELECT 'MONDAY' AS day_value UNION ALL SELECT 'TUESDAY' UNION ALL
    SELECT 'WEDNESDAY' UNION ALL SELECT 'THURSDAY' UNION ALL SELECT 'FRIDAY' UNION ALL
    SELECT 'SATURDAY' UNION ALL SELECT 'SUNDAY'
) AS days
WHERE NOT EXISTS (
    SELECT 1 FROM restaurant_operating_days existing
    WHERE existing.schedule_id = 2004 AND existing.day_of_week = days.day_value
);

INSERT INTO restaurant_operating_hours (id, schedule_id, opens_at, closes_at)
SELECT 3004, 2004, '00:00:00', '23:59:59'
WHERE NOT EXISTS (SELECT 1 FROM restaurant_operating_hours WHERE id = 3004);
