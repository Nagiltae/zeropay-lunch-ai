package com.zeropaylunch.backend.restaurant.application;

import java.util.List;

public record RecommendationItem(
        Long restaurantId,
        String name,
        String category,
        String representativeMenu,
        Integer averagePrice,
        String address,
        boolean zeroPayAvailable,
        boolean sampleData,
        String reason,
        List<MenuExample> menuExamples
) {
    public RecommendationItem {
        menuExamples = menuExamples == null ? List.of() : List.copyOf(menuExamples);
    }

    /** Compatibility constructor for legacy/sample recommendation DTOs. */
    public RecommendationItem(Long restaurantId, String name, String category, String representativeMenu,
            Integer averagePrice, String address, boolean zeroPayAvailable, boolean sampleData, String reason) {
        this(restaurantId, name, category, representativeMenu, averagePrice, address,
                zeroPayAvailable, sampleData, reason, List.of());
    }

    public record MenuExample(String name, Integer price) { }
}
