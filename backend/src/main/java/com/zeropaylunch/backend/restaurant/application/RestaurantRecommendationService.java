/**
 * 사용자 취향·ZeroPay·영업 상태를 적용해 추천 후보를 필터링하고 순위를 계산한다.
 * 자연어 해석 fallback과 DB 후보 조회 이후 최종 business ranking을 소유한다.
 */
package com.zeropaylunch.backend.restaurant.application;

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

    public RestaurantRecommendationService(RestaurantJpaRepository restaurantRepository,
            RecommendationContextService contextService, Clock clock) {
        this.restaurantRepository = restaurantRepository;
        this.contextService = contextService;
        this.clock = clock;
    }

    @Transactional(readOnly = true)
    public List<RecommendationItem> recommend(UUID userId, String message) {
        RecommendationContext context = contextService.build(userId, message);
        AnalyzedIntent intent = context.intent();
        IntentAnalysisRequest request = context.request();
        Integer budget = intent.maximumPrice() != null ? intent.maximumPrice() : request.defaultBudget();
        Set<Long> recent = request.recentMeals().stream()
                .map(IntentAnalysisRequest.RecentMeal::restaurantId).collect(Collectors.toSet());
        ZonedDateTime now = ZonedDateTime.now(clock);
        return restaurantRepository.findOpenRestaurants(now.getDayOfWeek().name(),
                        now.toLocalTime().truncatedTo(ChronoUnit.SECONDS)).stream()
                .filter(r -> matches(r, intent, request, budget, recent))
                .sorted(Comparator.comparingInt((Restaurant r) -> score(r, intent, request, budget))
                        .reversed().thenComparingInt(Restaurant::getAveragePrice).thenComparing(Restaurant::getId))
                .limit(MAX_RECOMMENDATIONS)
                .map(r -> toRecommendation(r, request, budget)).toList();
    }

    private boolean matches(Restaurant r, AnalyzedIntent intent, IntentAnalysisRequest request,
            Integer budget, Set<Long> recent) {
        if (!r.isZeroPayAvailable()) return false;
        if (budget != null && r.getAveragePrice() > budget) return false;
        if (intent.category().isPresent() && r.getCategory() != intent.category().get()) return false;
        if (request.dislikedCategories().contains(r.getCategory())) return false;
        return !recent.contains(r.getId());
    }

    private int score(Restaurant r, AnalyzedIntent intent, IntentAnalysisRequest request, Integer budget) {
        int score = 10;
        if (budget == null || r.getAveragePrice() <= budget) score += 20;
        if (intent.category().isEmpty() || r.getCategory() == intent.category().get()) score += 20;
        if (request.preferredCategories().contains(r.getCategory())) score += 15;
        return score;
    }

    private RecommendationItem toRecommendation(Restaurant r, IntentAnalysisRequest request, Integer budget) {
        List<String> reasons = new ArrayList<>();
        reasons.add("강남구 논현동 서비스 범위 음식점이에요");
        if (budget != null) reasons.add("설정하거나 요청한 예산 안이에요");
        if (request.preferredCategories().contains(r.getCategory())) reasons.add("선호하는 음식 종류예요");
        reasons.add("제로페이를 사용할 수 있어요");
        return new RecommendationItem(r.getId(), r.getName(), r.getCategory().label(),
                r.getRepresentativeMenu(), r.getAveragePrice(), r.getAddress(),
                r.isZeroPayAvailable(), r.isSampleData(), String.join(". ", reasons) + ".");
    }
}
