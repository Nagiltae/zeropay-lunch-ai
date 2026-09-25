package com.zeropaylunch.backend.recommendation.ai;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.zeropaylunch.backend.restaurant.application.RecommendationItem;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

class RecommendationExplanationEnricherTests {
    @Test
    void explanationAddsReasonsWithoutChangingRestaurantIdentityOrOrder() {
        SemanticAiClient client = mock(SemanticAiClient.class);
        when(client.explain(any())).thenReturn(new SemanticAiClient.ExplanationResponse(List.of(
                new SemanticAiClient.Explanation(1L, "근거가 있는 설명이에요.", List.of("E1"), List.of("E1"), "LLM"),
                new SemanticAiClient.Explanation(2L, "다른 근거 설명이에요.", List.of("E2"), List.of("E2"), "LLM"))));
        var enricher = new RecommendationExplanationEnricher(client, false);
        List<RecommendationItem> finalItems = List.of(item(1L), item(2L));

        List<RecommendationItem> result = enricher.explain("요청", finalItems, Map.of(1L, candidate(1L, "E1"),
                2L, candidate(2L, "E2")), 12_000);

        assertThat(result).extracting(RecommendationItem::restaurantId).containsExactly(1L, 2L);
        assertThat(result).extracting(RecommendationItem::reason)
                .containsExactly("근거가 있는 설명이에요.", "다른 근거 설명이에요.");
        verify(client).explain(any());
    }

    @Test
    void llmDisabledIsExplicitlySentAndFinalOrderIsPreserved() {
        SemanticAiClient client = mock(SemanticAiClient.class);
        when(client.explain(any())).thenAnswer(invocation -> {
            SemanticAiClient.ExplanationRequest request = invocation.getArgument(0);
            assertThat(request.useLlm()).isFalse();
            return new SemanticAiClient.ExplanationResponse(List.of(
                    new SemanticAiClient.Explanation(1L, "떡볶이 메뉴가 확인돼 추천했어요.",
                            List.of("E1"), List.of("E1"), "DETERMINISTIC_FALLBACK")));
        });
        var original = List.of(item(1L));
        var enriched = new RecommendationExplanationEnricher(client, false)
                .explain("떡볶이", original, Map.of(1L, candidate(1L, "E1")), null);
        assertThat(enriched).extracting(RecommendationItem::restaurantId).containsExactly(1L);
        assertThat(enriched.getFirst().reason()).isEqualTo("떡볶이 메뉴가 확인돼 추천했어요.");
    }

    @Test
    void experimentalLlmFlagIsExplicitlySentToFastApi() {
        SemanticAiClient client = mock(SemanticAiClient.class);
        when(client.explain(any())).thenAnswer(invocation -> {
            SemanticAiClient.ExplanationRequest request = invocation.getArgument(0);
            assertThat(request.useLlm()).isTrue();
            return new SemanticAiClient.ExplanationResponse(List.of(
                    new SemanticAiClient.Explanation(1L, "검증된 설명이에요.",
                            List.of("E1"), List.of("E1"), "LLM")));
        });
        new RecommendationExplanationEnricher(client, true)
                .explain("떡볶이", List.of(item(1L)), Map.of(1L, candidate(1L, "E1")), null);
    }

    @Test
    void clientFailurePreservesOriginalRecommendationsAndReasons() {
        SemanticAiClient client = mock(SemanticAiClient.class);
        when(client.explain(any())).thenThrow(new FastApiSemanticClient.AiUnavailableException());
        var enricher = new RecommendationExplanationEnricher(client, false);
        List<RecommendationItem> finalItems = List.of(item(1L));

        List<RecommendationItem> result = enricher.explain("요청", finalItems,
                Map.of(1L, candidate(1L, "E1")), null);

        assertThat(result).isSameAs(finalItems);
        assertThat(result.getFirst().reason()).isEqualTo("기존 결정론적 사유");
    }

    private RecommendationItem item(long id) {
        return new RecommendationItem(id, "식당 " + id, "한식", "메뉴", 9000,
                "논현동", true, false, "기존 결정론적 사유");
    }

    private SemanticAiClient.Candidate candidate(long id, String evidence) {
        return new SemanticAiClient.Candidate(id, 310, .7, List.of(
                new SemanticAiClient.MatchedClaim("claim-" + id, "FOOD_TYPE", .7, "EXACT",
                        true, false, false, false, null, List.of(evidence), "메뉴에서 음식이 확인된다.")));
    }
}
