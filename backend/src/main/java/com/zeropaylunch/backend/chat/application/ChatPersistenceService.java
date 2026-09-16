package com.zeropaylunch.backend.chat.application;

import com.zeropaylunch.backend.chat.domain.ChatMessage;
import com.zeropaylunch.backend.chat.domain.Conversation;
import com.zeropaylunch.backend.chat.domain.MessageRecommendation;
import com.zeropaylunch.backend.chat.infrastructure.ChatMessageJpaRepository;
import com.zeropaylunch.backend.chat.infrastructure.ConversationJpaRepository;
import com.zeropaylunch.backend.chat.infrastructure.MessageRecommendationJpaRepository;
import com.zeropaylunch.backend.location.domain.GangnamLocation;
import com.zeropaylunch.backend.restaurant.application.RecommendationItem;
import com.zeropaylunch.backend.restaurant.domain.Restaurant;
import com.zeropaylunch.backend.restaurant.infrastructure.RestaurantJpaRepository;
import java.time.Clock;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class ChatPersistenceService {

    private final ConversationJpaRepository conversationRepository;
    private final ChatMessageJpaRepository messageRepository;
    private final MessageRecommendationJpaRepository messageRecommendationRepository;
    private final RestaurantJpaRepository restaurantRepository;
    private final Clock clock;

    public ChatPersistenceService(
            ConversationJpaRepository conversationRepository,
            ChatMessageJpaRepository messageRepository,
            MessageRecommendationJpaRepository messageRecommendationRepository,
            RestaurantJpaRepository restaurantRepository,
            Clock clock
    ) {
        this.conversationRepository = conversationRepository;
        this.messageRepository = messageRepository;
        this.messageRecommendationRepository = messageRecommendationRepository;
        this.restaurantRepository = restaurantRepository;
        this.clock = clock;
    }

    @Transactional
    public Conversation createConversation(String locationId) {
        GangnamLocation location;
        try {
            location = GangnamLocation.fromId(locationId);
        } catch (IllegalArgumentException exception) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, exception.getMessage());
        }
        return conversationRepository.save(Conversation.create(location.id(), clock.instant()));
    }

    @Transactional
    public void deactivateConversation(UUID conversationId) {
        Conversation conversation = findConversation(conversationId);
        conversation.deactivate(clock.instant());
    }

    @Transactional
    public PendingExchange startExchange(UUID conversationId, String userContent) {
        Conversation conversation = conversationRepository.findByIdAndActiveTrue(conversationId)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.CONFLICT,
                        "활성 상태인 대화를 찾을 수 없습니다. 새 대화를 시작해 주세요."
                ));
        Instant now = clock.instant();
        ChatMessage userMessage = messageRepository.save(
                ChatMessage.completedUser(conversationId, userContent, now)
        );
        ChatMessage assistantMessage = messageRepository.save(
                ChatMessage.pendingAssistant(conversationId, now)
        );
        return new PendingExchange(
                conversation.getId(),
                conversation.getLocationId(),
                userMessage.getId(),
                assistantMessage.getId()
        );
    }

    @Transactional
    public void completeExchange(
            UUID assistantMessageId,
            String content,
            List<RecommendationItem> recommendations
    ) {
        ChatMessage assistantMessage = findMessage(assistantMessageId);
        assistantMessage.complete(content, clock.instant());
        List<MessageRecommendation> savedRecommendations = new ArrayList<>();
        for (int index = 0; index < recommendations.size(); index++) {
            RecommendationItem item = recommendations.get(index);
            savedRecommendations.add(new MessageRecommendation(
                    assistantMessageId,
                    item.restaurantId(),
                    index + 1,
                    item.reason()
            ));
        }
        messageRecommendationRepository.saveAll(savedRecommendations);
    }

    @Transactional
    public void failExchange(UUID assistantMessageId, String errorMessage) {
        findMessage(assistantMessageId).fail(errorMessage, clock.instant());
    }

    @Transactional(readOnly = true)
    public ConversationHistory getHistory(UUID conversationId) {
        Conversation conversation = findConversation(conversationId);
        List<ChatMessage> messages = messageRepository
                .findByConversationIdOrderByCreatedAtAsc(conversationId);
        List<UUID> messageIds = messages.stream().map(ChatMessage::getId).toList();
        Map<UUID, List<MessageRecommendation>> recommendationsByMessage =
                messageRecommendationRepository
                        .findByMessageIdInOrderByMessageIdAscRankAsc(messageIds)
                        .stream()
                        .collect(Collectors.groupingBy(
                                MessageRecommendation::getMessageId,
                                HashMap::new,
                                Collectors.toList()
                        ));
        List<Long> restaurantIds = recommendationsByMessage.values().stream()
                .flatMap(List::stream)
                .map(MessageRecommendation::getRestaurantId)
                .distinct()
                .toList();
        Map<Long, Restaurant> restaurants = restaurantRepository.findAllById(restaurantIds).stream()
                .collect(Collectors.toMap(Restaurant::getId, Function.identity()));

        List<HistoryMessage> historyMessages = messages.stream()
                .map(message -> new HistoryMessage(
                        message.getId(),
                        message.getRole().name(),
                        message.getStatus().name(),
                        message.getContent(),
                        message.getCreatedAt(),
                        recommendationsByMessage
                                .getOrDefault(message.getId(), List.of())
                                .stream()
                                .sorted(Comparator.comparingInt(MessageRecommendation::getRank))
                                .map(saved -> toRecommendation(saved, restaurants.get(
                                        saved.getRestaurantId()
                                )))
                                .toList()
                ))
                .toList();

        return new ConversationHistory(
                conversation.getId(),
                conversation.getLocationId(),
                conversation.isActive(),
                conversation.getCreatedAt(),
                historyMessages
        );
    }

    private RecommendationItem toRecommendation(
            MessageRecommendation saved,
            Restaurant restaurant
    ) {
        if (restaurant == null) {
            throw new IllegalStateException("추천 음식점 정보를 찾을 수 없습니다.");
        }
        GangnamLocation location = GangnamLocation.fromId(restaurant.getLocationId());
        return new RecommendationItem(
                restaurant.getId(), restaurant.getName(), restaurant.getCategory().label(),
                restaurant.getRepresentativeMenu(), restaurant.getAveragePrice(),
                restaurant.getAddress(), restaurant.getLocationId(), location.label(),
                restaurant.isZeroPayAvailable(), restaurant.isSampleData(), saved.getReason()
        );
    }

    private Conversation findConversation(UUID conversationId) {
        return conversationRepository.findById(conversationId)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "대화를 찾을 수 없습니다."
                ));
    }

    private ChatMessage findMessage(UUID messageId) {
        return messageRepository.findById(messageId)
                .orElseThrow(() -> new IllegalStateException("메시지를 찾을 수 없습니다."));
    }

    public record PendingExchange(
            UUID conversationId,
            String locationId,
            UUID userMessageId,
            UUID assistantMessageId
    ) {
    }

    public record ConversationHistory(
            UUID conversationId,
            String locationId,
            boolean active,
            Instant createdAt,
            List<HistoryMessage> messages
    ) {
    }

    public record HistoryMessage(
            UUID messageId,
            String role,
            String status,
            String content,
            Instant createdAt,
            List<RecommendationItem> recommendations
    ) {
    }
}
