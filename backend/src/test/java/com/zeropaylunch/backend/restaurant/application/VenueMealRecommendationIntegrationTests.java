package com.zeropaylunch.backend.restaurant.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.zeropaylunch.backend.meal.application.MealHistoryService;
import com.zeropaylunch.backend.meal.domain.MealHistory;
import com.zeropaylunch.backend.meal.infrastructure.MealHistoryJpaRepository;
import com.zeropaylunch.backend.preference.domain.SpiceLevel;
import com.zeropaylunch.backend.recommendation.ai.AnalyzedIntent;
import com.zeropaylunch.backend.recommendation.ai.AnalyzedIntent.IntentType;
import com.zeropaylunch.backend.recommendation.ai.IntentAnalysisRequest;
import com.zeropaylunch.backend.recommendation.application.RecommendationContextService;
import com.zeropaylunch.backend.recommendation.application.RecommendationContextService.RecommendationContext;
import com.zeropaylunch.backend.restaurant.domain.Restaurant;
import com.zeropaylunch.backend.restaurant.domain.RestaurantCategory;
import com.zeropaylunch.backend.restaurant.domain.RestaurantVenueAssociation;
import com.zeropaylunch.backend.restaurant.domain.RestaurantVenueAssociationStatus;
import com.zeropaylunch.backend.restaurant.domain.Venue;
import com.zeropaylunch.backend.restaurant.infrastructure.RestaurantJpaRepository;
import com.zeropaylunch.backend.restaurant.infrastructure.RestaurantVenueAssociationJpaRepository;
import com.zeropaylunch.backend.restaurant.infrastructure.VenueJpaRepository;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;

@SpringBootTest
@Transactional
class VenueMealRecommendationIntegrationTests {

    private static final long EATEN_RESTAURANT_ID = 98701L;
    private static final long CANDIDATE_RESTAURANT_ID = 98702L;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    private RestaurantJpaRepository restaurantRepository;

    @Autowired
    private VenueJpaRepository venueRepository;

    @Autowired
    private RestaurantVenueAssociationJpaRepository associationRepository;

    @Autowired
    private MealHistoryJpaRepository mealHistoryRepository;

    @Autowired
    private MealHistoryService mealHistoryService;

    @Autowired
    private Clock clock;

    private UUID userId;
    private UUID sourceMessageId;

    @BeforeEach
    void insertIsolatedRestaurantsAndMealOwner() {
        Instant now = Instant.parse("2026-09-24T00:00:00Z");
        insertRestaurant(EATEN_RESTAURANT_ID, "Venue 식당 A");
        insertRestaurant(CANDIDATE_RESTAURANT_ID, "Venue 식당 B");

        userId = UUID.randomUUID();
        UUID conversationId = UUID.randomUUID();
        sourceMessageId = UUID.randomUUID();
        jdbcTemplate.update("""
                INSERT INTO users (id, email, display_name, status, role, created_at, updated_at)
                VALUES (?, ?, 'Venue 테스트 사용자', 'ACTIVE', 'USER', ?, ?)
                """, userId.toString(), userId + "@venue-test.local", now, now);
        jdbcTemplate.update("""
                INSERT INTO conversations (id, location_id, active, created_at, updated_at, user_id)
                VALUES (?, 'gangnam', TRUE, ?, ?, ?)
                """, conversationId.toString(), now, now, userId.toString());
        jdbcTemplate.update("""
                INSERT INTO chat_messages (id, conversation_id, role, status, content, created_at, completed_at)
                VALUES (?, ?, 'USER', 'COMPLETED', 'Venue 테스트', ?, ?)
                """, sourceMessageId.toString(), conversationId.toString(), now, now);
    }

    @Test
    void mysqlAssociationAndMealHistoryExcludeSameVenueCandidate() {
        Restaurant eaten = restaurantRepository.findById(EATEN_RESTAURANT_ID).orElseThrow();
        Restaurant candidate = restaurantRepository.findById(CANDIDATE_RESTAURANT_ID).orElseThrow();
        Venue venue = venueRepository.save(Venue.create(
                "테스트 Venue", "서울 강남구 테스트로 987", null, null, clock.instant()));
        RestaurantVenueAssociation eatenAssociation = associationRepository.save(
                RestaurantVenueAssociation.pending(eaten, venue, "통합 테스트 근거", clock.instant()));
        RestaurantVenueAssociation candidateAssociation = associationRepository.save(
                RestaurantVenueAssociation.pending(candidate, venue, "통합 테스트 근거", clock.instant()));
        eatenAssociation.decide(RestaurantVenueAssociationStatus.CONFIRMED, "동일 Venue 확인", clock.instant());
        candidateAssociation.decide(RestaurantVenueAssociationStatus.CONFIRMED, "동일 Venue 확인", clock.instant());
        associationRepository.saveAll(List.of(eatenAssociation, candidateAssociation));
        mealHistoryRepository.save(MealHistory.create(
                userId, EATEN_RESTAURANT_ID, sourceMessageId, clock.instant()));

        assertThat(associationRepository.findAllByRestaurant_IdInAndStatusAndVenue_Status(
                List.of(EATEN_RESTAURANT_ID, CANDIDATE_RESTAURANT_ID),
                RestaurantVenueAssociationStatus.CONFIRMED,
                com.zeropaylunch.backend.restaurant.domain.VenueStatus.ACTIVE))
                .hasSize(2);
        assertThat(mealHistoryService.findRecent(userId))
                .extracting(MealHistoryService.MealRecord::restaurantId)
                .containsExactly(EATEN_RESTAURANT_ID);

        RecommendationContextService contextService = mock(RecommendationContextService.class);
        RestaurantJpaRepository candidateRepository = mock(RestaurantJpaRepository.class);
        when(candidateRepository.findOpenRestaurants(anyString(), any()))
                .thenReturn(List.of(candidate));
        List<MealHistoryService.MealRecord> recentMeals = mealHistoryService.findRecent(userId);
        IntentAnalysisRequest request = new IntentAnalysisRequest(
                "점심 추천해줘", 12_000, SpiceLevel.ANY, Set.of(RestaurantCategory.KOREAN),
                Set.of(), Set.of(), recentMeals.stream()
                        .map(meal -> new IntentAnalysisRequest.RecentMeal(
                                meal.restaurantId(), meal.category(), meal.eatenAt()))
                        .toList());
        when(contextService.build(userId, "점심 추천해줘"))
                .thenReturn(new RecommendationContext(request, new AnalyzedIntent(
                        IntentType.RECOMMEND_RESTAURANT, null, Optional.empty(), List.of(), false, null)));

        RestaurantRecommendationService service = new RestaurantRecommendationService(
                candidateRepository, associationRepository, contextService,
                Clock.fixed(Instant.parse("2026-09-24T00:00:00Z"), ZoneOffset.UTC));

        assertThat(service.recommend(userId, "점심 추천해줘")).isEmpty();
        assertThat(jdbcTemplate.queryForObject(
                "SELECT recommendation_eligibility FROM restaurants WHERE id = ?",
                String.class, CANDIDATE_RESTAURANT_ID)).isEqualTo("ELIGIBLE");
        assertThat(jdbcTemplate.queryForObject(
                "SELECT restaurant_id FROM meal_history WHERE user_id = ? AND source_message_id = ?",
                Long.class, userId.toString(), sourceMessageId.toString()))
                .isEqualTo(EATEN_RESTAURANT_ID);
    }

    private void insertRestaurant(long id, String name) {
        jdbcTemplate.update("""
                INSERT INTO restaurants (
                    id, name, category, representative_menu, average_price, address, location_id,
                    zero_pay_available, sample_data, active, recommendation_ready,
                    recommendation_eligibility, created_at, updated_at
                ) VALUES (?, ?, 'KOREAN', '테스트 메뉴', 9000, ?, 'gangnam',
                    TRUE, FALSE, TRUE, TRUE, 'ELIGIBLE', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """, id, name, "서울 강남구 테스트로 " + id);
    }
}
