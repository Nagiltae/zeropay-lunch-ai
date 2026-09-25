package com.zeropaylunch.backend.recommendation.ai;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.HashSet;
import java.util.List;

/** Internal FastAPI client. It is registered only when the semantic runtime feature flag is enabled. */
public final class FastApiSemanticClient implements SemanticAiClient {
    private final AiIntegrationProperties properties;
    private final HttpClient http;
    private final ObjectMapper mapper = new ObjectMapper();

    public FastApiSemanticClient(AiIntegrationProperties properties) {
        this.properties = properties;
        this.http = HttpClient.newBuilder().version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(properties.connectTimeout())
                .followRedirects(HttpClient.Redirect.NEVER).build();
    }

    @Override
    public IntentResult analyze(String query) {
        validateQuery(query);
        IntentResult result = post("/internal/v1/intent-analysis", new Query(query), IntentResult.class);
        if (result == null || !"RESTAURANT_RECOMMENDATION".equals(result.intent())
                || result.foodTerms() == null || result.diningContexts() == null
                || result.tasteTraits() == null || result.claimTypes() == null) {
            throw new AiUnavailableException();
        }
        return result;
    }

    @Override
    public RetrievalResult retrieve(String query, List<Long> ids, int topK) {
        validateQuery(query);
        if (ids == null || ids.size() > 1000 || ids.stream().anyMatch(id -> id == null || id <= 0)
                || topK < 1 || topK > 100) {
            throw new IllegalArgumentException("invalid semantic candidate scope");
        }
        if (ids.isEmpty()) return new RetrievalResult(List.of(), "empty-scope");
        List<Long> scope = ids.stream().distinct().toList();
        RetrievalResult result = post("/internal/v1/semantic-retrieval",
                new RetrievalRequest(query, scope, topK), RetrievalResult.class);
        if (result == null || result.candidates() == null || result.candidates().size() > topK) {
            throw new AiUnavailableException();
        }
        var seen = new HashSet<Long>();
        for (Candidate candidate : result.candidates()) {
            if (candidate == null || !scope.contains(candidate.restaurantId())
                    || !seen.add(candidate.restaurantId()) || !Double.isFinite(candidate.retrievalScore())
                    || !Double.isFinite(candidate.semanticSimilarity()) || candidate.matchedClaims() == null
                    || candidate.matchedClaims().isEmpty()) throw new AiUnavailableException();
            for (MatchedClaim claim : candidate.matchedClaims()) {
                if (claim == null || claim.claimId() == null || claim.claimType() == null
                        || claim.evidenceIds() == null || claim.evidenceIds().isEmpty()
                    || !Double.isFinite(claim.semanticSimilarity())) throw new AiUnavailableException();
                if (claim.claimText() == null || claim.claimText().isBlank() || claim.claimText().length() > 500) {
                    throw new AiUnavailableException();
                }
            }
        }
        return result;
    }

    @Override
    public ExplanationResponse explain(ExplanationRequest request) {
        if (request == null || request.query() == null || request.query().isBlank()
                || request.query().length() > 2000 || request.restaurants() == null
                || request.restaurants().isEmpty() || request.restaurants().size() > 3) {
            throw new IllegalArgumentException("invalid recommendation explanation request");
        }
        var requestedIds = new HashSet<Long>();
        for (ExplanationRestaurant restaurant : request.restaurants()) {
            if (restaurant == null || restaurant.restaurantId() == null || restaurant.restaurantId() <= 0
                    || restaurant.name() == null || restaurant.name().isBlank()
                    || restaurant.matchedClaims() == null || restaurant.matchedClaims().size() > 10
                    || restaurant.deterministicFacts() == null || !requestedIds.add(restaurant.restaurantId())) {
                throw new IllegalArgumentException("invalid recommendation explanation restaurant");
            }
            for (ExplanationClaim claim : restaurant.matchedClaims()) {
                if (claim == null || claim.claimType() == null || claim.text() == null || claim.text().isBlank()
                        || claim.matchType() == null || claim.evidenceIds() == null
                        || claim.evidenceIds().isEmpty()) {
                    throw new IllegalArgumentException("invalid recommendation explanation evidence");
                }
            }
        }
        ExplanationResponse response = post("/internal/v1/recommendation-explanations", request,
                ExplanationResponse.class, properties.explanationTimeout());
        if (response == null || response.explanations() == null
                || response.explanations().size() != request.restaurants().size()) {
            throw new AiUnavailableException();
        }
        List<Long> responseIds = response.explanations().stream().map(Explanation::restaurantId).toList();
        List<Long> expectedIds = request.restaurants().stream().map(ExplanationRestaurant::restaurantId).toList();
        if (!responseIds.equals(expectedIds)) throw new AiUnavailableException();
        for (int index = 0; index < response.explanations().size(); index++) {
            Explanation explanation = response.explanations().get(index);
            ExplanationRestaurant restaurant = request.restaurants().get(index);
            if (explanation.explanation() == null || explanation.explanation().isBlank()
                    || explanation.explanation().length() > 320
                    || explanation.usedEvidenceIds() == null
                    || explanation.availableEvidenceIds() == null
                    || explanation.availableEvidenceIds().size() > 100
                    || explanation.usedEvidenceIds().size() > 10
                    || explanation.availableEvidenceIds().stream().anyMatch(id -> id == null || id.isBlank())
                    || explanation.usedEvidenceIds().stream().anyMatch(id -> id == null || id.isBlank())
                    || !List.of("LLM", "DETERMINISTIC_FALLBACK").contains(explanation.source())) {
                throw new AiUnavailableException();
            }
            if (!request.useLlm() && "LLM".equals(explanation.source())) {
                throw new AiUnavailableException();
            }
            var allowedEvidence = new HashSet<>(explanation.availableEvidenceIds());
            if (allowedEvidence.size() != explanation.availableEvidenceIds().size()
                    || !allowedEvidence.containsAll(explanation.usedEvidenceIds())
                    || ("LLM".equals(explanation.source()) && explanation.usedEvidenceIds().isEmpty())) {
                throw new AiUnavailableException();
            }
        }
        return response;
    }

    private static void validateQuery(String query) {
        if (query == null || query.isBlank() || query.length() > 2000) {
            throw new IllegalArgumentException("invalid semantic query");
        }
    }

    private <T> T post(String path, Object body, Class<T> responseType) {
        return post(path, body, responseType, properties.responseTimeout());
    }

    private <T> T post(String path, Object body, Class<T> responseType, Duration timeout) {
        try {
            HttpRequest request = HttpRequest.newBuilder(properties.baseUrl().resolve(path))
                    .timeout(timeout).header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(mapper.writeValueAsString(body))).build();
            HttpResponse<String> response = http.send(request, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() != 200) throw new AiUnavailableException();
            return mapper.readValue(response.body(), responseType);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new AiUnavailableException();
        } catch (IOException exception) {
            throw new AiUnavailableException();
        }
    }

    public static final class AiUnavailableException extends RuntimeException {
        public AiUnavailableException() { super("AI dependency unavailable"); }
    }
}
