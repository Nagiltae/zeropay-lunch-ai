package com.zeropaylunch.backend.recommendation.ai;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.zeropaylunch.backend.preference.domain.SpiceLevel;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.Test;

class FastApiIntentAnalysisAdapterTests {
    @Test
    void mapsFastApiBudgetAndSemanticTermsToExistingIntentWhilePreservingSpringPreferences() {
        SemanticAiClient client = mock(SemanticAiClient.class);
        when(client.analyze("혼밥 12000원 안에서 떡볶이 먹고 싶어"))
                .thenReturn(new SemanticAiClient.IntentResult(
                        "RESTAURANT_RECOMMENDATION", List.of("떡볶이"), List.of("SOLO_DINING"),
                        List.of(), 12_000, false, "FOOD", List.of("FOOD_TYPE")));
        TemporaryIntentAnalyzer deterministic = new TemporaryIntentAnalyzer();
        FastApiIntentAnalysisAdapter adapter = new FastApiIntentAnalysisAdapter(client, deterministic);
        IntentAnalysisRequest request = new IntentAnalysisRequest(
                "혼밥 12000원 안에서 떡볶이 먹고 싶어", 15_000, SpiceLevel.ANY,
                Set.of(), Set.of(), Set.of(), List.of());

        AnalyzedIntent result = adapter.analyze(request);

        assertThat(result.maximumPrice()).isEqualTo(12_000);
        assertThat(result.keywords()).contains("떡볶이", "SOLO_DINING");
        assertThat(result.category()).isEmpty();
        assertThat(result.intent()).isEqualTo(AnalyzedIntent.IntentType.RECOMMEND_RESTAURANT);
    }

    @Test
    void usesSpringDefaultBudgetWhenFastApiDoesNotFindAnExplicitBudget() {
        SemanticAiClient client = mock(SemanticAiClient.class);
        when(client.analyze("떡볶이"))
                .thenReturn(new SemanticAiClient.IntentResult(
                        "RESTAURANT_RECOMMENDATION", List.of("떡볶이"), List.of(), List.of(),
                        null, false, "FOOD", List.of("FOOD_TYPE")));
        IntentAnalysisRequest request = new IntentAnalysisRequest(
                "떡볶이", 11_000, SpiceLevel.ANY, Set.of(), Set.of(), Set.of(), List.of());

        assertThat(new FastApiIntentAnalysisAdapter(client, new TemporaryIntentAnalyzer())
                .analyze(request).maximumPrice()).isNull();
    }
}
