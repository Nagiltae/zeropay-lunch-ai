package com.zeropaylunch.backend.recommendation.ai;

import static org.assertj.core.api.Assertions.assertThat;

import com.zeropaylunch.backend.preference.domain.SpiceLevel;
import com.zeropaylunch.backend.restaurant.domain.RestaurantCategory;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.Test;

class TemporaryIntentAnalyzerTests {

    private final TemporaryIntentAnalyzer analyzer = new TemporaryIntentAnalyzer();

    @Test
    void parsesOnlySupportedTemporaryConditions() {
        var result = analyzer.analyze(new IntentAnalysisRequest(
                "만원 이하로 제로페이 되는 국물 음식 추천해줘",
                "gangnam",
                null,
                SpiceLevel.ANY,
                Set.of(),
                Set.of(),
                Set.of(),
                List.of()
        ));

        assertThat(result.maximumPrice()).isEqualTo(10_000);
        assertThat(result.category()).contains(RestaurantCategory.KOREAN_SOUP);
        assertThat(result.keywords()).contains("국물");
    }
}
