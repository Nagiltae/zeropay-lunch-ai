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

@Entity
@Table(name = "venues")
public class Venue {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    @Column(nullable = false, length = 255)
    private String address;

    @Column(precision = 10, scale = 7)
    private BigDecimal latitude;

    @Column(precision = 10, scale = 7)
    private BigDecimal longitude;

    @Enumerated(EnumType.STRING)
    @Column(name = "venue_status", nullable = false, length = 16)
    private VenueStatus status;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    protected Venue() {
    }

    public static Venue create(
            String name,
            String address,
            BigDecimal latitude,
            BigDecimal longitude,
            Instant now
    ) {
        Venue venue = new Venue();
        venue.name = name;
        venue.address = address;
        venue.latitude = latitude;
        venue.longitude = longitude;
        venue.status = VenueStatus.ACTIVE;
        venue.createdAt = now;
        venue.updatedAt = now;
        return venue;
    }

    public Long getId() {
        return id;
    }

    public VenueStatus getStatus() {
        return status;
    }
}
