package com.zeropaylunch.backend.restaurant.enrichment.naver;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.naver-local.matching")
record NaverMatchingProperties(
        double nameExactScore,
        double nameContainsScore,
        double nameHighSimilarityScore,
        double nameModerateSimilarityScore,
        double highNameSimilarity,
        double moderateNameSimilarity,
        double addressExactScore,
        double addressHighSimilarityScore,
        double addressModerateSimilarityScore,
        double sameDongScore,
        double highAddressSimilarity,
        double moderateAddressSimilarity,
        double distance50mScore,
        double distance100mScore,
        double distance300mScore,
        double categoryScore,
        double maximumDistanceMeters,
        double matchedThreshold,
        double viableThreshold,
        double ambiguityMargin,
        double minimumNameScore,
        double strongNameScore,
        double strongAddressScore,
        double strongEvidenceDistanceMeters) {
}
