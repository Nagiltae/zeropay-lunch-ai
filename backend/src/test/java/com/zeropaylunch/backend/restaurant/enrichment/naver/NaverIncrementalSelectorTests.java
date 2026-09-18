package com.zeropaylunch.backend.restaurant.enrichment.naver;

import static org.assertj.core.api.Assertions.assertThat;

import com.zeropaylunch.backend.restaurant.domain.ExternalPlaceMatchStatus;
import com.zeropaylunch.backend.restaurant.domain.ExternalPlaceProvider;
import com.zeropaylunch.backend.restaurant.domain.Restaurant;
import com.zeropaylunch.backend.restaurant.domain.RestaurantExternalPlace;
import com.zeropaylunch.backend.restaurant.domain.RestaurantExternalPlaceSnapshot;
import com.zeropaylunch.backend.restaurant.domain.RestaurantSourceProvider;
import com.zeropaylunch.backend.restaurant.domain.RestaurantSourceSnapshot;
import com.zeropaylunch.backend.restaurant.domain.RecommendationEligibility;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import org.junit.jupiter.api.Test;

class NaverIncrementalSelectorTests {

    private static final Instant NOW = Instant.parse("2026-09-19T00:00:00Z");

    private final RestaurantMatchSourceHasher hasher = new RestaurantMatchSourceHasher();
    private final NaverIncrementalSelector selector = new NaverIncrementalSelector(hasher);

    @Test
    void newRestaurantOrMissingEnrichmentRequiresLookup() {
        assertThat(selector.requiresLookup(restaurant("토브"), null, NOW)).isTrue();
    }

    @Test
    void matchedAndUnchangedRestaurantWaitsUntilRefreshTtl() {
        Restaurant restaurant = restaurant("토브");
        RestaurantExternalPlace place = enrichment(
                restaurant, ExternalPlaceMatchStatus.MATCHED,
                hasher.hash(restaurant), NOW.plusSeconds(3600));

        assertThat(selector.requiresLookup(restaurant, place, NOW)).isFalse();
        assertThat(selector.requiresLookup(restaurant, place, NOW.plusSeconds(3601))).isTrue();
    }

    @Test
    void changedMatchingContentRequiresLookupBeforeTtl() {
        Restaurant original = restaurant("토브");
        Restaurant changed = restaurant("토브 강남점");
        RestaurantExternalPlace place = enrichment(
                changed, ExternalPlaceMatchStatus.MATCHED,
                hasher.hash(original), NOW.plusSeconds(3600));

        assertThat(selector.requiresLookup(changed, place, NOW)).isTrue();
    }

    @Test
    void unmatchedRestaurantIsRetriedOnlyWhenRetryTimeArrives() {
        Restaurant restaurant = restaurant("토브");
        RestaurantExternalPlace place = enrichment(
                restaurant, ExternalPlaceMatchStatus.UNMATCHED,
                hasher.hash(restaurant), NOW.plusSeconds(60));

        assertThat(selector.requiresLookup(restaurant, place, NOW)).isFalse();
        assertThat(selector.requiresLookup(restaurant, place, NOW.plusSeconds(60))).isTrue();
    }

    private Restaurant restaurant(String name) {
        return Restaurant.fromExternalSource(new RestaurantSourceSnapshot(
                RestaurantSourceProvider.KOMSCO, "merchant-1", name,
                "서울특별시 강남구 학동로 1", null, "06000",
                new BigDecimal("37.5000000"), new BigDecimal("127.0300000"),
                "11680108", "논현동", "561", "음식점 및 주점업", "I0000002",
                "01", "계속사업자", LocalDate.of(2026, 9, 1)), NOW);
    }

    private RestaurantExternalPlace enrichment(
            Restaurant restaurant,
            ExternalPlaceMatchStatus status,
            String sourceHash,
            Instant nextRetryAt) {
        RestaurantExternalPlaceSnapshot snapshot = new RestaurantExternalPlaceSnapshot(
                ExternalPlaceProvider.NAVER, "토브", "음식점>한식", "", "",
                "서울 강남구 논현동 1", "서울 강남구 학동로 1",
                new BigDecimal("37.5000000"), new BigDecimal("127.0300000"),
                status, new BigDecimal("90.00"), new BigDecimal("40.00"),
                new BigDecimal("30.00"), new BigDecimal("20.00"),
                new BigDecimal("10.00"), BigDecimal.ZERO, null, null,
                "토브 논현동", status == ExternalPlaceMatchStatus.MATCHED ? NOW : null,
                sourceHash, nextRetryAt, RecommendationEligibility.ELIGIBLE);
        return RestaurantExternalPlace.create(restaurant, snapshot, NOW);
    }
}
