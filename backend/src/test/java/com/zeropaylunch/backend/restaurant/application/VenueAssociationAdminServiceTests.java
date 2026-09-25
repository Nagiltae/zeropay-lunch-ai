package com.zeropaylunch.backend.restaurant.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.zeropaylunch.backend.restaurant.domain.RestaurantVenueAssociationStatus;
import com.zeropaylunch.backend.restaurant.infrastructure.RestaurantVenueAssociationJpaRepository;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@SpringBootTest
@Transactional
class VenueAssociationAdminServiceTests {

    @Autowired
    private VenueAssociationAdminService service;

    @Autowired
    private RestaurantVenueAssociationJpaRepository associationRepository;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @BeforeEach
    void insertRestaurant() {
        jdbcTemplate.update("""
                INSERT INTO restaurants (
                    id, name, category, average_price, address, zero_pay_available,
                    sample_data, active, recommendation_ready, recommendation_eligibility,
                    created_at, updated_at
                ) VALUES (
                    98001, 'Venue 승인 테스트', 'KOREAN', 9000, '서울 강남구 테스트로 1',
                    TRUE, FALSE, TRUE, TRUE, 'ELIGIBLE', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """);
    }

    @Test
    void createsPendingAndAllowsOneExplicitDecision() {
        VenueAssociationAdminService.AssociationView pending = service.createPending(
                98001L, "테스트 Venue", "서울 강남구 테스트로 1", null, null,
                "관리자 검토 대기");

        assertThat(pending.status()).isEqualTo(RestaurantVenueAssociationStatus.PENDING);

        VenueAssociationAdminService.AssociationView confirmed = service.decide(
                pending.id(), RestaurantVenueAssociationStatus.CONFIRMED, "동일 장소 확인 근거");

        assertThat(confirmed.status()).isEqualTo(RestaurantVenueAssociationStatus.CONFIRMED);
        assertThat(confirmed.verifiedAt()).isNotNull();
        assertThat(associationRepository.findById(pending.id()).orElseThrow().getStatus())
                .isEqualTo(RestaurantVenueAssociationStatus.CONFIRMED);

        VenueAssociationAdminService.AssociationView repeated = service.decide(
                pending.id(), RestaurantVenueAssociationStatus.CONFIRMED, "");
        assertThat(repeated.status()).isEqualTo(RestaurantVenueAssociationStatus.CONFIRMED);
    }

    @Test
    void rejectsSecondPendingAssociationAndConflictingDecision() {
        VenueAssociationAdminService.AssociationView pending = service.createPending(
                98001L, "테스트 Venue", "서울 강남구 테스트로 1", null, null,
                "검토 대기");

        assertThatThrownBy(() -> service.createPending(
                98001L, "두 번째 Venue", "다른 주소", null, null, "중복 요청"))
                .isInstanceOf(ResponseStatusException.class)
                .hasMessageContaining("이미 Venue association");

        service.decide(pending.id(), RestaurantVenueAssociationStatus.REJECTED, "별도 장소");
        assertThatThrownBy(() -> service.decide(
                pending.id(), RestaurantVenueAssociationStatus.CONFIRMED, "재승인"))
                .isInstanceOf(ResponseStatusException.class)
                .hasMessageContaining("Only PENDING");
    }
}
