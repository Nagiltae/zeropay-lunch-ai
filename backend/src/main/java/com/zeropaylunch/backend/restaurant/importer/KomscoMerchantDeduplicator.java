package com.zeropaylunch.backend.restaurant.importer;

import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

@Component
class KomscoMerchantDeduplicator {

    private static final DateTimeFormatter SOURCE_DATE = DateTimeFormatter.BASIC_ISO_DATE;

    KomscoDeduplicationResult selectLatest(List<KomscoMerchantRecord> records) {
        Map<String, LatestKomscoMerchant> latestByMerchant = new HashMap<>();
        int invalidCount = 0;
        for (KomscoMerchantRecord record : records) {
            if (record == null || !StringUtils.hasText(record.altText())) {
                invalidCount++;
                continue;
            }
            LocalDate referenceDate = parseReferenceDate(record.referenceDate());
            if (referenceDate == null) {
                invalidCount++;
                continue;
            }
            LatestKomscoMerchant candidate = new LatestKomscoMerchant(record, referenceDate);
            latestByMerchant.merge(
                    record.altText().trim(),
                    candidate,
                    (current, incoming) -> incoming.referenceDate().isAfter(current.referenceDate())
                            ? incoming
                            : current);
        }
        return new KomscoDeduplicationResult(List.copyOf(latestByMerchant.values()), invalidCount);
    }

    private LocalDate parseReferenceDate(String value) {
        if (!StringUtils.hasText(value)) {
            return null;
        }
        try {
            return LocalDate.parse(value.trim(), SOURCE_DATE);
        } catch (DateTimeParseException exception) {
            return null;
        }
    }
}
