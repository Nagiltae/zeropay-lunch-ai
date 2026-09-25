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
@Table(
        name = "restaurant_venue_associations",
        uniqueConstraints = {
                @UniqueConstraint(
                        name = "uk_restaurant_venue_association_restaurant",
                        columnNames = "restaurant_id"),
                @UniqueConstraint(
                        name = "uk_restaurant_venue_association_pair",
                        columnNames = {"restaurant_id", "venue_id"})
        })
public class RestaurantVenueAssociation {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "restaurant_id", nullable = false)
    private Restaurant restaurant;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "venue_id", nullable = false)
    private Venue venue;

    @Enumerated(EnumType.STRING)
    @Column(name = "association_status", nullable = false, length = 16)
    private RestaurantVenueAssociationStatus status;

    @Column(length = 1000)
    private String evidence;

    @Column(name = "verified_at")
    private Instant verifiedAt;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    protected RestaurantVenueAssociation() {
    }

    public static RestaurantVenueAssociation pending(
            Restaurant restaurant,
            Venue venue,
            String evidence,
            Instant now
    ) {
        RestaurantVenueAssociation association = new RestaurantVenueAssociation();
        association.restaurant = restaurant;
        association.venue = venue;
        association.status = RestaurantVenueAssociationStatus.PENDING;
        association.evidence = evidence;
        association.createdAt = now;
        association.updatedAt = now;
        return association;
    }

    public void decide(RestaurantVenueAssociationStatus decision, String decisionEvidence, Instant now) {
        if (decision != RestaurantVenueAssociationStatus.CONFIRMED
                && decision != RestaurantVenueAssociationStatus.REJECTED) {
            throw new IllegalArgumentException("Venue association decision must be CONFIRMED or REJECTED");
        }
        if (status != RestaurantVenueAssociationStatus.PENDING) {
            if (status == decision) {
                return;
            }
            throw new IllegalStateException("Only PENDING association can change decision");
        }
        status = decision;
        if (decisionEvidence != null && !decisionEvidence.isBlank()) {
            evidence = decisionEvidence;
        }
        verifiedAt = now;
        updatedAt = now;
    }

    public Long getRestaurantId() {
        return restaurant.getId();
    }

    public Long getVenueId() {
        return venue.getId();
    }

    public VenueStatus getVenueStatus() {
        return venue.getStatus();
    }

    public RestaurantVenueAssociationStatus getStatus() {
        return status;
    }

    public Long getId() {
        return id;
    }

    public String getEvidence() {
        return evidence;
    }

    public Instant getVerifiedAt() {
        return verifiedAt;
    }
}
