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
import java.math.BigDecimal;
import java.time.Instant;

@Entity
@Table(
        name = "restaurant_external_places",
        uniqueConstraints = @UniqueConstraint(
                name = "uk_external_places_restaurant_provider",
                columnNames = {"restaurant_id", "provider"}))
public class RestaurantExternalPlace {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "restaurant_id", nullable = false)
    private Restaurant restaurant;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 32)
    private ExternalPlaceProvider provider;

    @Column(name = "external_name")
    private String externalName;

    private String category;

    @Column(length = 1000)
    private String description;

    @Column(length = 1000)
    private String link;

    private String address;

    @Column(name = "road_address")
    private String roadAddress;

    @Column(precision = 10, scale = 7)
    private BigDecimal latitude;

    @Column(precision = 10, scale = 7)
    private BigDecimal longitude;

    @Enumerated(EnumType.STRING)
    @Column(name = "match_status", nullable = false, length = 16)
    private ExternalPlaceMatchStatus matchStatus;

    @Column(name = "match_score", nullable = false, precision = 5, scale = 2)
    private BigDecimal matchScore;

    @Column(name = "match_distance_meters", precision = 10, scale = 2)
    private BigDecimal matchDistanceMeters;

    @Column(name = "name_score", nullable = false, precision = 5, scale = 2)
    private BigDecimal nameScore;

    @Column(name = "address_score", nullable = false, precision = 5, scale = 2)
    private BigDecimal addressScore;

    @Column(name = "distance_score", nullable = false, precision = 5, scale = 2)
    private BigDecimal distanceScore;

    @Column(name = "category_score", nullable = false, precision = 5, scale = 2)
    private BigDecimal categoryScore;

    @Column(name = "runner_up_score", precision = 5, scale = 2)
    private BigDecimal runnerUpScore;

    @Column(name = "score_gap", precision = 5, scale = 2)
    private BigDecimal scoreGap;

    @Column(name = "query_used", nullable = false)
    private String queryUsed;

    @Column(name = "matched_at")
    private Instant matchedAt;

    @Column(name = "last_synced_at")
    private Instant lastSyncedAt;

    @Column(name = "source_content_hash", length = 64)
    private String sourceContentHash;

    @Enumerated(EnumType.STRING)
    @Column(name = "last_attempt_status", length = 16)
    private ExternalPlaceAttemptStatus lastAttemptStatus;

    @Column(name = "last_match_attempt_at")
    private Instant lastMatchAttemptAt;

    @Column(name = "next_retry_at")
    private Instant nextRetryAt;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    protected RestaurantExternalPlace() {
    }

    public static RestaurantExternalPlace create(
            Restaurant restaurant, RestaurantExternalPlaceSnapshot snapshot, Instant syncedAt) {
        RestaurantExternalPlace place = new RestaurantExternalPlace();
        place.restaurant = restaurant;
        place.provider = snapshot.provider();
        place.createdAt = syncedAt;
        place.apply(snapshot, syncedAt);
        return place;
    }

    public void apply(RestaurantExternalPlaceSnapshot snapshot, Instant syncedAt) {
        externalName = snapshot.externalName();
        category = snapshot.category();
        description = snapshot.description();
        link = snapshot.link();
        address = snapshot.address();
        roadAddress = snapshot.roadAddress();
        latitude = snapshot.latitude();
        longitude = snapshot.longitude();
        matchStatus = snapshot.matchStatus();
        matchScore = snapshot.matchScore();
        nameScore = snapshot.nameScore();
        addressScore = snapshot.addressScore();
        distanceScore = snapshot.distanceScore();
        categoryScore = snapshot.categoryScore();
        matchDistanceMeters = snapshot.matchDistanceMeters();
        runnerUpScore = snapshot.runnerUpScore();
        scoreGap = snapshot.scoreGap();
        queryUsed = snapshot.queryUsed();
        matchedAt = snapshot.matchedAt();
        sourceContentHash = snapshot.sourceContentHash();
        lastAttemptStatus = ExternalPlaceAttemptStatus.SUCCESS;
        lastMatchAttemptAt = syncedAt;
        nextRetryAt = snapshot.nextRetryAt();
        lastSyncedAt = syncedAt;
        updatedAt = syncedAt;
    }

    public static RestaurantExternalPlace createFailure(
            Restaurant restaurant,
            ExternalPlaceProvider provider,
            String sourceContentHash,
            String queryUsed,
            Instant attemptedAt,
            Instant nextRetryAt) {
        RestaurantExternalPlace place = new RestaurantExternalPlace();
        place.restaurant = restaurant;
        place.provider = provider;
        place.matchStatus = ExternalPlaceMatchStatus.API_ERROR;
        place.matchScore = BigDecimal.ZERO;
        place.nameScore = BigDecimal.ZERO;
        place.addressScore = BigDecimal.ZERO;
        place.distanceScore = BigDecimal.ZERO;
        place.categoryScore = BigDecimal.ZERO;
        place.queryUsed = queryUsed;
        place.sourceContentHash = sourceContentHash;
        place.lastAttemptStatus = ExternalPlaceAttemptStatus.API_ERROR;
        place.lastMatchAttemptAt = attemptedAt;
        place.nextRetryAt = nextRetryAt;
        place.createdAt = attemptedAt;
        place.updatedAt = attemptedAt;
        return place;
    }

    public void recordAttemptFailure(
            String sourceContentHash, Instant attemptedAt, Instant retryAt) {
        this.sourceContentHash = sourceContentHash;
        lastAttemptStatus = ExternalPlaceAttemptStatus.API_ERROR;
        lastMatchAttemptAt = attemptedAt;
        nextRetryAt = retryAt;
        updatedAt = attemptedAt;
    }

    public ExternalPlaceMatchStatus getMatchStatus() {
        return matchStatus;
    }

    public String getExternalName() {
        return externalName;
    }

    public BigDecimal getMatchScore() {
        return matchScore;
    }

    public BigDecimal getNameScore() {
        return nameScore;
    }

    public BigDecimal getAddressScore() {
        return addressScore;
    }

    public BigDecimal getDistanceScore() {
        return distanceScore;
    }

    public BigDecimal getCategoryScore() {
        return categoryScore;
    }

    public BigDecimal getRunnerUpScore() {
        return runnerUpScore;
    }

    public BigDecimal getScoreGap() {
        return scoreGap;
    }

    public BigDecimal getMatchDistanceMeters() {
        return matchDistanceMeters;
    }

    public String getSourceContentHash() {
        return sourceContentHash;
    }

    public ExternalPlaceAttemptStatus getLastAttemptStatus() {
        return lastAttemptStatus;
    }

    public Instant getLastMatchAttemptAt() {
        return lastMatchAttemptAt;
    }

    public Instant getNextRetryAt() {
        return nextRetryAt;
    }

    public Instant getLastSyncedAt() {
        return lastSyncedAt;
    }

    public Restaurant getRestaurant() {
        return restaurant;
    }
}
