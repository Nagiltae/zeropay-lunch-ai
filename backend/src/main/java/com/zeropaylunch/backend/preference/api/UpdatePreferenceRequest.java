package com.zeropaylunch.backend.preference.api;

import com.zeropaylunch.backend.preference.domain.SpiceLevel;
import com.zeropaylunch.backend.restaurant.domain.RestaurantCategory;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.Set;

public record UpdatePreferenceRequest(
        @Min(1000) @Max(100000) Integer defaultBudget,
        @NotNull SpiceLevel spiceLevel,
        @NotNull @Size(max = 10) Set<RestaurantCategory> preferredCategories,
        @NotNull @Size(max = 10) Set<RestaurantCategory> dislikedCategories,
        @NotNull @Size(max = 10) Set<@Size(max = 80) String> allergies
) {
}
