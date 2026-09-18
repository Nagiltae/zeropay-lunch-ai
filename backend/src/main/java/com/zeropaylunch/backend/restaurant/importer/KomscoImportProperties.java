package com.zeropaylunch.backend.restaurant.importer;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.komsco")
public record KomscoImportProperties(
        URI baseUrl,
        String serviceKey,
        int pageSize,
        Duration connectTimeout,
        Duration readTimeout,
        boolean importEnabled,
        boolean replaceExisting,
        boolean schedulerEnabled,
        String schedulerCron,
        String schedulerZone) {

    public KomscoImportProperties {
        if (pageSize < 1) {
            throw new IllegalArgumentException("app.komsco.page-size must be positive");
        }
    }
}
