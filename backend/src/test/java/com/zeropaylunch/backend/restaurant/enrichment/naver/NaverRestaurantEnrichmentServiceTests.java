package com.zeropaylunch.backend.restaurant.enrichment.naver;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.zeropaylunch.backend.restaurant.domain.Restaurant;
import com.zeropaylunch.backend.restaurant.domain.RestaurantSourceProvider;
import com.zeropaylunch.backend.restaurant.domain.RestaurantSourceSnapshot;
import com.zeropaylunch.backend.restaurant.infrastructure.RestaurantJpaRepository;
import com.zeropaylunch.backend.restaurant.infrastructure.RestaurantExternalPlaceJpaRepository;
import java.math.BigDecimal;
import java.net.URI;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.List;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

class NaverRestaurantEnrichmentServiceTests {

    private final RestaurantJpaRepository restaurantRepository =
            mock(RestaurantJpaRepository.class);
    private final NaverLocalSearchClient client = mock(NaverLocalSearchClient.class);
    private final RestaurantExternalPlaceJpaRepository externalPlaceRepository =
            mock(RestaurantExternalPlaceJpaRepository.class);
    private final RestaurantExternalPlaceWriter writer = mock(RestaurantExternalPlaceWriter.class);
    private final NaverRestaurantCategoryPolicy categoryPolicy =
            new NaverRestaurantCategoryPolicy();
    private final NaverRestaurantMatcher matcher = new NaverRestaurantMatcher(
            new NaverTextNormalizer(), new GeoDistanceCalculator(),
            new NaverCoordinateParser(),
            new NaverCandidateHardGate(matchingPolicy(), categoryPolicy),
            matchingPolicy());
    private final RecommendationEligibilityPolicy eligibilityPolicy =
            new RecommendationEligibilityPolicy(categoryPolicy);
    private final NaverTextNormalizer normalizer = new NaverTextNormalizer();
    private final NaverCoordinateParser coordinateParser = new NaverCoordinateParser();
    private final RestaurantMatchSourceHasher sourceHasher = new RestaurantMatchSourceHasher();
    private final StratifiedRestaurantSampler sampler = mock(StratifiedRestaurantSampler.class);
    private final NaverIncrementalSelector incrementalSelector =
            new NaverIncrementalSelector(sourceHasher);
    private final Clock clock = Clock.fixed(
            Instant.parse("2026-09-18T00:00:00Z"), ZoneOffset.UTC);

    @Test
    void perRestaurantApiFailurePreservesRestaurantAndRecordsRetryState() {
        Restaurant restaurant = restaurant();
        when(restaurantRepository
                .findBySourceProviderAndActiveTrueOrderByLegalDongCodeAscIdAsc(any()))
                .thenReturn(List.of(restaurant));
        when(sampler.select(any(), anyInt())).thenReturn(List.of(restaurant));
        when(client.search(any())).thenThrow(new NaverLocalApiException("temporary failure"));

        NaverEnrichmentResult result = service().enrichValidationSample(20);

        assertThat(result.processedCount()).isEqualTo(1);
        assertThat(result.apiFailureCount()).isEqualTo(1);
        assertThat(result.unknownCount()).isEqualTo(1);
        assertThat(result.skippedCount()).isEqualTo(1);
        assertThat(restaurant.getName()).isEqualTo("토브");
        assertThat(restaurant.getAddress()).isEqualTo("서울특별시 강남구 학동로 1");
        verify(writer, never()).upsert(any(), any());
        verify(writer).recordFailure(any(), any(), any(), any());
    }

    @Test
    void usesGangnamFallbackOnceWhenFirstQueryHasNoTrustedCandidate() {
        Restaurant restaurant = restaurant();
        when(restaurantRepository
                .findBySourceProviderAndActiveTrueOrderByLegalDongCodeAscIdAsc(any()))
                .thenReturn(List.of(restaurant));
        when(sampler.select(any(), anyInt())).thenReturn(List.of(restaurant));
        NaverLocalResponse empty = new NaverLocalResponse(null, 0, 1, 0, List.of());
        NaverLocalResponse matched = new NaverLocalResponse(null, 1, 1, 1, List.of(
                new NaverLocalItem("토브", "", "음식점>한식", "", "",
                        "서울 강남구 논현동 1", "서울 강남구 학동로 1",
                        "127.0300000", "37.5000000")));
        when(client.search(any())).thenReturn(empty, matched);
        when(writer.upsert(any(), any())).thenReturn(NaverEnrichmentWriteOutcome.INSERTED);

        NaverEnrichmentResult result = service().enrichValidationSample(20);

        ArgumentCaptor<String> queryCaptor = ArgumentCaptor.forClass(String.class);
        verify(client, org.mockito.Mockito.times(2)).search(queryCaptor.capture());
        assertThat(queryCaptor.getAllValues())
                .containsExactly("토브 논현동", "토브 강남구");
        assertThat(result.matchedCount()).isEqualTo(1);
        assertThat(result.eligibleCount()).isEqualTo(1);
        assertThat(result.ineligibleCount()).isZero();
        assertThat(result.unknownCount()).isZero();
        assertThat(result.insertedCount()).isEqualTo(1);
    }

    @Test
    void authenticationFailureStopsTheWholeRun() {
        when(restaurantRepository
                .findBySourceProviderAndActiveTrueOrderByLegalDongCodeAscIdAsc(any()))
                .thenReturn(List.of(restaurant()));
        when(sampler.select(any(), anyInt())).thenReturn(List.of(restaurant()));
        when(client.search(any())).thenThrow(
                new NaverLocalAuthenticationException("invalid credentials", null));

        assertThatThrownBy(() -> service().enrichValidationSample(20))
                .isInstanceOf(NaverLocalAuthenticationException.class)
                .hasMessageContaining("invalid credentials");
        verify(writer, never()).upsert(any(), any());
    }

    private NaverRestaurantEnrichmentService service() {
        return new NaverRestaurantEnrichmentService(
                restaurantRepository, externalPlaceRepository, client, matcher, normalizer,
                coordinateParser, writer, eligibilityPolicy, sourceHasher, sampler,
                incrementalSelector,
                properties(), clock);
    }

    private Restaurant restaurant() {
        return Restaurant.fromExternalSource(new RestaurantSourceSnapshot(
                RestaurantSourceProvider.KOMSCO, "merchant-1", "토브",
                "서울특별시 강남구 학동로 1", null, "06000",
                new BigDecimal("37.5000000"), new BigDecimal("127.0300000"),
                "11680108", "논현동", "561", "음식점 및 주점업", "I0000002",
                "01", "계속사업자", LocalDate.of(2026, 9, 1)), clock.instant());
    }

    private NaverLocalProperties properties() {
        return new NaverLocalProperties(
                URI.create("https://example.test/naver-local"), "id", "secret",
                Duration.ofSeconds(1), Duration.ofSeconds(1), Duration.ZERO,
                Duration.ofMillis(1), 2, 5, false, 20, 2, 100,
                Duration.ofDays(30), Duration.ofDays(7), Duration.ofDays(7),
                Duration.ofHours(1), Path.of("build/reports/naver-test"));
    }

    private NaverMatchingProperties matchingPolicy() {
        return new NaverMatchingProperties(
                40, 35, 32, 22, 0.85, 0.70,
                30, 25, 15, 8, 0.70, 0.45,
                20, 14, 6, 10, 300, 70, 45, 8,
                22, 32, 25, 50);
    }
}
