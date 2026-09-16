package com.zeropaylunch.backend.chat.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.zeropaylunch.backend.chat.application.ChatStreamService;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

class ChatControllerTests {

    private ExecutorService executorService;
    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        executorService = Executors.newVirtualThreadPerTaskExecutor();
        ChatStreamService chatStreamService = new ChatStreamService(executorService);
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
        MvcResult pendingResult = mockMvc.perform(post(
                        "/api/conversations/{conversationId}/messages",
                        conversationId
                )
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
                .contains("event:assistant_delta")
                .contains("event:completed")
                .contains("말씀하신 ‘따뜻한 국물")
                .contains("음식 추천해줘’ 요청");
    }
}
