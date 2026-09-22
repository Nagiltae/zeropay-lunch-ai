/**
 * 인증된 사용자의 대화 메시지 요청을 SSE 스트림 서비스로 전달하는 Controller.
 * 대화·메시지 저장과 추천 생성의 세부 책임은 ChatStreamService가 가진다.
 */
package com.zeropaylunch.backend.chat.api;

import com.zeropaylunch.backend.chat.application.ChatStreamService;
import jakarta.validation.Valid;
import java.util.UUID;
import org.springframework.http.MediaType;
import org.springframework.security.core.Authentication;
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
            @Valid @RequestBody ChatMessageRequest request,
            Authentication authentication
    ) {
        return chatStreamService.streamReply(
                conversationId,
                (UUID) authentication.getPrincipal(),
                request.message().trim()
        );
    }
}
