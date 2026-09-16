package com.zeropaylunch.backend.preference.domain;

import com.zeropaylunch.backend.restaurant.domain.RestaurantCategory;
import jakarta.persistence.CollectionTable;
import jakarta.persistence.Column;
import jakarta.persistence.ElementCollection;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.LinkedHashSet;
import java.util.Set;
import java.util.UUID;

@Entity
@Table(name = "user_preferences")
public class UserPreference {

    @Id
    @Column(name = "user_id")
    private UUID userId;

    @Column(name = "default_budget")
    private Integer defaultBudget;

    @Enumerated(EnumType.STRING)
    @Column(name = "spice_level", nullable = false, length = 16)
    private SpiceLevel spiceLevel;

    @ElementCollection(fetch = FetchType.EAGER)
    @CollectionTable(
            name = "user_preferred_categories",
            joinColumns = @JoinColumn(name = "user_id")
    )
    @Enumerated(EnumType.STRING)
    @Column(name = "category", nullable = false, length = 40)
    private Set<RestaurantCategory> preferredCategories = new LinkedHashSet<>();

    @ElementCollection(fetch = FetchType.EAGER)
    @CollectionTable(
            name = "user_disliked_categories",
            joinColumns = @JoinColumn(name = "user_id")
    )
    @Enumerated(EnumType.STRING)
    @Column(name = "category", nullable = false, length = 40)
    private Set<RestaurantCategory> dislikedCategories = new LinkedHashSet<>();

    @ElementCollection(fetch = FetchType.EAGER)
    @CollectionTable(name = "user_allergies", joinColumns = @JoinColumn(name = "user_id"))
    @Column(name = "allergy", nullable = false, length = 80)
    private Set<String> allergies = new LinkedHashSet<>();

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    protected UserPreference() {
    }

    private UserPreference(UUID userId, Instant now) {
        this.userId = userId;
        this.spiceLevel = SpiceLevel.ANY;
        this.createdAt = now;
        this.updatedAt = now;
    }

    public static UserPreference create(UUID userId, Instant now) {
        return new UserPreference(userId, now);
    }

    public void update(
            Integer defaultBudget,
            SpiceLevel spiceLevel,
            Set<RestaurantCategory> preferredCategories,
            Set<RestaurantCategory> dislikedCategories,
            Set<String> allergies,
            Instant now
    ) {
        this.defaultBudget = defaultBudget;
        this.spiceLevel = spiceLevel;
        this.preferredCategories.clear();
        this.preferredCategories.addAll(preferredCategories);
        this.dislikedCategories.clear();
        this.dislikedCategories.addAll(dislikedCategories);
        this.allergies.clear();
        this.allergies.addAll(allergies);
        this.updatedAt = now;
    }

    public UUID getUserId() {
        return userId;
    }

    public Integer getDefaultBudget() {
        return defaultBudget;
    }

    public SpiceLevel getSpiceLevel() {
        return spiceLevel;
    }

    public Set<RestaurantCategory> getPreferredCategories() {
        return Set.copyOf(preferredCategories);
    }

    public Set<RestaurantCategory> getDislikedCategories() {
        return Set.copyOf(dislikedCategories);
    }

    public Set<String> getAllergies() {
        return Set.copyOf(allergies);
    }
}
