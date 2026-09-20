package com.zeropaylunch.backend.location.domain;

import java.math.BigDecimal;

public class LocationDistanceCalculator {

    private static final double EARTH_RADIUS_METERS = 6_371_000.0;

    public static Double distanceMeters(
            double firstLatitude,
            double firstLongitude,
            BigDecimal secondLatitude,
            BigDecimal secondLongitude) {
        if (secondLatitude == null || secondLongitude == null) {
            return null;
        }
        double lat2 = secondLatitude.doubleValue();
        double lon2 = secondLongitude.doubleValue();

        double latitudeDelta = Math.toRadians(lat2 - firstLatitude);
        double longitudeDelta = Math.toRadians(lon2 - firstLongitude);
        double firstLatitudeRadians = Math.toRadians(firstLatitude);
        double secondLatitudeRadians = Math.toRadians(lat2);

        double haversine = Math.sin(latitudeDelta / 2) * Math.sin(latitudeDelta / 2)
                + Math.cos(firstLatitudeRadians) * Math.cos(secondLatitudeRadians)
                * Math.sin(longitudeDelta / 2) * Math.sin(longitudeDelta / 2);

        return 2 * EARTH_RADIUS_METERS * Math.asin(Math.sqrt(haversine));
    }
}
