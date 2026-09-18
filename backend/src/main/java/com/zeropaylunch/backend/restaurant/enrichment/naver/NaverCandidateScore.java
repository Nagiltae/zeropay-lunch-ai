package com.zeropaylunch.backend.restaurant.enrichment.naver;

record NaverCandidateScore(
        NaverSearchCandidate candidate,
        double nameScore,
        double addressScore,
        double distanceScore,
        double categoryScore,
        double totalScore,
        Double distanceMeters) {
}
