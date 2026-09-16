package com.zeropaylunch.backend.chat.infrastructure;

import com.zeropaylunch.backend.chat.domain.MessageRecommendation;
import java.util.Collection;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface MessageRecommendationJpaRepository
        extends JpaRepository<MessageRecommendation, Long> {

    List<MessageRecommendation> findByMessageIdInOrderByMessageIdAscRankAsc(
            Collection<UUID> messageIds
    );

    @Query("""
            SELECT CASE WHEN COUNT(recommendation) > 0 THEN true ELSE false END
            FROM MessageRecommendation recommendation, ChatMessage message, Conversation conversation
            WHERE recommendation.messageId = :messageId
              AND recommendation.restaurantId = :restaurantId
              AND message.id = recommendation.messageId
              AND conversation.id = message.conversationId
              AND conversation.userId = :userId
            """)
    boolean existsOwnedRecommendation(
            @Param("userId") UUID userId,
            @Param("messageId") UUID messageId,
            @Param("restaurantId") Long restaurantId
    );
}
