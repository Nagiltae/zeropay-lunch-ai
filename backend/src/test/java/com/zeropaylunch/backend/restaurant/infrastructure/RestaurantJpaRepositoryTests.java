package com.zeropaylunch.backend.restaurant.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.LocalTime;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;

@SpringBootTest
@Transactional
class RestaurantJpaRepositoryTests {

    @Autowired
    private RestaurantJpaRepository restaurantRepository;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @BeforeEach
    void insertRestaurantSchedule() {
        jdbcTemplate.update("""
                INSERT INTO restaurants (
                    id, name, category, representative_menu, average_price, address,
                    location_id, legal_dong_code, zero_pay_available, sample_data, active,
                    recommendation_eligibility, created_at, updated_at
                ) VALUES (
                    9001, '테스트 음식점', 'KOREAN', '테스트 메뉴', 9000, '강남구 테스트 주소',
                    'gangnam', '11680108', TRUE, TRUE, TRUE, 'ELIGIBLE',
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """);
        jdbcTemplate.update("""
                INSERT INTO restaurant_schedules (id, restaurant_id, name)
                VALUES (9101, 9001, '월요일 일정')
                """);
        jdbcTemplate.update("""
                INSERT INTO restaurant_operating_days (id, schedule_id, day_of_week)
                VALUES (9201, 9101, 'MONDAY')
                """);
        jdbcTemplate.update("""
                INSERT INTO restaurant_operating_hours (id, schedule_id, opens_at, closes_at)
                VALUES (9301, 9101, '11:00:00', '21:00:00')
                """);
        jdbcTemplate.update("""
                INSERT INTO restaurant_closed_hours (id, schedule_id, starts_at, ends_at)
                VALUES (9401, 9101, '15:00:00', '17:00:00')
                """);
        jdbcTemplate.update("""
                INSERT INTO restaurants (
                    id, name, category, representative_menu, average_price, address,
                    location_id, legal_dong_code, zero_pay_available, sample_data, active,
                    recommendation_eligibility, created_at, updated_at
                ) VALUES (
                    9002, '제로페이 불가 음식점', 'SALAD', '테스트 샐러드', 8000, '강남구 테스트 주소',
                    'gangnam', '11680108', FALSE, TRUE, TRUE, 'ELIGIBLE',
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """);
        jdbcTemplate.update("""
                INSERT INTO restaurant_schedules (id, restaurant_id, name)
                VALUES (9102, 9002, '월요일 일정')
                """);
        jdbcTemplate.update("""
                INSERT INTO restaurant_operating_days (id, schedule_id, day_of_week)
                VALUES (9202, 9102, 'MONDAY')
                """);
        jdbcTemplate.update("""
                INSERT INTO restaurant_operating_hours (id, schedule_id, opens_at, closes_at)
                VALUES (9302, 9102, '11:00:00', '21:00:00')
                """);
        jdbcTemplate.update("""
                INSERT INTO restaurants (
                    id, name, category, representative_menu, average_price, address,
                    location_id, legal_dong_code, zero_pay_available, sample_data, active, recommendation_ready,
                    created_at, updated_at
                ) VALUES (
                    9003, '보강 전 음식점', NULL, NULL, NULL, '서울특별시 강남구 테스트 주소',
                    NULL, '11680108', TRUE, FALSE, TRUE, FALSE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """);
        jdbcTemplate.update("""
                INSERT INTO restaurant_schedules (id, restaurant_id, name)
                VALUES (9103, 9003, '월요일 일정')
                """);
        jdbcTemplate.update("""
                INSERT INTO restaurant_operating_days (id, schedule_id, day_of_week)
                VALUES (9203, 9103, 'MONDAY')
                """);
        jdbcTemplate.update("""
                INSERT INTO restaurant_operating_hours (id, schedule_id, opens_at, closes_at)
                VALUES (9303, 9103, '11:00:00', '21:00:00')
                """);
    }

    @Test
    void returnsRestaurantDuringOperatingHours() {
        assertThat(restaurantRepository.findOpenRestaurants(
                "MONDAY", LocalTime.of(12, 0)
        )).extracting("id").contains(9001L);
    }

    @Test
    void excludesRestaurantDuringClosedHours() {
        assertThat(restaurantRepository.findOpenRestaurants(
                "MONDAY", LocalTime.of(15, 30)
        )).extracting("id").doesNotContain(9001L);
    }

    @Test
    void excludesRestaurantOutsideOperatingDays() {
        assertThat(restaurantRepository.findOpenRestaurants(
                "SUNDAY", LocalTime.of(12, 0)
        )).extracting("id").doesNotContain(9001L);
    }

    @Test
    void alwaysExcludesRestaurantsWithoutZeroPay() {
        assertThat(restaurantRepository.findOpenRestaurants(
                "MONDAY", LocalTime.of(12, 0)
        )).extracting("id").doesNotContain(9002L);
    }

    @Test
    void excludesRestaurantUntilRecommendationDataIsReady() {
        assertThat(restaurantRepository.findOpenRestaurants(
                "MONDAY", LocalTime.of(12, 0)
        )).extracting("id").doesNotContain(9003L);
    }

    @Test
    void excludesRestaurantWhenRecommendationEligibilityIsUnknown() {
        jdbcTemplate.update("""
                UPDATE restaurants
                SET recommendation_eligibility = 'UNKNOWN'
                WHERE id = 9001
                """);

        assertThat(restaurantRepository.findOpenRestaurants(
                "MONDAY", LocalTime.of(12, 0)
        )).extracting("id").doesNotContain(9001L);
    }

    @Test
    void excludesRestaurantOutsideTheFixedNonhyeonLegalDongWithoutDistanceFiltering() {
        jdbcTemplate.update("""
                INSERT INTO restaurants (
                    id, name, category, representative_menu, average_price, address,
                    location_id, legal_dong_code, zero_pay_available, sample_data, active,
                    recommendation_ready, recommendation_eligibility, created_at, updated_at
                ) VALUES (9004, '다른 법정동 식당', 'KOREAN', '테스트 메뉴', 9000,
                    '서울 강남구 인접 동 주소', 'gangnam', '11680107', TRUE, TRUE, TRUE,
                    TRUE, 'ELIGIBLE', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """);
        jdbcTemplate.update("INSERT INTO restaurant_schedules (id, restaurant_id, name) VALUES (9104, 9004, '월요일 일정')");
        jdbcTemplate.update("INSERT INTO restaurant_operating_days (id, schedule_id, day_of_week) VALUES (9204, 9104, 'MONDAY')");
        jdbcTemplate.update("INSERT INTO restaurant_operating_hours (id, schedule_id, opens_at, closes_at) VALUES (9304, 9104, '11:00:00', '21:00:00')");

        assertThat(restaurantRepository.findOpenRestaurants("MONDAY", LocalTime.of(12, 0)))
                .extracting("id").doesNotContain(9004L).contains(9001L);
    }
}
