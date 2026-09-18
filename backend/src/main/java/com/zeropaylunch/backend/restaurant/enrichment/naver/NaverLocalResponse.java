package com.zeropaylunch.backend.restaurant.enrichment.naver;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import java.util.List;

@JsonIgnoreProperties(ignoreUnknown = true)
record NaverLocalResponse(
        String lastBuildDate,
        int total,
        int start,
        int display,
        List<NaverLocalItem> items) {

    List<NaverLocalItem> results() {
        return items == null ? List.of() : items;
    }
}
