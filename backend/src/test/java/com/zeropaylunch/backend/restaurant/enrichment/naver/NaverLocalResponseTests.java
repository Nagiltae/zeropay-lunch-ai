package com.zeropaylunch.backend.restaurant.enrichment.naver;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

class NaverLocalResponseTests {

    private final ObjectMapper objectMapper = new ObjectMapper();

    @Test
    void parsesNaverLocalJsonAndWgs84Coordinates() throws Exception {
        String json = """
                {
                  "total": 1,
                  "start": 1,
                  "display": 1,
                  "items": [{
                    "title": "<b>토브</b>",
                    "link": "https://example.test/tove",
                    "category": "음식점>양식",
                    "description": "",
                    "telephone": "",
                    "address": "서울 강남구 논현동 1",
                    "roadAddress": "서울 강남구 학동로 1",
                    "mapx": "127.0300000",
                    "mapy": "37.5000000"
                  }]
                }
                """;

        NaverLocalResponse response = objectMapper.readValue(json, NaverLocalResponse.class);

        assertThat(response.results()).hasSize(1);
        assertThat(response.results().getFirst().title()).isEqualTo("<b>토브</b>");
        assertThat(response.results().getFirst().mapx()).isEqualTo("127.0300000");
        assertThat(response.results().getFirst().mapy()).isEqualTo("37.5000000");
    }

    @Test
    void acceptsNullableFieldsAndMissingItems() throws Exception {
        NaverLocalResponse nullable = objectMapper.readValue(
                """
                {"lastBuildDate":null,"total":1,"start":1,"display":1,
                 "items":[{"title":"식당","link":null,"category":null,
                 "description":null,"telephone":null,"address":null,
                 "roadAddress":null,"mapx":null,"mapy":null}]}
                """,
                NaverLocalResponse.class);
        NaverLocalResponse empty = objectMapper.readValue(
                "{\"lastBuildDate\":null,\"total\":0,\"start\":1,\"display\":0,\"items\":null}",
                NaverLocalResponse.class);

        assertThat(nullable.results().getFirst().roadAddress()).isNull();
        assertThat(nullable.results().getFirst().mapx()).isNull();
        assertThat(empty.results()).isEmpty();
    }
}
