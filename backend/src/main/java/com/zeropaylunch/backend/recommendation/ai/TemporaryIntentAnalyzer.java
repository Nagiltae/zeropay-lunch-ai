package com.zeropaylunch.backend.recommendation.ai;

import com.zeropaylunch.backend.recommendation.ai.AnalyzedIntent.IntentType;
import com.zeropaylunch.backend.restaurant.domain.RestaurantCategory;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.springframework.stereotype.Component;

@Component
public class TemporaryIntentAnalyzer {

    private static final Pattern TEN_THOUSAND_WON_PATTERN =
            Pattern.compile("(?:(\\d+)\\s*)?만\\s*원?\\s*이하");

    public AnalyzedIntent analyze(IntentAnalysisRequest request) {
        return new AnalyzedIntent(
                IntentType.RECOMMEND_RESTAURANT,
                parseMaximumPrice(request.message()),
                parseCategory(request.message()),
                parseKeywords(request.message()),
                false,
                null
        );
    }

    private Integer parseMaximumPrice(String message) {
        Matcher matcher = TEN_THOUSAND_WON_PATTERN.matcher(message);
        if (!matcher.find()) {
            return null;
        }
        int tenThousands = matcher.group(1) == null ? 1 : Integer.parseInt(matcher.group(1));
        return tenThousands * 10_000;
    }

    private Optional<RestaurantCategory> parseCategory(String message) {
        if (message.contains("국물") || message.contains("국밥")) {
            return Optional.of(RestaurantCategory.KOREAN_SOUP);
        }
        if (message.contains("샐러드") || message.contains("가볍")) {
            return Optional.of(RestaurantCategory.SALAD);
        }
        if (message.contains("한식") || message.contains("제육")) {
            return Optional.of(RestaurantCategory.KOREAN);
        }
        return Optional.empty();
    }

    private List<String> parseKeywords(String message) {
        List<String> keywords = new ArrayList<>();
        for (String keyword : List.of("국물", "국밥", "샐러드", "가볍게", "한식", "제육")) {
            if (message.contains(keyword)) {
                keywords.add(keyword);
            }
        }
        return List.copyOf(keywords);
    }
}
