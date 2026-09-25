package com.zeropaylunch.backend.recommendation.ai;

import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

/** Accepts Spring-filtered/ranked IDs only; attaches signals without reordering or dropping them. */
public final class SemanticCandidateEnricher {
    private final SemanticAiClient client;
    private final boolean fallbackEnabled;

    public SemanticCandidateEnricher(SemanticAiClient client, boolean fallbackEnabled) {
        this.client = client;
        this.fallbackEnabled = fallbackEnabled;
    }

    public Result enrich(String query, List<Long> hardFilteredIds) {
        if (hardFilteredIds.isEmpty()) return new Result(List.of(), false);
        try {
            var response = client.retrieve(query, hardFilteredIds, Math.min(100, hardFilteredIds.size()));
            Map<Long, SemanticAiClient.Candidate> signals = response.candidates().stream()
                    .filter(c -> hardFilteredIds.contains(c.restaurantId()))
                    .collect(Collectors.toMap(SemanticAiClient.Candidate::restaurantId, Function.identity()));
            return new Result(hardFilteredIds.stream().map(id -> new Item(id, signals.get(id))).toList(), false);
        } catch (FastApiSemanticClient.AiUnavailableException exception) {
            if (!fallbackEnabled) throw exception;
            return new Result(hardFilteredIds.stream().map(id -> new Item(id, null)).toList(), true);
        }
    }

    public record Item(Long restaurantId, SemanticAiClient.Candidate semanticSignal) { }
    public record Result(List<Item> candidatesInSpringOrder, boolean fallbackUsed) { }
}
