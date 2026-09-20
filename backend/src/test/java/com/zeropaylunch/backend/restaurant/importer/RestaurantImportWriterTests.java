package com.zeropaylunch.backend.restaurant.importer;

import static org.assertj.core.api.Assertions.assertThat;

import com.zeropaylunch.backend.restaurant.domain.Restaurant;
import com.zeropaylunch.backend.restaurant.domain.RestaurantSourceProvider;
import com.zeropaylunch.backend.restaurant.domain.RestaurantSourceSnapshot;
import com.zeropaylunch.backend.restaurant.domain.RecommendationEligibility;
import com.zeropaylunch.backend.restaurant.domain.NaverVerificationReason;
import com.zeropaylunch.backend.restaurant.domain.NaverVerificationStatus;
import com.zeropaylunch.backend.restaurant.domain.RestaurantNaverVerification;
import com.zeropaylunch.backend.restaurant.infrastructure.RestaurantJpaRepository;
import com.zeropaylunch.backend.restaurant.infrastructure.RestaurantNaverVerificationJpaRepository;
import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.annotation.Transactional;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;

@SpringBootTest
@Transactional
class RestaurantImportWriterTests {

    @Autowired
    private RestaurantImportWriter writer;

    @Autowired
    private RestaurantJpaRepository repository;

    @Autowired
    private RestaurantNaverVerificationJpaRepository verificationRepository;

    @PersistenceContext
    private EntityManager entityManager;

    @Test
    void insertsOnceAndDoesNotDuplicateTheSameSourceRecord() {
        RestaurantSourceSnapshot snapshot = snapshot("merchant-insert", "2026-08-01", "처음 이름");

        assertThat(writer.upsert(snapshot)).isEqualTo(RestaurantImportOutcome.INSERTED);
        assertThat(writer.upsert(snapshot)).isEqualTo(RestaurantImportOutcome.SKIPPED);
        assertThat(repository.findBySourceProviderAndExternalMerchantId(
                RestaurantSourceProvider.KOMSCO, "merchant-insert")).isPresent();
        assertThat(repository.count()).isEqualTo(1);
    }

    @Test
    void updatesNewerRecordAndKeepsOlderRecordOut() {
        writer.upsert(snapshot("merchant-update", "2026-05-01", "이전 이름"));

        assertThat(writer.upsert(snapshot("merchant-update", "2026-08-01", "최신 이름")))
                .isEqualTo(RestaurantImportOutcome.UPDATED);
        assertThat(writer.upsert(snapshot("merchant-update", "2026-01-01", "오래된 이름")))
                .isEqualTo(RestaurantImportOutcome.SKIPPED);

        Restaurant saved = repository.findBySourceProviderAndExternalMerchantId(
                RestaurantSourceProvider.KOMSCO, "merchant-update").orElseThrow();
        assertThat(saved.getName()).isEqualTo("최신 이름");
        assertThat(saved.getSourceReferenceDate()).isEqualTo(LocalDate.of(2026, 8, 1));
        assertThat(saved.isRecommendationReady()).isFalse();
        assertThat(saved.isZeroPayAvailable()).isTrue();
    }

    @Test
    void updatesChangedDataAtTheSameReferenceDate() {
        writer.upsert(snapshot("merchant-same-date", "2026-08-01", "이전 이름"));

        assertThat(writer.upsert(snapshot("merchant-same-date", "2026-08-01", "변경 이름")))
                .isEqualTo(RestaurantImportOutcome.UPDATED);
    }

    @Test
    void replacesAllExistingKomscoRowsInOneBatch() {
        writer.upsert(snapshot("merchant-old", "2026-08-01", "기존 이름"));

        int inserted = writer.replaceAllKomscoRestaurants(List.of(
                snapshot("merchant-new-1", "2026-09-01", "신규 이름 1"),
                snapshot("merchant-new-2", "2026-09-01", "신규 이름 2")));

        assertThat(inserted).isEqualTo(2);
        assertThat(repository.findBySourceProviderAndExternalMerchantId(
                RestaurantSourceProvider.KOMSCO, "merchant-old")).isEmpty();
        assertThat(repository.findBySourceProviderAndExternalMerchantId(
                RestaurantSourceProvider.KOMSCO, "merchant-new-1")).isPresent();
        assertThat(repository.count()).isEqualTo(2);
    }

    @Test
    void dailySyncUpdatesTimestampsDeactivatesAndReactivatesExistingRestaurant() {
        Instant firstSync = Instant.parse("2026-09-18T00:00:00Z");
        Instant inactiveSync = Instant.parse("2026-09-19T00:00:00Z");
        Instant reactivatedSync = Instant.parse("2026-09-20T00:00:00Z");
        new RestaurantImportWriter(repository, Clock.fixed(firstSync, ZoneOffset.UTC))
                .upsert(snapshot("merchant-lifecycle", "2026-09-18", "계속사업자", "기존 이름"));

        RestaurantSyncWriteResult inactiveResult = new RestaurantImportWriter(
                repository, Clock.fixed(inactiveSync, ZoneOffset.UTC))
                .synchronizeKomscoRestaurants(List.of(new RestaurantSyncCandidate(
                        snapshot("merchant-lifecycle", "2026-09-19", "폐업자", "기존 이름"),
                        false)));

        Restaurant inactive = find("merchant-lifecycle");
        assertThat(inactiveResult.updatedCount()).isEqualTo(1);
        assertThat(inactiveResult.deactivatedCount()).isEqualTo(1);
        assertThat(inactive.isActive()).isFalse();
        assertThat(inactive.getBusinessStatusName()).isEqualTo("폐업자");
        assertThat(inactive.getLastSyncedAt()).isEqualTo(inactiveSync);
        assertThat(inactive.getUpdatedAt()).isEqualTo(inactiveSync);

        RestaurantSyncWriteResult activeResult = new RestaurantImportWriter(
                repository, Clock.fixed(reactivatedSync, ZoneOffset.UTC))
                .synchronizeKomscoRestaurants(List.of(new RestaurantSyncCandidate(
                        snapshot("merchant-lifecycle", "2026-09-20", "계속사업자", "복구 이름"),
                        true)));

        Restaurant reactivated = find("merchant-lifecycle");
        assertThat(activeResult.reactivatedCount()).isEqualTo(1);
        assertThat(reactivated.isActive()).isTrue();
        assertThat(reactivated.getName()).isEqualTo("복구 이름");
        assertThat(reactivated.getUpdatedAt()).isEqualTo(reactivatedSync);
    }

    @Test
    void dailySyncTouchesUnchangedRecordButDoesNotApplyOlderSourceRecord() {
        Instant firstSync = Instant.parse("2026-09-18T00:00:00Z");
        Instant secondSync = Instant.parse("2026-09-19T00:00:00Z");
        Instant thirdSync = Instant.parse("2026-09-20T00:00:00Z");
        RestaurantSourceSnapshot current =
                snapshot("merchant-touch", "2026-09-18", "계속사업자", "현재 이름");
        new RestaurantImportWriter(repository, Clock.fixed(firstSync, ZoneOffset.UTC)).upsert(current);

        RestaurantSyncWriteResult touchResult = new RestaurantImportWriter(
                repository, Clock.fixed(secondSync, ZoneOffset.UTC))
                .synchronizeKomscoRestaurants(List.of(new RestaurantSyncCandidate(current, true)));

        assertThat(touchResult.updatedCount()).isZero();
        assertThat(touchResult.unchangedCount()).isEqualTo(1);
        assertThat(touchResult.changedRestaurantIds()).isEmpty();
        assertThat(find("merchant-touch").getUpdatedAt()).isEqualTo(secondSync);

        RestaurantSyncWriteResult oldResult = new RestaurantImportWriter(
                repository, Clock.fixed(thirdSync, ZoneOffset.UTC))
                .synchronizeKomscoRestaurants(List.of(new RestaurantSyncCandidate(
                        snapshot("merchant-touch", "2026-01-01", "폐업자", "오래된 이름"),
                        false)));

        Restaurant retained = find("merchant-touch");
        assertThat(oldResult.skippedCount()).isEqualTo(1);
        assertThat(retained.isActive()).isTrue();
        assertThat(retained.getName()).isEqualTo("현재 이름");
        assertThat(retained.getUpdatedAt()).isEqualTo(secondSync);
    }

    @Test
    void completedFullFetchDeactivatesMissingNonhyeonMerchantOnly() {
        writer.upsert(snapshot("merchant-stale", "2026-09-18", "계속사업자", "사라진 매장"));

        RestaurantSyncWriteResult result = writer.synchronizeKomscoRestaurants(List.of(), Set.of());

        assertThat(result.deactivatedCount()).isEqualTo(1);
        assertThat(find("merchant-stale").isActive()).isFalse();
    }

    @Test
    void matchingSourceChangeResetsEligibilityButStatusOnlyChangeDoesNot() {
        Instant firstSync = Instant.parse("2026-09-18T00:00:00Z");
        Restaurant restaurant = Restaurant.fromExternalSource(
                snapshot("merchant-eligibility", "2026-09-18", "원래 이름"), firstSync);
        restaurant.updateRecommendationEligibility(
                RecommendationEligibility.ELIGIBLE, firstSync);

        restaurant.synchronizeExternalSource(
                snapshot("merchant-eligibility", "2026-09-19", "원래 이름"),
                true,
                Instant.parse("2026-09-19T00:00:00Z"));
        assertThat(restaurant.getRecommendationEligibility())
                .isEqualTo(RecommendationEligibility.ELIGIBLE);

        restaurant.synchronizeExternalSource(
                snapshot("merchant-eligibility", "2026-09-20", "변경 이름"),
                true,
                Instant.parse("2026-09-20T00:00:00Z"));
        assertThat(restaurant.getRecommendationEligibility())
                .isEqualTo(RecommendationEligibility.UNKNOWN);
    }

    @Test
    void matchingSourceChangeMarksNaverVerificationForRecheck() {
        Instant syncedAt = Instant.parse("2026-09-18T00:00:00Z");
        writer.upsert(snapshot("merchant-verification", "2026-09-18", "원래 이름"));
        Restaurant restaurant = find("merchant-verification");
        verificationRepository.save(RestaurantNaverVerification.of(
                restaurant, "NAVER", NaverVerificationStatus.VERIFIED,
                NaverVerificationReason.VERIFIED, "123", "qwen3:8b", syncedAt, syncedAt));

        writer.synchronizeKomscoRestaurants(List.of(new RestaurantSyncCandidate(
                snapshot("merchant-verification", "2026-09-19", "변경 이름"), true)));

        entityManager.flush();
        entityManager.clear();
        RestaurantNaverVerification verification = verificationRepository
                .findByRestaurantIdAndProvider(restaurant.getId(), "NAVER").orElseThrow();
        assertThat(verification.getVerificationStatus()).isEqualTo(NaverVerificationStatus.UNRESOLVED);
        assertThat(verification.getVerificationReason()).isEqualTo(NaverVerificationReason.SOURCE_CHANGED);
    }

    private RestaurantSourceSnapshot snapshot(String id, String date, String name) {
        return snapshot(id, date, "계속사업자", name);
    }

    private RestaurantSourceSnapshot snapshot(
            String id, String date, String statusName, String name) {
        return new RestaurantSourceSnapshot(
                RestaurantSourceProvider.KOMSCO,
                id,
                name,
                "서울특별시 강남구 역삼동 1",
                "101호",
                "06200",
                new BigDecimal("37.5000000"),
                new BigDecimal("127.0300000"),
                "11680108",
                "논현동",
                "561",
                "음식점 및 주점업",
                "I0000002",
                "계속사업자".equals(statusName) ? "01" : "03",
                statusName,
                LocalDate.parse(date));
    }

    private Restaurant find(String externalMerchantId) {
        return repository.findBySourceProviderAndExternalMerchantId(
                RestaurantSourceProvider.KOMSCO, externalMerchantId).orElseThrow();
    }
}
