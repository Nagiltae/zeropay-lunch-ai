package com.zeropaylunch.backend.chat.application;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@Service
public class ChatStreamService {

    private static final Logger log = LoggerFactory.getLogger(ChatStreamService.class);
    private static final long STREAM_TIMEOUT_MILLIS = 60_000L;
    private static final long EVENT_DELAY_MILLIS = 120L;
    private static final int CHUNK_SIZE = 12;

    private final ExecutorService chatExecutor;

    public ChatStreamService(ExecutorService chatExecutor) {
        this.chatExecutor = chatExecutor;
    }

    public SseEmitter streamReply(UUID conversationId, String userMessage) {
        SseEmitter emitter = new SseEmitter(STREAM_TIMEOUT_MILLIS);
        chatExecutor.submit(() -> emitReply(emitter, conversationId, userMessage));
        return emitter;
    }

    private void emitReply(SseEmitter emitter, UUID conversationId, String userMessage) {
        UUID userMessageId = UUID.randomUUID();
        UUID assistantMessageId = UUID.randomUUID();

        try {
            send(emitter, "accepted", new AcceptedEvent(
                    conversationId,
                    userMessageId,
                    assistantMessageId
            ));
            send(emitter, "progress", new ProgressEvent(
                    "ANALYZING",
                    "요청을 확인하고 있어요."
            ));
            pause();
            send(emitter, "progress", new ProgressEvent(
                    "PREPARING",
                    "답변을 준비하고 있어요."
            ));
            pause();

            for (String chunk : splitIntoChunks(createPlaceholderReply(userMessage))) {
                send(emitter, "assistant_delta", new AssistantDeltaEvent(chunk));
                pause();
            }

            send(emitter, "completed", new CompletedEvent(assistantMessageId));
            emitter.complete();
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            emitError(emitter, "STREAM_INTERRUPTED", "답변 생성이 중단되었습니다.");
        } catch (IOException exception) {
            log.debug("SSE client disconnected from conversation {}", conversationId);
            emitter.completeWithError(exception);
        } catch (RuntimeException exception) {
            log.error("Unexpected chat streaming error for conversation {}", conversationId, exception);
            emitError(emitter, "STREAM_FAILED", "답변을 생성하지 못했습니다.");
        }
    }

    private void send(SseEmitter emitter, String eventName, Object data) throws IOException {
        emitter.send(SseEmitter.event()
                .name(eventName)
                .data(data));
    }

    private void emitError(SseEmitter emitter, String code, String message) {
        try {
            send(emitter, "error", new ErrorEvent(code, message));
            emitter.complete();
        } catch (IOException exception) {
            emitter.completeWithError(exception);
        }
    }

    private void pause() throws InterruptedException {
        Thread.sleep(EVENT_DELAY_MILLIS);
    }

    private String createPlaceholderReply(String userMessage) {
        return "말씀하신 ‘" + userMessage + "’ 요청을 받았어요. "
                + "현재는 React와 Spring Boot 사이의 실시간 대화 연결을 확인하는 단계예요. "
                + "다음 단계에서 음식점 검색과 AI 추천을 연결할게요.";
    }

    private List<String> splitIntoChunks(String text) {
        List<String> chunks = new ArrayList<>();
        int start = 0;
        while (start < text.length()) {
            int codePointCount = Math.min(CHUNK_SIZE, text.codePointCount(start, text.length()));
            int end = text.offsetByCodePoints(start, codePointCount);
            chunks.add(text.substring(start, end));
            start = end;
        }
        return chunks;
    }

    private record AcceptedEvent(
            UUID conversationId,
            UUID userMessageId,
            UUID assistantMessageId
    ) {
    }

    private record ProgressEvent(String stage, String message) {
    }

    private record AssistantDeltaEvent(String text) {
    }

    private record CompletedEvent(UUID assistantMessageId) {
    }

    private record ErrorEvent(String code, String message) {
    }
}
