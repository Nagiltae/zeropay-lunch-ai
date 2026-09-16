package com.zeropaylunch.backend.recommendation.ai;

import com.zeropaylunch.backend.restaurant.domain.RestaurantCategory;
import java.util.List;
import java.util.Optional;

public record AnalyzedIntent(
        IntentType intent,
        Integer maximumPrice,
        Optional<RestaurantCategory> category,
        List<String> keywords,
        boolean clarificationRequired,
        String clarificationQuestion
) {
    public enum IntentType {
        RECOMMEND_RESTAURANT
    }
}
