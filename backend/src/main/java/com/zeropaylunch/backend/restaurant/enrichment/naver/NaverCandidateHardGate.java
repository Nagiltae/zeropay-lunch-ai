package com.zeropaylunch.backend.restaurant.enrichment.naver;

import org.springframework.stereotype.Component;

@Component
class NaverCandidateHardGate {

    private final NaverMatchingProperties policy;
    private final NaverRestaurantCategoryPolicy categoryPolicy;

    NaverCandidateHardGate(
            NaverMatchingProperties policy, NaverRestaurantCategoryPolicy categoryPolicy) {
        this.policy = policy;
        this.categoryPolicy = categoryPolicy;
    }

    boolean acceptsCandidate(String category, double nameScore) {
        return nameScore >= policy.minimumNameScore()
                && !categoryPolicy.isExplicitlyNonFoodCategory(category);
    }

    boolean hasStrongEvidence(
            double nameScore, double addressScore, Double distanceMeters) {
        if (addressScore >= policy.strongAddressScore()) {
            return true;
        }
        return nameScore >= policy.strongNameScore()
                && distanceMeters != null
                && distanceMeters <= policy.strongEvidenceDistanceMeters();
    }

    boolean isFoodCategory(String category) {
        return categoryPolicy.isFoodCategory(category);
    }
}
