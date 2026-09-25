package com.zeropaylunch.backend.recommendation.ai;

import java.util.List;

/** Internal semantic runtime contract; registered only for the opt-in recommendation runtime. */
public interface SemanticAiClient {
    IntentResult analyze(String query);
    RetrievalResult retrieve(String query, List<Long> candidateRestaurantIds, int topK);
    ExplanationResponse explain(ExplanationRequest request);

    record Query(String query) { }
    record IntentResult(String intent, List<String> foodTerms, List<String> diningContexts,
            List<String> tasteTraits, Integer maxBudget, boolean quantitativeTaste,
            String primaryIntent, List<String> claimTypes) { }
    record RetrievalRequest(String query, List<Long> candidateRestaurantIds, int topK) { }
    record RetrievalResult(List<Candidate> candidates, String policyVersion) { }
    record Candidate(Long restaurantId, double retrievalScore, double semanticSimilarity,
            List<MatchedClaim> matchedClaims) { }
    record MatchedClaim(String claimId, String claimType, double semanticSimilarity,
            String matchType, boolean exactMatch, boolean synonymMatch, boolean categoryMatch,
            boolean traitMatch, Integer mentionCount, List<String> evidenceIds, String claimText) { }
    record ExplanationRequest(String query, List<ExplanationRestaurant> restaurants, boolean useLlm) { }
    record ExplanationRestaurant(Long restaurantId, String name, List<ExplanationClaim> matchedClaims,
            DeterministicFacts deterministicFacts) { }
    record ExplanationClaim(String claimType, String text, String matchType, List<String> evidenceIds) { }
    record DeterministicFacts(boolean zeroPayAvailable, Boolean budgetMatched) { }
    record ExplanationResponse(List<Explanation> explanations) { }
    record Explanation(Long restaurantId, String explanation, List<String> usedEvidenceIds,
            List<String> availableEvidenceIds, String source) { }
}
