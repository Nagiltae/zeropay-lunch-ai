package com.zeropaylunch.backend.restaurant.enrichment.naver;

class NaverLocalApiException extends RuntimeException {

    NaverLocalApiException(String message, Throwable cause) {
        super(message, cause);
    }

    NaverLocalApiException(String message) {
        super(message);
    }
}
