package com.zeropaylunch.backend.restaurant.domain;

public enum RestaurantCategory {
    KOREAN("한식"),
    KOREAN_SOUP("국물·한식"),
    SALAD("샐러드");

    private final String label;

    RestaurantCategory(String label) {
        this.label = label;
    }

    public String label() {
        return label;
    }
}
