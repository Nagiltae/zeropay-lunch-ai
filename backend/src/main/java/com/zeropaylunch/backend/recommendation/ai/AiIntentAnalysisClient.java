package com.zeropaylunch.backend.recommendation.ai;

public interface AiIntentAnalysisClient {

    AnalyzedIntent analyze(IntentAnalysisRequest request);
}
