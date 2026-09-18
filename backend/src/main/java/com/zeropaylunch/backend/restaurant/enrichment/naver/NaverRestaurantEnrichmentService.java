package com.zeropaylunch.backend.restaurant.enrichment.naver;

import com.zeropaylunch.backend.restaurant.domain.ExternalPlaceMatchStatus;
import com.zeropaylunch.backend.restaurant.domain.ExternalPlaceProvider;
import com.zeropaylunch.backend.restaurant.domain.Restaurant;
import com.zeropaylunch.backend.restaurant.domain.RestaurantExternalPlaceSnapshot;
import com.zeropaylunch.backend.restaurant.domain.RestaurantSourceProvider;
import com.zeropaylunch.backend.restaurant.domain.RestaurantExternalPlace;
import com.zeropaylunch.backend.restaurant.domain.RecommendationEligibility;
import com.zeropaylunch.backend.restaurant.infrastructure.RestaurantExternalPlaceJpaRepository;
import com.zeropaylunch.backend.restaurant.infrastructure.RestaurantJpaRepository;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Clock;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Comparator;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

@Service
class NaverRestaurantEnrichmentService {

    private static final Logger LOGGER =
            LoggerFactory.getLogger(NaverRestaurantEnrichmentService.class);

    private final RestaurantJpaRepository restaurantRepository;
    private final RestaurantExternalPlaceJpaRepository externalPlaceRepository;
    private final NaverLocalSearchClient client;
    private final NaverRestaurantMatcher matcher;
    private final NaverTextNormalizer normalizer;
    private final NaverCoordinateParser coordinateParser;
    private final RestaurantExternalPlaceWriter writer;
    private final RecommendationEligibilityPolicy eligibilityPolicy;
    private final RestaurantMatchSourceHasher sourceHasher;
    private final StratifiedRestaurantSampler sampler;
    private final NaverIncrementalSelector incrementalSelector;
    private final NaverLocalProperties properties;
    private final Clock clock;

    NaverRestaurantEnrichmentService(
            RestaurantJpaRepository restaurantRepository,
            RestaurantExternalPlaceJpaRepository externalPlaceRepository,
            NaverLocalSearchClient client,
            NaverRestaurantMatcher matcher,
            NaverTextNormalizer normalizer,
            NaverCoordinateParser coordinateParser,
            RestaurantExternalPlaceWriter writer,
            RecommendationEligibilityPolicy eligibilityPolicy,
            RestaurantMatchSourceHasher sourceHasher,
            StratifiedRestaurantSampler sampler,
            NaverIncrementalSelector incrementalSelector,
            NaverLocalProperties properties,
            Clock clock) {
        this.restaurantRepository = restaurantRepository;
        this.externalPlaceRepository = externalPlaceRepository;
        this.client = client;
        this.matcher = matcher;
        this.normalizer = normalizer;
        this.coordinateParser = coordinateParser;
        this.writer = writer;
        this.eligibilityPolicy = eligibilityPolicy;
        this.sourceHasher = sourceHasher;
        this.sampler = sampler;
        this.incrementalSelector = incrementalSelector;
        this.properties = properties;
        this.clock = clock;
    }

    NaverEnrichmentResult enrichValidationSample(int requestedLimit) {
        if (requestedLimit < 1 || requestedLimit > properties.maxValidationLimit()) {
            throw new IllegalArgumentException(
                    "Validation limit must be between 1 and "
                            + properties.maxValidationLimit());
        }
        List<Restaurant> all = activeKomscoRestaurants();
        return enrichRestaurants(sampler.select(all, requestedLimit));
    }

    NaverEnrichmentResult enrichAll() {
        return enrichRestaurants(activeKomscoRestaurants());
    }

    NaverEnrichmentResult enrichIncremental(int limit) {
        if (limit < 1) {
            throw new IllegalArgumentException("Incremental limit must be positive");
        }
        List<Restaurant> all = activeKomscoRestaurants();
        Map<Long, RestaurantExternalPlace> enrichmentByRestaurantId = externalPlaceRepository
                .findAllByProviderWithRestaurant(ExternalPlaceProvider.NAVER)
                .stream()
                .collect(Collectors.toMap(
                        place -> place.getRestaurant().getId(), Function.identity()));
        return enrichRestaurants(incrementalSelector.select(
                all, enrichmentByRestaurantId, clock.instant(), limit));
    }

    NaverEnrichmentResult enrichRestaurantIds(Collection<Long> restaurantIds) {
        if (restaurantIds.isEmpty()) {
            return emptyResult();
        }
        List<Restaurant> restaurants = restaurantRepository.findAllById(restaurantIds).stream()
                .filter(Restaurant::isActive)
                .filter(restaurant -> restaurant.getSourceProvider() == RestaurantSourceProvider.KOMSCO)
                .sorted(Comparator.comparing(Restaurant::getId))
                .toList();
        return enrichRestaurants(restaurants);
    }

    private List<Restaurant> activeKomscoRestaurants() {
        return restaurantRepository
                .findBySourceProviderAndActiveTrueOrderByLegalDongCodeAscIdAsc(
                        RestaurantSourceProvider.KOMSCO);
    }

    private NaverEnrichmentResult enrichRestaurants(List<Restaurant> restaurants) {
        int processed = 0;
        int matched = 0;
        int ambiguous = 0;
        int unmatched = 0;
        int apiFailures = 0;
        int eligible = 0;
        int ineligible = 0;
        int unknown = 0;
        int inserted = 0;
        int updated = 0;
        int skipped = 0;
        List<NaverEnrichmentDetail> details = new ArrayList<>();

        for (Restaurant restaurant : restaurants) {
            processed++;
            List<String> queries = queriesFor(restaurant);
            if (queries.isEmpty()) {
                skipped++;
                continue;
            }
            List<NaverSearchCandidate> candidates = new ArrayList<>();
            List<String> attemptedQueries = new ArrayList<>();
            NaverMatchDecision decision = null;
            String lastQuery = queries.getFirst();
            try {
                for (String query : queries) {
                    lastQuery = query;
                    attemptedQueries.add(query);
                    NaverLocalResponse response = client.search(query);
                    response.results().stream()
                            .map(item -> new NaverSearchCandidate(item, query))
                            .forEach(candidates::add);
                    decision = matcher.match(restaurant, candidates, lastQuery);
                    if (decision.status() == ExternalPlaceMatchStatus.MATCHED) {
                        break;
                    }
                }
            } catch (NaverLocalAuthenticationException exception) {
                throw exception;
            } catch (NaverLocalApiException exception) {
                apiFailures++;
                unknown++;
                skipped++;
                Instant retryAt = clock.instant().plus(properties.apiErrorRetryDelay());
                try {
                    writer.recordFailure(
                            restaurant,
                            sourceHasher.hash(restaurant),
                            lastQuery,
                            retryAt);
                } catch (RuntimeException persistenceException) {
                    LOGGER.warn("NAVER failure state persistence failed for restaurantId={}",
                            restaurant.getId());
                }
                LOGGER.warn("NAVER Local lookup failed for restaurantId={}: {}",
                        restaurant.getId(), exception.getMessage());
                details.add(errorDetail(
                        restaurant, attemptedQueries, exception.getMessage()));
                continue;
            }

            if (decision == null) {
                decision = matcher.match(restaurant, candidates, lastQuery);
            }
            RestaurantExternalPlaceSnapshot snapshot = snapshot(restaurant, decision);
            try {
                NaverEnrichmentWriteOutcome outcome = writer.upsert(restaurant, snapshot);
                if (outcome == NaverEnrichmentWriteOutcome.INSERTED) {
                    inserted++;
                } else {
                    updated++;
                }
            } catch (RuntimeException exception) {
                skipped++;
                LOGGER.warn("NAVER enrichment persistence failed for restaurantId={}",
                        restaurant.getId());
                continue;
            }

            if (decision.status() == ExternalPlaceMatchStatus.MATCHED) {
                matched++;
            } else if (decision.status() == ExternalPlaceMatchStatus.AMBIGUOUS) {
                ambiguous++;
            } else {
                unmatched++;
            }
            if (snapshot.recommendationEligibility() == RecommendationEligibility.ELIGIBLE) {
                eligible++;
            } else if (snapshot.recommendationEligibility()
                    == RecommendationEligibility.INELIGIBLE) {
                ineligible++;
            } else {
                unknown++;
            }
            details.add(detail(
                    restaurant,
                    attemptedQueries,
                    decision,
                    snapshot.recommendationEligibility()));
        }
        return new NaverEnrichmentResult(
                processed, matched, ambiguous, unmatched, apiFailures,
                eligible, ineligible, unknown,
                inserted, updated, skipped, List.copyOf(details));
    }

    private NaverEnrichmentResult emptyResult() {
        return new NaverEnrichmentResult(
                0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, List.of());
    }

    private List<String> queriesFor(Restaurant restaurant) {
        if (!StringUtils.hasText(restaurant.getName())) {
            return List.of();
        }
        Set<String> queries = new LinkedHashSet<>();
        if (StringUtils.hasText(restaurant.getLegalDongName())) {
            queries.add(restaurant.getName().trim() + " " + restaurant.getLegalDongName().trim());
        }
        queries.add(restaurant.getName().trim() + " 강남구");
        return queries.stream().limit(properties.maxSearchQueries()).toList();
    }

    private RestaurantExternalPlaceSnapshot snapshot(
            Restaurant restaurant, NaverMatchDecision decision) {
        NaverLocalItem item = decision.selected() == null
                ? null : decision.selected().candidate().item();
        NaverCandidateScore score = decision.selected();
        RecommendationEligibility eligibility = eligibilityPolicy.determine(
                decision.status(), item == null ? null : item.category());
        Instant matchedAt = decision.status() == ExternalPlaceMatchStatus.MATCHED
                ? clock.instant() : null;
        return new RestaurantExternalPlaceSnapshot(
                ExternalPlaceProvider.NAVER,
                item == null ? null : truncate(normalizer.cleanTitle(item.title()), 255),
                item == null ? null : truncate(item.category(), 255),
                item == null ? null : truncate(item.description(), 1000),
                item == null ? null : truncate(item.link(), 1000),
                item == null ? null : truncate(item.address(), 255),
                item == null ? null : truncate(item.roadAddress(), 255),
                item == null ? null : coordinateParser.latitude(item.mapy()),
                item == null ? null : coordinateParser.longitude(item.mapx()),
                decision.status(),
                decimal(decision.score()),
                decimal(score == null ? 0.0 : score.nameScore()),
                decimal(score == null ? 0.0 : score.addressScore()),
                decimal(score == null ? 0.0 : score.distanceScore()),
                decimal(score == null ? 0.0 : score.categoryScore()),
                decision.distanceMeters() == null ? null : decimal(decision.distanceMeters()),
                decimalOrNull(decision.runnerUpScore()),
                decimalOrNull(decision.scoreGap()),
                truncate(decision.queryUsed(), 255),
                matchedAt,
                sourceHasher.hash(restaurant),
                nextRetryAt(decision.status()),
                eligibility);
    }

    private NaverEnrichmentDetail detail(
            Restaurant restaurant,
            List<String> attemptedQueries,
            NaverMatchDecision decision,
            RecommendationEligibility eligibility) {
        NaverLocalItem item = decision.selected() == null
                ? null : decision.selected().candidate().item();
        NaverCandidateScore score = decision.selected();
        return new NaverEnrichmentDetail(
                restaurant.getId(),
                restaurant.getName(),
                restaurant.getAddress(),
                restaurant.getLatitude(),
                restaurant.getLongitude(),
                restaurant.getLegalDongName(),
                query(attemptedQueries, 0),
                query(attemptedQueries, 1),
                item == null ? null : normalizer.cleanTitle(item.title()),
                item == null ? null : item.category(),
                item == null ? null : item.address(),
                item == null ? null : item.roadAddress(),
                item == null ? null : coordinateParser.latitude(item.mapy()),
                item == null ? null : coordinateParser.longitude(item.mapx()),
                score == null ? 0.0 : score.nameScore(),
                score == null ? 0.0 : score.addressScore(),
                score == null ? 0.0 : score.distanceScore(),
                score == null ? 0.0 : score.categoryScore(),
                decision.distanceMeters(),
                decision.score(),
                decision.runnerUpScore(),
                decision.scoreGap(),
                decision.status(),
                eligibility,
                null);
    }

    private NaverEnrichmentDetail errorDetail(
            Restaurant restaurant, List<String> attemptedQueries, String message) {
        return new NaverEnrichmentDetail(
                restaurant.getId(), restaurant.getName(), restaurant.getAddress(),
                restaurant.getLatitude(), restaurant.getLongitude(), restaurant.getLegalDongName(),
                query(attemptedQueries, 0), query(attemptedQueries, 1),
                null, null, null, null, null, null,
                0.0, 0.0, 0.0, 0.0, null, 0.0, null, null,
                ExternalPlaceMatchStatus.API_ERROR,
                RecommendationEligibility.UNKNOWN,
                message);
    }

    private Instant nextRetryAt(ExternalPlaceMatchStatus status) {
        Instant now = clock.instant();
        return switch (status) {
            case MATCHED -> now.plus(properties.matchedRefreshTtl());
            case AMBIGUOUS -> now.plus(properties.ambiguousRetryDelay());
            case UNMATCHED -> now.plus(properties.unmatchedRetryDelay());
            case API_ERROR -> now.plus(properties.apiErrorRetryDelay());
        };
    }

    private String query(List<String> queries, int index) {
        return index < queries.size() ? queries.get(index) : null;
    }

    private BigDecimal decimal(double value) {
        return BigDecimal.valueOf(value).setScale(2, RoundingMode.HALF_UP);
    }

    private BigDecimal decimalOrNull(Double value) {
        return value == null ? null : decimal(value);
    }

    private String truncate(String value, int maximumLength) {
        if (!StringUtils.hasText(value)) {
            return null;
        }
        String trimmed = value.trim();
        return trimmed.length() <= maximumLength
                ? trimmed : trimmed.substring(0, maximumLength);
    }
}
