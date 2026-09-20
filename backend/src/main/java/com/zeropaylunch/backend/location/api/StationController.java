package com.zeropaylunch.backend.location.api;

import com.zeropaylunch.backend.location.domain.SubwayStation;
import com.zeropaylunch.backend.location.infrastructure.SubwayStationJpaRepository;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/stations")
public class StationController {

    private final SubwayStationJpaRepository stationRepository;

    public StationController(SubwayStationJpaRepository stationRepository) {
        this.stationRepository = stationRepository;
    }

    @GetMapping
    public List<StationResponse> listActiveStations() {
        return stationRepository.findAllByActiveTrueOrderByNameAscIdAsc().stream()
                .map(StationResponse::from)
                .toList();
    }

    public record StationResponse(String id, String name, String line) {

        private static StationResponse from(SubwayStation station) {
            return new StationResponse(station.getId(), station.getName(), station.getLine());
        }
    }
}
