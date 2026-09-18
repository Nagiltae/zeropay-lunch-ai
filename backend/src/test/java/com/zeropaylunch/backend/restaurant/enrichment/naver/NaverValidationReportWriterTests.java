package com.zeropaylunch.backend.restaurant.enrichment.naver;

import static org.assertj.core.api.Assertions.assertThat;

import com.zeropaylunch.backend.restaurant.domain.ExternalPlaceMatchStatus;
import com.zeropaylunch.backend.restaurant.domain.RecommendationEligibility;
import java.math.BigDecimal;
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class NaverValidationReportWriterTests {

    @TempDir
    Path reportDirectory;

    @Test
    void writesCsvWithQueriesScoreBreakdownAndStatus() throws Exception {
        Clock clock = Clock.fixed(Instant.parse("2026-09-19T00:00:00Z"), ZoneOffset.UTC);
        NaverValidationReportWriter writer =
                new NaverValidationReportWriter(properties(), clock);
        NaverEnrichmentDetail detail = new NaverEnrichmentDetail(
                1L, "토브", "서울 강남구 학동로 1",
                new BigDecimal("37.5000000"), new BigDecimal("127.0300000"), "논현동",
                "토브 논현동", "토브 강남구", "토브", "음식점>한식",
                "서울 강남구 논현동 1", "서울 강남구 학동로 1",
                new BigDecimal("37.5000000"), new BigDecimal("127.0300000"),
                40.0, 30.0, 20.0, 10.0, 0.0, 100.0, 50.0, 50.0,
                ExternalPlaceMatchStatus.MATCHED, RecommendationEligibility.ELIGIBLE, null);
        NaverEnrichmentResult result = new NaverEnrichmentResult(
                1, 1, 0, 0, 0, 1, 0, 0, 1, 0, 0, List.of(detail));

        Path report = writer.write(NaverEnrichmentMode.VALIDATION, result);
        Path reviewReport = writer.writeMatchedReview(result, 20);
        String csv = Files.readString(report);
        String reviewCsv = Files.readString(reviewReport);

        assertThat(report.getFileName().toString())
                .isEqualTo("naver-validation-20260919-000000.csv");
        assertThat(csv).contains(
                "first_query", "runner_up_score", "score_gap",
                "recommendation_eligibility");
        assertThat(csv).contains("\"토브 논현동\"", "\"MATCHED\"");
        assertThat(reviewReport.getFileName().toString())
                .isEqualTo("naver-matched-review-20260919-000000.csv");
        assertThat(reviewCsv).contains("\"토브\"", "\"ELIGIBLE\"");
    }

    private NaverLocalProperties properties() {
        return new NaverLocalProperties(
                URI.create("https://example.test/naver-local"), "id", "secret",
                Duration.ofSeconds(1), Duration.ofSeconds(1), Duration.ZERO,
                Duration.ofMillis(1), 2, 5, false, 100, 2, 100,
                Duration.ofDays(30), Duration.ofDays(7), Duration.ofDays(7),
                Duration.ofHours(1), reportDirectory);
    }
}
