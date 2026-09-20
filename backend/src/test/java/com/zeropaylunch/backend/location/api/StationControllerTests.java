package com.zeropaylunch.backend.location.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.zeropaylunch.backend.location.domain.SubwayStation;
import com.zeropaylunch.backend.location.infrastructure.SubwayStationJpaRepository;
import java.math.BigDecimal;
import java.util.List;
import org.junit.jupiter.api.Test;

class StationControllerTests {

    @Test
    void returnsActiveStationsInRepositoryOrder() {
        SubwayStationJpaRepository repository = mock(SubwayStationJpaRepository.class);
        SubwayStation station = new SubwayStation(
                "gangnam", "강남역", "2호선/신분당선",
                new BigDecimal("37.4980"), new BigDecimal("127.0276"), true,
                "SEOUL_OPEN_DATA");
        when(repository.findAllByActiveTrueOrderByNameAscIdAsc()).thenReturn(List.of(station));

        List<StationController.StationResponse> response =
                new StationController(repository).listActiveStations();

        assertThat(response)
                .extracting(StationController.StationResponse::id,
                        StationController.StationResponse::name,
                        StationController.StationResponse::line)
                .containsExactly(org.assertj.core.groups.Tuple.tuple(
                        "gangnam", "강남역", "2호선/신분당선"));
        verify(repository).findAllByActiveTrueOrderByNameAscIdAsc();
    }
}
