package com.zeropaylunch.backend.restaurant.domain;

public enum NaverVerificationReason {
    NO_SEARCH_RESULT,
    NON_FOOD,
    OUT_OF_SCOPE,
    NO_MATCH,
    SEMANTIC_UNCERTAIN,
    PLACE_ID_MISSING,
    DETAIL_LOAD_FAILED,
    QWEN_TIMEOUT,
    RATE_LIMITED,
    PLACE_ID_CONFLICT,
    SOURCE_CHANGED,
    VERIFIED
}
