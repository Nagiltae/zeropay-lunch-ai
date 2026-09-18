package com.zeropaylunch.backend.restaurant.enrichment.naver;

import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

@Component
class NaverAddressParser {

    private static final Pattern ROAD_ADDRESS_PATTERN = 
            Pattern.compile("^(?:서울(?:특별시|시)?\\s*(?:강남구)?\\s*|강남구\\s*)?([가-힣a-zA-Z0-9\\s]+(?:대로|로|길))\\s*(\\d+(?:-\\d+)?)");

    record ParsedAddress(String roadName, String buildingNumber) {}

    ParsedAddress parse(String address) {
        if (!StringUtils.hasText(address)) {
            return null;
        }
        Matcher matcher = ROAD_ADDRESS_PATTERN.matcher(address);
        if (matcher.find()) {
            String roadName = matcher.group(1).replace(" ", "");
            String buildingNumber = matcher.group(2);
            return new ParsedAddress(roadName, buildingNumber);
        }
        return null;
    }
}
