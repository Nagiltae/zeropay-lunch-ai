package com.zeropaylunch.backend.personalization;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.zeropaylunch.backend.auth.domain.User;
import com.zeropaylunch.backend.auth.infrastructure.UserRepository;
import com.zeropaylunch.backend.chat.application.ChatPersistenceService;
import com.zeropaylunch.backend.chat.domain.MessageRecommendation;
import com.zeropaylunch.backend.chat.infrastructure.MessageRecommendationJpaRepository;
import com.zeropaylunch.backend.meal.application.MealHistoryService;
import com.zeropaylunch.backend.preference.application.UserPreferenceService;
import com.zeropaylunch.backend.preference.domain.SpiceLevel;
import com.zeropaylunch.backend.restaurant.domain.RestaurantCategory;
import jakarta.persistence.EntityManager;
import java.sql.Timestamp;
import java.time.Clock;
import java.time.Duration;
import java.util.Set;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@SpringBootTest
@Transactional
class PersonalizationIntegrationTests {

    private static final long RESTAURANT_ID = 9701L;

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private UserPreferenceService preferenceService;

    @Autowired
    private MealHistoryService mealHistoryService;

    @Autowired
    private ChatPersistenceService chatPersistenceService;

    @Autowired
    private MessageRecommendationJpaRepository recommendationRepository;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    private Clock clock;

    @Autowired
    private EntityManager entityManager;

    @BeforeEach
    void insertRestaurant() {
        jdbcTemplate.update("""
                INSERT INTO restaurants (
                    id, name, category, representative_menu, average_price, address,
                    location_id, zero_pay_available, sample_data, active, created_at, updated_at
                ) VALUES (
                    ?, '개인화 테스트 식당', 'KOREAN', '테스트 메뉴', 9000, '강남구 테스트 주소',
                    'gangnam', TRUE, TRUE, TRUE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """, RESTAURANT_ID);
    }

    @Test
    void storesAndLoadsUserPreferences() {
        UUID userId = createUser("preference");

        var saved = preferenceService.update(
                userId,
                12_000,
                SpiceLevel.MEDIUM,
                Set.of(RestaurantCategory.KOREAN),
                Set.of(RestaurantCategory.SALAD),
                Set.of("땅콩")
        );

        assertThat(saved.defaultBudget()).isEqualTo(12_000);
        assertThat(preferenceService.get(userId).preferredCategories())
                .containsExactly(RestaurantCategory.KOREAN);
        assertThat(preferenceService.get(userId).allergies()).containsExactly("땅콩");
    }

    @Test
    void rejectsCategorySelectedAsBothPreferredAndDisliked() {
        UUID userId = createUser("overlap");

        assertThatThrownBy(() -> preferenceService.update(
                userId,
                null,
                SpiceLevel.ANY,
                Set.of(RestaurantCategory.KOREAN),
                Set.of(RestaurantCategory.KOREAN),
                Set.of()
        ))
                .isInstanceOf(ResponseStatusException.class)
                .hasMessageContaining("400 BAD_REQUEST");
    }

    @Test
    void storesOnlyOwnedRecommendationsAndUsesOnlyRecentThreeDays() {
        UUID userId = createUser("meal-owner");
        UUID otherUserId = createUser("meal-other");
        var conversation = chatPersistenceService.createConversation(userId);

        var oldExchange = chatPersistenceService.startExchange(
                conversation.getId(), userId, "첫 추천"
        );
        recommendationRepository.save(new MessageRecommendation(
                oldExchange.assistantMessageId(), RESTAURANT_ID, 1, "테스트 추천"
        ));
        var oldMeal = mealHistoryService.markEaten(
                userId, oldExchange.assistantMessageId(), RESTAURANT_ID
        );
        entityManager.flush();
        assertThat(jdbcTemplate.update(
                "UPDATE meal_history SET eaten_at = ? WHERE id = ?",
                Timestamp.from(clock.instant().minus(Duration.ofDays(4))),
                oldMeal.mealId().toString()
        )).isEqualTo(1);
        entityManager.clear();

        var recentExchange = chatPersistenceService.startExchange(
                conversation.getId(), userId, "두 번째 추천"
        );
        recommendationRepository.save(new MessageRecommendation(
                recentExchange.assistantMessageId(), RESTAURANT_ID, 1, "테스트 추천"
        ));
        var recentMeal = mealHistoryService.markEaten(
                userId, recentExchange.assistantMessageId(), RESTAURANT_ID
        );
        var repeated = mealHistoryService.markEaten(
                userId, recentExchange.assistantMessageId(), RESTAURANT_ID
        );

        assertThat(repeated.mealId()).isEqualTo(recentMeal.mealId());
        assertThat(mealHistoryService.findRecent(userId))
                .extracting(MealHistoryService.MealRecord::mealId)
                .containsExactly(recentMeal.mealId());
        assertThatThrownBy(() -> mealHistoryService.markEaten(
                otherUserId, recentExchange.assistantMessageId(), RESTAURANT_ID
        ))
                .isInstanceOf(ResponseStatusException.class)
                .hasMessageContaining("400 BAD_REQUEST");
    }

    private UUID createUser(String prefix) {
        User user = User.create(
                prefix + "-" + UUID.randomUUID() + "@example.com",
                "개인화 테스트 사용자",
                clock.instant()
        );
        return userRepository.save(user).getId();
    }
}
