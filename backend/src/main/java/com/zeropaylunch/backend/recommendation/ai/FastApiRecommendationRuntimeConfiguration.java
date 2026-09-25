package com.zeropaylunch.backend.recommendation.ai;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** Runtime wiring is deliberately opt-in; the default deployment keeps deterministic Spring behavior. */
@Configuration
@ConditionalOnProperty(prefix = "app.ai", name = "semantic-runtime-enabled", havingValue = "true")
public class FastApiRecommendationRuntimeConfiguration {
    @Bean
    SemanticAiClient semanticAiClient(AiIntegrationProperties properties) {
        return new FastApiSemanticClient(properties);
    }

    @Bean
    AiIntentAnalysisClient fastApiIntentAnalysisClient(
            SemanticAiClient semanticAiClient, TemporaryIntentAnalyzer deterministicAnalyzer) {
        return new FastApiIntentAnalysisAdapter(semanticAiClient, deterministicAnalyzer);
    }

    @Bean
    SemanticCandidateEnricher semanticCandidateEnricher(
            SemanticAiClient semanticAiClient, AiIntegrationProperties properties) {
        return new SemanticCandidateEnricher(semanticAiClient, properties.fallbackEnabled());
    }

    @Bean
    RecommendationExplanationEnricher recommendationExplanationEnricher(
            SemanticAiClient semanticAiClient, AiIntegrationProperties properties) {
        return new RecommendationExplanationEnricher(semanticAiClient, properties.llmExplanationEnabled());
    }
}
