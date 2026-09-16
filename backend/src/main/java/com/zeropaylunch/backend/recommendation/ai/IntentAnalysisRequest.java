package com.zeropaylunch.backend.recommendation.ai;

import com.zeropaylunch.backend.preference.domain.SpiceLevel;
import com.zeropaylunch.backend.restaurant.domain.RestaurantCategory;
import java.time.Instant;
import java.util.List;
import java.util.Set;

public record IntentAnalysisRequest(
        String message,
        String locationId,
        Integer defaultBudget,
        SpiceLevel spiceLevel,
        Set<RestaurantCategory> preferredCategories,
        Set<RestaurantCategory> dislikedCategories,
        Set<String> allergies,
        List<RecentMeal> recentMeals
) {
    public record RecentMeal(
            Long restaurantId,
            RestaurantCategory category,
            Instant eatenAt
    ) {
    }
}
