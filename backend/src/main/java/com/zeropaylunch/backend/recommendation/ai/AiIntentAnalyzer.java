package com.zeropaylunch.backend.recommendation.ai;

public interface AiIntentAnalyzer {

    AnalyzedIntent analyze(IntentAnalysisRequest request);
}
