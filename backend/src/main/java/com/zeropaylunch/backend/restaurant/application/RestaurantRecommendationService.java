/**
 * 사용자 취향·ZeroPay·영업 상태를 적용해 추천 후보를 필터링하고 순위를 계산한다.
 * 자연어 해석 fallback과 DB 후보 조회 이후 최종 business ranking을 소유한다.
 */
package com.zeropaylunch.backend.restaurant.application;

import com.zeropaylunch.backend.recommendation.ai.AnalyzedIntent;
import com.zeropaylunch.backend.recommendation.ai.IntentAnalysisRequest;
import com.zeropaylunch.backend.recommendation.ai.SemanticAiClient;
import com.zeropaylunch.backend.recommendation.ai.SemanticCandidateEnricher;
import com.zeropaylunch.backend.recommendation.ai.RecommendationExplanationEnricher;
import com.zeropaylunch.backend.recommendation.application.RecommendationContextService;
import com.zeropaylunch.backend.recommendation.application.RecommendationContextService.RecommendationContext;
import com.zeropaylunch.backend.restaurant.domain.Restaurant;
import com.zeropaylunch.backend.restaurant.domain.RestaurantVenueAssociation;
import com.zeropaylunch.backend.restaurant.domain.RestaurantVenueAssociationStatus;
import com.zeropaylunch.backend.restaurant.domain.VenueStatus;
import com.zeropaylunch.backend.restaurant.infrastructure.RestaurantJpaRepository;
import com.zeropaylunch.backend.restaurant.infrastructure.RestaurantVenueAssociationJpaRepository;
import java.time.Clock;
import java.time.ZonedDateTime;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Autowired;
import java.util.stream.Collectors;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class RestaurantRecommendationService {
    private static final int MAX_RECOMMENDATIONS = 3;
    private final RestaurantJpaRepository restaurantRepository;
    private final RestaurantVenueAssociationJpaRepository venueAssociationRepository;
    private final RecommendationContextService contextService;
    private final Clock clock;
    private final ObjectProvider<SemanticCandidateEnricher> semanticEnricherProvider;
    private final ObjectProvider<RecommendationExplanationEnricher> explanationEnricherProvider;
    private final ObjectProvider<RestaurantMenuExampleService> menuExampleServiceProvider;
    private final ObjectProvider<VerifiedNaverServingCandidateService> verifiedCandidateServiceProvider;

    @Autowired
    public RestaurantRecommendationService(RestaurantJpaRepository restaurantRepository,
            RestaurantVenueAssociationJpaRepository venueAssociationRepository,
            RecommendationContextService contextService, Clock clock,
            ObjectProvider<SemanticCandidateEnricher> semanticEnricherProvider,
            ObjectProvider<RecommendationExplanationEnricher> explanationEnricherProvider,
            ObjectProvider<RestaurantMenuExampleService> menuExampleServiceProvider,
            ObjectProvider<VerifiedNaverServingCandidateService> verifiedCandidateServiceProvider) {
        this.restaurantRepository = restaurantRepository;
        this.venueAssociationRepository = venueAssociationRepository;
        this.contextService = contextService;
        this.clock = clock;
        this.semanticEnricherProvider = semanticEnricherProvider;
        this.explanationEnricherProvider = explanationEnricherProvider;
        this.menuExampleServiceProvider = menuExampleServiceProvider;
        this.verifiedCandidateServiceProvider = verifiedCandidateServiceProvider;
    }

    public RestaurantRecommendationService(RestaurantJpaRepository restaurantRepository,
            RestaurantVenueAssociationJpaRepository venueAssociationRepository,
            RecommendationContextService contextService, Clock clock,
            ObjectProvider<SemanticCandidateEnricher> semanticEnricherProvider,
            ObjectProvider<RecommendationExplanationEnricher> explanationEnricherProvider) {
        this(restaurantRepository, venueAssociationRepository, contextService, clock,
                semanticEnricherProvider, explanationEnricherProvider, null, null);
    }

    public RestaurantRecommendationService(RestaurantJpaRepository restaurantRepository,
            RestaurantVenueAssociationJpaRepository venueAssociationRepository,
            RecommendationContextService contextService, Clock clock,
            ObjectProvider<SemanticCandidateEnricher> semanticEnricherProvider,
            ObjectProvider<RecommendationExplanationEnricher> explanationEnricherProvider,
            ObjectProvider<RestaurantMenuExampleService> menuExampleServiceProvider) {
        this(restaurantRepository, venueAssociationRepository, contextService, clock,
                semanticEnricherProvider, explanationEnricherProvider, menuExampleServiceProvider, null);
    }

    /** Keeps direct construction in existing unit fixtures equivalent to the feature-flag OFF path. */
    public RestaurantRecommendationService(RestaurantJpaRepository restaurantRepository,
            RestaurantVenueAssociationJpaRepository venueAssociationRepository,
            RecommendationContextService contextService, Clock clock) {
        this(restaurantRepository, venueAssociationRepository, contextService, clock, null, null);
    }

    public RestaurantRecommendationService(RestaurantJpaRepository restaurantRepository,
            RestaurantVenueAssociationJpaRepository venueAssociationRepository,
            RecommendationContextService contextService, Clock clock,
            ObjectProvider<SemanticCandidateEnricher> semanticEnricherProvider) {
        this(restaurantRepository, venueAssociationRepository, contextService, clock,
                semanticEnricherProvider, null);
    }

    @Transactional(readOnly = true)
    public List<RecommendationItem> recommend(UUID userId, String message) {
        RecommendationContext context = contextService.build(userId, message);
        AnalyzedIntent intent = context.intent();
        IntentAnalysisRequest request = context.request();
        Integer budget = intent.maximumPrice() != null ? intent.maximumPrice() : request.defaultBudget();
        Set<Long> recentRestaurantIds = request.recentMeals().stream()
                .map(IntentAnalysisRequest.RecentMeal::restaurantId).collect(Collectors.toSet());
        ZonedDateTime now = ZonedDateTime.now(clock);
        List<Restaurant> legacyOpenRestaurants = restaurantRepository.findOpenRestaurants(
                        now.getDayOfWeek().name(),
                        now.toLocalTime().truncatedTo(ChronoUnit.SECONDS)).stream()
                .filter(r -> matches(r, intent, request, budget, recentRestaurantIds))
                .sorted(Comparator.comparingInt((Restaurant r) -> score(r, intent, request, budget))
                        .reversed().thenComparingInt(this::priceTieBreak).thenComparing(Restaurant::getId))
                .toList();
        List<Restaurant> openRestaurants = new ArrayList<>(legacyOpenRestaurants);
        if (verifiedCandidateServiceProvider != null) {
            VerifiedNaverServingCandidateService servingCandidates = verifiedCandidateServiceProvider.getIfAvailable();
            if (servingCandidates != null) {
                List<Long> verifiedIds = servingCandidates.findOpenCandidateIds(
                        now.toLocalDate(), now.toLocalTime().truncatedTo(ChronoUnit.SECONDS), budget);
                Set<Long> alreadyIncluded = openRestaurants.stream().map(Restaurant::getId)
                        .collect(Collectors.toSet());
                restaurantRepository.findAllById(verifiedIds).stream()
                        .filter(r -> !alreadyIncluded.contains(r.getId()))
                        .filter(r -> matches(r, intent, request, budget, recentRestaurantIds))
                        .forEach(openRestaurants::add);
            }
        }
        Set<Long> associationRestaurantIds = new LinkedHashSet<>(recentRestaurantIds);
        associationRestaurantIds.addAll(openRestaurants.stream().map(Restaurant::getId).toList());
        Map<Long, Long> confirmedVenueIds = confirmedVenueIds(associationRestaurantIds);
        Set<Long> recentKeys = recentRestaurantIds.stream()
                .map(id -> confirmedVenueIds.getOrDefault(id, id))
                .collect(Collectors.toSet());
        List<Restaurant> hardFiltered = openRestaurants.stream()
                .filter(r -> !recentKeys.contains(confirmedVenueIds.getOrDefault(r.getId(), r.getId())))
                .toList();

        SemanticCandidateEnricher enricher = semanticEnricherProvider == null
                ? null : semanticEnricherProvider.getIfAvailable();
        Map<Long, SemanticAiClient.Candidate> semanticSignals = Map.of();
        if (enricher != null && !hardFiltered.isEmpty()) {
            List<Long> candidateIds = hardFiltered.stream().map(Restaurant::getId).toList();
            semanticSignals = enricher.enrich(message, candidateIds).candidatesInSpringOrder().stream()
                    .filter(item -> item.semanticSignal() != null)
                    .collect(Collectors.toMap(
                            SemanticCandidateEnricher.Item::restaurantId,
                            SemanticCandidateEnricher.Item::semanticSignal));
        }

        Map<Long, SemanticAiClient.Candidate> rankingSignals = semanticSignals;
        Set<Long> selectedVenueKeys = new HashSet<>();
        List<Restaurant> finalRestaurants = hardFiltered.stream()
                .sorted(Comparator.comparingInt((Restaurant r) -> score(r, intent, request, budget)).reversed()
                        // Semantic cosine is bounded to [0,1] and only breaks existing deterministic score ties.
                        .thenComparing(Comparator.comparingDouble((Restaurant r) ->
                                semanticRelevance(rankingSignals.get(r.getId()))).reversed())
                        .thenComparingInt(this::priceTieBreak)
                        .thenComparing(Restaurant::getId))
                .filter(r -> selectedVenueKeys.add(confirmedVenueIds.getOrDefault(r.getId(), r.getId())))
                .limit(MAX_RECOMMENDATIONS)
                .toList();
        List<RecommendationItem> finalRecommendations = finalRestaurants.stream()
                .map(r -> toRecommendation(r, request, budget)).toList();
        RecommendationExplanationEnricher explanationEnricher = explanationEnricherProvider == null
                ? null : explanationEnricherProvider.getIfAvailable();
        if (explanationEnricher == null) return finalRecommendations;
        Set<Long> finalIds = finalRecommendations.stream().map(RecommendationItem::restaurantId)
                .collect(Collectors.toSet());
        Map<Long, SemanticAiClient.Candidate> finalSignals = new HashMap<>();
        semanticSignals.forEach((id, signal) -> {
            if (finalIds.contains(id)) finalSignals.put(id, signal);
        });
        return explanationEnricher.explain(message, finalRecommendations, finalSignals, budget);
    }

    private double semanticRelevance(SemanticAiClient.Candidate candidate) {
        if (candidate == null || !Double.isFinite(candidate.semanticSimilarity())) return 0.0;
        return Math.max(0.0, Math.min(1.0, candidate.semanticSimilarity()));
    }

    private Map<Long, Long> confirmedVenueIds(Set<Long> restaurantIds) {
        if (restaurantIds.isEmpty()) {
            return Map.of();
        }
        return venueAssociationRepository.findAllByRestaurant_IdInAndStatusAndVenue_Status(
                        restaurantIds,
                        RestaurantVenueAssociationStatus.CONFIRMED,
                        VenueStatus.ACTIVE)
                .stream()
                .collect(Collectors.toMap(
                        RestaurantVenueAssociation::getRestaurantId,
                        RestaurantVenueAssociation::getVenueId,
                        (first, ignored) -> first,
                        HashMap::new
                ));
    }

    private boolean matches(Restaurant r, AnalyzedIntent intent, IntentAnalysisRequest request,
            Integer budget, Set<Long> recent) {
        if (!r.isZeroPayAvailable()) return false;
        // Unknown price basis never becomes an implicit budget pass.
        if (budget != null && (r.getAveragePrice() == null || r.getAveragePrice() > budget)) return false;
        // Unknown provider taxonomy is not a reason to suppress an otherwise verified KOMSCO row.
        if (r.getCategory() != null && intent.category().isPresent()
                && r.getCategory() != intent.category().get()) return false;
        if (r.getCategory() != null && request.dislikedCategories().contains(r.getCategory())) return false;
        return !recent.contains(r.getId());
    }

    private int score(Restaurant r, AnalyzedIntent intent, IntentAnalysisRequest request, Integer budget) {
        int score = 10;
        if (budget == null || (r.getAveragePrice() != null && r.getAveragePrice() <= budget)) score += 20;
        if (r.getCategory() == null || intent.category().isEmpty()
                || r.getCategory() == intent.category().get()) score += 20;
        if (r.getCategory() != null && request.preferredCategories().contains(r.getCategory())) score += 15;
        return score;
    }

    private int priceTieBreak(Restaurant restaurant) {
        return restaurant.getAveragePrice() == null ? Integer.MAX_VALUE : restaurant.getAveragePrice();
    }

    private RecommendationItem toRecommendation(Restaurant r, IntentAnalysisRequest request, Integer budget) {
        List<String> reasons = new ArrayList<>();
        reasons.add("강남구 논현동 서비스 범위 음식점이에요");
        if (budget != null) reasons.add("설정하거나 요청한 예산 안이에요");
        if (r.getCategory() != null && request.preferredCategories().contains(r.getCategory())) {
            reasons.add("선호하는 음식 종류예요");
        }
        reasons.add("제로페이를 사용할 수 있어요");
        List<RecommendationItem.MenuExample> menuExamples = List.of();
        if (!r.isSampleData() && menuExampleServiceProvider != null) {
            RestaurantMenuExampleService menuService = menuExampleServiceProvider.getIfAvailable();
            if (menuService != null) menuExamples = menuService.findExamples(r.getId());
        }
        return new RecommendationItem(r.getId(), r.getName(),
                r.getCategory() == null ? null : r.getCategory().label(),
                r.getRepresentativeMenu(), r.getAveragePrice(), r.getAddress(),
                r.isZeroPayAvailable(), r.isSampleData(), String.join(". ", reasons) + ".", menuExamples);
    }
}
