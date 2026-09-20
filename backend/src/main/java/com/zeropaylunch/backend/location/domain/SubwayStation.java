package com.zeropaylunch.backend.location.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.Instant;

@Entity
@Table(name = "subway_stations")
public class SubwayStation {

    @Id
    @Column(length = 32)
    private String id;

    @Column(nullable = false)
    private String name;

    @Column(length = 100)
    private String line;

    @Column(nullable = false, precision = 10, scale = 7)
    private BigDecimal latitude;

    @Column(nullable = false, precision = 10, scale = 7)
    private BigDecimal longitude;

    @Column(nullable = false)
    private boolean active;

    @Column
    private String source;

    @Column(name = "source_updated_at")
    private Instant sourceUpdatedAt;

    protected SubwayStation() {
    }

    public SubwayStation(String id, String name, String line, BigDecimal latitude, BigDecimal longitude, boolean active, String source) {
        this.id = id;
        this.name = name;
        this.line = line;
        this.latitude = latitude;
        this.longitude = longitude;
        this.active = active;
        this.source = source;
    }

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getLine() {
        return line;
    }

    public BigDecimal getLatitude() {
        return latitude;
    }

    public BigDecimal getLongitude() {
        return longitude;
    }

    public boolean isActive() {
        return active;
    }

    public String getSource() {
        return source;
    }

    public Instant getSourceUpdatedAt() {
        return sourceUpdatedAt;
    }
}
