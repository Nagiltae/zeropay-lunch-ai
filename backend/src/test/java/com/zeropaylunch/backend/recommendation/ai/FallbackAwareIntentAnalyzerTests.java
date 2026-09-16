package com.zeropaylunch.backend.recommendation.ai;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.zeropaylunch.backend.preference.domain.SpiceLevel;
import java.net.URI;
import java.time.Duration;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.Test;

class FallbackAwareIntentAnalyzerTests {

    private final TemporaryIntentAnalyzer fallback = new TemporaryIntentAnalyzer();
    private final IntentAnalysisRequest request = new IntentAnalysisRequest(
            "국물 음식 추천해줘", "gangnam", null, SpiceLevel.ANY,
            Set.of(), Set.of(), Set.of(), List.of()
    );

    @Test
    void usesDeterministicAnalyzerBeforeFastApiClientExists() {
        FallbackAwareIntentAnalyzer analyzer = new FallbackAwareIntentAnalyzer(
                List.of(), fallback, properties(true)
        );

        assertThat(analyzer.analyze(request).category()).isPresent();
    }

    @Test
    void fallsBackWhenAiClientFailsAndPolicyAllowsIt() {
        AiIntentAnalysisClient failingClient = ignored -> {
            throw new IllegalStateException("AI unavailable");
        };
        FallbackAwareIntentAnalyzer analyzer = new FallbackAwareIntentAnalyzer(
                List.of(failingClient), fallback, properties(true)
        );

        assertThat(analyzer.analyze(request).category()).isPresent();
    }

    @Test
    void propagatesFailureWhenFallbackIsDisabled() {
        AiIntentAnalysisClient failingClient = ignored -> {
            throw new IllegalStateException("AI unavailable");
        };
        FallbackAwareIntentAnalyzer analyzer = new FallbackAwareIntentAnalyzer(
                List.of(failingClient), fallback, properties(false)
        );

        assertThatThrownBy(() -> analyzer.analyze(request))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("AI unavailable");
    }

    private AiIntegrationProperties properties(boolean fallbackEnabled) {
        return new AiIntegrationProperties(
                URI.create("http://localhost:8001"),
                Duration.ofSeconds(2),
                Duration.ofSeconds(8),
                1,
                fallbackEnabled
        );
    }
}
