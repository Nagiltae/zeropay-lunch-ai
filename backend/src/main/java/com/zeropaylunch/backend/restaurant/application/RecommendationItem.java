package com.zeropaylunch.backend.restaurant.application;

public record RecommendationItem(
        Long restaurantId,
        String name,
        String category,
        String representativeMenu,
        int averagePrice,
        String address,
        String locationId,
        String locationLabel,
        boolean zeroPayAvailable,
        boolean sampleData,
        String reason
) {
}
