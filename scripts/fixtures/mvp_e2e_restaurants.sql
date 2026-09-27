INSERT INTO restaurants (
    id, name, category, representative_menu, average_price, address, location_id,
    zero_pay_available, sample_data, active, recommendation_ready,
    recommendation_eligibility, legal_dong_code, legal_dong_name,
    created_at, updated_at
) VALUES
    (9617, '마성김밥 논현역점', 'KOREAN', '김밥, 떡볶이', 9000,
     '서울특별시 강남구 논현동 1-1', 'gangnam', TRUE, TRUE, TRUE, TRUE,
     'ELIGIBLE', '11680108', '논현동', UTC_TIMESTAMP(6), UTC_TIMESTAMP(6)),
    (9568, 'E2E Verified Candidate 9568', NULL, NULL, NULL,
     '서울특별시 강남구 논현동 1-2', 'gangnam', TRUE, FALSE, TRUE, TRUE,
     'ELIGIBLE', '11680108', '논현동', UTC_TIMESTAMP(6), UTC_TIMESTAMP(6)),
    (9569, 'E2E Verified Candidate 9569', NULL, NULL, NULL,
     '서울특별시 강남구 논현동 1-3', 'gangnam', TRUE, FALSE, TRUE, TRUE,
     'ELIGIBLE', '11680108', '논현동', UTC_TIMESTAMP(6), UTC_TIMESTAMP(6)),
    (9570, 'E2E Verified Candidate 9570', NULL, NULL, NULL,
     '서울특별시 강남구 논현동 1-4', 'gangnam', TRUE, FALSE, TRUE, TRUE,
     'ELIGIBLE', '11680108', '논현동', UTC_TIMESTAMP(6), UTC_TIMESTAMP(6)),
    (9571, 'E2E Verified Candidate 9571', NULL, NULL, NULL,
     '서울특별시 강남구 논현동 1-5', 'gangnam', TRUE, FALSE, TRUE, TRUE,
     'ELIGIBLE', '11680108', '논현동', UTC_TIMESTAMP(6), UTC_TIMESTAMP(6)),
    (9580, 'E2E Verified Candidate 9580', NULL, NULL, NULL,
     '서울특별시 강남구 논현동 1-6', 'gangnam', TRUE, FALSE, TRUE, TRUE,
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

-- Exercise the current verified NAVER serving-candidate path, not the legacy readiness gate.
UPDATE restaurants
SET source_provider = 'KOMSCO', recommendation_ready = FALSE
WHERE id IN (9617, 9568, 9569, 9570, 9571, 9580);

INSERT INTO restaurant_external_places (
    restaurant_id, provider, external_name, match_status, match_score, query_used,
    external_place_id, last_synced_at, created_at, updated_at
)
SELECT id, 'NAVER', name, 'MATCHED', 100, 'isolated-e2e fixture',
       CONCAT(id, '0001'), UTC_TIMESTAMP(6), UTC_TIMESTAMP(6), UTC_TIMESTAMP(6)
FROM restaurants WHERE id IN (9617, 9568, 9569, 9570, 9571, 9580);

INSERT INTO restaurant_naver_verifications (
    restaurant_id, provider, verification_status, verification_reason,
    external_place_id, verified_at, last_attempt_at
)
SELECT id, 'NAVER', 'VERIFIED', 'ISOLATED_E2E_FIXTURE', CONCAT(id, '0001'),
       UTC_TIMESTAMP(6), UTC_TIMESTAMP(6)
FROM restaurants WHERE id IN (9617, 9568, 9569, 9570, 9571, 9580);

INSERT INTO restaurant_detail_section_states (
    restaurant_id, provider, external_place_id, section, state, checked_at
)
SELECT id, 'NAVER', CONCAT(id, '0001'), section_name, 'SUCCESS', UTC_TIMESTAMP(6)
FROM restaurants
CROSS JOIN (SELECT 'menu' AS section_name UNION ALL SELECT 'business_hours') sections
WHERE id IN (9617, 9568, 9569, 9570, 9571, 9580);

INSERT INTO restaurant_menus (
    restaurant_id, provider, external_place_id, external_menu_id, name, price_value, active
)
SELECT id, 'NAVER', CONCAT(id, '0001'), CONCAT('e2e-menu-', id),
       CASE id WHEN 9617 THEN '떡볶이' WHEN 9568 THEN '떡만두국'
           WHEN 9569 THEN '김밥추가' WHEN 9570 THEN '파스타'
           WHEN 9571 THEN '피자' ELSE '피자 세트' END,
       9000, TRUE
FROM restaurants WHERE id IN (9617, 9568, 9569, 9570, 9571, 9580);

INSERT INTO restaurant_business_hours (
    restaurant_id, provider, external_place_id, day_of_week, interval_index,
    open_time, close_time, description, active
)
SELECT restaurants.id, 'NAVER', CONCAT(restaurants.id, '0001'), days.day_of_week, 0,
       '00:00', '24:00', 'isolated E2E all-day source fixture', TRUE
FROM restaurants CROSS JOIN (
    SELECT '월' AS day_of_week UNION ALL SELECT '화' UNION ALL
    SELECT '수' UNION ALL SELECT '목' UNION ALL
    SELECT '금' UNION ALL SELECT '토' UNION ALL SELECT '일'
) days
WHERE restaurants.id IN (9617, 9568, 9569, 9570, 9571, 9580);
