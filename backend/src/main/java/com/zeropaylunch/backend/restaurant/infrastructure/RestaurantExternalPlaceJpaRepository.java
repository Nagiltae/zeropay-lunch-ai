package com.zeropaylunch.backend.restaurant.infrastructure;

import com.zeropaylunch.backend.restaurant.domain.ExternalPlaceProvider;
import com.zeropaylunch.backend.restaurant.domain.RestaurantExternalPlace;
import java.util.Optional;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface RestaurantExternalPlaceJpaRepository
        extends JpaRepository<RestaurantExternalPlace, Long> {

    Optional<RestaurantExternalPlace> findByRestaurantIdAndProvider(
            Long restaurantId, ExternalPlaceProvider provider);

    @Query("""
            SELECT place
            FROM RestaurantExternalPlace place
            JOIN FETCH place.restaurant
            WHERE place.provider = :provider
            """)
    List<RestaurantExternalPlace> findAllByProviderWithRestaurant(
            @Param("provider") ExternalPlaceProvider provider);
}
