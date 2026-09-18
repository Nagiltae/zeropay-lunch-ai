package com.zeropaylunch.backend.restaurant.enrichment.naver;

import java.net.URI;
import java.time.Duration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.util.UriComponentsBuilder;

@Component
class NaverLocalHttpClient implements NaverLocalSearchClient {

    private static final String CLIENT_ID_HEADER = "X-NCP-APIGW-API-KEY-ID";
    private static final String CLIENT_SECRET_HEADER = "X-NCP-APIGW-API-KEY";

    private final RestClient restClient;
    private final NaverLocalProperties properties;
    private long lastRequestNanos;

    NaverLocalHttpClient(RestClient naverLocalRestClient, NaverLocalProperties properties) {
        this.restClient = naverLocalRestClient;
        this.properties = properties;
    }

    @Override
    public NaverLocalResponse search(String query) {
        validateCredentials();
        URI uri = UriComponentsBuilder.fromUri(properties.baseUrl())
                .queryParam("query", query)
                .queryParam("display", properties.display())
                .queryParam("start", 1)
                .queryParam("sort", "random")
                .queryParam("format", "json")
                .build()
                .encode()
                .toUri();

        RestClientException lastFailure = null;
        for (int attempt = 1; attempt <= properties.maxAttempts(); attempt++) {
            throttle();
            try {
                NaverLocalResponse response = restClient.get()
                        .uri(uri)
                        .header(CLIENT_ID_HEADER, properties.clientId())
                        .header(CLIENT_SECRET_HEADER, properties.clientSecret())
                        .header(HttpHeaders.ACCEPT, MediaType.APPLICATION_JSON_VALUE)
                        .retrieve()
                        .body(NaverLocalResponse.class);
                if (response == null) {
                    throw new NaverLocalApiException("NAVER Local returned an empty response");
                }
                return response;
            } catch (RestClientResponseException exception) {
                if (exception.getStatusCode().value() == 401
                        || exception.getStatusCode().value() == 403) {
                    throw new NaverLocalAuthenticationException(
                            "NAVER Local authentication failed; check configured credentials",
                            exception);
                }
                lastFailure = exception;
                if (!isRetryable(exception) || attempt == properties.maxAttempts()) {
                    break;
                }
                pause(properties.retryBackoff());
            } catch (RestClientException exception) {
                lastFailure = exception;
                if (attempt == properties.maxAttempts()) {
                    break;
                }
                pause(properties.retryBackoff());
            }
        }
        throw new NaverLocalApiException("NAVER Local request failed for query: " + query,
                lastFailure);
    }

    private void validateCredentials() {
        if (!StringUtils.hasText(properties.clientId())
                || !StringUtils.hasText(properties.clientSecret())) {
            throw new NaverLocalAuthenticationException(
                    "NAVER Local credentials are not configured", null);
        }
    }

    private boolean isRetryable(RestClientResponseException exception) {
        int status = exception.getStatusCode().value();
        return status == 429 || status >= 500;
    }

    private synchronized void throttle() {
        long intervalNanos = properties.requestInterval().toNanos();
        long elapsed = System.nanoTime() - lastRequestNanos;
        if (lastRequestNanos != 0 && elapsed < intervalNanos) {
            pause(Duration.ofNanos(intervalNanos - elapsed));
        }
        lastRequestNanos = System.nanoTime();
    }

    private void pause(Duration duration) {
        try {
            Thread.sleep(duration);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new NaverLocalApiException("NAVER Local request was interrupted", exception);
        }
    }
}
