package com.zeropaylunch.backend.meal.application;

import com.zeropaylunch.backend.chat.infrastructure.MessageRecommendationJpaRepository;
import com.zeropaylunch.backend.meal.domain.MealHistory;
import com.zeropaylunch.backend.meal.infrastructure.MealHistoryJpaRepository;
import com.zeropaylunch.backend.restaurant.domain.Restaurant;
import com.zeropaylunch.backend.restaurant.infrastructure.RestaurantJpaRepository;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class MealHistoryService {

    public static final Duration RECOMMENDATION_LOOKBACK = Duration.ofDays(3);

    private final MealHistoryJpaRepository mealHistoryRepository;
    private final MessageRecommendationJpaRepository recommendationRepository;
    private final RestaurantJpaRepository restaurantRepository;
    private final Clock clock;

    public MealHistoryService(
            MealHistoryJpaRepository mealHistoryRepository,
            MessageRecommendationJpaRepository recommendationRepository,
            RestaurantJpaRepository restaurantRepository,
            Clock clock
    ) {
        this.mealHistoryRepository = mealHistoryRepository;
        this.recommendationRepository = recommendationRepository;
        this.restaurantRepository = restaurantRepository;
        this.clock = clock;
    }

    @Transactional
    public MealRecord markEaten(UUID userId, UUID sourceMessageId, Long restaurantId) {
        return mealHistoryRepository.findByUserIdAndSourceMessageIdAndRestaurantId(
                        userId, sourceMessageId, restaurantId
                )
                .map(history -> toRecord(history, findRestaurant(restaurantId)))
                .orElseGet(() -> createMealRecord(userId, sourceMessageId, restaurantId));
    }

    @Transactional(readOnly = true)
    public List<MealRecord> findRecent(UUID userId) {
        Instant earliest = clock.instant().minus(RECOMMENDATION_LOOKBACK);
        List<MealHistory> histories = mealHistoryRepository
                .findByUserIdAndEatenAtGreaterThanEqualOrderByEatenAtDesc(userId, earliest);
        Map<Long, Restaurant> restaurants = restaurantRepository.findAllById(
                        histories.stream().map(MealHistory::getRestaurantId).distinct().toList()
                ).stream()
                .collect(Collectors.toMap(Restaurant::getId, Function.identity()));
        return histories.stream()
                .map(history -> toRecord(history, restaurants.get(history.getRestaurantId())))
                .toList();
    }

    private MealRecord createMealRecord(UUID userId, UUID sourceMessageId, Long restaurantId) {
        if (!recommendationRepository.existsOwnedRecommendation(
                userId, sourceMessageId, restaurantId
        )) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "본인에게 추천된 음식점만 식사 기록으로 저장할 수 있습니다."
            );
        }
        Restaurant restaurant = findRestaurant(restaurantId);
        MealHistory history = mealHistoryRepository.save(
                MealHistory.create(userId, restaurantId, sourceMessageId, clock.instant())
        );
        return toRecord(history, restaurant);
    }

    private Restaurant findRestaurant(Long restaurantId) {
        return restaurantRepository.findById(restaurantId)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "음식점을 찾을 수 없습니다."
                ));
    }

    private MealRecord toRecord(MealHistory history, Restaurant restaurant) {
        if (restaurant == null) {
            throw new IllegalStateException("식사 기록의 음식점 정보를 찾을 수 없습니다.");
        }
        return new MealRecord(
                history.getId(),
                history.getRestaurantId(),
                restaurant.getName(),
                restaurant.getCategory(),
                history.getSourceMessageId(),
                history.getEatenAt()
        );
    }

    public record MealRecord(
            UUID mealId,
            Long restaurantId,
            String restaurantName,
            com.zeropaylunch.backend.restaurant.domain.RestaurantCategory category,
            UUID sourceMessageId,
            Instant eatenAt
    ) {
    }
}
