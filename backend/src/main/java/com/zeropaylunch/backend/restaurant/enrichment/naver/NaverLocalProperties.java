package com.zeropaylunch.backend.restaurant.enrichment.naver;

import java.net.URI;
import java.time.Duration;
import java.nio.file.Path;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.naver-local")
record NaverLocalProperties(
        URI baseUrl,
        String clientId,
        String clientSecret,
        Duration connectTimeout,
        Duration readTimeout,
        Duration requestInterval,
        Duration retryBackoff,
        int maxAttempts,
        int display,
        boolean enrichmentEnabled,
        int enrichmentLimit,
        int maxSearchQueries,
        int maxValidationLimit,
        Duration matchedRefreshTtl,
        Duration ambiguousRetryDelay,
        Duration unmatchedRetryDelay,
        Duration apiErrorRetryDelay,
        Path reportDirectory) {

    NaverLocalProperties {
        if (display < 1 || display > 5) {
            throw new IllegalArgumentException("app.naver-local.display must be between 1 and 5");
        }
        if (enrichmentLimit < 1) {
            throw new IllegalArgumentException("app.naver-local.enrichment-limit must be positive");
        }
        if (maxSearchQueries < 1 || maxSearchQueries > 2) {
            throw new IllegalArgumentException(
                    "app.naver-local.max-search-queries must be between 1 and 2");
        }
        if (maxAttempts < 1 || maxAttempts > 3) {
            throw new IllegalArgumentException("app.naver-local.max-attempts must be between 1 and 3");
        }
        if (maxValidationLimit < 1) {
            throw new IllegalArgumentException(
                    "app.naver-local.max-validation-limit must be positive");
        }
    }
}
