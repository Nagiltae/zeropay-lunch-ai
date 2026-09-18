package com.zeropaylunch.backend.restaurant.importer;

public record RestaurantImportResult(
        int fetchedCount,
        int deduplicatedCount,
        int activeRestaurantCount,
        int insertedCount,
        int updatedCount,
        int skippedCount) {}
