package com.zeropaylunch.backend.chat.application;

import static org.assertj.core.api.Assertions.assertThat;

import com.zeropaylunch.backend.chat.domain.Conversation;
import com.zeropaylunch.backend.chat.infrastructure.ConversationJpaRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.annotation.Transactional;

@SpringBootTest
@Transactional
class ChatPersistenceServiceTests {

    @Autowired
    private ChatPersistenceService chatPersistenceService;

    @Autowired
    private ConversationJpaRepository conversationRepository;

    @Test
    void deactivatesConversationInsteadOfDeletingIt() {
        Conversation conversation = chatPersistenceService.createConversation("gangnam");

        chatPersistenceService.deactivateConversation(conversation.getId());

        Conversation saved = conversationRepository.findById(conversation.getId()).orElseThrow();
        assertThat(saved.isActive()).isFalse();
        assertThat(conversationRepository.findByIdAndActiveTrue(conversation.getId())).isEmpty();
    }

    @Test
    void returnsEmptyHistoryForNewConversation() {
        Conversation conversation = chatPersistenceService.createConversation("gangnam");

        var history = chatPersistenceService.getHistory(conversation.getId());

        assertThat(history.active()).isTrue();
        assertThat(history.messages()).isEmpty();
    }
}
