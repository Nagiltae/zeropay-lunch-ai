package com.zeropaylunch.backend.restaurant.enrichment.naver;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.zeropaylunch.backend.restaurant.domain.Restaurant;
import java.util.List;
import org.junit.jupiter.api.Test;

class StratifiedRestaurantSamplerTests {

    private final StratifiedRestaurantSampler sampler = new StratifiedRestaurantSampler();

    @Test
    void selectsDeterministicallyAcrossLegalDongsBeforeTakingSecondRows() {
        Restaurant gaepo1 = restaurant(3L, "11680103");
        Restaurant gaepo2 = restaurant(4L, "11680103");
        Restaurant nonhyeon1 = restaurant(1L, "11680108");
        Restaurant nonhyeon2 = restaurant(2L, "11680108");
        Restaurant daechi = restaurant(5L, "11680106");

        List<Restaurant> selected = sampler.select(
                List.of(nonhyeon2, gaepo2, daechi, nonhyeon1, gaepo1), 4);

        assertThat(selected)
                .containsExactly(gaepo1, daechi, nonhyeon1, gaepo2);
    }

    private Restaurant restaurant(long id, String legalDongCode) {
        Restaurant restaurant = mock(Restaurant.class);
        when(restaurant.getId()).thenReturn(id);
        when(restaurant.getLegalDongCode()).thenReturn(legalDongCode);
        return restaurant;
    }
}
