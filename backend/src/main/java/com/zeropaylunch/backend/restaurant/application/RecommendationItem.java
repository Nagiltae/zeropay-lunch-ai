package com.zeropaylunch.backend.restaurant.application;

public record RecommendationItem(
        Long restaurantId,
        String name,
        String category,
        String representativeMenu,
        int averagePrice,
        String address,
        boolean zeroPayAvailable,
        boolean sampleData,
        String reason
) {
}
