package com.zeropaylunch.backend.preference.api;

import com.zeropaylunch.backend.preference.application.UserPreferenceService.PreferenceSnapshot;
import com.zeropaylunch.backend.preference.domain.SpiceLevel;
import com.zeropaylunch.backend.restaurant.domain.RestaurantCategory;
import java.util.Set;

public record UserPreferenceResponse(
        Integer defaultBudget,
        SpiceLevel spiceLevel,
        Set<RestaurantCategory> preferredCategories,
        Set<RestaurantCategory> dislikedCategories,
        Set<String> allergies,
        boolean zeroPayRequired
) {
    public static UserPreferenceResponse from(PreferenceSnapshot snapshot) {
        return new UserPreferenceResponse(
                snapshot.defaultBudget(),
                snapshot.spiceLevel(),
                snapshot.preferredCategories(),
                snapshot.dislikedCategories(),
                snapshot.allergies(),
                true
        );
    }
}
