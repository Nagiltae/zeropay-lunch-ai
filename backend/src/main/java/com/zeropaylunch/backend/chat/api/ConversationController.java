package com.zeropaylunch.backend.chat.api;

import com.zeropaylunch.backend.chat.application.ChatPersistenceService;
import com.zeropaylunch.backend.chat.application.ChatPersistenceService.ConversationHistory;
import com.zeropaylunch.backend.chat.domain.Conversation;
import jakarta.validation.Valid;
import java.time.Instant;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/conversations")
public class ConversationController {

    private final ChatPersistenceService chatPersistenceService;

    public ConversationController(ChatPersistenceService chatPersistenceService) {
        this.chatPersistenceService = chatPersistenceService;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public ConversationResponse create(
            @Valid @RequestBody CreateConversationRequest request,
            Authentication authentication
    ) {
        UUID userId = (UUID) authentication.getPrincipal();
        Conversation conversation = chatPersistenceService.createConversation(
                userId);
        return new ConversationResponse(
                conversation.getId(),
                conversation.isActive(),
                conversation.getCreatedAt()
        );
    }

    @PostMapping("/{conversationId}/deactivate")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void deactivate(@PathVariable UUID conversationId, Authentication authentication) {
        chatPersistenceService.deactivateConversation(
                conversationId,
                (UUID) authentication.getPrincipal()
        );
    }

    @GetMapping("/{conversationId}")
    public ConversationHistory history(@PathVariable UUID conversationId, Authentication authentication) {
        return chatPersistenceService.getHistory(
                conversationId,
                (UUID) authentication.getPrincipal()
        );
    }

    public record ConversationResponse(
            UUID conversationId,
            boolean active,
            Instant createdAt
    ) {
    }
}
