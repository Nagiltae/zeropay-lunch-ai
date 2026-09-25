INSERT INTO restaurants (
    id, name, category, representative_menu, average_price, address, location_id,
    zero_pay_available, sample_data, active, recommendation_ready,
    recommendation_eligibility, legal_dong_code, legal_dong_name,
    created_at, updated_at
) VALUES
    (9617, '마성김밥 논현역점', 'KOREAN', '김밥, 떡볶이', 9000,
     '서울특별시 강남구 논현동 1-1', 'gangnam', TRUE, TRUE, TRUE, TRUE,
     'ELIGIBLE', '11680108', '논현동', UTC_TIMESTAMP(6), UTC_TIMESTAMP(6)),
    (9620, 'E2E 지역 필터 제외점', 'KOREAN', '김밥', 8000,
     '서울특별시 강남구 역삼동 1-1', 'gangnam', TRUE, TRUE, TRUE, TRUE,
     'ELIGIBLE', '11680101', '역삼동', UTC_TIMESTAMP(6), UTC_TIMESTAMP(6));

INSERT INTO restaurant_schedules (restaurant_id, name) VALUES
    (9617, 'E2E all day'),
    (9620, 'E2E all day');

INSERT INTO restaurant_operating_days (schedule_id, day_of_week)
SELECT schedule.id, days.day_of_week
FROM restaurant_schedules schedule
CROSS JOIN (
    SELECT 'MONDAY' AS day_of_week UNION ALL SELECT 'TUESDAY' UNION ALL
    SELECT 'WEDNESDAY' UNION ALL SELECT 'THURSDAY' UNION ALL
    SELECT 'FRIDAY' UNION ALL SELECT 'SATURDAY' UNION ALL SELECT 'SUNDAY'
) days
WHERE schedule.restaurant_id IN (9617, 9620);

INSERT INTO restaurant_operating_hours (schedule_id, opens_at, closes_at)
SELECT id, '00:00:00', '23:59:59'
FROM restaurant_schedules
WHERE restaurant_id IN (9617, 9620);
