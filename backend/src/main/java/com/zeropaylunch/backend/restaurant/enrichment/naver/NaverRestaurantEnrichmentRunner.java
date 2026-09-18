package com.zeropaylunch.backend.restaurant.enrichment.naver;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;
import java.nio.file.Path;
import java.util.List;

@Component
@ConditionalOnProperty(
        prefix = "app.naver-local", name = "enrichment-enabled", havingValue = "true")
class NaverRestaurantEnrichmentRunner implements ApplicationRunner {

    private static final Logger LOGGER =
            LoggerFactory.getLogger(NaverRestaurantEnrichmentRunner.class);

    private final NaverRestaurantEnrichmentService service;
    private final NaverLocalProperties properties;
    private final NaverValidationReportWriter reportWriter;

    NaverRestaurantEnrichmentRunner(
            NaverRestaurantEnrichmentService service,
            NaverLocalProperties properties,
            NaverValidationReportWriter reportWriter) {
        this.service = service;
        this.properties = properties;
        this.reportWriter = reportWriter;
    }

    @Override
    public void run(ApplicationArguments arguments) {
        boolean all = arguments.containsOption("all");
        boolean incremental = arguments.containsOption("incremental");
        if (all && incremental) {
            throw new IllegalArgumentException("Use either --all or --incremental, not both");
        }
        int limit = limit(arguments);
        NaverEnrichmentMode mode;
        NaverEnrichmentResult result;
        if (all) {
            mode = NaverEnrichmentMode.ALL;
            result = service.enrichAll();
        } else if (incremental) {
            mode = NaverEnrichmentMode.INCREMENTAL;
            result = service.enrichIncremental(limit);
        } else {
            mode = NaverEnrichmentMode.VALIDATION;
            result = service.enrichValidationSample(limit);
        }
        Path report = reportWriter.write(mode, result);
        Path matchedReviewReport = reportWriter.writeMatchedReview(result, 20);
        result.details().stream()
                .filter(detail -> detail.matchStatus()
                        == com.zeropaylunch.backend.restaurant.domain.ExternalPlaceMatchStatus.MATCHED)
                .limit(10)
                .forEach(detail -> logMatched(detail));
        LOGGER.info(
                "NAVER enrichment completed: mode={}, processed={}, matched={}, ambiguous={}, "
                        + "unmatched={}, apiError={}, inserted={}, updated={}, skipped={}, report={}",
                mode,
                result.processedCount(), result.matchedCount(), result.ambiguousCount(),
                result.unmatchedCount(), result.apiFailureCount(), result.insertedCount(),
                result.updatedCount(), result.skippedCount(), report);
        LOGGER.info(
                "NAVER eligibility: eligible={}, ineligible={}, unknown={}, matchedReviewReport={}",
                result.eligibleCount(), result.ineligibleCount(), result.unknownCount(),
                matchedReviewReport);
    }

    private void logMatched(NaverEnrichmentDetail detail) {
            LOGGER.info(
                    "NAVER matched sample: restaurantId={}, komscoName={}, naverName={}, "
                            + "distanceMeters={}, nameScore={}, addressScore={}, distanceScore={}, "
                            + "categoryScore={}, totalScore={}, runnerUpScore={}, gap={}",
                    detail.restaurantId(),
                    detail.komscoName(),
                    detail.naverName(),
                    detail.distanceMeters() == null
                            ? null : String.format("%.1f", detail.distanceMeters()),
                    detail.nameScore(), detail.addressScore(), detail.distanceScore(),
                    detail.categoryScore(), detail.totalScore(), detail.runnerUpScore(),
                    detail.scoreGap());
    }

    private int limit(ApplicationArguments arguments) {
        List<String> values = arguments.getOptionValues("limit");
        if (values == null || values.isEmpty()) {
            return properties.enrichmentLimit();
        }
        if (values.size() != 1) {
            throw new IllegalArgumentException("--limit must have exactly one value");
        }
        try {
            int parsed = Integer.parseInt(values.getFirst());
            if (parsed < 1) {
                throw new IllegalArgumentException("--limit must be positive");
            }
            return parsed;
        } catch (NumberFormatException exception) {
            throw new IllegalArgumentException("--limit must be an integer", exception);
        }
    }
}
