package com.zeropaylunch.backend.restaurant.application;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Clock;
import java.time.Duration;
import java.time.LocalDate;
import java.time.LocalTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Resolves live KOMSCO serving candidates from the verified source tables, without copying schedules. */
@Service
public class VerifiedNaverServingCandidateService {
    private static final Duration DETAIL_FRESHNESS = Duration.ofDays(30);
    private static final String SOURCE_QUERY = """
            SELECT restaurant.id, hours.day_of_week, hours.open_time, hours.close_time,
                   hours.break_hours, hours.regular_closed_day, hours.irregular_closed_day,
                   hours.description
            FROM restaurants restaurant
            JOIN restaurant_external_places place
              ON place.restaurant_id = restaurant.id AND place.provider = 'NAVER'
             AND place.match_status = 'MATCHED' AND place.external_place_id REGEXP '^[0-9]+$'
            JOIN restaurant_naver_verifications verification
              ON verification.restaurant_id = restaurant.id AND verification.provider = 'NAVER'
             AND verification.verification_status = 'VERIFIED'
             AND (verification.external_place_id IS NULL
                  OR verification.external_place_id = place.external_place_id)
            JOIN restaurant_detail_section_states menu_state
              ON menu_state.restaurant_id = restaurant.id AND menu_state.provider = 'NAVER'
             AND menu_state.external_place_id = place.external_place_id
             AND menu_state.section = 'menu' AND menu_state.state = 'SUCCESS'
             AND menu_state.checked_at >= ?
            JOIN restaurant_detail_section_states hours_state
              ON hours_state.restaurant_id = restaurant.id AND hours_state.provider = 'NAVER'
             AND hours_state.external_place_id = place.external_place_id
             AND hours_state.section = 'business_hours' AND hours_state.state = 'SUCCESS'
             AND hours_state.checked_at >= ?
            JOIN restaurant_menus menu
              ON menu.restaurant_id = restaurant.id AND menu.provider = 'NAVER'
             AND menu.external_place_id = place.external_place_id AND menu.active = TRUE
            JOIN restaurant_business_hours hours
              ON hours.restaurant_id = restaurant.id AND hours.provider = 'NAVER'
             AND hours.external_place_id = place.external_place_id AND hours.active = TRUE
            WHERE restaurant.source_provider = 'KOMSCO'
              AND restaurant.active = TRUE
              AND restaurant.recommendation_eligibility = 'ELIGIBLE'
              AND restaurant.zero_pay_available = TRUE
              AND restaurant.legal_dong_code = '11680108'
              AND (SELECT COUNT(*) FROM restaurant_external_places owner
                   WHERE owner.provider = 'NAVER' AND owner.match_status = 'MATCHED'
                     AND owner.external_place_id = place.external_place_id) = 1
            ORDER BY restaurant.id, hours.id
            """;

    private final JdbcTemplate jdbcTemplate;
    private final VerifiedHoursPolicy hoursPolicy;
    private final ServingReadinessPolicy readinessPolicy;
    private final Clock clock;

    public VerifiedNaverServingCandidateService(JdbcTemplate jdbcTemplate, Clock clock) {
        this.jdbcTemplate = jdbcTemplate;
        this.hoursPolicy = new VerifiedHoursPolicy();
        this.readinessPolicy = new ServingReadinessPolicy();
        this.clock = clock;
    }

    @Transactional(readOnly = true)
    public List<Long> findOpenCandidateIds(LocalDate date, LocalTime time, Integer budget) {
        // Until an approved menu-role snapshot is imported, unknown price basis is not a budget pass.
        if (budget != null) return List.of();
        Map<Long, List<VerifiedHoursPolicy.SourceHours>> hoursByRestaurant = new LinkedHashMap<>();
        jdbcTemplate.query(SOURCE_QUERY, this::mapRow,
                java.sql.Timestamp.from(clock.instant().minus(DETAIL_FRESHNESS)),
                java.sql.Timestamp.from(clock.instant().minus(DETAIL_FRESHNESS)))
                .forEach(row -> hoursByRestaurant.computeIfAbsent(row.restaurantId(), ignored -> new ArrayList<>())
                        .add(row.hours()));
        return hoursByRestaurant.entrySet().stream()
                .filter(entry -> readinessPolicy.assess(true, true, true, true, true,
                        true, true, true, hoursPolicy.evaluate(entry.getValue(), date, time),
                        false, false).status() == ServingReadinessPolicy.Status.READY)
                .map(Map.Entry::getKey)
                .toList();
    }

    private CandidateHours mapRow(ResultSet resultSet, int rowNumber) throws SQLException {
        return new CandidateHours(resultSet.getLong("id"), new VerifiedHoursPolicy.SourceHours(
                resultSet.getString("day_of_week"), resultSet.getString("open_time"),
                resultSet.getString("close_time"), resultSet.getString("break_hours"),
                resultSet.getString("regular_closed_day"), resultSet.getString("irregular_closed_day"),
                resultSet.getString("description")));
    }

    private record CandidateHours(long restaurantId, VerifiedHoursPolicy.SourceHours hours) { }
}
