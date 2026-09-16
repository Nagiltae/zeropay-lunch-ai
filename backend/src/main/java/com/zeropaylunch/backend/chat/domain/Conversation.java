package com.zeropaylunch.backend.chat.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "conversations")
public class Conversation {

    @Id
    private UUID id;

    @Column(name = "location_id", nullable = false, length = 32)
    private String locationId;

    @Column(name = "user_id")
    private UUID userId;

    @Column(nullable = false)
    private boolean active;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    @Column(name = "deactivated_at")
    private Instant deactivatedAt;

    protected Conversation() {
    }

    private Conversation(UUID id, String locationId, UUID userId, Instant now) {
        this.id = id;
        this.locationId = locationId;
        this.userId = userId;
        this.active = true;
        this.createdAt = now;
        this.updatedAt = now;
    }

    public static Conversation create(String locationId, UUID userId, Instant now) {
        return new Conversation(UUID.randomUUID(), locationId, userId, now);
    }

    public void deactivate(Instant now) {
        if (!active) {
            return;
        }
        active = false;
        deactivatedAt = now;
        updatedAt = now;
    }

    public UUID getId() {
        return id;
    }

    public String getLocationId() {
        return locationId;
    }

    public boolean isActive() {
        return active;
    }

    public UUID getUserId() {
        return userId;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
