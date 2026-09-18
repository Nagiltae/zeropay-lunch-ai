package com.zeropaylunch.backend.restaurant.enrichment.naver;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
record NaverLocalItem(
        String title,
        String link,
        String category,
        String description,
        String telephone,
        String address,
        String roadAddress,
        String mapx,
        String mapy) {
}
