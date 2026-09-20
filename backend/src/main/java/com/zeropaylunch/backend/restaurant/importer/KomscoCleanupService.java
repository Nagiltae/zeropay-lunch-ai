package com.zeropaylunch.backend.restaurant.importer;

import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** One-time KOMSCO source reset. Historical user references are protected. */
@Service
public class KomscoCleanupService {

    private static final String TARGET = "r.source_provider = 'KOMSCO'";
    private static final String DELETABLE = TARGET
            + " AND NOT EXISTS (SELECT 1 FROM meal_history h WHERE h.restaurant_id=r.id)"
            + " AND NOT EXISTS (SELECT 1 FROM message_recommendations m WHERE m.restaurant_id=r.id)";
    private final JdbcTemplate jdbc;

    KomscoCleanupService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(readOnly = true)
    public KomscoCleanupPlan dryRun() {
        Map<String, Long> counts = new LinkedHashMap<>();
        counts.put("restaurants", count("SELECT COUNT(*) FROM restaurants r WHERE " + DELETABLE));
        for (String table : new String[]{"restaurant_external_places", "restaurant_business_hours", "restaurant_menus",
                "restaurant_review_summaries", "restaurant_review_keywords", "restaurant_representative_reviews",
                "restaurant_closed_days"}) {
            counts.put(table, count("SELECT COUNT(*) FROM " + table + " x JOIN restaurants r ON r.id=x.restaurant_id WHERE " + DELETABLE));
        }
        for (String table : new String[]{"restaurant_operating_days", "restaurant_operating_hours", "restaurant_closed_hours"}) {
            counts.put(table, count("SELECT COUNT(*) FROM " + table + " x JOIN restaurant_schedules s ON s.id=x.schedule_id JOIN restaurants r ON r.id=s.restaurant_id WHERE " + DELETABLE));
        }
        counts.put("restaurant_schedules", count("SELECT COUNT(*) FROM restaurant_schedules x JOIN restaurants r ON r.id=x.restaurant_id WHERE " + DELETABLE));
        counts.put("protected_by_user_history", count("""
                SELECT COUNT(*) FROM restaurants r
                WHERE r.source_provider = 'KOMSCO'
                  AND (EXISTS (SELECT 1 FROM meal_history h WHERE h.restaurant_id=r.id)
                    OR EXISTS (SELECT 1 FROM message_recommendations m WHERE m.restaurant_id=r.id))
                """));
        counts.put("protected_meal_history", count("""
                SELECT COUNT(*) FROM restaurants r
                WHERE r.source_provider = 'KOMSCO'
                  AND EXISTS (SELECT 1 FROM meal_history h WHERE h.restaurant_id=r.id)
                """));
        counts.put("protected_message_recommendations", count("""
                SELECT COUNT(*) FROM restaurants r
                WHERE r.source_provider = 'KOMSCO'
                  AND EXISTS (SELECT 1 FROM message_recommendations m WHERE m.restaurant_id=r.id)
                """));
        counts.put("protected_overlap", count("""
                SELECT COUNT(*) FROM restaurants r
                WHERE r.source_provider = 'KOMSCO'
                  AND EXISTS (SELECT 1 FROM meal_history h WHERE h.restaurant_id=r.id)
                  AND EXISTS (SELECT 1 FROM message_recommendations m WHERE m.restaurant_id=r.id)
                """));
        return new KomscoCleanupPlan(counts);
    }

    @Transactional
    public KomscoCleanupPlan cleanup() {
        KomscoCleanupPlan plan = dryRun();
        delete("restaurant_business_hours");
        delete("restaurant_menus");
        delete("restaurant_review_summaries");
        delete("restaurant_review_keywords");
        delete("restaurant_representative_reviews");
        delete("restaurant_external_places");
        delete("restaurant_operating_days", "schedule_id");
        delete("restaurant_operating_hours", "schedule_id");
        delete("restaurant_closed_hours", "schedule_id");
        delete("restaurant_closed_days");
        delete("restaurant_schedules");
        jdbc.update("""
                DELETE r FROM restaurants r
                WHERE r.source_provider = 'KOMSCO'
                  AND NOT EXISTS (SELECT 1 FROM meal_history h WHERE h.restaurant_id=r.id)
                  AND NOT EXISTS (SELECT 1 FROM message_recommendations m WHERE m.restaurant_id=r.id)
                """);
        return plan;
    }

    private long count(String sql) {
        Long value = jdbc.queryForObject(sql, Long.class);
        return value == null ? 0 : value;
    }

    private void delete(String table) {
        jdbc.update("DELETE x FROM " + table + " x JOIN restaurants r ON r.id=x.restaurant_id WHERE " + TARGET
                + " AND NOT EXISTS (SELECT 1 FROM meal_history h WHERE h.restaurant_id=r.id)"
                + " AND NOT EXISTS (SELECT 1 FROM message_recommendations m WHERE m.restaurant_id=r.id)");
    }

    private void delete(String table, String scheduleColumn) {
        jdbc.update("DELETE x FROM " + table + " x JOIN restaurant_schedules s ON s.id=x." + scheduleColumn
                + " JOIN restaurants r ON r.id=s.restaurant_id WHERE " + TARGET
                + " AND NOT EXISTS (SELECT 1 FROM meal_history h WHERE h.restaurant_id=r.id)"
                + " AND NOT EXISTS (SELECT 1 FROM message_recommendations m WHERE m.restaurant_id=r.id)");
    }

    public record KomscoCleanupPlan(Map<String, Long> rows) {
        public long restaurants() { return rows.getOrDefault("restaurants", 0L); }
        public long protectedRestaurants() { return rows.getOrDefault("protected_by_user_history", 0L); }
        public long mealHistoryReferences() { return rows.getOrDefault("protected_meal_history", 0L); }
        public long messageRecommendationReferences() { return rows.getOrDefault("protected_message_recommendations", 0L); }
        public long protectedOverlap() { return rows.getOrDefault("protected_overlap", 0L); }
    }
}
