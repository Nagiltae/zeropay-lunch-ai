package com.zeropaylunch.backend.restaurant.enrichment.naver;

import com.zeropaylunch.backend.restaurant.domain.ExternalPlaceProvider;
import com.zeropaylunch.backend.restaurant.domain.Restaurant;
import com.zeropaylunch.backend.restaurant.domain.RestaurantExternalPlace;
import com.zeropaylunch.backend.restaurant.domain.RestaurantExternalPlaceSnapshot;
import com.zeropaylunch.backend.restaurant.domain.RecommendationEligibility;
import com.zeropaylunch.backend.restaurant.infrastructure.RestaurantExternalPlaceJpaRepository;
import com.zeropaylunch.backend.restaurant.infrastructure.RestaurantJpaRepository;
import java.time.Clock;
import java.time.Instant;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
class RestaurantExternalPlaceWriter {

    private final RestaurantExternalPlaceJpaRepository repository;
    private final RestaurantJpaRepository restaurantRepository;
    private final Clock clock;

    RestaurantExternalPlaceWriter(
            RestaurantExternalPlaceJpaRepository repository,
            RestaurantJpaRepository restaurantRepository,
            Clock clock) {
        this.repository = repository;
        this.restaurantRepository = restaurantRepository;
        this.clock = clock;
    }

    @Transactional
    public NaverEnrichmentWriteOutcome upsert(
            Restaurant restaurant, RestaurantExternalPlaceSnapshot snapshot) {
        Instant syncedAt = clock.instant();
        Restaurant managedRestaurant = managedRestaurant(restaurant);
        RestaurantExternalPlace existing = repository
                .findByRestaurantIdAndProvider(restaurant.getId(), ExternalPlaceProvider.NAVER)
                .orElse(null);
        if (existing == null) {
            repository.save(RestaurantExternalPlace.create(
                    managedRestaurant, snapshot, syncedAt));
            managedRestaurant.updateRecommendationEligibility(
                    snapshot.recommendationEligibility(), syncedAt);
            return NaverEnrichmentWriteOutcome.INSERTED;
        }
        existing.apply(snapshot, syncedAt);
        managedRestaurant.updateRecommendationEligibility(
                snapshot.recommendationEligibility(), syncedAt);
        return NaverEnrichmentWriteOutcome.UPDATED;
    }

    @Transactional
    public void recordFailure(
            Restaurant restaurant,
            String sourceContentHash,
            String queryUsed,
            Instant nextRetryAt) {
        Instant attemptedAt = clock.instant();
        Restaurant managedRestaurant = managedRestaurant(restaurant);
        RestaurantExternalPlace existing = repository
                .findByRestaurantIdAndProvider(restaurant.getId(), ExternalPlaceProvider.NAVER)
                .orElse(null);
        if (existing == null) {
            repository.save(RestaurantExternalPlace.createFailure(
                    managedRestaurant,
                    ExternalPlaceProvider.NAVER,
                    sourceContentHash,
                    queryUsed,
                    attemptedAt,
                    nextRetryAt));
        } else {
            existing.recordAttemptFailure(sourceContentHash, attemptedAt, nextRetryAt);
        }
        managedRestaurant.updateRecommendationEligibility(
                RecommendationEligibility.UNKNOWN, attemptedAt);
    }

    private Restaurant managedRestaurant(Restaurant restaurant) {
        return restaurantRepository.findById(restaurant.getId())
                .orElseThrow(() -> new IllegalStateException(
                        "Restaurant not found: " + restaurant.getId()));
    }
}
