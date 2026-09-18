package com.zeropaylunch.backend.restaurant.enrichment.naver;

import java.util.List;

record NaverEnrichmentResult(
        int processedCount,
        int matchedCount,
        int ambiguousCount,
        int unmatchedCount,
        int apiFailureCount,
        int eligibleCount,
        int ineligibleCount,
        int unknownCount,
        int insertedCount,
        int updatedCount,
        int skippedCount,
        List<NaverEnrichmentDetail> details) {
}
