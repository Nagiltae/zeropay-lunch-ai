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
@Table(name = "restaurants")
public class Restaurant {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 40)
    private RestaurantCategory category;

    @Column(name = "representative_menu", nullable = false, length = 120)
    private String representativeMenu;

    @Column(name = "average_price", nullable = false)
    private int averagePrice;

    @Column(nullable = false)
    private String address;

    @Column(name = "location_id", nullable = false, length = 32)
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

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    protected Restaurant() {
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

    public int getAveragePrice() {
        return averagePrice;
    }

    public String getAddress() {
        return address;
    }

    public String getLocationId() {
        return locationId;
    }

    public boolean isZeroPayAvailable() {
        return zeroPayAvailable;
    }

    public boolean isSampleData() {
        return sampleData;
    }
}
