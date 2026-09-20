package com.zeropaylunch.backend.restaurant.importer;

import com.zeropaylunch.backend.restaurant.domain.RestaurantSourceProvider;
import com.zeropaylunch.backend.restaurant.domain.RestaurantSourceSnapshot;
import java.math.BigDecimal;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

@Service
public class RestaurantImportService {

    private static final Logger LOGGER = LoggerFactory.getLogger(RestaurantImportService.class);

    private final KomscoMerchantClient client;
    private final KomscoMerchantDeduplicator deduplicator;
    private final KomscoMerchantFilter filter;
    private final RestaurantImportWriter writer;

    RestaurantImportService(
            KomscoMerchantClient client,
            KomscoMerchantDeduplicator deduplicator,
            KomscoMerchantFilter filter,
            RestaurantImportWriter writer) {
        this.client = client;
        this.deduplicator = deduplicator;
        this.filter = filter;
        this.writer = writer;
    }

    public RestaurantImportResult importRestaurants() {
        return importRestaurants(false);
    }

    public RestaurantImportResult replaceRestaurants() {
        return importRestaurants(true);
    }

    public RestaurantSyncResult synchronizeRestaurants() {
        List<KomscoMerchantRecord> fetched = client.fetchAllGangnamMerchants();
        KomscoDeduplicationResult deduplicated = deduplicator.selectLatest(fetched);
        List<RestaurantSyncCandidate> candidates = deduplicated.records().stream()
                .map(merchant -> new RestaurantSyncCandidate(
                        toSnapshot(merchant), filter.isActiveGangnamRestaurant(merchant)))
                .filter(candidate -> candidate.snapshot() != null)
                .toList();
        int eligibleCount = (int) candidates.stream()
                .filter(RestaurantSyncCandidate::eligible)
                .filter(candidate -> candidate.snapshot().name() != null)
                .filter(candidate -> candidate.snapshot().address() != null)
                .count();
        Set<String> observedMerchantIds = deduplicated.records().stream()
                .map(merchant -> merchant.source().altText())
                .filter(Objects::nonNull)
                .map(String::trim)
                .collect(Collectors.toSet());
        RestaurantSyncWriteResult writeResult = writer.synchronizeKomscoRestaurants(
                candidates, observedMerchantIds);
        int skipped = fetched.size()
                - writeResult.insertedCount()
                - writeResult.updatedCount()
                - writeResult.unchangedCount();
        return new RestaurantSyncResult(
                fetched.size(),
                deduplicated.records().size(),
                eligibleCount,
                writeResult.insertedCount(),
                writeResult.updatedCount(),
                writeResult.unchangedCount(),
                writeResult.deactivatedCount(),
                writeResult.reactivatedCount(),
                skipped,
                writeResult.changedRestaurantIds());
    }

    private RestaurantImportResult importRestaurants(boolean replaceExisting) {
        List<KomscoMerchantRecord> fetched = client.fetchAllGangnamMerchants();
        KomscoDeduplicationResult deduplicated = deduplicator.selectLatest(fetched);
        List<LatestKomscoMerchant> activeRestaurants = deduplicated.records().stream()
                .filter(filter::isActiveGangnamRestaurant)
                .toList();

        List<RestaurantSourceSnapshot> snapshots = activeRestaurants.stream()
                .map(this::toSnapshot)
                .filter(Objects::nonNull)
                .filter(snapshot -> snapshot.name() != null && snapshot.address() != null)
                .toList();

        if (replaceExisting) {
            int inserted = writer.replaceAllKomscoRestaurants(snapshots);
            return new RestaurantImportResult(
                    fetched.size(),
                    deduplicated.records().size(),
                    activeRestaurants.size(),
                    inserted,
                    0,
                    fetched.size() - inserted);
        }

        int inserted = 0;
        int updated = 0;
        for (RestaurantSourceSnapshot snapshot : snapshots) {
            try {
                RestaurantImportOutcome outcome = writer.upsert(snapshot);
                if (outcome == RestaurantImportOutcome.INSERTED) {
                    inserted++;
                } else if (outcome == RestaurantImportOutcome.UPDATED) {
                    updated++;
                }
            } catch (RuntimeException exception) {
                LOGGER.warn("Skipping invalid KOMSCO merchant during persistence: {}",
                        snapshot.externalMerchantId());
            }
        }
        int skipped = fetched.size() - inserted - updated;
        return new RestaurantImportResult(
                fetched.size(),
                deduplicated.records().size(),
                activeRestaurants.size(),
                inserted,
                updated,
                skipped);
    }

    private RestaurantSourceSnapshot toSnapshot(LatestKomscoMerchant merchant) {
        KomscoMerchantRecord source = merchant.source();
        return new RestaurantSourceSnapshot(
                RestaurantSourceProvider.KOMSCO,
                source.altText().trim(),
                trimToNull(source.name()),
                trimToNull(source.address()),
                trimToNull(source.detailAddress()),
                trimToNull(source.postalCode()),
                decimalOrNull(source.lat()),
                decimalOrNull(source.lot()),
                trimToNull(source.legalDongCode()),
                trimToNull(source.legalDongName()),
                trimToNull(source.industryCode()),
                trimToNull(source.industryName()),
                trimToNull(source.providerInstitutionCode()),
                trimToNull(source.businessStatus()),
                trimToNull(source.businessStatusName()),
                merchant.referenceDate());
    }

    private BigDecimal decimalOrNull(String value) {
        if (!StringUtils.hasText(value)) {
            return null;
        }
        try {
            return new BigDecimal(value.trim());
        } catch (NumberFormatException exception) {
            return null;
        }
    }

    private String trimToNull(String value) {
        return StringUtils.hasText(value) ? value.trim() : null;
    }
}
