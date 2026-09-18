package com.zeropaylunch.backend.restaurant.enrichment.naver;

import java.math.BigDecimal;
import org.springframework.stereotype.Component;

@Component
class GeoDistanceCalculator {

    private static final double EARTH_RADIUS_METERS = 6_371_000.0;

    Double distanceMeters(
            BigDecimal firstLatitude,
            BigDecimal firstLongitude,
            BigDecimal secondLatitude,
            BigDecimal secondLongitude) {
        if (firstLatitude == null || firstLongitude == null
                || secondLatitude == null || secondLongitude == null) {
            return null;
        }
        double latitudeDelta = Math.toRadians(
                secondLatitude.doubleValue() - firstLatitude.doubleValue());
        double longitudeDelta = Math.toRadians(
                secondLongitude.doubleValue() - firstLongitude.doubleValue());
        double firstLatitudeRadians = Math.toRadians(firstLatitude.doubleValue());
        double secondLatitudeRadians = Math.toRadians(secondLatitude.doubleValue());
        double haversine = Math.sin(latitudeDelta / 2) * Math.sin(latitudeDelta / 2)
                + Math.cos(firstLatitudeRadians) * Math.cos(secondLatitudeRadians)
                * Math.sin(longitudeDelta / 2) * Math.sin(longitudeDelta / 2);
        return 2 * EARTH_RADIUS_METERS * Math.asin(Math.sqrt(haversine));
    }
}
