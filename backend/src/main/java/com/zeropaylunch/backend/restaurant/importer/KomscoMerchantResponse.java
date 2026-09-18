package com.zeropaylunch.backend.restaurant.importer;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import java.util.List;

@JsonIgnoreProperties(ignoreUnknown = true)
public record KomscoMerchantResponse(
        int currentCount,
        List<KomscoMerchantRecord> data,
        long matchCount,
        int page,
        int perPage,
        long totalCount) {

    public List<KomscoMerchantRecord> records() {
        return data == null ? List.of() : data;
    }
}
