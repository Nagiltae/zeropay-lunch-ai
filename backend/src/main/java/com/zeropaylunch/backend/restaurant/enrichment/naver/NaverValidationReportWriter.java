package com.zeropaylunch.backend.restaurant.enrichment.naver;

import java.io.BufferedWriter;
import java.io.IOException;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import com.zeropaylunch.backend.restaurant.domain.ExternalPlaceMatchStatus;
import org.springframework.stereotype.Component;

@Component
class NaverValidationReportWriter {

    private static final String HEADER = String.join(",",
            "restaurant_id", "komsco_name", "komsco_address", "komsco_latitude",
            "komsco_longitude", "legal_dong", "first_query", "second_query",
            "naver_title", "naver_category", "naver_address", "naver_road_address",
            "naver_latitude", "naver_longitude", "name_score", "address_score",
            "distance_score", "category_score", "total_score", "distance_meters",
            "runner_up_score", "score_gap", "match_status",
            "recommendation_eligibility", "error_message");

    private final NaverLocalProperties properties;
    private final Clock clock;

    NaverValidationReportWriter(NaverLocalProperties properties, Clock clock) {
        this.properties = properties;
        this.clock = clock;
    }

    Path write(NaverEnrichmentMode mode, NaverEnrichmentResult result) {
        return writeDetails(mode.name().toLowerCase(), result.details());
    }

    Path writeMatchedReview(NaverEnrichmentResult result, int limit) {
        return writeDetails("matched-review", matchedReviewSample(result.details(), limit));
    }

    private Path writeDetails(String reportName, List<NaverEnrichmentDetail> details) {
        String timestamp = DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss")
                .withZone(clock.getZone())
                .format(clock.instant());
        Path directory = properties.reportDirectory().toAbsolutePath().normalize();
        Path report = directory.resolve(
                "naver-" + reportName + '-' + timestamp + ".csv");
        try {
            Files.createDirectories(directory);
            try (BufferedWriter writer = Files.newBufferedWriter(
                    report, StandardCharsets.UTF_8)) {
                writer.write('\ufeff');
                writer.write(HEADER);
                writer.newLine();
                for (NaverEnrichmentDetail detail : details) {
                    writer.write(row(detail));
                    writer.newLine();
                }
            }
            return report;
        } catch (IOException exception) {
            throw new IllegalStateException("Failed to write NAVER validation report", exception);
        }
    }

    private List<NaverEnrichmentDetail> matchedReviewSample(
            List<NaverEnrichmentDetail> details, int limit) {
        Map<String, List<NaverEnrichmentDetail>> byLegalDong = new TreeMap<>();
        details.stream()
                .filter(detail -> detail.matchStatus() == ExternalPlaceMatchStatus.MATCHED)
                .sorted(Comparator.comparingDouble(NaverEnrichmentDetail::totalScore)
                        .thenComparing(NaverEnrichmentDetail::restaurantId))
                .forEach(detail -> byLegalDong
                        .computeIfAbsent(groupKey(detail), ignored -> new ArrayList<>())
                        .add(detail));

        List<NaverEnrichmentDetail> selected = new ArrayList<>();
        int offset = 0;
        while (selected.size() < limit) {
            boolean added = false;
            for (List<NaverEnrichmentDetail> group : byLegalDong.values()) {
                if (offset < group.size()) {
                    selected.add(group.get(offset));
                    added = true;
                    if (selected.size() == limit) {
                        break;
                    }
                }
            }
            if (!added) {
                break;
            }
            offset++;
        }
        return List.copyOf(selected);
    }

    private String groupKey(NaverEnrichmentDetail detail) {
        return detail.legalDongName() == null ? "~UNKNOWN" : detail.legalDongName();
    }

    private String row(NaverEnrichmentDetail detail) {
        return String.join(",",
                csv(detail.restaurantId()),
                csv(detail.komscoName()),
                csv(detail.komscoAddress()),
                csv(detail.komscoLatitude()),
                csv(detail.komscoLongitude()),
                csv(detail.legalDongName()),
                csv(detail.firstQuery()),
                csv(detail.secondQuery()),
                csv(detail.naverName()),
                csv(detail.naverCategory()),
                csv(detail.naverAddress()),
                csv(detail.naverRoadAddress()),
                csv(detail.naverLatitude()),
                csv(detail.naverLongitude()),
                csv(detail.nameScore()),
                csv(detail.addressScore()),
                csv(detail.distanceScore()),
                csv(detail.categoryScore()),
                csv(detail.totalScore()),
                csv(detail.distanceMeters()),
                csv(detail.runnerUpScore()),
                csv(detail.scoreGap()),
                csv(detail.matchStatus()),
                csv(detail.recommendationEligibility()),
                csv(detail.errorMessage()));
    }

    private String csv(Object value) {
        if (value == null) {
            return "";
        }
        String text = value instanceof BigDecimal decimal
                ? decimal.toPlainString() : value.toString();
        return '"' + text.replace("\"", "\"\"") + '"';
    }
}
