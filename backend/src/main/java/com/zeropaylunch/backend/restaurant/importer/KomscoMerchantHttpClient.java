package com.zeropaylunch.backend.restaurant.importer;

import java.net.URI;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.util.UriComponentsBuilder;

@Component
class KomscoMerchantHttpClient implements KomscoPageClient {

    private final RestClient restClient;
    private final KomscoImportProperties properties;

    KomscoMerchantHttpClient(RestClient komscoRestClient, KomscoImportProperties properties) {
        this.restClient = komscoRestClient;
        this.properties = properties;
    }

    @Override
    public KomscoMerchantResponse fetchPage(String legalDongCode, int page, int pageSize) {
        if (!StringUtils.hasText(properties.serviceKey())) {
            throw new KomscoImportException("KOMSCO_SERVICE_KEY is not configured");
        }

        URI uri = UriComponentsBuilder.fromUri(properties.baseUrl())
                .queryParam("serviceKey", properties.serviceKey())
                .queryParam("page", page)
                .queryParam("perPage", pageSize)
                .queryParam("cond[emd_cd::EQ]", legalDongCode)
                .queryParam("cond[pvsn_inst_cd::EQ]", "I0000002")
                .queryParam("returnType", "JSON")
                .build()
                .encode()
                .toUri();
        try {
            KomscoMerchantResponse response = restClient.get()
                    .uri(uri)
                    .retrieve()
                    .body(KomscoMerchantResponse.class);
            if (response == null) {
                throw new KomscoImportException("KOMSCO returned an empty response");
            }
            return response;
        } catch (RestClientException exception) {
            throw new KomscoImportException(
                    "KOMSCO request failed for legalDong=" + legalDongCode + ", page=" + page);
        }
    }
}
