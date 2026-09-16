package com.zeropaylunch.backend.chat.infrastructure;

import com.zeropaylunch.backend.chat.domain.MessageRecommendation;
import java.util.Collection;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface MessageRecommendationJpaRepository
        extends JpaRepository<MessageRecommendation, Long> {

    List<MessageRecommendation> findByMessageIdInOrderByMessageIdAscRankAsc(
            Collection<UUID> messageIds
    );
}
