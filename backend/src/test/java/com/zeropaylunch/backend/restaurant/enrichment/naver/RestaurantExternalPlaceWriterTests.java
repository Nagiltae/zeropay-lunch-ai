package com.zeropaylunch.backend.restaurant.enrichment.naver;

import static org.assertj.core.api.Assertions.assertThat;

import com.zeropaylunch.backend.restaurant.domain.ExternalPlaceMatchStatus;
import com.zeropaylunch.backend.restaurant.domain.ExternalPlaceAttemptStatus;
import com.zeropaylunch.backend.restaurant.domain.ExternalPlaceProvider;
import com.zeropaylunch.backend.restaurant.domain.Restaurant;
import com.zeropaylunch.backend.restaurant.domain.RestaurantExternalPlaceSnapshot;
import com.zeropaylunch.backend.restaurant.domain.RestaurantSourceProvider;
import com.zeropaylunch.backend.restaurant.domain.RestaurantSourceSnapshot;
import com.zeropaylunch.backend.restaurant.domain.RecommendationEligibility;
import com.zeropaylunch.backend.restaurant.infrastructure.RestaurantExternalPlaceJpaRepository;
import com.zeropaylunch.backend.restaurant.infrastructure.RestaurantJpaRepository;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.annotation.Transactional;

@SpringBootTest
@Transactional
class RestaurantExternalPlaceWriterTests {

    @Autowired
    private RestaurantJpaRepository restaurantRepository;

    @Autowired
    private RestaurantExternalPlaceJpaRepository externalPlaceRepository;

    @Autowired
    private RestaurantExternalPlaceWriter writer;

    @Test
    void repeatedEnrichmentUpdatesOneProviderRowWithoutDuplicates() {
        Restaurant restaurant = restaurantRepository.save(Restaurant.fromExternalSource(
                sourceSnapshot(), Instant.parse("2026-09-18T00:00:00Z")));

        assertThat(writer.upsert(restaurant, enrichment("토브", new BigDecimal("100.00"))))
                .isEqualTo(NaverEnrichmentWriteOutcome.INSERTED);
        assertThat(writer.upsert(restaurant, enrichment("토브 강남", new BigDecimal("95.00"))))
                .isEqualTo(NaverEnrichmentWriteOutcome.UPDATED);

        assertThat(externalPlaceRepository.count()).isEqualTo(1);
        assertThat(externalPlaceRepository.findByRestaurantIdAndProvider(
                restaurant.getId(), ExternalPlaceProvider.NAVER).orElseThrow().getExternalName())
                .isEqualTo("토브 강남");
        assertThat(restaurantRepository.findById(restaurant.getId()).orElseThrow()
                .getRecommendationEligibility())
                .isEqualTo(RecommendationEligibility.ELIGIBLE);
    }

    @Test
    void apiFailureKeepsExistingMatchedDataAndOnlyRecordsAttemptState() {
        Restaurant restaurant = restaurantRepository.save(Restaurant.fromExternalSource(
                sourceSnapshot(), Instant.parse("2026-09-18T00:00:00Z")));
        writer.upsert(restaurant, enrichment("토브", new BigDecimal("100.00")));
        var before = externalPlaceRepository.findByRestaurantIdAndProvider(
                restaurant.getId(), ExternalPlaceProvider.NAVER).orElseThrow();
        Instant successfulSync = before.getLastSyncedAt();

        writer.recordFailure(
                restaurant, "new-source-hash", "토브 논현동",
                Instant.parse("2026-09-25T00:00:00Z"));
        externalPlaceRepository.flush();

        var after = externalPlaceRepository.findByRestaurantIdAndProvider(
                restaurant.getId(), ExternalPlaceProvider.NAVER).orElseThrow();
        assertThat(after.getMatchStatus()).isEqualTo(ExternalPlaceMatchStatus.MATCHED);
        assertThat(after.getExternalName()).isEqualTo("토브");
        assertThat(after.getMatchScore()).isEqualByComparingTo("100.00");
        assertThat(after.getLastSyncedAt()).isEqualTo(successfulSync);
        assertThat(after.getLastAttemptStatus())
                .isEqualTo(ExternalPlaceAttemptStatus.API_ERROR);
        assertThat(after.getSourceContentHash()).isEqualTo("new-source-hash");
        assertThat(restaurantRepository.findById(restaurant.getId()).orElseThrow()
                .getRecommendationEligibility())
                .isEqualTo(RecommendationEligibility.UNKNOWN);
    }

    private RestaurantSourceSnapshot sourceSnapshot() {
        return new RestaurantSourceSnapshot(
                RestaurantSourceProvider.KOMSCO, "merchant-naver", "토브",
                "서울특별시 강남구 학동로 1", null, "06000",
                new BigDecimal("37.5000000"), new BigDecimal("127.0300000"),
                "11680108", "논현동", "561", "음식점 및 주점업", "I0000002",
                "01", "계속사업자", LocalDate.of(2026, 9, 1));
    }

    private RestaurantExternalPlaceSnapshot enrichment(String name, BigDecimal score) {
        return new RestaurantExternalPlaceSnapshot(
                ExternalPlaceProvider.NAVER, name, "음식점>한식", "", "https://example.test",
                "서울 강남구 논현동 1", "서울 강남구 학동로 1",
                new BigDecimal("37.5000000"), new BigDecimal("127.0300000"),
                ExternalPlaceMatchStatus.MATCHED, score,
                new BigDecimal("40.00"), new BigDecimal("30.00"),
                new BigDecimal("20.00"), new BigDecimal("10.00"),
                BigDecimal.ZERO, new BigDecimal("50.00"), new BigDecimal("50.00"),
                "토브 논현동", Instant.parse("2026-09-18T00:00:00Z"),
                "source-hash", Instant.parse("2026-10-18T00:00:00Z"),
                RecommendationEligibility.ELIGIBLE);
    }
}
