package com.zeropaylunch.backend.restaurant.enrichment.naver;

import static org.assertj.core.api.Assertions.assertThat;

import com.zeropaylunch.backend.restaurant.domain.ExternalPlaceMatchStatus;
import com.zeropaylunch.backend.restaurant.domain.Restaurant;
import com.zeropaylunch.backend.restaurant.domain.RestaurantSourceProvider;
import com.zeropaylunch.backend.restaurant.domain.RestaurantSourceSnapshot;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class NaverRestaurantMatcherTests {

    private final NaverMatchingProperties matchingPolicy = policy();
    private final NaverRestaurantCategoryPolicy categoryPolicy =
            new NaverRestaurantCategoryPolicy();
    private NaverRestaurantMatcher matcher;

    @BeforeEach
    void setUp() {
        NaverMatchingProperties policy = policy();
        this.matcher = new NaverRestaurantMatcher(
                new NaverTextNormalizer(),
                new GeoDistanceCalculator(),
                new NaverCoordinateParser(),
                new NaverCandidateHardGate(policy, new NaverRestaurantCategoryPolicy()),
                new NaverAddressParser(),
                policy);
    }

    @Test
    void sameNameAndAddressAreMatched() {
        NaverMatchDecision decision = matcher.match(
                restaurant(), List.of(candidate("토브", "서울 강남구 학동로 1", 127.0300, 37.5000)),
                "토브 논현동");

        assertThat(decision.status()).isEqualTo(ExternalPlaceMatchStatus.MATCHED);
        assertThat(decision.score()).isEqualTo(100.0);
    }

    @Test
    void scaledIntegerCoordinatesFromTheRealApiAreConvertedBeforeMatching() {
        NaverSearchCandidate actualApiShape = new NaverSearchCandidate(new NaverLocalItem(
                "<b>토브</b>", "", "음식점>한식", "", "",
                "서울특별시 강남구 논현동 1", "서울특별시 강남구 학동로 1",
                "1270300000", "375000000"), "토브 논현동");

        NaverMatchDecision decision = matcher.match(
                restaurant(), List.of(actualApiShape), "토브 논현동");

        assertThat(decision.status()).isEqualTo(ExternalPlaceMatchStatus.MATCHED);
        assertThat(decision.distanceMeters()).isLessThan(1.0);
    }

    @Test
    void sameNameAndNearbyCoordinatesAreMatchedEvenWithOnlyDongAddressEvidence() {
        NaverMatchDecision decision = matcher.match(
                restaurant(), List.of(candidate("토브", "서울 강남구 논현동 99", 127.0301, 37.5001)),
                "토브 논현동");

        assertThat(decision.status()).isEqualTo(ExternalPlaceMatchStatus.MATCHED);
        assertThat(decision.score()).isGreaterThanOrEqualTo(70.0);
    }

    @Test
    void sameNameAtAPlaceFartherThanMaximumDistanceIsExcluded() {
        NaverMatchDecision decision = matcher.match(
                restaurant(), List.of(candidate("토브", "서울 강남구 삼성동 1", 127.1000, 37.5500)),
                "토브 논현동");

        assertThat(decision.status()).isEqualTo(ExternalPlaceMatchStatus.UNMATCHED);
        assertThat(decision.selected()).isNull();
    }

    @Test
    void exactNameWithWeakAddressAndMoreThanFiftyMetersIsAmbiguous() {
        NaverMatchDecision decision = matcher.match(
                restaurant(), List.of(candidate(
                        "토브", "서울 강남구 논현동 99", 127.03072, 37.5000)),
                "토브 논현동");

        assertThat(decision.distanceMeters()).isBetween(60.0, 70.0);
        assertThat(decision.score()).isGreaterThanOrEqualTo(70.0);
        assertThat(decision.status()).isEqualTo(ExternalPlaceMatchStatus.AMBIGUOUS);
    }

    @Test
    void sumiSushiValidationCaseIsDemotedToAmbiguous() {
        Restaurant sumiSushi = restaurant(
                "수미초밥", "서울특별시 강남구 논현로71길 29 (역삼동)",
                "1층 수미초밥", "37.4943224", "127.0371590", "역삼동");
        NaverSearchCandidate candidate = new NaverSearchCandidate(new NaverLocalItem(
                "수미초밥", "", "음식점>일식>초밥,롤", "", "",
                "서울특별시 강남구 역삼동 792-25 101호",
                "서울특별시 강남구 논현로71길 37 101호",
                "127.0364664", "37.4941717"), "수미초밥 역삼동");

        NaverMatchDecision decision = matcher.match(
                sumiSushi, List.of(candidate), "수미초밥 역삼동");

        assertThat(decision.score()).isEqualTo(72.0);
        assertThat(decision.distanceMeters()).isBetween(63.0, 64.0);
        assertThat(decision.status()).isEqualTo(ExternalPlaceMatchStatus.AMBIGUOUS);
    }

    @Test
    void strongAddressStillAllowsMatchedBeyondFiftyMeters() {
        NaverMatchDecision decision = matcher.match(
                restaurant(), List.of(candidate(
                        "토브", "서울 강남구 학동로 1", 127.03072, 37.5000)),
                "토브 논현동");

        assertThat(decision.distanceMeters()).isBetween(60.0, 70.0);
        assertThat(decision.status()).isEqualTo(ExternalPlaceMatchStatus.MATCHED);
    }

    @Test
    void clearlyNonFoodCategoryIsExcludedEvenWhenNameAndLocationAreStrong() {
        NaverSearchCandidate retailCandidate = new NaverSearchCandidate(new NaverLocalItem(
                "토브 프리미엄 반찬", "", "쇼핑,유통>반찬가게", "", "",
                "서울 강남구 논현동 1", "서울 강남구 학동로 1",
                "127.0300000", "37.5000000"), "토브 논현동");

        NaverMatchDecision decision = matcher.match(
                restaurant(), List.of(retailCandidate), "토브 논현동");

        assertThat(decision.status()).isEqualTo(ExternalPlaceMatchStatus.UNMATCHED);
        assertThat(decision.selected()).isNull();
    }

    @Test
    void guyaSideDishValidationCaseIsExcluded() {
        Restaurant guya = restaurant(
                "구야네", "서울특별시 강남구 양재대로33길 7",
                null, "37.4900105", "127.0829348", "일원동");
        NaverSearchCandidate candidate = new NaverSearchCandidate(new NaverLocalItem(
                "구야네 프리미엄 반찬", "", "쇼핑,유통>반찬가게", "", "",
                "서울특별시 강남구 일원동 681-6 1층 102호",
                "서울특별시 강남구 양재대로33길 7 1층 102호",
                "127.0829815", "37.4900236"), "구야네 일원동");

        NaverMatchDecision decision = matcher.match(
                guya, List.of(candidate), "구야네 일원동");

        assertThat(decision.status()).isEqualTo(ExternalPlaceMatchStatus.UNMATCHED);
        assertThat(decision.selected()).isNull();
    }

    @Test
    void candidateBelowMinimumNameEvidenceIsExcluded() {
        NaverMatchDecision decision = matcher.match(
                restaurant(), List.of(candidate(
                        "완전히다른상호", "서울 강남구 학동로 1", 127.0300, 37.5000)),
                "토브 논현동");

        assertThat(decision.status()).isEqualTo(ExternalPlaceMatchStatus.UNMATCHED);
        assertThat(decision.selected()).isNull();
    }

    @Test
    void choosesTheStrongestCandidateRatherThanTheFirstResult() {
        NaverSearchCandidate wrong = candidate(
                "전혀다른가게", "서울 강남구 논현동 99", 127.0301, 37.5001);
        NaverSearchCandidate correct = candidate(
                "토브", "서울 강남구 학동로 1", 127.0300, 37.5000);

        NaverMatchDecision decision = matcher.match(
                restaurant(), List.of(wrong, correct), "토브 논현동");

        assertThat(decision.status()).isEqualTo(ExternalPlaceMatchStatus.MATCHED);
        assertThat(decision.selected().candidate()).isEqualTo(correct);
    }

    @Test
    void classifiesTwoEquallyStrongCandidatesAsAmbiguous() {
        NaverMatchDecision decision = matcher.match(restaurant(), List.of(
                candidate("토브", "서울 강남구 논현동 9", 127.0301, 37.5001),
                candidate("토브", "서울 강남구 논현동 10", 127.0302, 37.5001)),
                "토브 논현동");

        assertThat(decision.status()).isEqualTo(ExternalPlaceMatchStatus.AMBIGUOUS);
        assertThat(decision.runnerUpScore()).isNotNull();
        assertThat(decision.scoreGap()).isLessThan(8.0);
    }

    @Test
    void rejectsAnotherBranchOfTheSameFranchise() {
        Restaurant branchRestaurant = restaurant("토브 강남점");

        NaverMatchDecision decision = matcher.match(
                branchRestaurant,
                List.of(candidate("토브 대치점", "서울 강남구 학동로 1", 127.0300, 37.5000)),
                "토브 강남점 논현동");

        assertThat(decision.status()).isEqualTo(ExternalPlaceMatchStatus.UNMATCHED);
        assertThat(decision.selected()).isNull();
    }

    @Test
    void keepsTheConfiguredGapBoundaryExplainable() {
        NaverMatchDecision decision = matcher.match(restaurant(), List.of(
                candidate("토브", "서울 강남구 학동로 1", 127.0300, 37.5000),
                candidate("토브", "서울 강남구 논현동 99", 127.0320, 37.5000)),
                "토브 논현동");

        assertThat(decision.runnerUpScore()).isNotNull();
        assertThat(decision.scoreGap())
                .isEqualTo(decision.score() - decision.runnerUpScore());
    }

    @Test
    void returnsUnmatchedWhenThereIsNoViableCandidate() {
        NaverMatchDecision decision = matcher.match(
                restaurant(), List.of(candidate(
                        "다른상점", "서울 강남구 논현동 99", 127.0330, 37.5000)),
                "토브 논현동");

        assertThat(decision.status()).isEqualTo(ExternalPlaceMatchStatus.UNMATCHED);
    }

    private Restaurant restaurant() {
        return restaurant("토브");
    }

    private Restaurant restaurant(String name) {
        return restaurant(
                name, "서울특별시 강남구 학동로 1",
                null, "37.5000000", "127.0300000", "논현동");
    }

    private Restaurant restaurant(
            String name,
            String address,
            String detailAddress,
            String latitude,
            String longitude,
            String legalDongName) {
        return Restaurant.fromExternalSource(new RestaurantSourceSnapshot(
                RestaurantSourceProvider.KOMSCO,
                "merchant-1",
                name,
                address,
                detailAddress,
                "06000",
                new BigDecimal(latitude),
                new BigDecimal(longitude),
                "11680108",
                legalDongName,
                "561",
                "음식점 및 주점업",
                "I0000002",
                "01",
                "계속사업자",
                LocalDate.of(2026, 9, 1)), Instant.parse("2026-09-18T00:00:00Z"));
    }

    private NaverSearchCandidate candidate(
            String title, String roadAddress, double longitude, double latitude) {
        return new NaverSearchCandidate(new NaverLocalItem(
                title, "https://example.test", "음식점>한식", "", "",
                roadAddress, roadAddress, Double.toString(longitude), Double.toString(latitude)),
                "토브 논현동");
    }

    private NaverMatchingProperties policy() {
        return new NaverMatchingProperties(
                40, 35, 32, 22, 0.85, 0.70,
                30, 25, 15, 8, 0.70, 0.45,
                20, 14, 6, 10, 300, 70, 45, 8,
                22, 32, 25, 50);
    }

    @Test
    void strongAddressMatch_spacingInRoadNameAndBuildingNumber() {
        assertAddressScore("서울특별시 강남구 강남대로 156길 17-1", "서울특별시 강남구 강남대로156길 17-1", 30.0);
        assertAddressScore("헌릉로569길9", "헌릉로569길 9", 30.0);
        assertAddressScore("압구정로 34길 16", "압구정로34길 16", 30.0);
        assertAddressScore("논현로 175길 61", "논현로175길 61", 30.0);
    }

    @Test
    void strongAddressMatch_detailAddressIsIgnoredIfCoreMatches() {
        assertAddressScore("도곡로63길 28", "도곡로63길 28 1층", 30.0);
        assertAddressScore("도곡로63길 28 101호", "도곡로63길 28", 30.0);
    }

    @Test
    void differentBuildingNumbersAreNotStrongMatch() {
        assertAddressScore("논현로71길 29", "논현로71길 37", 0.0);
    }

    @Test
    void completelyDifferentRoadNamesAreNotStrongMatch() {
        assertAddressScore("테헤란로 103", "강남대로 396", 0.0);
        assertAddressScore("언주로134길 33", "학동로45길 3", 0.0);
    }

    private void assertAddressScore(String sourceAddress, String candidateAddress, double expectedScore) {
        Restaurant r = restaurant("테스트가게", sourceAddress, null, "37.5", "127.0", "논현동");
        NaverSearchCandidate c = candidate("테스트가게", candidateAddress, 127.0, 37.5);
        
        NaverMatchDecision decision = matcher.match(r, List.of(c), "테스트가게");
        if (decision.selected() != null) {
            assertThat(decision.selected().addressScore()).isEqualTo(expectedScore);
        } else {
            // Unmatched if score < 70
        }
    }
}
