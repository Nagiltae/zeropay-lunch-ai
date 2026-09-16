package com.zeropaylunch.backend.preference.application;

import com.zeropaylunch.backend.preference.domain.SpiceLevel;
import com.zeropaylunch.backend.preference.domain.UserPreference;
import com.zeropaylunch.backend.preference.infrastructure.UserPreferenceJpaRepository;
import com.zeropaylunch.backend.restaurant.domain.RestaurantCategory;
import java.time.Clock;
import java.util.LinkedHashSet;
import java.util.Set;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class UserPreferenceService {

    private final UserPreferenceJpaRepository preferenceRepository;
    private final Clock clock;

    public UserPreferenceService(UserPreferenceJpaRepository preferenceRepository, Clock clock) {
        this.preferenceRepository = preferenceRepository;
        this.clock = clock;
    }

    @Transactional(readOnly = true)
    public PreferenceSnapshot get(UUID userId) {
        return preferenceRepository.findById(userId)
                .map(this::toSnapshot)
                .orElseGet(() -> PreferenceSnapshot.empty(userId));
    }

    @Transactional
    public PreferenceSnapshot update(
            UUID userId,
            Integer defaultBudget,
            SpiceLevel spiceLevel,
            Set<RestaurantCategory> preferredCategories,
            Set<RestaurantCategory> dislikedCategories,
            Set<String> allergies
    ) {
        Set<RestaurantCategory> overlap = new LinkedHashSet<>(preferredCategories);
        overlap.retainAll(dislikedCategories);
        if (!overlap.isEmpty()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "같은 음식 종류를 선호와 비선호에 동시에 선택할 수 없습니다."
            );
        }
        Set<String> normalizedAllergies = new LinkedHashSet<>();
        for (String allergy : allergies) {
            String normalized = allergy.trim();
            if (!normalized.isEmpty()) {
                normalizedAllergies.add(normalized);
            }
        }

        UserPreference preference = preferenceRepository.findById(userId)
                .orElseGet(() -> UserPreference.create(userId, clock.instant()));
        preference.update(
                defaultBudget,
                spiceLevel,
                preferredCategories,
                dislikedCategories,
                normalizedAllergies,
                clock.instant()
        );
        return toSnapshot(preferenceRepository.save(preference));
    }

    private PreferenceSnapshot toSnapshot(UserPreference preference) {
        return new PreferenceSnapshot(
                preference.getUserId(),
                preference.getDefaultBudget(),
                preference.getSpiceLevel(),
                preference.getPreferredCategories(),
                preference.getDislikedCategories(),
                preference.getAllergies()
        );
    }

    public record PreferenceSnapshot(
            UUID userId,
            Integer defaultBudget,
            SpiceLevel spiceLevel,
            Set<RestaurantCategory> preferredCategories,
            Set<RestaurantCategory> dislikedCategories,
            Set<String> allergies
    ) {
        public static PreferenceSnapshot empty(UUID userId) {
            return new PreferenceSnapshot(
                    userId, null, SpiceLevel.ANY, Set.of(), Set.of(), Set.of()
            );
        }
    }
}
