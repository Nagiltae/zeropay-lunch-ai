package com.zeropaylunch.backend.restaurant.importer;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(prefix = "app.komsco", name = "scheduler-enabled", havingValue = "true")
class KomscoRestaurantSyncScheduler {

    private static final Logger LOGGER = LoggerFactory.getLogger(KomscoRestaurantSyncScheduler.class);

    private final RestaurantImportService importService;

    KomscoRestaurantSyncScheduler(RestaurantImportService importService) {
        this.importService = importService;
    }

    @Scheduled(cron = "${app.komsco.scheduler-cron}", zone = "${app.komsco.scheduler-zone}")
    void synchronize() {
        try {
            RestaurantSyncResult result = importService.synchronizeRestaurants();
            LOGGER.info(
                    "KOMSCO weekly sync completed: fetchedCount={}, deduplicatedCount={}, "
                            + "eligibleRestaurantCount={}, insertedCount={}, updatedCount={}, "
                            + "unchangedCount={}, changedForNaverCount={}, deactivatedCount={}, "
                            + "reactivatedCount={}, skippedCount={}",
                    result.fetchedCount(),
                    result.deduplicatedCount(),
                    result.eligibleRestaurantCount(),
                    result.insertedCount(),
                    result.updatedCount(),
                    result.unchangedCount(),
                    result.changedRestaurantIds().size(),
                    result.deactivatedCount(),
                    result.reactivatedCount(),
                    result.skippedCount());
        } catch (KomscoImportException exception) {
            LOGGER.error("KOMSCO weekly sync failed before database synchronization: {}",
                    exception.getMessage());
        }
    }
}
