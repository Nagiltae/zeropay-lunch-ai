package com.zeropaylunch.backend.chat.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "chat_messages")
public class ChatMessage {

    @Id
    private UUID id;

    @Column(name = "conversation_id", nullable = false)
    private UUID conversationId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 16)
    private MessageRole role;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 16)
    private MessageStatus status;

    @Column(nullable = false, columnDefinition = "TEXT")
    private String content;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "completed_at")
    private Instant completedAt;

    protected ChatMessage() {
    }

    private ChatMessage(
            UUID id,
            UUID conversationId,
            MessageRole role,
            MessageStatus status,
            String content,
            Instant createdAt
    ) {
        this.id = id;
        this.conversationId = conversationId;
        this.role = role;
        this.status = status;
        this.content = content;
        this.createdAt = createdAt;
    }

    public static ChatMessage completedUser(UUID conversationId, String content, Instant now) {
        ChatMessage message = new ChatMessage(
                UUID.randomUUID(), conversationId, MessageRole.USER,
                MessageStatus.COMPLETED, content, now
        );
        message.completedAt = now;
        return message;
    }

    public static ChatMessage pendingAssistant(UUID conversationId, Instant now) {
        return new ChatMessage(
                UUID.randomUUID(), conversationId, MessageRole.ASSISTANT,
                MessageStatus.PENDING, "", now
        );
    }

    public void complete(String content, Instant now) {
        this.content = content;
        this.status = MessageStatus.COMPLETED;
        this.completedAt = now;
    }

    public void fail(String content, Instant now) {
        this.content = content;
        this.status = MessageStatus.FAILED;
        this.completedAt = now;
    }

    public UUID getId() {
        return id;
    }

    public UUID getConversationId() {
        return conversationId;
    }

    public MessageRole getRole() {
        return role;
    }

    public MessageStatus getStatus() {
        return status;
    }

    public String getContent() {
        return content;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
