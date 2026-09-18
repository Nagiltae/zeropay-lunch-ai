package com.zeropaylunch.backend.restaurant.enrichment.naver;

import com.zeropaylunch.backend.restaurant.domain.ExternalPlaceMatchStatus;
import com.zeropaylunch.backend.restaurant.domain.RecommendationEligibility;
import org.springframework.stereotype.Component;

@Component
class RecommendationEligibilityPolicy {

    private final NaverRestaurantCategoryPolicy categoryPolicy;

    RecommendationEligibilityPolicy(NaverRestaurantCategoryPolicy categoryPolicy) {
        this.categoryPolicy = categoryPolicy;
    }

    RecommendationEligibility determine(
            ExternalPlaceMatchStatus matchStatus, String naverCategory) {
        if (matchStatus != ExternalPlaceMatchStatus.MATCHED) {
            return RecommendationEligibility.UNKNOWN;
        }
        return switch (categoryPolicy.classify(naverCategory)) {
            case FOOD -> RecommendationEligibility.ELIGIBLE;
            case NON_FOOD -> RecommendationEligibility.INELIGIBLE;
            case UNKNOWN -> RecommendationEligibility.UNKNOWN;
        };
    }
}
