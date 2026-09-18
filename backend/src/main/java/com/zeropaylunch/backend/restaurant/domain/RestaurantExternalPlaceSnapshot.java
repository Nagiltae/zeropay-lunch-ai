package com.zeropaylunch.backend.restaurant.domain;

import java.math.BigDecimal;
import java.time.Instant;

public record RestaurantExternalPlaceSnapshot(
        ExternalPlaceProvider provider,
        String externalName,
        String category,
        String description,
        String link,
        String address,
        String roadAddress,
        BigDecimal latitude,
        BigDecimal longitude,
        ExternalPlaceMatchStatus matchStatus,
        BigDecimal matchScore,
        BigDecimal nameScore,
        BigDecimal addressScore,
        BigDecimal distanceScore,
        BigDecimal categoryScore,
        BigDecimal matchDistanceMeters,
        BigDecimal runnerUpScore,
        BigDecimal scoreGap,
        String queryUsed,
        Instant matchedAt,
        String sourceContentHash,
        Instant nextRetryAt,
        RecommendationEligibility recommendationEligibility) {
}
