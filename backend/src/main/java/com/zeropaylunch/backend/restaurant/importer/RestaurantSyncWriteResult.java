package com.zeropaylunch.backend.restaurant.importer;

import java.util.List;

record RestaurantSyncWriteResult(
        int insertedCount,
        int updatedCount,
        int unchangedCount,
        int deactivatedCount,
        int reactivatedCount,
        int skippedCount,
        List<Long> changedRestaurantIds) {}
