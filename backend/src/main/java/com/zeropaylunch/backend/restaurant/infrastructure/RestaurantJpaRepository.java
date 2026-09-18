package com.zeropaylunch.backend.restaurant.infrastructure;

import com.zeropaylunch.backend.restaurant.domain.Restaurant;
import com.zeropaylunch.backend.restaurant.domain.RestaurantSourceProvider;
import java.time.LocalTime;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface RestaurantJpaRepository extends JpaRepository<Restaurant, Long> {

    Optional<Restaurant> findBySourceProviderAndExternalMerchantId(
            RestaurantSourceProvider sourceProvider, String externalMerchantId);

    List<Restaurant> findAllBySourceProvider(RestaurantSourceProvider sourceProvider);

    List<Restaurant> findBySourceProviderAndActiveTrueOrderByIdAsc(
            RestaurantSourceProvider sourceProvider, Pageable pageable);

    List<Restaurant> findBySourceProviderAndActiveTrueOrderByLegalDongCodeAscIdAsc(
            RestaurantSourceProvider sourceProvider);

    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Query("DELETE FROM Restaurant restaurant WHERE restaurant.sourceProvider = :sourceProvider")
    int deleteAllBySourceProvider(
            @Param("sourceProvider") RestaurantSourceProvider sourceProvider);

    @Query(value = """
            SELECT DISTINCT r.*
            FROM restaurants r
            JOIN restaurant_schedules schedule ON schedule.restaurant_id = r.id
            JOIN restaurant_operating_days operating_day ON operating_day.schedule_id = schedule.id
            JOIN restaurant_operating_hours operating_hour ON operating_hour.schedule_id = schedule.id
            WHERE r.active = TRUE
              AND r.recommendation_ready = TRUE
              AND r.recommendation_eligibility = 'ELIGIBLE'
              AND r.zero_pay_available = TRUE
              AND operating_day.day_of_week = :dayOfWeek
              AND :currentTime >= operating_hour.opens_at
              AND :currentTime <= operating_hour.closes_at
              AND NOT EXISTS (
                  SELECT 1
                  FROM restaurant_closed_days closed_day
                  WHERE closed_day.restaurant_id = r.id
                    AND closed_day.day_of_week = :dayOfWeek
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM restaurant_closed_hours closed_hour
                  WHERE closed_hour.schedule_id = schedule.id
                    AND :currentTime >= closed_hour.starts_at
                    AND :currentTime < closed_hour.ends_at
              )
            """, nativeQuery = true)
    List<Restaurant> findOpenRestaurants(
            @Param("dayOfWeek") String dayOfWeek,
            @Param("currentTime") LocalTime currentTime
    );
}
