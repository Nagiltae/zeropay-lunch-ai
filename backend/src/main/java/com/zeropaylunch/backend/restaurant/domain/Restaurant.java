package com.zeropaylunch.backend.restaurant.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.Objects;

@Entity
@Table(name = "restaurants")
public class Restaurant {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    @Enumerated(EnumType.STRING)
    @Column(length = 40)
    private RestaurantCategory category;

    @Column(name = "representative_menu", length = 120)
    private String representativeMenu;

    @Column(name = "average_price")
    private Integer averagePrice;

    @Column(nullable = false)
    private String address;

    @Column(name = "detail_address")
    private String detailAddress;

    @Column(name = "postal_code", length = 20)
    private String postalCode;

    @Column(name = "location_id", length = 32)
    private String locationId;

    @Column(precision = 10, scale = 7)
    private BigDecimal latitude;

    @Column(precision = 10, scale = 7)
    private BigDecimal longitude;

    @Column(name = "zero_pay_available", nullable = false)
    private boolean zeroPayAvailable;

    @Column(name = "sample_data", nullable = false)
    private boolean sampleData;

    @Column(nullable = false)
    private boolean active;

    @Column(name = "recommendation_ready", nullable = false)
    private boolean recommendationReady;

    @Enumerated(EnumType.STRING)
    @Column(name = "recommendation_eligibility", nullable = false, length = 16)
    private RecommendationEligibility recommendationEligibility;

    @Column(name = "external_merchant_id")
    private String externalMerchantId;

    @Column(name = "legal_dong_code", length = 16)
    private String legalDongCode;

    @Column(name = "legal_dong_name", length = 80)
    private String legalDongName;

    @Column(name = "industry_code", length = 20)
    private String industryCode;

    @Column(name = "industry_name")
    private String industryName;

    @Column(name = "provider_institution_code", length = 20)
    private String providerInstitutionCode;

    @Column(name = "business_status_code", length = 20)
    private String businessStatusCode;

    @Column(name = "business_status_name", length = 80)
    private String businessStatusName;

    @Column(name = "source_reference_date")
    private LocalDate sourceReferenceDate;

    @Enumerated(EnumType.STRING)
    @Column(name = "source_provider", length = 32)
    private RestaurantSourceProvider sourceProvider;

    @Column(name = "last_synced_at")
    private Instant lastSyncedAt;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    protected Restaurant() {
    }

    public static Restaurant fromExternalSource(RestaurantSourceSnapshot snapshot, Instant syncedAt) {
        Restaurant restaurant = new Restaurant();
        restaurant.zeroPayAvailable = true;
        restaurant.sampleData = false;
        restaurant.active = true;
        restaurant.recommendationReady = false;
        restaurant.recommendationEligibility = RecommendationEligibility.UNKNOWN;
        restaurant.applyExternalSource(snapshot, syncedAt);
        return restaurant;
    }

    public boolean hasSameExternalSourceData(RestaurantSourceSnapshot snapshot) {
        return sourceProvider == snapshot.sourceProvider()
                && Objects.equals(externalMerchantId, snapshot.externalMerchantId())
                && Objects.equals(name, snapshot.name())
                && Objects.equals(address, snapshot.address())
                && Objects.equals(detailAddress, snapshot.detailAddress())
                && Objects.equals(postalCode, snapshot.postalCode())
                && sameDecimal(latitude, snapshot.latitude())
                && sameDecimal(longitude, snapshot.longitude())
                && Objects.equals(legalDongCode, snapshot.legalDongCode())
                && Objects.equals(legalDongName, snapshot.legalDongName())
                && Objects.equals(industryCode, snapshot.industryCode())
                && Objects.equals(industryName, snapshot.industryName())
                && Objects.equals(providerInstitutionCode, snapshot.providerInstitutionCode())
                && Objects.equals(businessStatusCode, snapshot.businessStatusCode())
                && Objects.equals(businessStatusName, snapshot.businessStatusName())
                && Objects.equals(sourceReferenceDate, snapshot.sourceReferenceDate());
    }

    public boolean hasSameMatchingSourceData(RestaurantSourceSnapshot snapshot) {
        return Objects.equals(name, snapshot.name())
                && Objects.equals(address, snapshot.address())
                && Objects.equals(detailAddress, snapshot.detailAddress())
                && sameDecimal(latitude, snapshot.latitude())
                && sameDecimal(longitude, snapshot.longitude())
                && Objects.equals(legalDongName, snapshot.legalDongName());
    }

    private boolean sameDecimal(BigDecimal current, BigDecimal incoming) {
        if (current == null || incoming == null) {
            return current == incoming;
        }
        return current.compareTo(incoming) == 0;
    }

    public void updateExternalSource(RestaurantSourceSnapshot snapshot, Instant syncedAt) {
        synchronizeExternalSource(snapshot, true, syncedAt);
    }

    public void synchronizeExternalSource(
            RestaurantSourceSnapshot snapshot, boolean eligible, Instant syncedAt) {
        boolean matchingSourceChanged = !hasSameMatchingSourceData(snapshot);
        applyExternalSource(snapshot, syncedAt);
        zeroPayAvailable = true;
        active = eligible;
        if (matchingSourceChanged) {
            recommendationEligibility = RecommendationEligibility.UNKNOWN;
        }
    }

    public void updateRecommendationEligibility(
            RecommendationEligibility eligibility, Instant updatedAt) {
        recommendationEligibility = Objects.requireNonNull(eligibility);
        this.updatedAt = updatedAt;
    }

    private void applyExternalSource(RestaurantSourceSnapshot snapshot, Instant syncedAt) {
        sourceProvider = snapshot.sourceProvider();
        externalMerchantId = snapshot.externalMerchantId();
        if (snapshot.name() != null) {
            name = snapshot.name();
        }
        if (snapshot.address() != null) {
            address = snapshot.address();
        }
        detailAddress = snapshot.detailAddress();
        postalCode = snapshot.postalCode();
        latitude = snapshot.latitude();
        longitude = snapshot.longitude();
        legalDongCode = snapshot.legalDongCode();
        legalDongName = snapshot.legalDongName();
        industryCode = snapshot.industryCode();
        industryName = snapshot.industryName();
        providerInstitutionCode = snapshot.providerInstitutionCode();
        businessStatusCode = snapshot.businessStatusCode();
        businessStatusName = snapshot.businessStatusName();
        sourceReferenceDate = snapshot.sourceReferenceDate();
        lastSyncedAt = syncedAt;
        updatedAt = syncedAt;
        if (createdAt == null) {
            createdAt = syncedAt;
        }
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public RestaurantCategory getCategory() {
        return category;
    }

    public String getRepresentativeMenu() {
        return representativeMenu;
    }

    public Integer getAveragePrice() {
        return averagePrice;
    }

    public String getAddress() {
        return address;
    }

    public String getLocationId() {
        return locationId;
    }

    public BigDecimal getLatitude() {
        return latitude;
    }

    public BigDecimal getLongitude() {
        return longitude;
    }

    public boolean isZeroPayAvailable() {
        return zeroPayAvailable;
    }

    public boolean isSampleData() {
        return sampleData;
    }

    public boolean isActive() {
        return active;
    }

    public boolean isRecommendationReady() {
        return recommendationReady;
    }

    public RecommendationEligibility getRecommendationEligibility() {
        return recommendationEligibility;
    }

    public String getExternalMerchantId() {
        return externalMerchantId;
    }

    public String getDetailAddress() {
        return detailAddress;
    }

    public String getPostalCode() {
        return postalCode;
    }

    public String getLegalDongCode() {
        return legalDongCode;
    }

    public String getLegalDongName() {
        return legalDongName;
    }

    public String getIndustryCode() {
        return industryCode;
    }

    public String getIndustryName() {
        return industryName;
    }

    public String getProviderInstitutionCode() {
        return providerInstitutionCode;
    }

    public String getBusinessStatusCode() {
        return businessStatusCode;
    }

    public String getBusinessStatusName() {
        return businessStatusName;
    }

    public LocalDate getSourceReferenceDate() {
        return sourceReferenceDate;
    }

    public RestaurantSourceProvider getSourceProvider() {
        return sourceProvider;
    }

    public Instant getLastSyncedAt() {
        return lastSyncedAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }
}
