package com.zeropaylunch.backend.restaurant.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.data.Offset.offset;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.anyMap;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.zeropaylunch.backend.preference.domain.SpiceLevel;
import com.zeropaylunch.backend.location.domain.SubwayStation;
import com.zeropaylunch.backend.recommendation.ai.AnalyzedIntent;
import com.zeropaylunch.backend.recommendation.ai.AnalyzedIntent.IntentType;
import com.zeropaylunch.backend.recommendation.ai.IntentAnalysisRequest;
import com.zeropaylunch.backend.recommendation.application.RecommendationContextService;
import com.zeropaylunch.backend.recommendation.application.RecommendationContextService.RecommendationContext;
import com.zeropaylunch.backend.restaurant.domain.Restaurant;
import com.zeropaylunch.backend.restaurant.domain.RestaurantCategory;
import com.zeropaylunch.backend.restaurant.domain.RestaurantVenueAssociation;
import com.zeropaylunch.backend.restaurant.domain.RestaurantVenueAssociationStatus;
import com.zeropaylunch.backend.restaurant.domain.VenueStatus;
import com.zeropaylunch.backend.location.infrastructure.SubwayStationJpaRepository;
import com.zeropaylunch.backend.restaurant.infrastructure.RestaurantJpaRepository;
import com.zeropaylunch.backend.restaurant.infrastructure.RestaurantVenueAssociationJpaRepository;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import org.springframework.beans.factory.ObjectProvider;
import org.junit.jupiter.api.Test;

class RestaurantRecommendationServiceTests {

    @Test
    void runtimeRetrievalReceivesEveryHardFilteredCandidateBeforeVenueDedupAndMaxThree() {
        UUID userId = UUID.randomUUID();
        RestaurantJpaRepository repository = mock(RestaurantJpaRepository.class);
        RestaurantVenueAssociationJpaRepository venueRepository = mock(RestaurantVenueAssociationJpaRepository.class);
        RecommendationContextService contextService = mock(RecommendationContextService.class);
        var enricher = mock(com.zeropaylunch.backend.recommendation.ai.SemanticCandidateEnricher.class);
        @SuppressWarnings("unchecked")
        ObjectProvider<com.zeropaylunch.backend.recommendation.ai.SemanticCandidateEnricher> provider =
                mock(ObjectProvider.class);
        when(provider.getIfAvailable()).thenReturn(enricher);

        List<Restaurant> candidates = List.of(
                restaurant(51L, RestaurantCategory.KOREAN, 9_000),
                restaurant(52L, RestaurantCategory.KOREAN, 9_000),
                restaurant(53L, RestaurantCategory.KOREAN, 9_000),
                restaurant(54L, RestaurantCategory.KOREAN, 9_000));
        when(repository.findOpenRestaurants(anyString(), any())).thenReturn(candidates);
        when(venueRepository.findAllByRestaurant_IdInAndStatusAndVenue_Status(
                any(), eq(RestaurantVenueAssociationStatus.CONFIRMED), eq(VenueStatus.ACTIVE)))
                .thenReturn(List.of());
        IntentAnalysisRequest request = new IntentAnalysisRequest(
                "떡볶이 먹고 싶어", 12_000, SpiceLevel.ANY, Set.of(), Set.of(), Set.of(), List.of());
        AnalyzedIntent intent = new AnalyzedIntent(
                IntentType.RECOMMEND_RESTAURANT, null, Optional.empty(), List.of("떡볶이"), false, null);
        when(contextService.build(userId, request.message())).thenReturn(new RecommendationContext(request, intent));
        List<Long> scope = List.of(51L, 52L, 53L, 54L);
        var signal = new com.zeropaylunch.backend.recommendation.ai.SemanticAiClient.Candidate(
                54L, 310.5, 0.91, List.of(new com.zeropaylunch.backend.recommendation.ai.SemanticAiClient.MatchedClaim(
                        "claim-54", "FOOD_TYPE", 0.91, "EXACT", true, false, false, false,
                        null, List.of("E1"), "메뉴에서 떡볶이가 확인된다.")));
        when(enricher.enrich("떡볶이 먹고 싶어", scope)).thenReturn(
                new com.zeropaylunch.backend.recommendation.ai.SemanticCandidateEnricher.Result(
                        List.of(
                                new com.zeropaylunch.backend.recommendation.ai.SemanticCandidateEnricher.Item(51L, null),
                                new com.zeropaylunch.backend.recommendation.ai.SemanticCandidateEnricher.Item(52L, null),
                                new com.zeropaylunch.backend.recommendation.ai.SemanticCandidateEnricher.Item(53L, null),
                                new com.zeropaylunch.backend.recommendation.ai.SemanticCandidateEnricher.Item(54L, signal)),
                        false));

        RestaurantRecommendationService service = new RestaurantRecommendationService(
                repository, venueRepository, contextService,
                Clock.fixed(Instant.parse("2026-09-16T03:00:00Z"), ZoneId.of("Asia/Seoul")), provider);

        assertThat(service.recommend(userId, request.message()))
                .extracting(RecommendationItem::restaurantId)
                .containsExactly(54L, 51L, 52L);
        verify(enricher).enrich(request.message(), scope);
    }

    @Test
    void semanticRuntimeKeepsUnindexedHardFilteredRestaurant() {
        UUID userId = UUID.randomUUID();
        RestaurantJpaRepository repository = mock(RestaurantJpaRepository.class);
        RestaurantVenueAssociationJpaRepository venueRepository = mock(RestaurantVenueAssociationJpaRepository.class);
        RecommendationContextService contextService = mock(RecommendationContextService.class);
        var enricher = mock(com.zeropaylunch.backend.recommendation.ai.SemanticCandidateEnricher.class);
        @SuppressWarnings("unchecked")
        ObjectProvider<com.zeropaylunch.backend.recommendation.ai.SemanticCandidateEnricher> provider =
                mock(ObjectProvider.class);
        when(provider.getIfAvailable()).thenReturn(enricher);
        Restaurant candidate = restaurant(61L, RestaurantCategory.KOREAN, 9_000);
        when(repository.findOpenRestaurants(anyString(), any())).thenReturn(List.of(candidate));
        when(venueRepository.findAllByRestaurant_IdInAndStatusAndVenue_Status(
                any(), eq(RestaurantVenueAssociationStatus.CONFIRMED), eq(VenueStatus.ACTIVE)))
                .thenReturn(List.of());
        IntentAnalysisRequest request = new IntentAnalysisRequest(
                "점심 추천", 12_000, SpiceLevel.ANY, Set.of(), Set.of(), Set.of(), List.of());
        when(contextService.build(userId, request.message())).thenReturn(new RecommendationContext(request,
                new AnalyzedIntent(IntentType.RECOMMEND_RESTAURANT, null, Optional.empty(), List.of(), false, null)));
        when(enricher.enrich(request.message(), List.of(61L))).thenReturn(
                new com.zeropaylunch.backend.recommendation.ai.SemanticCandidateEnricher.Result(
                        List.of(new com.zeropaylunch.backend.recommendation.ai.SemanticCandidateEnricher.Item(61L, null)),
                        false));

        RestaurantRecommendationService service = new RestaurantRecommendationService(
                repository, venueRepository, contextService,
                Clock.fixed(Instant.parse("2026-09-16T03:00:00Z"), ZoneId.of("Asia/Seoul")), provider);

        assertThat(service.recommend(userId, request.message()))
                .extracting(RecommendationItem::restaurantId).containsExactly(61L);
    }

    @Test
    void explanationRunsOnlyAfterSpringHasSelectedAndLimitedFinalRestaurants() {
        UUID userId = UUID.randomUUID();
        RestaurantJpaRepository repository = mock(RestaurantJpaRepository.class);
        RestaurantVenueAssociationJpaRepository venueRepository = mock(RestaurantVenueAssociationJpaRepository.class);
        RecommendationContextService contextService = mock(RecommendationContextService.class);
        @SuppressWarnings("unchecked")
        ObjectProvider<com.zeropaylunch.backend.recommendation.ai.SemanticCandidateEnricher> semanticProvider =
                mock(ObjectProvider.class);
        var semanticEnricher = mock(com.zeropaylunch.backend.recommendation.ai.SemanticCandidateEnricher.class);
        when(semanticProvider.getIfAvailable()).thenReturn(semanticEnricher);
        @SuppressWarnings("unchecked")
        ObjectProvider<com.zeropaylunch.backend.recommendation.ai.RecommendationExplanationEnricher> explanationProvider =
                mock(ObjectProvider.class);
        var explanationEnricher = mock(
                com.zeropaylunch.backend.recommendation.ai.RecommendationExplanationEnricher.class);
        when(explanationProvider.getIfAvailable()).thenReturn(explanationEnricher);
        List<Restaurant> candidates = List.of(
                restaurant(71L, RestaurantCategory.KOREAN, 9_000),
                restaurant(72L, RestaurantCategory.KOREAN, 9_000),
                restaurant(73L, RestaurantCategory.KOREAN, 9_000),
                restaurant(74L, RestaurantCategory.KOREAN, 9_000));
        when(repository.findOpenRestaurants(anyString(), any())).thenReturn(candidates);
        when(venueRepository.findAllByRestaurant_IdInAndStatusAndVenue_Status(
                any(), eq(RestaurantVenueAssociationStatus.CONFIRMED), eq(VenueStatus.ACTIVE)))
                .thenReturn(List.of());
        IntentAnalysisRequest request = new IntentAnalysisRequest(
                "점심", 12_000, SpiceLevel.ANY, Set.of(), Set.of(), Set.of(), List.of());
        when(contextService.build(userId, "점심")).thenReturn(new RecommendationContext(request,
                new AnalyzedIntent(IntentType.RECOMMEND_RESTAURANT, null, Optional.empty(), List.of(), false, null)));
        when(semanticEnricher.enrich("점심", List.of(71L, 72L, 73L, 74L))).thenReturn(
                new com.zeropaylunch.backend.recommendation.ai.SemanticCandidateEnricher.Result(
                        List.of(71L, 72L, 73L, 74L).stream()
                                .map(id -> new com.zeropaylunch.backend.recommendation.ai.SemanticCandidateEnricher.Item(id, null))
                                .toList(), false));
        when(explanationEnricher.explain(eq("점심"), anyList(), anyMap(), eq(12_000)))
                .thenAnswer(invocation -> invocation.<List<RecommendationItem>>getArgument(1).stream()
                        .map(item -> new RecommendationItem(item.restaurantId(), item.name(), item.category(),
                                item.representativeMenu(), item.averagePrice(), item.address(),
                                item.zeroPayAvailable(), item.sampleData(), "설명 사유"))
                        .toList());

        RestaurantRecommendationService service = new RestaurantRecommendationService(
                repository, venueRepository, contextService,
                Clock.fixed(Instant.parse("2026-09-16T03:00:00Z"), ZoneId.of("Asia/Seoul")),
                semanticProvider, explanationProvider);

        List<RecommendationItem> result = service.recommend(userId, "점심");

        assertThat(result).extracting(RecommendationItem::restaurantId).containsExactly(71L, 72L, 73L);
        assertThat(result).extracting(RecommendationItem::reason).containsOnly("설명 사유");
        verify(explanationEnricher).explain(eq("점심"), anyList(), anyMap(), eq(12_000));
    }

    @Test
    void appliesDefaultBudgetDislikedCategoriesAndRecentMeals() {
        UUID userId = UUID.randomUUID();
        RestaurantJpaRepository repository = mock(RestaurantJpaRepository.class);
        RestaurantVenueAssociationJpaRepository venueRepository =
                mock(RestaurantVenueAssociationJpaRepository.class);
        RecommendationContextService contextService = mock(RecommendationContextService.class);
        Restaurant recent = restaurant(1L, RestaurantCategory.KOREAN, 9_000);
        Restaurant disliked = restaurant(2L, RestaurantCategory.SALAD, 9_000);
        Restaurant overBudget = restaurant(3L, RestaurantCategory.KOREAN, 15_000);
        Restaurant eligible = restaurant(4L, RestaurantCategory.KOREAN, 10_000);
        when(repository.findOpenRestaurants(anyString(), any()))
                .thenReturn(List.of(recent, disliked, overBudget, eligible));

        IntentAnalysisRequest request = new IntentAnalysisRequest(
                "점심 추천해줘",
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
        when(contextService.build(userId, "점심 추천해줘"))
                .thenReturn(new RecommendationContext(request, intent));
        RestaurantRecommendationService service = new RestaurantRecommendationService(
                repository,
                venueRepository,
                contextService,
                Clock.fixed(
                        Instant.parse("2026-09-16T03:00:00Z"),
                        ZoneId.of("Asia/Seoul")
                )
        );

        assertThat(service.recommend(userId, "점심 추천해줘"))
                .extracting(RecommendationItem::restaurantId)
                .containsExactly(4L);

        // Contract seam: only real Spring-filtered IDs reach the semantic client.
        var ai = mock(com.zeropaylunch.backend.recommendation.ai.SemanticAiClient.class);
        when(ai.retrieve("점심 추천해줘", List.of(4L), 1)).thenReturn(
                new com.zeropaylunch.backend.recommendation.ai.SemanticAiClient.RetrievalResult(
                        List.of(), "pilot"));
        var enricher = new com.zeropaylunch.backend.recommendation.ai.SemanticCandidateEnricher(ai, true);
        var signals = enricher.enrich("점심 추천해줘", service.recommend(userId, "점심 추천해줘").stream()
                .map(RecommendationItem::restaurantId).toList());
        verify(ai).retrieve("점심 추천해줘", List.of(4L), 1);
        assertThat(signals.candidatesInSpringOrder())
                .extracting(com.zeropaylunch.backend.recommendation.ai.SemanticCandidateEnricher.Item::restaurantId)
                .containsExactly(4L);
    }

    @Test
    void confirmedVenueIsReturnedOnceWhileUnassociatedRestaurantRemainsCompatible() {
        UUID userId = UUID.randomUUID();
        RestaurantJpaRepository repository = mock(RestaurantJpaRepository.class);
        RestaurantVenueAssociationJpaRepository venueRepository =
                mock(RestaurantVenueAssociationJpaRepository.class);
        RecommendationContextService contextService = mock(RecommendationContextService.class);
        Restaurant first = restaurant(10L, RestaurantCategory.KOREAN, 9_000);
        Restaurant duplicateVenue = restaurant(11L, RestaurantCategory.KOREAN, 9_000);
        Restaurant unassociated = restaurant(12L, RestaurantCategory.KOREAN, 9_000);
        when(repository.findOpenRestaurants(anyString(), any()))
                .thenReturn(List.of(first, duplicateVenue, unassociated));

        RestaurantVenueAssociation association = mock(RestaurantVenueAssociation.class);
        when(association.getRestaurantId()).thenReturn(10L);
        when(association.getVenueId()).thenReturn(900L);
        when(association.getStatus()).thenReturn(RestaurantVenueAssociationStatus.CONFIRMED);
        RestaurantVenueAssociation duplicateAssociation = mock(RestaurantVenueAssociation.class);
        when(duplicateAssociation.getRestaurantId()).thenReturn(11L);
        when(duplicateAssociation.getVenueId()).thenReturn(900L);
        when(duplicateAssociation.getStatus()).thenReturn(RestaurantVenueAssociationStatus.CONFIRMED);
        when(venueRepository.findAllByRestaurant_IdInAndStatusAndVenue_Status(
                any(), eq(RestaurantVenueAssociationStatus.CONFIRMED), eq(VenueStatus.ACTIVE)))
                .thenReturn(List.of(association, duplicateAssociation));

        IntentAnalysisRequest request = new IntentAnalysisRequest(
                "점심 추천해줘", 12_000, SpiceLevel.ANY, Set.of(RestaurantCategory.KOREAN),
                Set.of(), Set.of(), List.of());
        AnalyzedIntent intent = new AnalyzedIntent(
                IntentType.RECOMMEND_RESTAURANT, null, Optional.empty(), List.of(), false, null);
        when(contextService.build(userId, "점심 추천해줘"))
                .thenReturn(new RecommendationContext(request, intent));

        RestaurantRecommendationService service = new RestaurantRecommendationService(
                repository, venueRepository, contextService,
                Clock.fixed(Instant.parse("2026-09-16T03:00:00Z"), ZoneId.of("Asia/Seoul")));

        assertThat(service.recommend(userId, "점심 추천해줘"))
                .extracting(RecommendationItem::restaurantId)
                .containsExactly(10L, 12L);
        verify(venueRepository).findAllByRestaurant_IdInAndStatusAndVenue_Status(
                any(), eq(RestaurantVenueAssociationStatus.CONFIRMED), eq(VenueStatus.ACTIVE));
    }

    @Test
    void recentMealAtConfirmedVenueExcludesOtherRestaurantInSameVenue() {
        UUID userId = UUID.randomUUID();
        RestaurantJpaRepository repository = mock(RestaurantJpaRepository.class);
        RestaurantVenueAssociationJpaRepository venueRepository =
                mock(RestaurantVenueAssociationJpaRepository.class);
        RecommendationContextService contextService = mock(RecommendationContextService.class);
        Restaurant eatenRestaurant = restaurant(20L, RestaurantCategory.KOREAN, 9_000);
        Restaurant sameVenueCandidate = restaurant(21L, RestaurantCategory.KOREAN, 9_000);
        when(repository.findOpenRestaurants(anyString(), any()))
                .thenReturn(List.of(sameVenueCandidate));

        RestaurantVenueAssociation eatenAssociation = mock(RestaurantVenueAssociation.class);
        when(eatenAssociation.getRestaurantId()).thenReturn(20L);
        when(eatenAssociation.getVenueId()).thenReturn(901L);
        RestaurantVenueAssociation candidateAssociation = mock(RestaurantVenueAssociation.class);
        when(candidateAssociation.getRestaurantId()).thenReturn(21L);
        when(candidateAssociation.getVenueId()).thenReturn(901L);
        when(venueRepository.findAllByRestaurant_IdInAndStatusAndVenue_Status(
                any(), eq(RestaurantVenueAssociationStatus.CONFIRMED), eq(VenueStatus.ACTIVE)))
                .thenReturn(List.of(eatenAssociation, candidateAssociation));

        IntentAnalysisRequest request = new IntentAnalysisRequest(
                "점심 추천해줘", 12_000, SpiceLevel.ANY, Set.of(RestaurantCategory.KOREAN),
                Set.of(), Set.of(), List.of(new IntentAnalysisRequest.RecentMeal(
                        eatenRestaurant.getId(), RestaurantCategory.KOREAN,
                        Instant.parse("2026-09-16T03:00:00Z"))));
        AnalyzedIntent intent = new AnalyzedIntent(
                IntentType.RECOMMEND_RESTAURANT, null, Optional.empty(), List.of(), false, null);
        when(contextService.build(userId, "점심 추천해줘"))
                .thenReturn(new RecommendationContext(request, intent));

        RestaurantRecommendationService service = new RestaurantRecommendationService(
                repository, venueRepository, contextService,
                Clock.fixed(Instant.parse("2026-09-16T03:00:00Z"), ZoneId.of("Asia/Seoul")));

        assertThat(service.recommend(userId, "점심 추천해줘")).isEmpty();
    }

    @Test
    void recentMealDoesNotExpandToUnconfirmedOrInactiveVenueAssociation() {
        UUID userId = UUID.randomUUID();
        RestaurantJpaRepository repository = mock(RestaurantJpaRepository.class);
        RestaurantVenueAssociationJpaRepository venueRepository =
                mock(RestaurantVenueAssociationJpaRepository.class);
        RecommendationContextService contextService = mock(RecommendationContextService.class);
        Restaurant candidate = restaurant(31L, RestaurantCategory.KOREAN, 9_000);
        when(repository.findOpenRestaurants(anyString(), any())).thenReturn(List.of(candidate));
        when(venueRepository.findAllByRestaurant_IdInAndStatusAndVenue_Status(
                any(), eq(RestaurantVenueAssociationStatus.CONFIRMED), eq(VenueStatus.ACTIVE)))
                .thenReturn(List.of());

        IntentAnalysisRequest request = new IntentAnalysisRequest(
                "점심 추천해줘", 12_000, SpiceLevel.ANY, Set.of(RestaurantCategory.KOREAN),
                Set.of(), Set.of(), List.of(new IntentAnalysisRequest.RecentMeal(
                        30L, RestaurantCategory.KOREAN, Instant.parse("2026-09-16T03:00:00Z"))));
        AnalyzedIntent intent = new AnalyzedIntent(
                IntentType.RECOMMEND_RESTAURANT, null, Optional.empty(), List.of(), false, null);
        when(contextService.build(userId, "점심 추천해줘"))
                .thenReturn(new RecommendationContext(request, intent));

        RestaurantRecommendationService service = new RestaurantRecommendationService(
                repository, venueRepository, contextService,
                Clock.fixed(Instant.parse("2026-09-16T03:00:00Z"), ZoneId.of("Asia/Seoul")));

        assertThat(service.recommend(userId, "점심 추천해줘"))
                .extracting(RecommendationItem::restaurantId)
                .containsExactly(31L);
    }

    private Restaurant restaurant(Long id, RestaurantCategory category, int price) {
        return restaurant(id, category, price,
                new BigDecimal("37.4980"), new BigDecimal("127.0276"));
    }

    private Restaurant restaurant(
            Long id, RestaurantCategory category, int price,
            BigDecimal latitude, BigDecimal longitude) {
        Restaurant restaurant = mock(Restaurant.class);
        when(restaurant.getId()).thenReturn(id);
        when(restaurant.getName()).thenReturn("테스트 식당 " + id);
        when(restaurant.getCategory()).thenReturn(category);
        when(restaurant.getRepresentativeMenu()).thenReturn("테스트 메뉴");
        when(restaurant.getAveragePrice()).thenReturn(price);
        when(restaurant.getAddress()).thenReturn("서울특별시 강남구 테스트로 " + id);
        when(restaurant.getLocationId()).thenReturn("gangnam");
        when(restaurant.isZeroPayAvailable()).thenReturn(true);
        when(restaurant.getLatitude()).thenReturn(latitude);
        when(restaurant.getLongitude()).thenReturn(longitude);
        when(restaurant.isSampleData()).thenReturn(true);
        return restaurant;
    }

    private SubwayStation station(String id, double latitude, double longitude) {
        return new SubwayStation(
                id, "강남역", "2호선", BigDecimal.valueOf(latitude),
                BigDecimal.valueOf(longitude), true, "TEST");
    }

    private BigDecimal latitudeAtMeters(double meters) {
        return BigDecimal.valueOf(37.4980 + Math.toDegrees(meters / 6_371_000.0));
    }
}
