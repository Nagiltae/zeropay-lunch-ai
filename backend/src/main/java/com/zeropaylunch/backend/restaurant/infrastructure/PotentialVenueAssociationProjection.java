package com.zeropaylunch.backend.restaurant.infrastructure;

import java.math.BigDecimal;

public interface PotentialVenueAssociationProjection {
    Long getFirstRestaurantId();
    String getFirstRestaurantName();
    String getFirstAddress();
    BigDecimal getFirstLatitude();
    BigDecimal getFirstLongitude();
    Long getSecondRestaurantId();
    String getSecondRestaurantName();
    String getSecondAddress();
    BigDecimal getSecondLatitude();
    BigDecimal getSecondLongitude();
}
