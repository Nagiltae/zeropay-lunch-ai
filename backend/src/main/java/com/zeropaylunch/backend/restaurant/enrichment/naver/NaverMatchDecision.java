package com.zeropaylunch.backend.restaurant.enrichment.naver;

import com.zeropaylunch.backend.restaurant.domain.ExternalPlaceMatchStatus;

record NaverMatchDecision(
        ExternalPlaceMatchStatus status,
        NaverCandidateScore selected,
        Double runnerUpScore,
        Double scoreGap,
        String queryUsed) {

    double score() {
        return selected == null ? 0.0 : selected.totalScore();
    }

    Double distanceMeters() {
        return selected == null ? null : selected.distanceMeters();
    }
}
