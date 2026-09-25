package com.zeropaylunch.backend.restaurant.api;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class VenueAssociationAdminControllerTests {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void requiresAdminRoleForVenueCandidates() throws Exception {
        mockMvc.perform(get("/api/admin/venue-associations/candidates"))
                .andExpect(status().isUnauthorized());
        mockMvc.perform(get("/api/admin/venue-associations/candidates")
                        .with(user("regular-user").roles("USER")))
                .andExpect(status().isForbidden());
        mockMvc.perform(get("/api/admin/venue-associations/candidates")
                        .with(user("admin").roles("ADMIN")))
                .andExpect(status().isOk());
    }
}
