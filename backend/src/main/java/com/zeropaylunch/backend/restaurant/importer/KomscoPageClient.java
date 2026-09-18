package com.zeropaylunch.backend.restaurant.importer;

interface KomscoPageClient {

    KomscoMerchantResponse fetchPage(String legalDongCode, int page, int pageSize);
}
