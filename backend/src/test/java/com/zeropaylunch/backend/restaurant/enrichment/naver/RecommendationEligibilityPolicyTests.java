package com.zeropaylunch.backend.restaurant.enrichment.naver;

import static org.assertj.core.api.Assertions.assertThat;

import com.zeropaylunch.backend.restaurant.domain.ExternalPlaceMatchStatus;
import com.zeropaylunch.backend.restaurant.domain.RecommendationEligibility;
import org.junit.jupiter.api.Test;

class RecommendationEligibilityPolicyTests {

    private final NaverRestaurantCategoryPolicy categoryPolicy =
            new NaverRestaurantCategoryPolicy();
    private final RecommendationEligibilityPolicy eligibilityPolicy =
            new RecommendationEligibilityPolicy(categoryPolicy);

    @Test
    void matchedLunchRestaurantCategoriesAreEligible() {
        assertThat(eligibility("음식점>한식"))
                .isEqualTo(RecommendationEligibility.ELIGIBLE);
        assertThat(eligibility("음식점>일식"))
                .isEqualTo(RecommendationEligibility.ELIGIBLE);
        assertThat(eligibility("분식>종합분식"))
                .isEqualTo(RecommendationEligibility.ELIGIBLE);
        assertThat(eligibility("카페,디저트>베이커리"))
                .isEqualTo(RecommendationEligibility.ELIGIBLE);
        assertThat(eligibility("술집>이자카야"))
                .isEqualTo(RecommendationEligibility.ELIGIBLE);
    }

    @Test
    void matchedClearlyNonFoodExamplesAreIneligible() {
        assertThat(eligibility("건강,의료>약국"))
                .isEqualTo(RecommendationEligibility.INELIGIBLE);
        assertThat(eligibility("사회,복지"))
                .isEqualTo(RecommendationEligibility.INELIGIBLE);
        assertThat(eligibility("컴퓨터프로그래밍,정보서비스업>소프트웨어개발"))
                .isEqualTo(RecommendationEligibility.INELIGIBLE);
        assertThat(eligibility("쇼핑,유통>반찬가게"))
                .isEqualTo(RecommendationEligibility.INELIGIBLE);
    }

    @Test
    void uncertainMatchStatesAndUnknownCategoriesRemainUnknown() {
        assertThat(eligibilityPolicy.determine(
                ExternalPlaceMatchStatus.AMBIGUOUS, "음식점>한식"))
                .isEqualTo(RecommendationEligibility.UNKNOWN);
        assertThat(eligibilityPolicy.determine(
                ExternalPlaceMatchStatus.UNMATCHED, "건강,의료>약국"))
                .isEqualTo(RecommendationEligibility.UNKNOWN);
        assertThat(eligibilityPolicy.determine(
                ExternalPlaceMatchStatus.API_ERROR, "음식점>한식"))
                .isEqualTo(RecommendationEligibility.UNKNOWN);
        assertThat(eligibilityPolicy.determine(
                ExternalPlaceMatchStatus.MATCHED, null))
                .isEqualTo(RecommendationEligibility.UNKNOWN);
        assertThat(eligibilityPolicy.determine(
                ExternalPlaceMatchStatus.MATCHED, "기타>분류미정"))
                .isEqualTo(RecommendationEligibility.UNKNOWN);
    }

    @Test
    void matchingHardGateUsesTheSameCategoryPolicy() {
        NaverCandidateHardGate hardGate = new NaverCandidateHardGate(
                matchingPolicy(), categoryPolicy);

        assertThat(hardGate.acceptsCandidate("음식점>한식", 40)).isTrue();
        assertThat(hardGate.acceptsCandidate("건강,의료>약국", 40)).isFalse();
        assertThat(hardGate.acceptsCandidate("기타>분류미정", 40)).isTrue();
    }

    private RecommendationEligibility eligibility(String category) {
        return eligibilityPolicy.determine(ExternalPlaceMatchStatus.MATCHED, category);
    }

    private NaverMatchingProperties matchingPolicy() {
        return new NaverMatchingProperties(
                40, 35, 32, 22, 0.85, 0.70,
                30, 25, 15, 8, 0.70, 0.45,
                20, 14, 6, 10, 300, 70, 45, 8,
                22, 32, 25, 50);
    }
}
