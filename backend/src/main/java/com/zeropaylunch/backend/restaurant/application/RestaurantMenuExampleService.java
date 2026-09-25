package com.zeropaylunch.backend.restaurant.application;

import com.zeropaylunch.backend.restaurant.application.RecommendationItem.MenuExample;
import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Reads source-ordered examples only from a currently verified NAVER menu snapshot. */
@Service
public class RestaurantMenuExampleService {
    private final JdbcTemplate jdbcTemplate;

    public RestaurantMenuExampleService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional(readOnly = true)
    public List<MenuExample> findExamples(long restaurantId) {
        return jdbcTemplate.query("""
                SELECT menu.name, menu.price_value
                FROM restaurants restaurant
                JOIN restaurant_external_places place
                  ON place.restaurant_id = restaurant.id
                 AND place.provider = 'NAVER'
                 AND place.match_status = 'MATCHED'
                 AND place.external_place_id REGEXP '^[0-9]+$'
                JOIN restaurant_naver_verifications verification
                  ON verification.restaurant_id = restaurant.id
                 AND verification.provider = 'NAVER'
                 AND verification.verification_status = 'VERIFIED'
                JOIN restaurant_detail_section_states state
                  ON state.restaurant_id = restaurant.id
                 AND state.provider = 'NAVER'
                 AND state.external_place_id = place.external_place_id
                 AND state.section = 'menu'
                 AND state.state = 'SUCCESS'
                 AND state.checked_at >= CURRENT_TIMESTAMP - INTERVAL 30 DAY
                JOIN restaurant_menus menu
                  ON menu.restaurant_id = restaurant.id
                 AND menu.provider = 'NAVER'
                 AND menu.external_place_id = place.external_place_id
                 AND menu.active = TRUE
                WHERE restaurant.id = ?
                  AND restaurant.source_provider = 'KOMSCO'
                ORDER BY CASE WHEN menu.external_menu_id REGEXP '^dom-[0-9]+$' THEN 0 ELSE 1 END,
                         CAST(SUBSTRING(menu.external_menu_id, 5) AS UNSIGNED), menu.id
                LIMIT 3
                """, (rs, rowNum) -> new MenuExample(rs.getString("name"),
                rs.getObject("price_value", Integer.class)), restaurantId);
    }
}
