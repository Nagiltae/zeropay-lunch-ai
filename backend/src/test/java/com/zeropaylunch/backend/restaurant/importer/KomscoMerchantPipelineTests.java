package com.zeropaylunch.backend.restaurant.importer;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import java.net.URI;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

class KomscoMerchantPipelineTests {

    private final KomscoMerchantDeduplicator deduplicator = new KomscoMerchantDeduplicator();
    private final KomscoMerchantFilter filter = new KomscoMerchantFilter();

    @Test
    void parsesKomscoJsonAndNullableFields() throws Exception {
        String json = """
                {
                  "currentCount": 1,
                  "data": [{
                    "alt_text": "merchant-1",
                    "bzmn_stts_nm": "계속사업자",
                    "crtr_ymd": "20260901",
                    "frcs_nm": "강남 식당",
                    "frcs_addr": "서울특별시 강남구 역삼동",
                    "frcs_dtl_addr": null,
                    "ksic_cd": "561",
                    "lat": null,
                    "lot": "127.03"
                  }],
                  "matchCount": 1,
                  "page": 1,
                  "perPage": 100,
                  "totalCount": 1
                }
                """;

        KomscoMerchantResponse response =
                new ObjectMapper().readValue(json, KomscoMerchantResponse.class);

        assertThat(response.records()).hasSize(1);
        assertThat(response.records().getFirst().altText()).isEqualTo("merchant-1");
        assertThat(response.records().getFirst().detailAddress()).isNull();
        assertThat(response.records().getFirst().lat()).isNull();
    }

    @Test
    void treatsNullDataAsAnEmptyPage() {
        KomscoMerchantResponse response = new KomscoMerchantResponse(0, null, 0, 1, 100, 0);

        assertThat(response.records()).isEmpty();
    }

    @Test
    void keepsOnlyLatestRecordForEachMerchantAndSkipsMissingRequiredFields() {
        KomscoDeduplicationResult result = deduplicator.selectLatest(List.of(
                merchant("A", "20260101", "계속사업자", "561", "11680108", "11680"),
                merchant("A", "20260801", "휴업자", "561", "11680108", "11680"),
                merchant("B", null, "계속사업자", "561", "11680108", "11680"),
                merchant(null, "20260801", "계속사업자", "561", "11680108", "11680")));

        assertThat(result.records()).hasSize(1);
        assertThat(result.records().getFirst().source().businessStatusName()).isEqualTo("휴업자");
        assertThat(result.records().getFirst().referenceDate()).hasToString("2026-08-01");
        assertThat(result.invalidCount()).isEqualTo(2);
    }

    @Test
    void latestActiveRecordPassesButLatestClosedRecordDoesNot() {
        LatestKomscoMerchant latestActive = deduplicator.selectLatest(List.of(
                merchant("A", "20260101", "폐업자", "561", "11680108", "11680"),
                merchant("A", "20260801", "계속사업자", "561", "11680108", "11680")))
                .records().getFirst();
        LatestKomscoMerchant latestClosed = deduplicator.selectLatest(List.of(
                merchant("B", "20260101", "계속사업자", "561", "11680108", "11680"),
                merchant("B", "20260801", "폐업자", "561", "11680108", "11680")))
                .records().getFirst();

        assertThat(filter.isActiveGangnamRestaurant(latestActive)).isTrue();
        assertThat(filter.isActiveGangnamRestaurant(latestClosed)).isFalse();
    }

    @Test
    void acceptsOnlyExactActiveStatusAndRestaurantIndustry() {
        assertThat(filter.isActiveGangnamRestaurant(latest(
                merchant("A", "20260801", "계속사업자", "561", "11680108", "11680"))))
                .isTrue();
        assertThat(filter.isActiveGangnamRestaurant(latest(
                merchant("B", "20260801", "계속 사업자", "561", "11680108", "11680"))))
                .isFalse();
        KomscoMerchantRecord wrongProvider = merchant(
                "D", "20260801", "계속사업자", "561", "11680108", "11680");
        wrongProvider = copyWithProvider(wrongProvider, "OTHER");
        assertThat(filter.isActiveGangnamRestaurant(latest(wrongProvider))).isTrue();
        assertThat(filter.isActiveGangnamRestaurant(latest(
                merchant("C", "20260801", "계속사업자", "562", "11680108", "11680"))))
                .isFalse();
    }

    @Test
    void excludesRowsWithoutDefensiveGangnamEvidence() {
        assertThat(filter.isActiveGangnamRestaurant(latest(
                merchant("A", "20260801", "계속사업자", "561", "11680108", "11110"))))
                .isTrue();
        KomscoMerchantRecord outside = merchant(
                "B", "20260801", "계속사업자", "561", "11680108", "11110");
        outside = copyWithAddress(outside, "서울특별시 종로구 세종대로");
        assertThat(filter.isActiveGangnamRestaurant(latest(outside))).isFalse();
        assertThat(filter.isActiveGangnamRestaurant(latest(
                merchant("C", "20260801", "계속사업자", "561", "11110101", "11680"))))
                .isFalse();
    }

    @Test
    void paginatesEveryGangnamLegalDongUntilTheLastPage() {
        List<String> calls = new ArrayList<>();
        KomscoPageClient pageClient = (code, page, size) -> {
            calls.add(code + ":" + page);
            if (code.equals("11680108") && page == 1) {
                return new KomscoMerchantResponse(2, List.of(
                        merchant("A", "20260801", "계속사업자", "561", code, "11680"),
                        merchant("B", "20260801", "계속사업자", "561", code, "11680")),
                        3, 1, size, 3);
            }
            if (code.equals("11680108") && page == 2) {
                return new KomscoMerchantResponse(1, List.of(
                        merchant("C", "20260801", "계속사업자", "561", code, "11680")),
                        3, 2, size, 3);
            }
            return new KomscoMerchantResponse(0, List.of(), 0, page, size, 0);
        };
        KomscoImportProperties properties = properties(2);

        List<KomscoMerchantRecord> records =
                new KomscoMerchantClient(pageClient, properties).fetchAllGangnamMerchants();

        assertThat(records).hasSize(3);
        assertThat(calls).hasSize(GangnamLegalDong.values().length + 1);
            assertThat(calls).contains("11680108:1", "11680108:2");
    }

    @Test
    void apiFailureOccursBeforeAnyDatabaseWrite() {
        KomscoMerchantClient client = mock(KomscoMerchantClient.class);
        RestaurantImportWriter writer = mock(RestaurantImportWriter.class);
        when(client.fetchAllGangnamMerchants()).thenThrow(new KomscoImportException("failed"));
        RestaurantImportService service = new RestaurantImportService(
                client, deduplicator, filter, writer);

        assertThatThrownBy(service::importRestaurants).isInstanceOf(KomscoImportException.class);
        verifyNoInteractions(writer);
    }

    @Test
    void scheduledSynchronizationAlsoStopsBeforeDatabaseWriteOnApiFailure() {
        KomscoMerchantClient client = mock(KomscoMerchantClient.class);
        RestaurantImportWriter writer = mock(RestaurantImportWriter.class);
        when(client.fetchAllGangnamMerchants()).thenThrow(new KomscoImportException("failed"));
        RestaurantImportService service = new RestaurantImportService(
                client, deduplicator, filter, writer);

        assertThatThrownBy(service::synchronizeRestaurants)
                .isInstanceOf(KomscoImportException.class);
        verifyNoInteractions(writer);
    }

    private LatestKomscoMerchant latest(KomscoMerchantRecord record) {
        return deduplicator.selectLatest(List.of(record)).records().getFirst();
    }

    private KomscoImportProperties properties(int pageSize) {
        return new KomscoImportProperties(
                URI.create("https://example.test/komsco"),
                "test-key",
                pageSize,
                Duration.ofSeconds(1),
                Duration.ofSeconds(1),
                false,
                false,
                false,
                "0 0 3 * * SUN",
                "Asia/Seoul");
    }

    private KomscoMerchantRecord merchant(
            String id,
            String date,
            String statusName,
            String industryCode,
            String legalDongCode,
            String usageRegionCode) {
        return new KomscoMerchantRecord(
                id,
                "1234567890",
                "01",
                statusName,
                date,
                legalDongCode,
                "역삼동",
                "서울특별시 강남구 역삼동 1",
                null,
                "테스트 식당",
                "01",
                "제로페이",
                null,
                "06200",
                industryCode,
                "음식점 및 주점업",
                "37.50",
                "127.03",
                "I0000002",
                usageRegionCode);
    }

    private KomscoMerchantRecord copyWithAddress(KomscoMerchantRecord source, String address) {
        return new KomscoMerchantRecord(
                source.altText(), source.brno(), source.businessStatus(), source.businessStatusName(),
                source.referenceDate(), source.legalDongCode(), source.legalDongName(), address,
                source.detailAddress(), source.name(), source.registrationType(),
                source.registrationTypeName(), source.telephone(), source.postalCode(),
                source.industryCode(), source.industryName(), source.lat(), source.lot(),
                source.providerInstitutionCode(), source.usageRegionCode());
    }

    private KomscoMerchantRecord copyWithProvider(KomscoMerchantRecord source, String provider) {
        return new KomscoMerchantRecord(
                source.altText(), source.brno(), source.businessStatus(), source.businessStatusName(),
                source.referenceDate(), source.legalDongCode(), source.legalDongName(), source.address(),
                source.detailAddress(), source.name(), source.registrationType(),
                source.registrationTypeName(), source.telephone(), source.postalCode(),
                source.industryCode(), source.industryName(), source.lat(), source.lot(), provider,
                source.usageRegionCode());
    }
}
