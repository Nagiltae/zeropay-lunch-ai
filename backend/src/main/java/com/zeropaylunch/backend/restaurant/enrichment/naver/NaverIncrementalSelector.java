package com.zeropaylunch.backend.restaurant.enrichment.naver;

import com.zeropaylunch.backend.restaurant.domain.Restaurant;
import com.zeropaylunch.backend.restaurant.domain.RestaurantExternalPlace;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Component;

@Component
class NaverIncrementalSelector {

    private final RestaurantMatchSourceHasher sourceHasher;

    NaverIncrementalSelector(RestaurantMatchSourceHasher sourceHasher) {
        this.sourceHasher = sourceHasher;
    }

    List<Restaurant> select(
            List<Restaurant> restaurants,
            Map<Long, RestaurantExternalPlace> enrichmentByRestaurantId,
            Instant now,
            int limit) {
        return restaurants.stream()
                .filter(restaurant -> requiresLookup(
                        restaurant, enrichmentByRestaurantId.get(restaurant.getId()), now))
                .limit(limit)
                .toList();
    }

    boolean requiresLookup(
            Restaurant restaurant, RestaurantExternalPlace enrichment, Instant now) {
        if (enrichment == null) {
            return true;
        }
        if (!sourceHasher.hash(restaurant).equals(enrichment.getSourceContentHash())) {
            return true;
        }
        return isDue(enrichment.getNextRetryAt(), now);
    }

    private boolean isDue(Instant retryAt, Instant now) {
        return retryAt == null || !retryAt.isAfter(now);
    }
}
