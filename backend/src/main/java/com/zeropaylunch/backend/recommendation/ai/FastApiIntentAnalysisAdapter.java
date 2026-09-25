package com.zeropaylunch.backend.recommendation.ai;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;

/** Maps the internal FastAPI intent contract onto the existing Spring recommendation intent. */
public final class FastApiIntentAnalysisAdapter implements AiIntentAnalysisClient {
    private final SemanticAiClient client;
    private final TemporaryIntentAnalyzer deterministicAnalyzer;

    public FastApiIntentAnalysisAdapter(SemanticAiClient client, TemporaryIntentAnalyzer deterministicAnalyzer) {
        this.client = client;
        this.deterministicAnalyzer = deterministicAnalyzer;
    }

    @Override
    public AnalyzedIntent analyze(IntentAnalysisRequest request) {
        SemanticAiClient.IntentResult aiIntent = client.analyze(request.message());
        AnalyzedIntent baseline = deterministicAnalyzer.analyze(request);
        LinkedHashSet<String> keywords = new LinkedHashSet<>(baseline.keywords());
        keywords.addAll(aiIntent.foodTerms());
        keywords.addAll(aiIntent.diningContexts());
        keywords.addAll(aiIntent.tasteTraits());
        return new AnalyzedIntent(
                AnalyzedIntent.IntentType.RECOMMEND_RESTAURANT,
                aiIntent.maxBudget() != null ? aiIntent.maxBudget() : baseline.maximumPrice(),
                baseline.category(),
                List.copyOf(keywords),
                baseline.clarificationRequired(),
                baseline.clarificationQuestion());
    }
}
