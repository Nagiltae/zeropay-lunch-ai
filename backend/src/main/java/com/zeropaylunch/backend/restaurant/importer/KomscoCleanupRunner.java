package com.zeropaylunch.backend.restaurant.importer;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/** Explicit one-shot cleanup entrypoint; disabled unless opt-in is provided. */
@Component
@ConditionalOnProperty(prefix = "app.komsco", name = "cleanup-enabled", havingValue = "true")
class KomscoCleanupRunner implements ApplicationRunner {

    private static final Logger LOGGER = LoggerFactory.getLogger(KomscoCleanupRunner.class);
    private final KomscoCleanupService cleanupService;
    private final ConfigurableApplicationContext context;

    KomscoCleanupRunner(KomscoCleanupService cleanupService, ConfigurableApplicationContext context) {
        this.cleanupService = cleanupService;
        this.context = context;
    }

    @Override
    public void run(ApplicationArguments args) {
        KomscoCleanupService.KomscoCleanupPlan plan = cleanupService.dryRun();
        LOGGER.warn("KOMSCO cleanup dry-run: {}", plan.rows());
        if (args.containsOption("execute")) {
            cleanupService.cleanup();
            LOGGER.warn("KOMSCO cleanup executed after explicit --execute opt-in");
        }
        SpringApplication.exit(context);
    }
}
