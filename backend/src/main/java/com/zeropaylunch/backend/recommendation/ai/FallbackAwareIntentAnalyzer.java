package com.zeropaylunch.backend.recommendation.ai;

import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class FallbackAwareIntentAnalyzer implements AiIntentAnalyzer {

    private final List<AiIntentAnalysisClient> clients;
    private final TemporaryIntentAnalyzer fallbackAnalyzer;
    private final AiIntegrationProperties properties;

    public FallbackAwareIntentAnalyzer(
            List<AiIntentAnalysisClient> clients,
            TemporaryIntentAnalyzer fallbackAnalyzer,
            AiIntegrationProperties properties
    ) {
        this.clients = clients;
        this.fallbackAnalyzer = fallbackAnalyzer;
        this.properties = properties;
    }

    @Override
    public AnalyzedIntent analyze(IntentAnalysisRequest request) {
        if (clients.isEmpty()) {
            return fallbackAnalyzer.analyze(request);
        }
        try {
            return clients.getFirst().analyze(request);
        } catch (RuntimeException exception) {
            if (!properties.fallbackEnabled()) {
                throw exception;
            }
            return fallbackAnalyzer.analyze(request);
        }
    }
}
