package com.zeropaylunch.backend.restaurant.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.zeropaylunch.backend.preference.domain.SpiceLevel;
import com.zeropaylunch.backend.recommendation.ai.AiIntegrationProperties;
import com.zeropaylunch.backend.recommendation.ai.FastApiIntentAnalysisAdapter;
import com.zeropaylunch.backend.recommendation.ai.FastApiSemanticClient;
import com.zeropaylunch.backend.recommendation.ai.IntentAnalysisRequest;
import com.zeropaylunch.backend.recommendation.ai.SemanticCandidateEnricher;
import com.zeropaylunch.backend.recommendation.ai.TemporaryIntentAnalyzer;
import com.zeropaylunch.backend.recommendation.application.RecommendationContextService;
import com.zeropaylunch.backend.recommendation.application.RecommendationContextService.RecommendationContext;
import com.zeropaylunch.backend.restaurant.domain.Restaurant;
import com.zeropaylunch.backend.restaurant.domain.RestaurantCategory;
import com.zeropaylunch.backend.restaurant.infrastructure.RestaurantJpaRepository;
import com.zeropaylunch.backend.restaurant.infrastructure.RestaurantVenueAssociationJpaRepository;
import java.net.URI;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.ObjectProvider;

/** Opt-in read-only recommendation service flow using live FastAPI/Ollama/Qdrant and mocked MySQL reads. */
@EnabledIfEnvironmentVariable(named = "FASTAPI_CONTRACT_URL", matches = "http://127\\.0\\.0\\.1:.*")
class RecommendationFastApiLiveFlowTests {
    @Test
    void intentHardFilterScopedRetrievalRankingDedupAndLimitUseTheRealService() {
        String query = "혼밥하면서 떡볶이 먹고 싶어";
        var client = new FastApiSemanticClient(new AiIntegrationProperties(
                URI.create(System.getenv("FASTAPI_CONTRACT_URL")), Duration.ofSeconds(2),
                Duration.ofSeconds(8), Duration.ofSeconds(27), 1, true, false));
        var request = new IntentAnalysisRequest(query, 12_000, SpiceLevel.ANY,
                Set.of(), Set.of(), Set.of(), List.of());
        var intent = new FastApiIntentAnalysisAdapter(client, new TemporaryIntentAnalyzer()).analyze(request);
        RecommendationContextService contextService = mock(RecommendationContextService.class);
        when(contextService.build(any(UUID.class), anyString()))
                .thenReturn(new RecommendationContext(request, intent));

        RestaurantJpaRepository restaurants = mock(RestaurantJpaRepository.class);
        Restaurant eligible = mock(Restaurant.class);
        when(eligible.getId()).thenReturn(9617L);
        when(eligible.getName()).thenReturn("마성떡볶이 논현역점");
        when(eligible.getCategory()).thenReturn(RestaurantCategory.KOREAN);
        when(eligible.getRepresentativeMenu()).thenReturn("떡볶이");
        when(eligible.getAveragePrice()).thenReturn(9_000);
        when(eligible.getAddress()).thenReturn("서울 강남구 논현동");
        when(eligible.isZeroPayAvailable()).thenReturn(true);
        when(eligible.isSampleData()).thenReturn(false);
        when(restaurants.findOpenRestaurants(anyString(), any())).thenReturn(List.of(eligible));
        RestaurantVenueAssociationJpaRepository associations = mock(RestaurantVenueAssociationJpaRepository.class);
        when(associations.findAllByRestaurant_IdInAndStatusAndVenue_Status(any(), any(), any()))
                .thenReturn(List.of());

        ObjectProvider<SemanticCandidateEnricher> provider = mockProvider(
                new SemanticCandidateEnricher(client, true));
        var service = new RestaurantRecommendationService(restaurants, associations, contextService,
                Clock.fixed(Instant.parse("2026-09-25T03:00:00Z"), ZoneId.of("Asia/Seoul")), provider);

        assertThat(service.recommend(UUID.randomUUID(), query))
                .extracting(RecommendationItem::restaurantId).containsExactly(9617L);
    }

    @SuppressWarnings("unchecked")
    private ObjectProvider<SemanticCandidateEnricher> mockProvider(SemanticCandidateEnricher enricher) {
        ObjectProvider<SemanticCandidateEnricher> provider = mock(ObjectProvider.class);
        when(provider.getIfAvailable()).thenReturn(enricher);
        return provider;
    }
}
