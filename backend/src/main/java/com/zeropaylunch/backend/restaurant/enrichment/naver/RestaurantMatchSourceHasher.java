package com.zeropaylunch.backend.restaurant.enrichment.naver;

import com.zeropaylunch.backend.restaurant.domain.Restaurant;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import org.springframework.stereotype.Component;

@Component
class RestaurantMatchSourceHasher {

    String hash(Restaurant restaurant) {
        String content = String.join("\u001f",
                text(restaurant.getName()),
                text(restaurant.getAddress()),
                text(restaurant.getDetailAddress()),
                decimal(restaurant.getLatitude()),
                decimal(restaurant.getLongitude()),
                text(restaurant.getLegalDongName()));
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return HexFormat.of().formatHex(digest.digest(content.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 is not available", exception);
        }
    }

    private String text(String value) {
        return value == null ? "" : value.trim();
    }

    private String decimal(BigDecimal value) {
        return value == null ? "" : value.stripTrailingZeros().toPlainString();
    }
}
