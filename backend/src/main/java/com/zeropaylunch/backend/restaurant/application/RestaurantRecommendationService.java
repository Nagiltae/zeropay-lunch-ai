package com.zeropaylunch.backend.restaurant.application;

import com.zeropaylunch.backend.location.domain.GangnamLocation;
import com.zeropaylunch.backend.restaurant.application.TemporaryRequestParser.RequestConditions;
import com.zeropaylunch.backend.restaurant.domain.Restaurant;
import com.zeropaylunch.backend.restaurant.infrastructure.RestaurantJpaRepository;
import java.time.Clock;
import java.time.ZonedDateTime;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class RestaurantRecommendationService {

    private static final int MAX_RECOMMENDATIONS = 3;

    private final RestaurantJpaRepository restaurantRepository;
    private final TemporaryRequestParser requestParser;
    private final Clock clock;

    public RestaurantRecommendationService(
            RestaurantJpaRepository restaurantRepository,
            TemporaryRequestParser requestParser,
            Clock clock
    ) {
        this.restaurantRepository = restaurantRepository;
        this.requestParser = requestParser;
        this.clock = clock;
    }

    @Transactional(readOnly = true)
    public List<RecommendationItem> recommend(String message, String requestedLocationId) {
        GangnamLocation requestedLocation = GangnamLocation.fromId(requestedLocationId);
        RequestConditions conditions = requestParser.parse(message);
        ZonedDateTime now = ZonedDateTime.now(clock);

        return restaurantRepository.findOpenRestaurants(
                        now.getDayOfWeek().name(),
                        now.toLocalTime().truncatedTo(ChronoUnit.SECONDS)
                ).stream()
                .filter(restaurant -> matchesRequiredConditions(restaurant, conditions))
                .sorted(Comparator
                        .comparingInt((Restaurant restaurant) -> score(
                                restaurant, requestedLocation, conditions
                        )).reversed()
                        .thenComparingInt(Restaurant::getAveragePrice)
                        .thenComparing(Restaurant::getId))
                .limit(MAX_RECOMMENDATIONS)
                .map(restaurant -> toRecommendation(
                        restaurant, requestedLocation, conditions
                ))
                .toList();
    }

    private boolean matchesRequiredConditions(
            Restaurant restaurant,
            RequestConditions conditions
    ) {
        if (conditions.maximumPrice() != null
                && restaurant.getAveragePrice() > conditions.maximumPrice()) {
            return false;
        }
        if (conditions.category().isPresent()
                && restaurant.getCategory() != conditions.category().get()) {
            return false;
        }
        return !conditions.zeroPayRequired() || restaurant.isZeroPayAvailable();
    }

    private int score(
            Restaurant restaurant,
            GangnamLocation requestedLocation,
            RequestConditions conditions
    ) {
        int score = 0;
        if (restaurant.getLocationId().equals(requestedLocation.id())) {
            score += 40;
        }
        if (conditions.maximumPrice() == null
                || restaurant.getAveragePrice() <= conditions.maximumPrice()) {
            score += 20;
        }
        if (conditions.category().isEmpty()
                || restaurant.getCategory() == conditions.category().get()) {
            score += 20;
        }
        if (restaurant.isZeroPayAvailable()) {
            score += 10;
        }
        return score;
    }

    private RecommendationItem toRecommendation(
            Restaurant restaurant,
            GangnamLocation requestedLocation,
            RequestConditions conditions
    ) {
        GangnamLocation restaurantLocation = GangnamLocation.fromId(restaurant.getLocationId());
        List<String> reasons = new ArrayList<>();
        if (restaurantLocation == requestedLocation) {
            reasons.add("선택한 " + requestedLocation.label() + " 기준 위치와 일치해요");
        } else {
            reasons.add("강남구 내 " + restaurantLocation.label() + " 인근이에요");
        }
        if (conditions.maximumPrice() != null) {
            reasons.add("요청한 예산 안이에요");
        }
        if (restaurant.isZeroPayAvailable()) {
            reasons.add("제로페이를 사용할 수 있어요");
        }

        return new RecommendationItem(
                restaurant.getId(),
                restaurant.getName(),
                restaurant.getCategory().label(),
                restaurant.getRepresentativeMenu(),
                restaurant.getAveragePrice(),
                restaurant.getAddress(),
                restaurant.getLocationId(),
                restaurantLocation.label(),
                restaurant.isZeroPayAvailable(),
                restaurant.isSampleData(),
                String.join(". ", reasons) + "."
        );
    }
}
