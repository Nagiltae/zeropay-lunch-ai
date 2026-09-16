package com.zeropaylunch.backend.restaurant.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.zeropaylunch.backend.preference.domain.SpiceLevel;
import com.zeropaylunch.backend.recommendation.ai.AnalyzedIntent;
import com.zeropaylunch.backend.recommendation.ai.AnalyzedIntent.IntentType;
import com.zeropaylunch.backend.recommendation.ai.IntentAnalysisRequest;
import com.zeropaylunch.backend.recommendation.application.RecommendationContextService;
import com.zeropaylunch.backend.recommendation.application.RecommendationContextService.RecommendationContext;
import com.zeropaylunch.backend.restaurant.domain.Restaurant;
import com.zeropaylunch.backend.restaurant.domain.RestaurantCategory;
import com.zeropaylunch.backend.restaurant.infrastructure.RestaurantJpaRepository;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class RestaurantRecommendationServiceTests {

    @Test
    void appliesDefaultBudgetDislikedCategoriesAndRecentMeals() {
        UUID userId = UUID.randomUUID();
        RestaurantJpaRepository repository = mock(RestaurantJpaRepository.class);
        RecommendationContextService contextService = mock(RecommendationContextService.class);
        Restaurant recent = restaurant(1L, RestaurantCategory.KOREAN, 9_000);
        Restaurant disliked = restaurant(2L, RestaurantCategory.SALAD, 9_000);
        Restaurant overBudget = restaurant(3L, RestaurantCategory.KOREAN, 15_000);
        Restaurant eligible = restaurant(4L, RestaurantCategory.KOREAN, 10_000);
        when(repository.findOpenRestaurants(anyString(), any()))
                .thenReturn(List.of(recent, disliked, overBudget, eligible));

        IntentAnalysisRequest request = new IntentAnalysisRequest(
                "점심 추천해줘",
                "gangnam",
                12_000,
                SpiceLevel.ANY,
                Set.of(RestaurantCategory.KOREAN),
                Set.of(RestaurantCategory.SALAD),
                Set.of(),
                List.of(new IntentAnalysisRequest.RecentMeal(
                        1L, RestaurantCategory.KOREAN, Instant.parse("2026-09-16T03:00:00Z")
                ))
        );
        AnalyzedIntent intent = new AnalyzedIntent(
                IntentType.RECOMMEND_RESTAURANT,
                null,
                Optional.empty(),
                List.of(),
                false,
                null
        );
        when(contextService.build(userId, "점심 추천해줘", "gangnam"))
                .thenReturn(new RecommendationContext(request, intent));
        RestaurantRecommendationService service = new RestaurantRecommendationService(
                repository,
                contextService,
                Clock.fixed(
                        Instant.parse("2026-09-16T03:00:00Z"),
                        ZoneId.of("Asia/Seoul")
                )
        );

        assertThat(service.recommend(userId, "점심 추천해줘", "gangnam"))
                .extracting(RecommendationItem::restaurantId)
                .containsExactly(4L);
    }

    private Restaurant restaurant(Long id, RestaurantCategory category, int price) {
        Restaurant restaurant = mock(Restaurant.class);
        when(restaurant.getId()).thenReturn(id);
        when(restaurant.getName()).thenReturn("테스트 식당 " + id);
        when(restaurant.getCategory()).thenReturn(category);
        when(restaurant.getRepresentativeMenu()).thenReturn("테스트 메뉴");
        when(restaurant.getAveragePrice()).thenReturn(price);
        when(restaurant.getAddress()).thenReturn("서울특별시 강남구 테스트로 " + id);
        when(restaurant.getLocationId()).thenReturn("gangnam");
        when(restaurant.isZeroPayAvailable()).thenReturn(true);
        when(restaurant.isSampleData()).thenReturn(true);
        return restaurant;
    }
}
