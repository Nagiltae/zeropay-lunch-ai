package com.zeropaylunch.backend.recommendation.ai;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class FastApiSemanticClientTests {
    private HttpServer server;
    private FastApiSemanticClient client;
    private final AtomicReference<String> request = new AtomicReference<>();
    private final AtomicReference<String> response = new AtomicReference<>();
    private final AtomicInteger status = new AtomicInteger(200);
    private final AtomicInteger calls = new AtomicInteger();
    private final ObjectMapper mapper = new ObjectMapper();

    @BeforeEach
    void setup() throws Exception {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/internal/v1/", exchange -> {
            calls.incrementAndGet();
            request.set(new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
            byte[] body = response.get().getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("Content-Type", "application/json");
            exchange.sendResponseHeaders(status.get(), body.length);
            exchange.getResponseBody().write(body);
            exchange.close();
        });
        server.start();
        client = new FastApiSemanticClient(properties(Duration.ofSeconds(1)));
    }

    private AiIntegrationProperties properties(Duration timeout) {
        return new AiIntegrationProperties(URI.create("http://127.0.0.1:" + server.getAddress().getPort()),
                Duration.ofMillis(200), timeout, Duration.ofSeconds(1), 1, true, false);
    }

    @AfterEach
    void stop() { server.stop(0); }

    @Test
    void intentRequestAndResponse() throws Exception {
        response.set("""
                {"intent":"RESTAURANT_RECOMMENDATION","foodTerms":["떡볶이"],
                 "diningContexts":["SOLO_DINING"],"tasteTraits":[],"maxBudget":12000,
                 "quantitativeTaste":false,"primaryIntent":"FOOD","claimTypes":["FOOD_TYPE"]}
                """);
        var result = client.analyze("혼밥 12000원 떡볶이");
        assertThat(result.maxBudget()).isEqualTo(12000);
        assertThat(mapper.readTree(request.get()).get("query").asText()).contains("떡볶이");
    }

    private static String candidate(long id) {
        return """
                {"candidates":[{"restaurantId":%d,"retrievalScore":320.001,"semanticSimilarity":0.5,
                "matchedClaims":[{"claimId":"c1","claimType":"FOOD_TYPE","semanticSimilarity":0.5,
                "claimText":"메뉴에서 떡볶이가 확인된다.",
                "matchType":"EXACT","exactMatch":true,"synonymMatch":false,"categoryMatch":false,
                "traitMatch":true,"mentionCount":null,"evidenceIds":["E011"]}]}],"policyVersion":"v2"}
                """.formatted(id);
    }

    @Test
    void scopeAndEvidenceRoundTrip() throws Exception {
        response.set(candidate(9617));
        var result = client.retrieve("떡볶이", List.of(9617L), 10);
        assertThat(mapper.readTree(request.get()).get("candidateRestaurantIds").get(0).asLong()).isEqualTo(9617L);
        assertThat(result.candidates().getFirst().matchedClaims().getFirst().evidenceIds()).containsExactly("E011");
        assertThat(result.candidates().getFirst().semanticSimilarity()).isEqualTo(.5);
    }

    @Test
    void rejectsOutOfScopeResponse() {
        response.set(candidate(9731));
        assertThatThrownBy(() -> client.retrieve("떡볶이", List.of(9617L), 10))
                .isInstanceOf(FastApiSemanticClient.AiUnavailableException.class);
    }

    @Test
    void emptyScopeSkipsHttp() {
        assertThat(client.retrieve("떡볶이", List.of(), 10).candidates()).isEmpty();
        assertThat(calls.get()).isZero();
    }

    @Test
    void failuresPreserveSpringCandidatesAndOrder() {
        response.set("{\"code\":\"SEMANTIC_RETRIEVAL_UNAVAILABLE\"}");
        status.set(503);
        var result = new SemanticCandidateEnricher(client, true).enrich("떡볶이", List.of(9617L, 9568L));
        assertThat(result.fallbackUsed()).isTrue();
        assertThat(result.candidatesInSpringOrder()).extracting(SemanticCandidateEnricher.Item::restaurantId)
                .containsExactly(9617L, 9568L);
        assertThat(calls.get()).isEqualTo(1);
        assertThatThrownBy(() -> new SemanticCandidateEnricher(client, false).enrich("떡볶이", List.of(9617L)))
                .isInstanceOf(FastApiSemanticClient.AiUnavailableException.class);
    }

    @Test
    void semanticOrderCannotOverrideSpringRankingOrIntroduceIds() {
        response.set(candidate(9568));
        var result = new SemanticCandidateEnricher(client, true).enrich("떡볶이", List.of(9617L, 9568L));
        assertThat(result.candidatesInSpringOrder()).extracting(SemanticCandidateEnricher.Item::restaurantId)
                .containsExactly(9617L, 9568L);
        assertThat(result.candidatesInSpringOrder().getFirst().semanticSignal()).isNull();
    }

    @Test
    void malformedJsonIsUnavailable() {
        response.set("not-json");
        assertThatThrownBy(() -> client.retrieve("떡볶이", List.of(9617L), 10))
                .isInstanceOf(FastApiSemanticClient.AiUnavailableException.class);
    }

    @Test
    void explanationRequestIsGroundedAndResponseIdentityIsValidated() throws Exception {
        response.set("""
                {"explanations":[{"restaurantId":9617,
                "explanation":"떡볶이 메뉴가 확인돼 요청과 잘 맞아요.",
                "usedEvidenceIds":["E011"],"availableEvidenceIds":["E011"],"source":"DETERMINISTIC_FALLBACK"}]}
                """);
        var explanationRequest = new SemanticAiClient.ExplanationRequest("떡볶이 먹고 싶어", List.of(
                new SemanticAiClient.ExplanationRestaurant(9617L, "테스트 식당", List.of(
                        new SemanticAiClient.ExplanationClaim(
                                "FOOD_TYPE", "메뉴에서 떡볶이가 확인된다.", "EXACT", List.of("E011"))),
                new SemanticAiClient.DeterministicFacts(true, true))), false);

        var result = client.explain(explanationRequest);

        assertThat(result.explanations().getFirst().restaurantId()).isEqualTo(9617L);
        assertThat(result.explanations().getFirst().usedEvidenceIds()).containsExactly("E011");
        assertThat(mapper.readTree(request.get()).get("restaurants").get(0).get("name").asText())
                .isEqualTo("테스트 식당");
        assertThat(mapper.readTree(request.get()).get("restaurants").get(0).has("retrievalScore")).isFalse();
        assertThat(mapper.readTree(request.get()).get("restaurants").get(0).has("catalogHash")).isFalse();
        assertThat(mapper.readTree(request.get()).get("useLlm").asBoolean()).isFalse();
    }

    @Test
    void explanationRejectsForeignRestaurantIdsAndUnknownEvidence() {
        response.set("""
                {"explanations":[{"restaurantId":9999,"explanation":"설명입니다.",
                "usedEvidenceIds":["E999"],"availableEvidenceIds":["E999"],"source":"LLM"}]}
                """);
        var explanationRequest = new SemanticAiClient.ExplanationRequest("떡볶이", List.of(
                new SemanticAiClient.ExplanationRestaurant(9617L, "테스트", List.of(
                        new SemanticAiClient.ExplanationClaim("FOOD_TYPE", "떡볶이 메뉴", "EXACT", List.of("E011"))),
                        new SemanticAiClient.DeterministicFacts(true, null))), false);
        assertThatThrownBy(() -> client.explain(explanationRequest))
                .isInstanceOf(FastApiSemanticClient.AiUnavailableException.class);
    }

    @Test
    void explanationAcceptsSupplementalEvidenceDeclaredByScopedFastApiLookup() {
        response.set("""
                {"explanations":[{"restaurantId":9617,"explanation":"혼밥 평가가 확인돼요.",
                "usedEvidenceIds":["E011","E023"],"availableEvidenceIds":["E011","E023"],"source":"LLM"}]}
                """);
        var explanationRequest = new SemanticAiClient.ExplanationRequest("혼밥하면서 떡볶이", List.of(
                new SemanticAiClient.ExplanationRestaurant(9617L, "테스트", List.of(
                        new SemanticAiClient.ExplanationClaim("FOOD_TYPE", "떡볶이 메뉴", "EXACT", List.of("E011"))),
                        new SemanticAiClient.DeterministicFacts(true, null))), true);
        var result = client.explain(explanationRequest);
        assertThat(result.explanations().getFirst().usedEvidenceIds()).containsExactly("E011", "E023");
        assertThat(result.explanations().getFirst().availableEvidenceIds()).containsExactly("E011", "E023");
    }

    @Test
    void responseTimeoutIsBounded() {
        server.createContext("/slow", exchange -> { exchange.close(); });
        response.set(candidate(9617));
        // An accepted TCP connection that never produces response headers.
        server.removeContext("/internal/v1/");
        server.createContext("/internal/v1/", exchange -> { });
        var shortClient = new FastApiSemanticClient(properties(Duration.ofMillis(100)));
        assertThatThrownBy(() -> shortClient.retrieve("떡볶이", List.of(9617L), 10))
                .isInstanceOf(FastApiSemanticClient.AiUnavailableException.class);
    }
}
