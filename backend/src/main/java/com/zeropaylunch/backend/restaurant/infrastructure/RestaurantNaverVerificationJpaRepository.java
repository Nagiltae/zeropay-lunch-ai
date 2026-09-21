package com.zeropaylunch.backend.restaurant.infrastructure;

import com.zeropaylunch.backend.restaurant.domain.RestaurantNaverVerification;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface RestaurantNaverVerificationJpaRepository
        extends JpaRepository<RestaurantNaverVerification, Long> {
    Optional<RestaurantNaverVerification> findByRestaurantIdAndProvider(
            Long restaurantId, String provider);

    Optional<RestaurantNaverVerification> findByRestaurantIdAndProviderAndSourceFingerprint(
            Long restaurantId, String provider, String sourceFingerprint);

    @Modifying
    @Query("UPDATE RestaurantNaverVerification v SET v.verificationStatus = 'UNRESOLVED', "
            + "v.verificationReason = 'SOURCE_CHANGED', v.sourceFingerprint = NULL, v.verifiedAt = NULL "
            + "WHERE v.restaurant.id = :restaurantId AND v.provider = 'NAVER'")
    int markStaleForSourceChange(@Param("restaurantId") Long restaurantId);
}
