package com.zeropaylunch.backend.recommendation.ai;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.ai")
public record AiIntegrationProperties(
        URI baseUrl,
        Duration connectTimeout,
        Duration responseTimeout,
        Duration explanationTimeout,
        int maxAttempts,
        boolean fallbackEnabled,
        boolean llmExplanationEnabled
) {
}
