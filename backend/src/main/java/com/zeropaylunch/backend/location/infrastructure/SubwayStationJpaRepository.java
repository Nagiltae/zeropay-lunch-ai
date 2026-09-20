package com.zeropaylunch.backend.location.infrastructure;

import com.zeropaylunch.backend.location.domain.SubwayStation;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

@Repository
public interface SubwayStationJpaRepository extends JpaRepository<SubwayStation, String> {

    List<SubwayStation> findAllByActiveTrueOrderByNameAscIdAsc();
}
