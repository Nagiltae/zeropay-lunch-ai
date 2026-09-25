package com.zeropaylunch.backend.restaurant.api;

import com.zeropaylunch.backend.restaurant.application.VenueAssociationAdminService;
import com.zeropaylunch.backend.restaurant.domain.RestaurantVenueAssociationStatus;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/admin/venue-associations")
public class VenueAssociationAdminController {

    private final VenueAssociationAdminService service;

    public VenueAssociationAdminController(VenueAssociationAdminService service) {
        this.service = service;
    }

    @GetMapping("/candidates")
    public List<VenueAssociationAdminService.PotentialVenueCandidate> candidates() {
        return service.candidates();
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public VenueAssociationAdminService.AssociationView createPending(
            @Valid @RequestBody CreatePendingRequest request
    ) {
        return service.createPending(
                request.restaurantId(), request.name(), request.address(), request.latitude(),
                request.longitude(), request.evidence());
    }

    @PatchMapping("/{associationId}")
    public VenueAssociationAdminService.AssociationView decide(
            @PathVariable @Positive Long associationId,
            @Valid @RequestBody DecisionRequest request
    ) {
        return service.decide(associationId, request.decision(), request.evidence());
    }

    public record CreatePendingRequest(
            @NotNull @Positive Long restaurantId,
            @NotBlank @Size(max = 120) String name,
            @NotBlank @Size(max = 255) String address,
            BigDecimal latitude,
            BigDecimal longitude,
            @NotBlank @Size(max = 1000) String evidence
    ) {
    }

    public record DecisionRequest(
            @NotNull RestaurantVenueAssociationStatus decision,
            @NotBlank @Size(max = 1000) String evidence
    ) {
    }
}
