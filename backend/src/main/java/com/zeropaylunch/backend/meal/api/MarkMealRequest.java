package com.zeropaylunch.backend.meal.api;

import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import java.util.UUID;

public record MarkMealRequest(
        @NotNull @Positive Long restaurantId,
        @NotNull UUID sourceMessageId
) {
}
