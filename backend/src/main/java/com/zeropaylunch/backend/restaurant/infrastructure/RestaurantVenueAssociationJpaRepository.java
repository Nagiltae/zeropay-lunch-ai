package com.zeropaylunch.backend.restaurant.infrastructure;

import com.zeropaylunch.backend.restaurant.domain.RestaurantVenueAssociation;
import com.zeropaylunch.backend.restaurant.domain.RestaurantVenueAssociationStatus;
import com.zeropaylunch.backend.restaurant.domain.VenueStatus;
import java.util.Collection;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface RestaurantVenueAssociationJpaRepository
        extends JpaRepository<RestaurantVenueAssociation, Long> {

    Optional<RestaurantVenueAssociation> findByRestaurant_Id(Long restaurantId);

    List<RestaurantVenueAssociation> findAllByRestaurant_IdInAndStatusAndVenue_Status(
            Collection<Long> restaurantIds,
            RestaurantVenueAssociationStatus status,
            VenueStatus venueStatus
    );
}
