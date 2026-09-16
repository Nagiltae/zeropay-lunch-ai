package com.zeropaylunch.backend.restaurant.application;

import static org.assertj.core.api.Assertions.assertThat;

import com.zeropaylunch.backend.restaurant.domain.RestaurantCategory;
import org.junit.jupiter.api.Test;

class TemporaryRequestParserTests {

    private final TemporaryRequestParser parser = new TemporaryRequestParser();

    @Test
    void parsesOnlySupportedTemporaryConditions() {
        var result = parser.parse("만원 이하로 제로페이 되는 국물 음식 추천해줘");

        assertThat(result.maximumPrice()).isEqualTo(10_000);
        assertThat(result.category()).contains(RestaurantCategory.KOREAN_SOUP);
        assertThat(result.zeroPayRequired()).isTrue();
    }
}
