package com.zeropaylunch.backend.restaurant.importer;

import java.util.List;

public record RestaurantSyncResult(
        int fetchedCount,
        int deduplicatedCount,
        int eligibleRestaurantCount,
        int insertedCount,
        int updatedCount,
        int unchangedCount,
        int deactivatedCount,
        int reactivatedCount,
        int skippedCount,
        List<Long> changedRestaurantIds) {}
