INSERT INTO restaurants (
    id, name, category, representative_menu, average_price, address, location_id,
    latitude, longitude, zero_pay_available, sample_data, active,
    recommendation_eligibility, created_at, updated_at
)
SELECT
    1001, '강남 샘플 한식당', 'KOREAN', '제육볶음', 9000,
    '서울특별시 강남구 강남대로 샘플 101', 'gangnam',
    37.4979520, 127.0276190, TRUE, TRUE, TRUE,
    'ELIGIBLE', CURRENT_TIMESTAMP(6), CURRENT_TIMESTAMP(6)
WHERE NOT EXISTS (SELECT 1 FROM restaurants WHERE id = 1001);

INSERT INTO restaurants (
    id, name, category, representative_menu, average_price, address, location_id,
    latitude, longitude, zero_pay_available, sample_data, active,
    recommendation_eligibility, created_at, updated_at
)
SELECT
    1002, '역삼 샘플 국밥집', 'KOREAN_SOUP', '돼지국밥', 10000,
    '서울특별시 강남구 테헤란로 샘플 202', 'yeoksam',
    37.5006580, 127.0364300, TRUE, TRUE, TRUE,
    'ELIGIBLE', CURRENT_TIMESTAMP(6), CURRENT_TIMESTAMP(6)
WHERE NOT EXISTS (SELECT 1 FROM restaurants WHERE id = 1002);

INSERT INTO restaurants (
    id, name, category, representative_menu, average_price, address, location_id,
    latitude, longitude, zero_pay_available, sample_data, active,
    recommendation_eligibility, created_at, updated_at
)
SELECT
    1003, '선릉 샘플 샐러드', 'SALAD', '닭가슴살 샐러드', 11000,
    '서울특별시 강남구 선릉로 샘플 303', 'seolleung',
    37.5044870, 127.0489570, FALSE, TRUE, TRUE,
    'ELIGIBLE', CURRENT_TIMESTAMP(6), CURRENT_TIMESTAMP(6)
WHERE NOT EXISTS (SELECT 1 FROM restaurants WHERE id = 1003);

INSERT INTO restaurant_schedules (id, restaurant_id, name)
SELECT 2001, 1001, '평일 영업'
WHERE NOT EXISTS (SELECT 1 FROM restaurant_schedules WHERE id = 2001);
INSERT INTO restaurant_schedules (id, restaurant_id, name)
SELECT 2002, 1002, '매일 영업'
WHERE NOT EXISTS (SELECT 1 FROM restaurant_schedules WHERE id = 2002);
INSERT INTO restaurant_schedules (id, restaurant_id, name)
SELECT 2003, 1003, '월요일부터 토요일 영업'
WHERE NOT EXISTS (SELECT 1 FROM restaurant_schedules WHERE id = 2003);

INSERT INTO restaurant_operating_days (schedule_id, day_of_week)
SELECT 2001, day_value
FROM (
    SELECT 'MONDAY' AS day_value UNION ALL SELECT 'TUESDAY' UNION ALL
    SELECT 'WEDNESDAY' UNION ALL SELECT 'THURSDAY' UNION ALL SELECT 'FRIDAY'
) AS days
WHERE NOT EXISTS (
    SELECT 1 FROM restaurant_operating_days existing
    WHERE existing.schedule_id = 2001 AND existing.day_of_week = days.day_value
);

INSERT INTO restaurant_operating_days (schedule_id, day_of_week)
SELECT 2002, day_value
FROM (
    SELECT 'MONDAY' AS day_value UNION ALL SELECT 'TUESDAY' UNION ALL
    SELECT 'WEDNESDAY' UNION ALL SELECT 'THURSDAY' UNION ALL SELECT 'FRIDAY' UNION ALL
    SELECT 'SATURDAY' UNION ALL SELECT 'SUNDAY'
) AS days
WHERE NOT EXISTS (
    SELECT 1 FROM restaurant_operating_days existing
    WHERE existing.schedule_id = 2002 AND existing.day_of_week = days.day_value
);

INSERT INTO restaurant_operating_days (schedule_id, day_of_week)
SELECT 2003, day_value
FROM (
    SELECT 'MONDAY' AS day_value UNION ALL SELECT 'TUESDAY' UNION ALL
    SELECT 'WEDNESDAY' UNION ALL SELECT 'THURSDAY' UNION ALL SELECT 'FRIDAY' UNION ALL
    SELECT 'SATURDAY'
) AS days
WHERE NOT EXISTS (
    SELECT 1 FROM restaurant_operating_days existing
    WHERE existing.schedule_id = 2003 AND existing.day_of_week = days.day_value
);

INSERT INTO restaurant_operating_hours (id, schedule_id, opens_at, closes_at)
SELECT 3001, 2001, '11:00:00', '21:00:00'
WHERE NOT EXISTS (SELECT 1 FROM restaurant_operating_hours WHERE id = 3001);
INSERT INTO restaurant_operating_hours (id, schedule_id, opens_at, closes_at)
SELECT 3002, 2002, '00:00:00', '23:59:59'
WHERE NOT EXISTS (SELECT 1 FROM restaurant_operating_hours WHERE id = 3002);
INSERT INTO restaurant_operating_hours (id, schedule_id, opens_at, closes_at)
SELECT 3003, 2003, '10:30:00', '20:30:00'
WHERE NOT EXISTS (SELECT 1 FROM restaurant_operating_hours WHERE id = 3003);

INSERT INTO restaurant_closed_days (restaurant_id, day_of_week)
SELECT 1001, 'SATURDAY'
WHERE NOT EXISTS (
    SELECT 1 FROM restaurant_closed_days WHERE restaurant_id = 1001 AND day_of_week = 'SATURDAY'
);
INSERT INTO restaurant_closed_days (restaurant_id, day_of_week)
SELECT 1001, 'SUNDAY'
WHERE NOT EXISTS (
    SELECT 1 FROM restaurant_closed_days WHERE restaurant_id = 1001 AND day_of_week = 'SUNDAY'
);
INSERT INTO restaurant_closed_days (restaurant_id, day_of_week)
SELECT 1003, 'SUNDAY'
WHERE NOT EXISTS (
    SELECT 1 FROM restaurant_closed_days WHERE restaurant_id = 1003 AND day_of_week = 'SUNDAY'
);

INSERT INTO restaurant_closed_hours (id, schedule_id, starts_at, ends_at)
SELECT 4001, 2001, '15:00:00', '17:00:00'
WHERE NOT EXISTS (SELECT 1 FROM restaurant_closed_hours WHERE id = 4001);
INSERT INTO restaurant_closed_hours (id, schedule_id, starts_at, ends_at)
SELECT 4002, 2003, '15:00:00', '16:00:00'
WHERE NOT EXISTS (SELECT 1 FROM restaurant_closed_hours WHERE id = 4002);
