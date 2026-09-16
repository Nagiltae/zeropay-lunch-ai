package com.zeropaylunch.backend.chat.api;

import com.zeropaylunch.backend.chat.application.ChatStreamService;
import jakarta.validation.Valid;
import java.util.UUID;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@RestController
@RequestMapping("/api/conversations")
public class ChatController {

    private final ChatStreamService chatStreamService;

    public ChatController(ChatStreamService chatStreamService) {
        this.chatStreamService = chatStreamService;
    }

    @PostMapping(
            path = "/{conversationId}/messages",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    public SseEmitter sendMessage(
            @PathVariable UUID conversationId,
            @Valid @RequestBody ChatMessageRequest request
    ) {
        return chatStreamService.streamReply(conversationId, request.message().trim());
    }
}
