package com.zeropaylunch.backend.chat.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.util.UUID;

@Entity
@Table(name = "message_recommendations")
public class MessageRecommendation {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "message_id", nullable = false)
    private UUID messageId;

    @Column(name = "restaurant_id", nullable = false)
    private Long restaurantId;

    @Column(name = "recommendation_rank", nullable = false)
    private int rank;

    @Column(nullable = false, length = 500)
    private String reason;

    protected MessageRecommendation() {
    }

    public MessageRecommendation(UUID messageId, Long restaurantId, int rank, String reason) {
        this.messageId = messageId;
        this.restaurantId = restaurantId;
        this.rank = rank;
        this.reason = reason;
    }

    public UUID getMessageId() {
        return messageId;
    }

    public Long getRestaurantId() {
        return restaurantId;
    }

    public int getRank() {
        return rank;
    }

    public String getReason() {
        return reason;
    }
}
