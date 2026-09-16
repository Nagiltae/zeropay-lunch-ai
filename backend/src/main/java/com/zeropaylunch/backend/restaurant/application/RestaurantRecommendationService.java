package com.zeropaylunch.backend.restaurant.application;

import com.zeropaylunch.backend.location.domain.GangnamLocation;
import com.zeropaylunch.backend.recommendation.ai.AnalyzedIntent;
import com.zeropaylunch.backend.recommendation.ai.IntentAnalysisRequest;
import com.zeropaylunch.backend.recommendation.application.RecommendationContextService;
import com.zeropaylunch.backend.recommendation.application.RecommendationContextService.RecommendationContext;
import com.zeropaylunch.backend.restaurant.domain.Restaurant;
import com.zeropaylunch.backend.restaurant.infrastructure.RestaurantJpaRepository;
import java.time.Clock;
import java.time.ZonedDateTime;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class RestaurantRecommendationService {

    private static final int MAX_RECOMMENDATIONS = 3;

    private final RestaurantJpaRepository restaurantRepository;
    private final RecommendationContextService contextService;
    private final Clock clock;

    public RestaurantRecommendationService(
            RestaurantJpaRepository restaurantRepository,
            RecommendationContextService contextService,
            Clock clock
    ) {
        this.restaurantRepository = restaurantRepository;
        this.contextService = contextService;
        this.clock = clock;
    }

    @Transactional(readOnly = true)
    public List<RecommendationItem> recommend(
            UUID userId,
            String message,
            String requestedLocationId
    ) {
        GangnamLocation requestedLocation = GangnamLocation.fromId(requestedLocationId);
        RecommendationContext context = contextService.build(
                userId, message, requestedLocationId
        );
        AnalyzedIntent intent = context.intent();
        IntentAnalysisRequest request = context.request();
        Integer effectiveBudget = intent.maximumPrice() != null
                ? intent.maximumPrice()
                : request.defaultBudget();
        Set<Long> recentRestaurantIds = request.recentMeals().stream()
                .map(IntentAnalysisRequest.RecentMeal::restaurantId)
                .collect(Collectors.toSet());
        ZonedDateTime now = ZonedDateTime.now(clock);

        return restaurantRepository.findOpenRestaurants(
                        now.getDayOfWeek().name(),
                        now.toLocalTime().truncatedTo(ChronoUnit.SECONDS)
                ).stream()
                .filter(restaurant -> matchesRequiredConditions(
                        restaurant, intent, request, effectiveBudget, recentRestaurantIds
                ))
                .sorted(Comparator
                        .comparingInt((Restaurant restaurant) -> score(
                                restaurant, requestedLocation, intent, request, effectiveBudget
                        )).reversed()
                        .thenComparingInt(Restaurant::getAveragePrice)
                        .thenComparing(Restaurant::getId))
                .limit(MAX_RECOMMENDATIONS)
                .map(restaurant -> toRecommendation(
                        restaurant, requestedLocation, intent, request, effectiveBudget
                ))
                .toList();
    }

    private boolean matchesRequiredConditions(
            Restaurant restaurant,
            AnalyzedIntent intent,
            IntentAnalysisRequest request,
            Integer effectiveBudget,
            Set<Long> recentRestaurantIds
    ) {
        if (!restaurant.isZeroPayAvailable()) {
            return false;
        }
        if (effectiveBudget != null && restaurant.getAveragePrice() > effectiveBudget) {
            return false;
        }
        if (intent.category().isPresent()
                && restaurant.getCategory() != intent.category().get()) {
            return false;
        }
        if (request.dislikedCategories().contains(restaurant.getCategory())) {
            return false;
        }
        return !recentRestaurantIds.contains(restaurant.getId());
    }

    private int score(
            Restaurant restaurant,
            GangnamLocation requestedLocation,
            AnalyzedIntent intent,
            IntentAnalysisRequest request,
            Integer effectiveBudget
    ) {
        int score = 0;
        if (restaurant.getLocationId().equals(requestedLocation.id())) {
            score += 40;
        }
        if (effectiveBudget == null || restaurant.getAveragePrice() <= effectiveBudget) {
            score += 20;
        }
        if (intent.category().isEmpty()
                || restaurant.getCategory() == intent.category().get()) {
            score += 20;
        }
        if (request.preferredCategories().contains(restaurant.getCategory())) {
            score += 15;
        }
        score += 10;
        return score;
    }

    private RecommendationItem toRecommendation(
            Restaurant restaurant,
            GangnamLocation requestedLocation,
            AnalyzedIntent intent,
            IntentAnalysisRequest request,
            Integer effectiveBudget
    ) {
        GangnamLocation restaurantLocation = GangnamLocation.fromId(restaurant.getLocationId());
        List<String> reasons = new ArrayList<>();
        if (restaurantLocation == requestedLocation) {
            reasons.add("선택한 " + requestedLocation.label() + " 기준 위치와 일치해요");
        } else {
            reasons.add("강남구 내 " + restaurantLocation.label() + " 인근이에요");
        }
        if (effectiveBudget != null) {
            reasons.add("설정하거나 요청한 예산 안이에요");
        }
        if (request.preferredCategories().contains(restaurant.getCategory())) {
            reasons.add("선호하는 음식 종류예요");
        }
        reasons.add("제로페이를 사용할 수 있어요");

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
