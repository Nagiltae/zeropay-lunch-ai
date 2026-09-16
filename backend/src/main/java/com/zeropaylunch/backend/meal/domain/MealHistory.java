package com.zeropaylunch.backend.meal.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "meal_history")
public class MealHistory {

    @Id
    private UUID id;

    @Column(name = "user_id", nullable = false)
    private UUID userId;

    @Column(name = "restaurant_id", nullable = false)
    private Long restaurantId;

    @Column(name = "source_message_id", nullable = false)
    private UUID sourceMessageId;

    @Column(name = "eaten_at", nullable = false)
    private Instant eatenAt;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected MealHistory() {
    }

    private MealHistory(
            UUID id,
            UUID userId,
            Long restaurantId,
            UUID sourceMessageId,
            Instant now
    ) {
        this.id = id;
        this.userId = userId;
        this.restaurantId = restaurantId;
        this.sourceMessageId = sourceMessageId;
        this.eatenAt = now;
        this.createdAt = now;
    }

    public static MealHistory create(
            UUID userId,
            Long restaurantId,
            UUID sourceMessageId,
            Instant now
    ) {
        return new MealHistory(UUID.randomUUID(), userId, restaurantId, sourceMessageId, now);
    }

    public UUID getId() {
        return id;
    }

    public UUID getUserId() {
        return userId;
    }

    public Long getRestaurantId() {
        return restaurantId;
    }

    public UUID getSourceMessageId() {
        return sourceMessageId;
    }

    public Instant getEatenAt() {
        return eatenAt;
    }
}
