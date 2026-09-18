package com.zeropaylunch.backend.restaurant.importer;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

@JsonIgnoreProperties(ignoreUnknown = true)
public record KomscoMerchantRecord(
        @JsonProperty("alt_text") String altText,
        String brno,
        @JsonProperty("bzmn_stts") String businessStatus,
        @JsonProperty("bzmn_stts_nm") String businessStatusName,
        @JsonProperty("crtr_ymd") String referenceDate,
        @JsonProperty("emd_cd") String legalDongCode,
        @JsonProperty("emd_nm") String legalDongName,
        @JsonProperty("frcs_addr") String address,
        @JsonProperty("frcs_dtl_addr") String detailAddress,
        @JsonProperty("frcs_nm") String name,
        @JsonProperty("frcs_reg_se") String registrationType,
        @JsonProperty("frcs_reg_se_nm") String registrationTypeName,
        @JsonProperty("frcs_rprs_telno") String telephone,
        @JsonProperty("frcs_zip") String postalCode,
        @JsonProperty("ksic_cd") String industryCode,
        @JsonProperty("ksic_cd_nm") String industryName,
        String lat,
        String lot,
        @JsonProperty("pvsn_inst_cd") String providerInstitutionCode,
        @JsonProperty("usage_rgn_cd") String usageRegionCode) {}
