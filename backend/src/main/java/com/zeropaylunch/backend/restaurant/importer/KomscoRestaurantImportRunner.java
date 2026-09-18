package com.zeropaylunch.backend.restaurant.importer;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(prefix = "app.komsco", name = "import-enabled", havingValue = "true")
class KomscoRestaurantImportRunner implements ApplicationRunner {

    private static final Logger LOGGER = LoggerFactory.getLogger(KomscoRestaurantImportRunner.class);

    private final RestaurantImportService importService;
    private final KomscoImportProperties properties;

    KomscoRestaurantImportRunner(
            RestaurantImportService importService, KomscoImportProperties properties) {
        this.importService = importService;
        this.properties = properties;
    }

    @Override
    public void run(ApplicationArguments arguments) {
        RestaurantImportResult result = properties.replaceExisting()
                ? importService.replaceRestaurants()
                : importService.importRestaurants();
        LOGGER.info(
                "KOMSCO import completed: fetchedCount={}, deduplicatedCount={}, "
                        + "activeRestaurantCount={}, insertedCount={}, updatedCount={}, skippedCount={}",
                result.fetchedCount(),
                result.deduplicatedCount(),
                result.activeRestaurantCount(),
                result.insertedCount(),
                result.updatedCount(),
                result.skippedCount());
    }
}
