package com.zeropaylunch.backend.restaurant.importer;

import com.zeropaylunch.backend.restaurant.domain.Restaurant;
import com.zeropaylunch.backend.restaurant.domain.RestaurantSourceProvider;
import com.zeropaylunch.backend.restaurant.domain.RestaurantSourceSnapshot;
import com.zeropaylunch.backend.restaurant.infrastructure.RestaurantJpaRepository;
import com.zeropaylunch.backend.restaurant.infrastructure.RestaurantNaverVerificationJpaRepository;
import java.time.Clock;
import java.time.Instant;
import java.util.List;
import java.util.ArrayList;
import java.util.Set;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.springframework.stereotype.Component;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.transaction.annotation.Transactional;

@Component
class RestaurantImportWriter {

    private final RestaurantJpaRepository repository;
    private final Clock clock;
    private final RestaurantNaverVerificationJpaRepository naverVerificationRepository;

    RestaurantImportWriter(RestaurantJpaRepository repository, Clock clock) {
        this(repository, clock, null);
    }

    @Autowired
    RestaurantImportWriter(
            RestaurantJpaRepository repository,
            Clock clock,
            RestaurantNaverVerificationJpaRepository naverVerificationRepository) {
        this.repository = repository;
        this.clock = clock;
        this.naverVerificationRepository = naverVerificationRepository;
    }

    @Transactional
    public RestaurantImportOutcome upsert(RestaurantSourceSnapshot snapshot) {
        Restaurant existing = repository
                .findBySourceProviderAndExternalMerchantId(
                        snapshot.sourceProvider(), snapshot.externalMerchantId())
                .orElse(null);
        Instant syncedAt = clock.instant();
        if (existing == null) {
            repository.save(Restaurant.fromExternalSource(snapshot, syncedAt));
            return RestaurantImportOutcome.INSERTED;
        }
        if (existing.getSourceReferenceDate() != null
                && snapshot.sourceReferenceDate().isBefore(existing.getSourceReferenceDate())) {
            return RestaurantImportOutcome.SKIPPED;
        }
        if (existing.hasSameExternalSourceData(snapshot)) {
            return RestaurantImportOutcome.SKIPPED;
        }
        existing.updateExternalSource(snapshot, syncedAt);
        return RestaurantImportOutcome.UPDATED;
    }

    @Transactional
    public int replaceAllKomscoRestaurants(List<RestaurantSourceSnapshot> snapshots) {
        repository.deleteAllBySourceProvider(RestaurantSourceProvider.KOMSCO);
        Instant syncedAt = clock.instant();
        List<Restaurant> restaurants = snapshots.stream()
                .map(snapshot -> Restaurant.fromExternalSource(snapshot, syncedAt))
                .toList();
        repository.saveAll(restaurants);
        repository.flush();
        return restaurants.size();
    }

    @Transactional
    public RestaurantSyncWriteResult synchronizeKomscoRestaurants(
            List<RestaurantSyncCandidate> candidates) {
        return synchronizeKomscoRestaurants(candidates, candidates.stream()
                .map(candidate -> candidate.snapshot().externalMerchantId())
                .collect(Collectors.toSet()));
    }

    @Transactional
    public RestaurantSyncWriteResult synchronizeKomscoRestaurants(
            List<RestaurantSyncCandidate> candidates, Set<String> observedMerchantIds) {
        Map<String, Restaurant> existingByMerchantId = repository
                .findAllBySourceProvider(RestaurantSourceProvider.KOMSCO)
                .stream()
                .collect(Collectors.toMap(Restaurant::getExternalMerchantId, Function.identity()));
        Instant syncedAt = clock.instant();
        int inserted = 0;
        int updated = 0;
        int unchanged = 0;
        int deactivated = 0;
        int reactivated = 0;
        int skipped = 0;
        List<Long> changedRestaurantIds = new ArrayList<>();

        for (RestaurantSyncCandidate candidate : candidates) {
            RestaurantSourceSnapshot snapshot = candidate.snapshot();
            Restaurant existing = existingByMerchantId.get(snapshot.externalMerchantId());
            if (existing == null) {
                if (!candidate.eligible() || snapshot.name() == null || snapshot.address() == null) {
                    skipped++;
                    continue;
                }
                Restaurant insertedRestaurant = Restaurant.fromExternalSource(snapshot, syncedAt);
                repository.save(insertedRestaurant);
                existingByMerchantId.put(snapshot.externalMerchantId(), insertedRestaurant);
                inserted++;
                changedRestaurantIds.add(insertedRestaurant.getId());
                continue;
            }
            if (existing.getSourceReferenceDate() != null
                    && snapshot.sourceReferenceDate().isBefore(existing.getSourceReferenceDate())) {
                skipped++;
                continue;
            }

            boolean wasActive = existing.isActive();
            boolean matchingSourceChanged = !existing.hasSameMatchingSourceData(snapshot);
            boolean sourceDataChanged = !existing.hasSameExternalSourceData(snapshot)
                    || wasActive != candidate.eligible();
            existing.synchronizeExternalSource(snapshot, candidate.eligible(), syncedAt);
            if (sourceDataChanged) {
                updated++;
            } else {
                unchanged++;
            }
            if (matchingSourceChanged) {
                changedRestaurantIds.add(existing.getId());
                if (naverVerificationRepository != null) {
                    naverVerificationRepository.markStaleForSourceChange(existing.getId());
                }
            }
            if (wasActive && !candidate.eligible()) {
                deactivated++;
            } else if (!wasActive && candidate.eligible()) {
                reactivated++;
            }
        }
        for (Restaurant existing : existingByMerchantId.values()) {
            if ("11680108".equals(existing.getLegalDongCode())
                    && !observedMerchantIds.contains(existing.getExternalMerchantId())
                    && existing.isActive()) {
                existing.deactivateAsStale(syncedAt);
                deactivated++;
            }
        }
        repository.flush();
        return new RestaurantSyncWriteResult(
                inserted, updated, unchanged, deactivated, reactivated, skipped,
                List.copyOf(changedRestaurantIds));
    }
}
