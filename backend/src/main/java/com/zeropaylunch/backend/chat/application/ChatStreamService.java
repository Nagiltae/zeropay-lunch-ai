package com.zeropaylunch.backend.chat.application;

import com.zeropaylunch.backend.chat.application.ChatPersistenceService.PendingExchange;
import com.zeropaylunch.backend.restaurant.application.RecommendationItem;
import com.zeropaylunch.backend.restaurant.application.RestaurantRecommendationService;
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
    private final ChatPersistenceService chatPersistenceService;
    private final RestaurantRecommendationService recommendationService;

    public ChatStreamService(
            ExecutorService chatExecutor,
            ChatPersistenceService chatPersistenceService,
            RestaurantRecommendationService recommendationService
    ) {
        this.chatExecutor = chatExecutor;
        this.chatPersistenceService = chatPersistenceService;
        this.recommendationService = recommendationService;
    }

    public SseEmitter streamReply(UUID conversationId, UUID userId, String userMessage) {
        PendingExchange exchange = chatPersistenceService.startExchange(
                conversationId,
                userId,
                userMessage
        );
        SseEmitter emitter = new SseEmitter(STREAM_TIMEOUT_MILLIS);
        chatExecutor.submit(() -> emitReply(emitter, exchange, userMessage));
        return emitter;
    }

    private void emitReply(SseEmitter emitter, PendingExchange exchange, String userMessage) {
        try {
            send(emitter, "accepted", new AcceptedEvent(
                    exchange.conversationId(),
                    exchange.userMessageId(),
                    exchange.assistantMessageId()
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

            List<RecommendationItem> recommendations = recommendationService.recommend(
                    userMessage,
                    exchange.locationId()
            );
            String reply = createReply(recommendations);
            chatPersistenceService.completeExchange(
                    exchange.assistantMessageId(),
                    reply,
                    recommendations
            );
            send(emitter, "recommendations", new RecommendationsEvent(recommendations));

            for (String chunk : splitIntoChunks(reply)) {
                send(emitter, "assistant_delta", new AssistantDeltaEvent(chunk));
                pause();
            }

            send(emitter, "completed", new CompletedEvent(exchange.assistantMessageId()));
            emitter.complete();
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            failAndEmitError(
                    emitter, exchange.assistantMessageId(),
                    "STREAM_INTERRUPTED", "답변 생성이 중단되었습니다."
            );
        } catch (IOException exception) {
            log.debug("SSE client disconnected from conversation {}", exchange.conversationId());
            emitter.completeWithError(exception);
        } catch (RuntimeException exception) {
            log.error(
                    "Unexpected chat streaming error for conversation {}",
                    exchange.conversationId(),
                    exception
            );
            failAndEmitError(
                    emitter, exchange.assistantMessageId(),
                    "STREAM_FAILED", "답변을 생성하지 못했습니다."
            );
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

    private void failAndEmitError(
            SseEmitter emitter,
            UUID assistantMessageId,
            String code,
            String message
    ) {
        try {
            chatPersistenceService.failExchange(assistantMessageId, message);
        } catch (RuntimeException persistenceException) {
            log.error("Failed to persist assistant message failure", persistenceException);
        }
        emitError(emitter, code, message);
    }

    private void pause() throws InterruptedException {
        Thread.sleep(EVENT_DELAY_MILLIS);
    }

    private String createReply(List<RecommendationItem> recommendations) {
        if (recommendations.isEmpty()) {
            return "현재 영업 중이면서 요청 조건에 맞는 샘플 음식점을 찾지 못했어요. "
                    + "다른 메뉴나 예산으로 다시 요청해 주세요.";
        }
        return "현재 영업시간과 요청 조건을 확인해 " + recommendations.size()
                + "곳을 골랐어요. 지금은 개발용 샘플 데이터로 보여드리고 있어요.";
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

    private record RecommendationsEvent(List<RecommendationItem> items) {
    }

    private record CompletedEvent(UUID assistantMessageId) {
    }

    private record ErrorEvent(String code, String message) {
    }
}
