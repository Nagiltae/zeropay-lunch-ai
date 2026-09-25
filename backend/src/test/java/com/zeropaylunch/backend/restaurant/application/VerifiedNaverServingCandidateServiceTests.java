package com.zeropaylunch.backend.restaurant.application;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.LocalDate;
import java.time.LocalTime;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;

@SpringBootTest
@Transactional
class VerifiedNaverServingCandidateServiceTests {
    @Autowired private JdbcTemplate jdbc;
    @Autowired private VerifiedNaverServingCandidateService service;

    @BeforeEach
    void insertSourceGroundedKomscoRestaurant() {
        jdbc.update("""
                INSERT INTO restaurants (id,name,address,location_id,zero_pay_available,sample_data,active,
                    recommendation_ready,recommendation_eligibility,legal_dong_code,source_provider,created_at,updated_at)
                VALUES (97001,'검증 점심 식당','서울 강남구 논현동 테스트','gangnam',TRUE,FALSE,TRUE,FALSE,
                    'ELIGIBLE','11680108','KOMSCO',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)
                """);
        jdbc.update("""
                INSERT INTO restaurant_external_places (restaurant_id,provider,external_place_id,match_status,
                    match_score,name_score,address_score,distance_score,category_score,query_used,
                    last_synced_at,created_at,updated_at)
                VALUES (97001,'NAVER','987654321','MATCHED',1,1,1,1,1,'test',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)
                """);
        jdbc.update("""
                INSERT INTO restaurant_naver_verifications (restaurant_id,provider,verification_status,
                    verification_reason,last_attempt_at)
                VALUES (97001,'NAVER','VERIFIED','TEST',CURRENT_TIMESTAMP)
                """);
        jdbc.update("""
                INSERT INTO restaurant_detail_section_states (restaurant_id,provider,external_place_id,section,state,checked_at)
                VALUES (97001,'NAVER','987654321','menu','SUCCESS',CURRENT_TIMESTAMP),
                       (97001,'NAVER','987654321','business_hours','SUCCESS',CURRENT_TIMESTAMP)
                """);
        jdbc.update("""
                INSERT INTO restaurant_menus (restaurant_id,provider,external_place_id,external_menu_id,name,price_value)
                VALUES (97001,'NAVER','987654321','dom-1','점심 메뉴',9000)
                """);
        jdbc.update("""
                INSERT INTO restaurant_business_hours (restaurant_id,provider,external_place_id,day_of_week,
                    open_time,close_time,description,active)
                VALUES (97001,'NAVER','987654321','매일','11:00','22:00','매일 11:00 - 22:00',TRUE)
                """);
    }

    @Test
    void includesVerifiedSourceCandidateEvenWhenLegacyReadyFlagIsFalse() {
        assertThat(service.findOpenCandidateIds(LocalDate.of(2026, 9, 24), LocalTime.NOON, null))
                .containsExactly(97001L);
    }

    @Test
    void unknownBudgetClassificationDoesNotPassAnExplicitBudget() {
        assertThat(service.findOpenCandidateIds(LocalDate.of(2026, 9, 24), LocalTime.NOON, 10_000))
                .doesNotContain(97001L);
    }
}
