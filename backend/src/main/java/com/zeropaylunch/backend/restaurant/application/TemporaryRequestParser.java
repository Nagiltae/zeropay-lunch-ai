package com.zeropaylunch.backend.restaurant.application;

import com.zeropaylunch.backend.restaurant.domain.RestaurantCategory;
import java.util.Optional;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.springframework.stereotype.Component;

@Component
public class TemporaryRequestParser {

    private static final Pattern TEN_THOUSAND_WON_PATTERN =
            Pattern.compile("(?:(\\d+)\\s*)?만\\s*원?\\s*이하");

    public RequestConditions parse(String message) {
        return new RequestConditions(
                parseMaximumPrice(message),
                parseCategory(message),
                message.contains("제로페이")
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

    public record RequestConditions(
            Integer maximumPrice,
            Optional<RestaurantCategory> category,
            boolean zeroPayRequired
    ) {
    }
}
