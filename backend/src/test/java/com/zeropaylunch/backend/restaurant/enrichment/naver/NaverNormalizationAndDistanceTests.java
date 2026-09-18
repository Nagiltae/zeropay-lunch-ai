package com.zeropaylunch.backend.restaurant.enrichment.naver;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class NaverNormalizationAndDistanceTests {

    private final NaverTextNormalizer normalizer = new NaverTextNormalizer();
    private final GeoDistanceCalculator distanceCalculator = new GeoDistanceCalculator();
    private final NaverCoordinateParser coordinateParser = new NaverCoordinateParser();

    @Test
    void normalizesHtmlWhitespaceAndSpecialCharactersInTitle() {
        assertThat(normalizer.normalizeName("  <b>토브</b>  강남점! "))
                .isEqualTo("토브강남점");
    }

    @Test
    void extractsBranchNamesWithoutTreatingAllParenthesesAsBranches() {
        NaverNameProfile branch = normalizer.nameProfile("토브 (강남점)");
        NaverNameProfile description = normalizer.nameProfile("토브(수제버거)");

        assertThat(branch.normalizedBase()).isEqualTo("토브");
        assertThat(branch.branchName()).isEqualTo("강남점");
        assertThat(description.normalizedWithoutParentheses()).isEqualTo("토브");
        assertThat(description.branchName()).isNull();
    }

    @Test
    void normalizesSeoulAliasesParenthesesAndAddressPunctuation() {
        assertThat(normalizer.normalizeAddress("서울특별시 강남구 학동로 1 (논현동), 2층"))
                .isEqualTo("서울 강남구 학동로 1 2층");
    }

    @Test
    void calculatesHaversineDistanceInMeters() {
        Double distance = distanceCalculator.distanceMeters(
                new BigDecimal("37.5000000"), new BigDecimal("127.0300000"),
                new BigDecimal("37.5000000"), new BigDecimal("127.0310000"));

        assertThat(distance).isBetween(87.0, 89.0);
    }

    @Test
    void convertsScaledNaverCoordinatesAndAlsoAcceptsDecimalWgs84() {
        assertThat(coordinateParser.longitude("1270538567"))
                .isEqualByComparingTo("127.0538567");
        assertThat(coordinateParser.latitude("374987973"))
                .isEqualByComparingTo("37.4987973");
        assertThat(coordinateParser.longitude("127.0538567"))
                .isEqualByComparingTo("127.0538567");
    }
}
