package com.zeropaylunch.backend.restaurant.importer;

import java.util.ArrayList;
import java.util.List;
import org.springframework.stereotype.Component;

@Component
public class KomscoMerchantClient {

    private final KomscoPageClient pageClient;
    private final KomscoImportProperties properties;

    KomscoMerchantClient(KomscoPageClient pageClient, KomscoImportProperties properties) {
        this.pageClient = pageClient;
        this.properties = properties;
    }

    public List<KomscoMerchantRecord> fetchAllGangnamMerchants() {
        List<KomscoMerchantRecord> allRecords = new ArrayList<>();
        for (GangnamLegalDong legalDong : GangnamLegalDong.values()) {
            fetchAllPages(legalDong, allRecords);
        }
        return List.copyOf(allRecords);
    }

    private void fetchAllPages(
            GangnamLegalDong legalDong, List<KomscoMerchantRecord> destination) {
        int page = 1;
        while (true) {
            KomscoMerchantResponse response =
                    pageClient.fetchPage(legalDong.code(), page, properties.pageSize());
            List<KomscoMerchantRecord> records = response.records();
            destination.addAll(records);
            if (records.isEmpty()
                    || response.currentCount() == 0
                    || (long) page * properties.pageSize() >= response.totalCount()) {
                return;
            }
            page++;
        }
    }
}
