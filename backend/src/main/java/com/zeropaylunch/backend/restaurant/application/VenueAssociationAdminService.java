package com.zeropaylunch.backend.restaurant.application;

import com.zeropaylunch.backend.restaurant.domain.Restaurant;
import com.zeropaylunch.backend.restaurant.domain.RestaurantVenueAssociation;
import com.zeropaylunch.backend.restaurant.domain.RestaurantVenueAssociationStatus;
import com.zeropaylunch.backend.restaurant.domain.Venue;
import com.zeropaylunch.backend.restaurant.domain.VenueStatus;
import com.zeropaylunch.backend.restaurant.infrastructure.PotentialVenueAssociationProjection;
import com.zeropaylunch.backend.restaurant.infrastructure.RestaurantJpaRepository;
import com.zeropaylunch.backend.restaurant.infrastructure.RestaurantVenueAssociationJpaRepository;
import com.zeropaylunch.backend.restaurant.infrastructure.VenueJpaRepository;
import java.math.BigDecimal;
import java.time.Clock;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class VenueAssociationAdminService {

    private final RestaurantJpaRepository restaurantRepository;
    private final VenueJpaRepository venueRepository;
    private final RestaurantVenueAssociationJpaRepository associationRepository;
    private final Clock clock;

    public VenueAssociationAdminService(
            RestaurantJpaRepository restaurantRepository,
            VenueJpaRepository venueRepository,
            RestaurantVenueAssociationJpaRepository associationRepository,
            Clock clock
    ) {
        this.restaurantRepository = restaurantRepository;
        this.venueRepository = venueRepository;
        this.associationRepository = associationRepository;
        this.clock = clock;
    }

    @Transactional(readOnly = true)
    public List<PotentialVenueCandidate> candidates() {
        return restaurantRepository.findPotentialVenueAssociations().stream()
                .map(PotentialVenueCandidate::from)
                .toList();
    }

    @Transactional
    public AssociationView createPending(
            Long restaurantId,
            String name,
            String address,
            BigDecimal latitude,
            BigDecimal longitude,
            String evidence
    ) {
        Restaurant restaurant = restaurantRepository.findById(restaurantId)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "음식점을 찾을 수 없습니다."));
        if (associationRepository.findByRestaurant_Id(restaurantId).isPresent()) {
            throw new ResponseStatusException(
                    HttpStatus.CONFLICT, "이미 Venue association이 존재합니다.");
        }
        Venue venue = venueRepository.save(Venue.create(
                name, address, latitude, longitude, clock.instant()));
        RestaurantVenueAssociation association = associationRepository.save(
                RestaurantVenueAssociation.pending(restaurant, venue, evidence, clock.instant()));
        return AssociationView.from(association);
    }

    @Transactional
    public AssociationView decide(
            Long associationId,
            RestaurantVenueAssociationStatus decision,
            String evidence
    ) {
        if (decision != RestaurantVenueAssociationStatus.CONFIRMED
                && decision != RestaurantVenueAssociationStatus.REJECTED) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "decision은 CONFIRMED 또는 REJECTED여야 합니다.");
        }
        RestaurantVenueAssociation association = associationRepository.findById(associationId)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Venue association을 찾을 수 없습니다."));
        if (decision == RestaurantVenueAssociationStatus.CONFIRMED
                && association.getVenueStatus() != VenueStatus.ACTIVE) {
            throw new ResponseStatusException(
                    HttpStatus.CONFLICT, "비활성 Venue는 CONFIRMED로 승인할 수 없습니다.");
        }
        try {
            association.decide(decision, evidence, clock.instant());
        } catch (IllegalStateException error) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, error.getMessage(), error);
        }
        return AssociationView.from(associationRepository.save(association));
    }

    public record PotentialVenueCandidate(
            Long firstRestaurantId,
            String firstRestaurantName,
            String firstAddress,
            BigDecimal firstLatitude,
            BigDecimal firstLongitude,
            Long secondRestaurantId,
            String secondRestaurantName,
            String secondAddress,
            BigDecimal secondLatitude,
            BigDecimal secondLongitude
    ) {
        static PotentialVenueCandidate from(PotentialVenueAssociationProjection row) {
            return new PotentialVenueCandidate(
                    row.getFirstRestaurantId(), row.getFirstRestaurantName(), row.getFirstAddress(),
                    row.getFirstLatitude(), row.getFirstLongitude(), row.getSecondRestaurantId(),
                    row.getSecondRestaurantName(), row.getSecondAddress(), row.getSecondLatitude(),
                    row.getSecondLongitude());
        }
    }

    public record AssociationView(
            Long id,
            Long restaurantId,
            Long venueId,
            RestaurantVenueAssociationStatus status,
            String evidence,
            java.time.Instant verifiedAt
    ) {
        static AssociationView from(RestaurantVenueAssociation association) {
            return new AssociationView(
                    association.getId(), association.getRestaurantId(), association.getVenueId(),
                    association.getStatus(), association.getEvidence(), association.getVerifiedAt());
        }
    }
}
