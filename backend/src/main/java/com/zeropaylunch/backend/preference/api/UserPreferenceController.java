package com.zeropaylunch.backend.preference.api;

import com.zeropaylunch.backend.preference.application.UserPreferenceService;
import jakarta.validation.Valid;
import java.util.UUID;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/preferences/me")
public class UserPreferenceController {

    private final UserPreferenceService preferenceService;

    public UserPreferenceController(UserPreferenceService preferenceService) {
        this.preferenceService = preferenceService;
    }

    @GetMapping
    public UserPreferenceResponse get(Authentication authentication) {
        return UserPreferenceResponse.from(
                preferenceService.get((UUID) authentication.getPrincipal())
        );
    }

    @PutMapping
    public UserPreferenceResponse update(
            @Valid @RequestBody UpdatePreferenceRequest request,
            Authentication authentication
    ) {
        return UserPreferenceResponse.from(preferenceService.update(
                (UUID) authentication.getPrincipal(),
                request.defaultBudget(),
                request.spiceLevel(),
                request.preferredCategories(),
                request.dislikedCategories(),
                request.allergies()
        ));
    }
}
