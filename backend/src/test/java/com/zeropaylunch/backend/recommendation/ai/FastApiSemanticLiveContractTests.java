package com.zeropaylunch.backend.recommendation.ai;

import static org.assertj.core.api.Assertions.assertThat;

import java.net.URI;
import java.time.Duration;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

/** Opt-in real HTTP integration. No Spring context, JPA, scheduler, or DB writes. */
@EnabledIfEnvironmentVariable(named = "FASTAPI_CONTRACT_URL", matches = "http://127\\.0\\.0\\.1:.*")
class FastApiSemanticLiveContractTests {
    @Test
    void intentAndScopedRetrievalThroughRealHttp() {
        var client = new FastApiSemanticClient(new AiIntegrationProperties(
                URI.create(System.getenv("FASTAPI_CONTRACT_URL")), Duration.ofSeconds(2),
                Duration.ofSeconds(8), Duration.ofSeconds(27), 1, true, false));
        var intent = client.analyze("혼밥 12000원 안에서 떡볶이 먹고 싶어");
        assertThat(intent.maxBudget()).isEqualTo(12000);
        assertThat(intent.foodTerms()).contains("떡볶이");
        var response = client.retrieve("떡볶이 먹고 싶어", List.of(9617L), 10);
        assertThat(response.candidates()).hasSize(1);
        assertThat(response.candidates().getFirst().restaurantId()).isEqualTo(9617L);
        assertThat(response.candidates().getFirst().matchedClaims().getFirst().evidenceIds()).isNotEmpty();
        // Spring candidate order is preserved when attaching the real response.
        var enriched = new SemanticCandidateEnricher(client, true).enrich("떡볶이", List.of(9617L));
        assertThat(enriched.fallbackUsed()).isFalse();
        assertThat(enriched.candidatesInSpringOrder().getFirst().restaurantId()).isEqualTo(9617L);
        assertThat(client.retrieve("떡볶이", List.of(), 10).candidates()).isEmpty();
    }
}
