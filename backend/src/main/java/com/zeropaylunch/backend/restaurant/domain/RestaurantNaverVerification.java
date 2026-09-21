package com.zeropaylunch.backend.restaurant.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.time.Instant;

@Entity
@Table(name = "restaurant_naver_verifications",
        uniqueConstraints = @UniqueConstraint(
                name = "uk_naver_verifications_restaurant_provider",
                columnNames = {"restaurant_id", "provider"}))
public class RestaurantNaverVerification {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "restaurant_id", nullable = false)
    private Restaurant restaurant;

    @Column(nullable = false, length = 32)
    private String provider;

    @Enumerated(EnumType.STRING)
    @Column(name = "verification_status", nullable = false, length = 16)
    private NaverVerificationStatus verificationStatus;

    @Enumerated(EnumType.STRING)
    @Column(name = "verification_reason", nullable = false, length = 64)
    private NaverVerificationReason verificationReason;

    @Column(name = "source_fingerprint", length = 64)
    private String sourceFingerprint;

    @Column(name = "external_place_id", length = 64)
    private String externalPlaceId;

    @Column(name = "model_name", length = 128)
    private String modelName;

    @Column(name = "verified_at")
    private Instant verifiedAt;

    @Column(name = "last_attempt_at", nullable = false)
    private Instant lastAttemptAt;

    protected RestaurantNaverVerification() {}

    public static RestaurantNaverVerification of(
            Restaurant restaurant,
            String provider,
            NaverVerificationStatus status,
            NaverVerificationReason reason,
            String externalPlaceId,
            String modelName,
            Instant verifiedAt,
            Instant lastAttemptAt) {
        return of(restaurant, provider, status, reason, externalPlaceId, modelName,
                null, verifiedAt, lastAttemptAt);
    }

    public static RestaurantNaverVerification of(
            Restaurant restaurant,
            String provider,
            NaverVerificationStatus status,
            NaverVerificationReason reason,
            String externalPlaceId,
            String modelName,
            String sourceFingerprint,
            Instant verifiedAt,
            Instant lastAttemptAt) {
        RestaurantNaverVerification verification = new RestaurantNaverVerification();
        verification.restaurant = restaurant;
        verification.provider = provider;
        verification.verificationStatus = status;
        verification.verificationReason = reason;
        verification.externalPlaceId = externalPlaceId;
        verification.modelName = modelName;
        verification.sourceFingerprint = sourceFingerprint;
        verification.verifiedAt = verifiedAt;
        verification.lastAttemptAt = lastAttemptAt;
        return verification;
    }

    public NaverVerificationStatus getVerificationStatus() {
        return verificationStatus;
    }

    public NaverVerificationReason getVerificationReason() {
        return verificationReason;
    }

    public String getSourceFingerprint() {
        return sourceFingerprint;
    }
}
