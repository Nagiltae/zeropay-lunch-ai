package com.zeropaylunch.backend.restaurant.enrichment.naver;

import com.zeropaylunch.backend.restaurant.domain.ExternalPlaceMatchStatus;
import com.zeropaylunch.backend.restaurant.domain.RecommendationEligibility;
import java.math.BigDecimal;

record NaverEnrichmentDetail(
        Long restaurantId,
        String komscoName,
        String komscoAddress,
        BigDecimal komscoLatitude,
        BigDecimal komscoLongitude,
        String legalDongName,
        String firstQuery,
        String secondQuery,
        String naverName,
        String naverCategory,
        String naverAddress,
        String naverRoadAddress,
        BigDecimal naverLatitude,
        BigDecimal naverLongitude,
        double nameScore,
        double addressScore,
        double distanceScore,
        double categoryScore,
        Double distanceMeters,
        double totalScore,
        Double runnerUpScore,
        Double scoreGap,
        ExternalPlaceMatchStatus matchStatus,
        RecommendationEligibility recommendationEligibility,
        String errorMessage) {
}
