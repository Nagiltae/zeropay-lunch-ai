package com.zeropaylunch.backend.restaurant.enrichment.naver;

import java.math.BigDecimal;
import java.math.RoundingMode;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

@Component
class NaverCoordinateParser {

    private static final BigDecimal NAVER_COORDINATE_SCALE = new BigDecimal("10000000");

    BigDecimal longitude(String value) {
        return coordinate(value, new BigDecimal("180"));
    }

    BigDecimal latitude(String value) {
        return coordinate(value, new BigDecimal("90"));
    }

    private BigDecimal coordinate(String value, BigDecimal maximumAbsoluteValue) {
        if (!StringUtils.hasText(value)) {
            return null;
        }
        try {
            BigDecimal parsed = new BigDecimal(value.trim());
            if (parsed.abs().compareTo(maximumAbsoluteValue) > 0) {
                parsed = parsed.divide(NAVER_COORDINATE_SCALE, 7, RoundingMode.HALF_UP);
            }
            if (parsed.abs().compareTo(maximumAbsoluteValue) > 0) {
                return null;
            }
            return parsed.setScale(7, RoundingMode.HALF_UP);
        } catch (NumberFormatException exception) {
            return null;
        }
    }
}
