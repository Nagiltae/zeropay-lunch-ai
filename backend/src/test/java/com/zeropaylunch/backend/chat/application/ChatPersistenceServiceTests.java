package com.zeropaylunch.backend.chat.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.zeropaylunch.backend.chat.domain.Conversation;
import com.zeropaylunch.backend.chat.infrastructure.ConversationJpaRepository;
import com.zeropaylunch.backend.auth.domain.User;
import com.zeropaylunch.backend.auth.infrastructure.UserRepository;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

import java.util.UUID;

@SpringBootTest
@Transactional
class ChatPersistenceServiceTests {

    @Autowired
    private ChatPersistenceService chatPersistenceService;

    @Autowired
    private ConversationJpaRepository conversationRepository;

    @Autowired
    private UserRepository userRepository;

    @Test
    void deactivatesConversationInsteadOfDeletingIt() {
        UUID userId = createUser();
        Conversation conversation = chatPersistenceService.createConversation(userId);

        chatPersistenceService.deactivateConversation(conversation.getId(), userId);

        Conversation saved = conversationRepository.findById(conversation.getId()).orElseThrow();
        assertThat(saved.isActive()).isFalse();
    }

    @Test
    void returnsEmptyHistoryForNewConversation() {
        UUID userId = createUser();
        Conversation conversation = chatPersistenceService.createConversation(userId);

        var history = chatPersistenceService.getHistory(conversation.getId(), userId);

        assertThat(history.active()).isTrue();
        assertThat(history.messages()).isEmpty();
    }

    @Test
    void rejectsConversationAccessByAnotherUser() {
        UUID ownerId = createUser();
        Conversation conversation = chatPersistenceService.createConversation(ownerId);

        assertThatThrownBy(() -> chatPersistenceService.getHistory(
                conversation.getId(),
                UUID.randomUUID()
        ))
                .isInstanceOf(ResponseStatusException.class)
                .hasMessageContaining("404 NOT_FOUND");
    }

    private UUID createUser() {
        String unique = UUID.randomUUID().toString();
        User user = User.create(unique + "@example.com", "테스트 사용자", Instant.now());
        return userRepository.save(user).getId();
    }
}
