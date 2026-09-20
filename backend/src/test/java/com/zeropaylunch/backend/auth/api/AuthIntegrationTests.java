package com.zeropaylunch.backend.auth.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.zeropaylunch.backend.auth.domain.User;
import com.zeropaylunch.backend.auth.infrastructure.UserRepository;
import com.zeropaylunch.backend.chat.domain.Conversation;
import com.zeropaylunch.backend.chat.infrastructure.ConversationJpaRepository;
import jakarta.servlet.http.HttpSession;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.transaction.annotation.Transactional;

@SpringBootTest
@AutoConfigureMockMvc
@Transactional
class AuthIntegrationTests {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private ConversationJpaRepository conversationRepository;

    @Test
    void requiresAuthenticationForConversationApi() throws Exception {
        mockMvc.perform(post("/api/conversations")
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {}
                                """))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void returnsConflictForDuplicateEmail() throws Exception {
        signup("duplicate@example.com", "duplicate-user");

        signupRequest("duplicate@example.com", "duplicate-user")
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code").value("EMAIL_ALREADY_IN_USE"));
    }

    @Test
    void rotatesSessionAndRestrictsConversationToItsOwner() throws Exception {
        String ownerEmail = "owner@example.com";
        signup(ownerEmail, "owner");
        signup("other@example.com", "other");

        MockHttpSession existingSession = new MockHttpSession();
        String previousSessionId = existingSession.getId();
        MvcResult ownerLogin = login(ownerEmail, existingSession);
        HttpSession ownerSession = ownerLogin.getRequest().getSession(false);

        assertThat(ownerSession).isNotNull();
        assertThat(ownerSession.getId()).isNotEqualTo(previousSessionId);

        mockMvc.perform(get("/api/auth/me").session((MockHttpSession) ownerSession))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.email").value(ownerEmail));

        MvcResult created = mockMvc.perform(post("/api/conversations")
                        .session((MockHttpSession) ownerSession)
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {}
                                """))
                .andExpect(status().isCreated())
                .andReturn();
        UUID conversationId = UUID.fromString(extractJsonString(
                created.getResponse().getContentAsString(),
                "conversationId"
        ));
        User owner = userRepository.findByEmail(ownerEmail).orElseThrow();
        Conversation conversation = conversationRepository.findById(conversationId).orElseThrow();
        assertThat(conversation.getUserId()).isEqualTo(owner.getId());

        MockHttpSession otherSession = (MockHttpSession) login(
                "other@example.com",
                new MockHttpSession()
        ).getRequest().getSession(false);

        mockMvc.perform(get("/api/conversations/{conversationId}", conversationId)
                        .session(otherSession))
                .andExpect(status().isNotFound());
        mockMvc.perform(post("/api/conversations/{conversationId}/deactivate", conversationId)
                        .session(otherSession)
                        .with(csrf()))
                .andExpect(status().isNotFound());
    }

    private void signup(String email, String displayName) throws Exception {
        signupRequest(email, displayName).andExpect(status().isOk());
    }

    private org.springframework.test.web.servlet.ResultActions signupRequest(
            String email,
            String displayName
    ) throws Exception {
        return mockMvc.perform(post("/api/auth/signup")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"email":"%s","password":"password123","displayName":"%s"}
                        """.formatted(email, displayName)));
    }

    private MvcResult login(String email, MockHttpSession session) throws Exception {
        return mockMvc.perform(post("/api/auth/login")
                        .session(session)
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"email":"%s","password":"password123"}
                                """.formatted(email)))
                .andExpect(status().isOk())
                .andReturn();
    }

    private String extractJsonString(String json, String field) {
        String prefix = "\"" + field + "\":\"";
        int start = json.indexOf(prefix) + prefix.length();
        int end = json.indexOf('"', start);
        return json.substring(start, end);
    }
}
