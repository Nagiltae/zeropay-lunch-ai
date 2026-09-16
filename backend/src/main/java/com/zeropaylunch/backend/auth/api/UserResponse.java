package com.zeropaylunch.backend.auth.api;

import java.util.UUID;

public record UserResponse(
        UUID userId,
        String email,
        String displayName
) {
}
