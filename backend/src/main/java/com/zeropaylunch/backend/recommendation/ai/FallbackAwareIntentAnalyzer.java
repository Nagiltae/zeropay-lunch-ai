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
			// FastAPI 연동 전 개발 환경에서도 추천 흐름을 유지하도록 결정론적 분석기를 사용한다.
            return fallbackAnalyzer.analyze(request);
        }
        try {
            return clients.getFirst().analyze(request);
        } catch (RuntimeException exception) {
            if (!properties.fallbackEnabled()) {
                throw exception;
            }
			// AI 경계 장애가 후보 필터링 전체를 중단시키지 않도록 설정된 경우에만 fallback한다.
            return fallbackAnalyzer.analyze(request);
        }
    }
}
