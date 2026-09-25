package com.zeropaylunch.backend.recommendation.ai;

import com.zeropaylunch.backend.restaurant.application.RecommendationItem;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/** Adds explanations to an already-final Spring list without changing its membership or order. */
public final class RecommendationExplanationEnricher {
    private final SemanticAiClient client;
    private final boolean llmExplanationEnabled;

    public RecommendationExplanationEnricher(SemanticAiClient client, boolean llmExplanationEnabled) {
        this.client = client;
        this.llmExplanationEnabled = llmExplanationEnabled;
    }

    public List<RecommendationItem> explain(
            String query,
            List<RecommendationItem> finalRecommendations,
            Map<Long, SemanticAiClient.Candidate> semanticSignals,
            Integer budget
    ) {
        if (finalRecommendations.isEmpty()) return finalRecommendations;
        List<SemanticAiClient.ExplanationRestaurant> restaurants = finalRecommendations.stream()
                .map(item -> toRequest(item, semanticSignals.get(item.restaurantId()), budget))
                .toList();
        try {
            SemanticAiClient.ExplanationResponse response = client.explain(
                    new SemanticAiClient.ExplanationRequest(query, restaurants, llmExplanationEnabled));
            Map<Long, SemanticAiClient.Explanation> explanations = new HashMap<>();
            response.explanations().forEach(item -> explanations.put(item.restaurantId(), item));
            return finalRecommendations.stream().map(item -> {
                SemanticAiClient.Explanation explanation = explanations.get(item.restaurantId());
                return explanation == null ? item : withReason(item, explanation.explanation());
            }).toList();
        } catch (RuntimeException ignored) {
            // Explanation is auxiliary: preserve Spring's original recommendation and reason.
            return finalRecommendations;
        }
    }

    private SemanticAiClient.ExplanationRestaurant toRequest(
            RecommendationItem item, SemanticAiClient.Candidate signal, Integer budget) {
        List<SemanticAiClient.ExplanationClaim> claims = signal == null ? List.of()
                : signal.matchedClaims().stream()
                        .filter(claim -> claim.claimText() != null && !claim.claimText().isBlank())
                        .map(claim -> new SemanticAiClient.ExplanationClaim(
                                claim.claimType(), claim.claimText(), claim.matchType(), claim.evidenceIds()))
                        .toList();
        Boolean budgetMatched = budget == null ? null : item.averagePrice() <= budget;
        return new SemanticAiClient.ExplanationRestaurant(
                item.restaurantId(), item.name(), claims,
                new SemanticAiClient.DeterministicFacts(item.zeroPayAvailable(), budgetMatched));
    }

    private RecommendationItem withReason(RecommendationItem item, String reason) {
        return new RecommendationItem(item.restaurantId(), item.name(), item.category(),
                item.representativeMenu(), item.averagePrice(), item.address(), item.zeroPayAvailable(),
                item.sampleData(), reason);
    }
}
