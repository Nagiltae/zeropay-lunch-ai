package com.zeropaylunch.backend.chat.api;

import jakarta.validation.constraints.NotBlank;

public record CreateConversationRequest(
        @NotBlank(message = "기준 위치를 선택해 주세요.")
        String locationId
) {
}
