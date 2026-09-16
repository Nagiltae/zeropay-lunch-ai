package com.zeropaylunch.backend.meal.infrastructure;

import com.zeropaylunch.backend.meal.domain.MealHistory;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface MealHistoryJpaRepository extends JpaRepository<MealHistory, UUID> {

    List<MealHistory> findByUserIdAndEatenAtGreaterThanEqualOrderByEatenAtDesc(
            UUID userId,
            Instant earliestEatenAt
    );

    Optional<MealHistory> findByUserIdAndSourceMessageIdAndRestaurantId(
            UUID userId,
            UUID sourceMessageId,
            Long restaurantId
    );
}
