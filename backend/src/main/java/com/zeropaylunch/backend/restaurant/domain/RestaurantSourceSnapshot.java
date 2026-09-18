package com.zeropaylunch.backend.restaurant.domain;

import java.math.BigDecimal;
import java.time.LocalDate;

public record RestaurantSourceSnapshot(
        RestaurantSourceProvider sourceProvider,
        String externalMerchantId,
        String name,
        String address,
        String detailAddress,
        String postalCode,
        BigDecimal latitude,
        BigDecimal longitude,
        String legalDongCode,
        String legalDongName,
        String industryCode,
        String industryName,
        String providerInstitutionCode,
        String businessStatusCode,
        String businessStatusName,
        LocalDate sourceReferenceDate) {}
