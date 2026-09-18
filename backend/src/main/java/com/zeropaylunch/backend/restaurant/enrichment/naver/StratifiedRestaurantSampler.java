package com.zeropaylunch.backend.restaurant.enrichment.naver;

import com.zeropaylunch.backend.restaurant.domain.Restaurant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Component;

@Component
class StratifiedRestaurantSampler {

    List<Restaurant> select(List<Restaurant> restaurants, int limit) {
        Map<String, List<Restaurant>> byLegalDong = new LinkedHashMap<>();
        restaurants.stream()
                .sorted(Comparator.comparing(
                                Restaurant::getLegalDongCode,
                                Comparator.nullsLast(Comparator.naturalOrder()))
                        .thenComparing(Restaurant::getId))
                .forEach(restaurant -> byLegalDong
                        .computeIfAbsent(groupKey(restaurant), ignored -> new ArrayList<>())
                        .add(restaurant));

        List<Restaurant> selected = new ArrayList<>(Math.min(limit, restaurants.size()));
        int offset = 0;
        while (selected.size() < limit) {
            boolean added = false;
            for (List<Restaurant> group : byLegalDong.values()) {
                if (offset < group.size()) {
                    selected.add(group.get(offset));
                    added = true;
                    if (selected.size() == limit) {
                        break;
                    }
                }
            }
            if (!added) {
                break;
            }
            offset++;
        }
        return List.copyOf(selected);
    }

    private String groupKey(Restaurant restaurant) {
        return restaurant.getLegalDongCode() == null
                ? "~UNKNOWN" : restaurant.getLegalDongCode();
    }
}
