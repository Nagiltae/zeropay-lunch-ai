package com.zeropaylunch.backend.restaurant.importer;

import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

@Component
class KomscoMerchantFilter {

    private static final String RESTAURANT_INDUSTRY = "561";
    private static final String ACTIVE_BUSINESS = "계속사업자";
    private static final String ZERO_PAY_PROVIDER = "I0000002";
    private static final String GANGNAM_REGION_PREFIX = "11680";

    boolean isActiveGangnamRestaurant(LatestKomscoMerchant merchant) {
        KomscoMerchantRecord source = merchant.source();
        return RESTAURANT_INDUSTRY.equals(trim(source.industryCode()))
                && ACTIVE_BUSINESS.equals(trim(source.businessStatusName()))
                && ZERO_PAY_PROVIDER.equals(trim(source.providerInstitutionCode()))
                && GangnamLegalDong.containsCode(trim(source.legalDongCode()))
                && hasGangnamEvidence(source);
    }

    private boolean hasGangnamEvidence(KomscoMerchantRecord source) {
        String regionCode = trim(source.usageRegionCode());
        String address = trim(source.address());
        return regionCode.startsWith(GANGNAM_REGION_PREFIX)
                || (StringUtils.hasText(address) && address.contains("강남구"));
    }

    private String trim(String value) {
        return value == null ? "" : value.trim();
    }
}
