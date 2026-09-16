package com.zeropaylunch.backend.chat.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.zeropaylunch.backend.chat.application.ChatStreamService;
import com.zeropaylunch.backend.chat.application.ChatPersistenceService;
import com.zeropaylunch.backend.chat.application.ChatPersistenceService.PendingExchange;
import com.zeropaylunch.backend.restaurant.application.RecommendationItem;
import com.zeropaylunch.backend.restaurant.application.RestaurantRecommendationService;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

class ChatControllerTests {

    private ExecutorService executorService;
    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        executorService = Executors.newVirtualThreadPerTaskExecutor();
        ChatPersistenceService persistenceService = mock(ChatPersistenceService.class);
        RestaurantRecommendationService recommendationService =
                mock(RestaurantRecommendationService.class);
        when(persistenceService.startExchange(any(UUID.class), any(UUID.class), anyString()))
                .thenAnswer(invocation -> {
                    UUID conversationId = invocation.getArgument(0);
                    return new PendingExchange(
                            conversationId,
                            invocation.getArgument(1),
                            "gangnam",
                            UUID.randomUUID(),
                            UUID.randomUUID()
                    );
                });
        when(recommendationService.recommend(any(UUID.class), anyString(), anyString()))
                .thenReturn(java.util.List.of(new RecommendationItem(
                        1001L,
                        "강남 샘플 한식당",
                        "한식",
                        "제육볶음",
                        9000,
                        "서울특별시 강남구 강남대로 샘플 101",
                        "gangnam",
                        "강남역",
                        true,
                        true,
                        "선택한 강남역 기준 위치와 일치해요."
                )));
        ChatStreamService chatStreamService = new ChatStreamService(
                executorService,
                persistenceService,
                recommendationService
        );
        mockMvc = MockMvcBuilders
                .standaloneSetup(new ChatController(chatStreamService))
                .build();
    }

    @AfterEach
    void tearDown() {
        executorService.close();
    }

    @Test
    void streamsChatReplyAsServerSentEvents() throws Exception {
        UUID conversationId = UUID.randomUUID();
        UUID userId = UUID.randomUUID();
        MvcResult pendingResult = mockMvc.perform(post(
                        "/api/conversations/{conversationId}/messages",
                        conversationId
                )
                        .principal(new UsernamePasswordAuthenticationToken(userId, null))
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.TEXT_EVENT_STREAM)
                        .content("""
                                {"message":"따뜻한 국물 음식 추천해줘"}
                                """))
                .andExpect(request().asyncStarted())
                .andReturn();

        String responseBody = mockMvc.perform(asyncDispatch(pendingResult))
                .andExpect(status().isOk())
                .andReturn()
                .getResponse()
                .getContentAsString(StandardCharsets.UTF_8);

        assertThat(responseBody)
                .contains("event:accepted")
                .contains("event:progress")
                .contains("event:recommendations")
                .contains("event:assistant_delta")
                .contains("event:completed")
                .contains("강남 샘플 한식당")
                .contains("샘플 데이터");
    }
}
