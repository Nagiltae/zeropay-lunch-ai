package com.zeropaylunch.backend.restaurant.infrastructure;

import com.zeropaylunch.backend.restaurant.domain.Venue;
import org.springframework.data.jpa.repository.JpaRepository;

public interface VenueJpaRepository extends JpaRepository<Venue, Long> {
}
