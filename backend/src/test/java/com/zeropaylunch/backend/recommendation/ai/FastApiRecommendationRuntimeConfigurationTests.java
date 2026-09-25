package com.zeropaylunch.backend.recommendation.ai;

import static org.assertj.core.api.Assertions.assertThat;

import java.net.URI;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class FastApiRecommendationRuntimeConfigurationTests {
    private final ApplicationContextRunner contextRunner = new ApplicationContextRunner()
            .withUserConfiguration(FastApiRecommendationRuntimeConfiguration.class)
            .withBean(AiIntegrationProperties.class, () -> new AiIntegrationProperties(
                    URI.create("http://127.0.0.1:8001"), Duration.ofSeconds(2), Duration.ofSeconds(8),
                    Duration.ofSeconds(27), 1, true, false))
            .withBean(TemporaryIntentAnalyzer.class, TemporaryIntentAnalyzer::new);

    @Test
    void runtimeBeansAreAbsentByDefault() {
        contextRunner.run(context -> {
            assertThat(context).doesNotHaveBean(SemanticAiClient.class);
            assertThat(context).doesNotHaveBean(AiIntentAnalysisClient.class);
            assertThat(context).doesNotHaveBean(SemanticCandidateEnricher.class);
            assertThat(context).doesNotHaveBean(RecommendationExplanationEnricher.class);
        });
    }

    @Test
    void enablingFeatureFlagRegistersExistingIntentAndRetrievalSeams() {
        contextRunner.withPropertyValues("app.ai.semantic-runtime-enabled=true").run(context -> {
            assertThat(context).hasSingleBean(SemanticAiClient.class);
            assertThat(context).hasSingleBean(AiIntentAnalysisClient.class);
            assertThat(context).hasSingleBean(SemanticCandidateEnricher.class);
            assertThat(context).hasSingleBean(RecommendationExplanationEnricher.class);
        });
    }

    @Test
    void llmFlagWithoutSemanticRuntimeLeavesAiExplanationDisabled() {
        contextRunner.withPropertyValues("app.ai.llm-explanation-enabled=true").run(context -> {
            assertThat(context).doesNotHaveBean(SemanticAiClient.class);
            assertThat(context).doesNotHaveBean(RecommendationExplanationEnricher.class);
        });
    }
}
