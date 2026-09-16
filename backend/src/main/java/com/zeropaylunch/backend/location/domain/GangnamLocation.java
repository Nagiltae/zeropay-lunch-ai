package com.zeropaylunch.backend.location.domain;

import java.util.Arrays;

public enum GangnamLocation {
    GANGNAM("gangnam", "강남역"),
    YEOKSAM("yeoksam", "역삼역"),
    SEOLLEUNG("seolleung", "선릉역"),
    SAMSEONG("samseong", "삼성역"),
    SINSA("sinsa", "신사역"),
    APGUJEONG("apgujeong", "압구정역"),
    CHEONGDAM("cheongdam", "청담역"),
    SUSEO("suseo", "수서역");

    private final String id;
    private final String label;

    GangnamLocation(String id, String label) {
        this.id = id;
        this.label = label;
    }

    public String id() {
        return id;
    }

    public String label() {
        return label;
    }

    public static GangnamLocation fromId(String id) {
        return Arrays.stream(values())
                .filter(location -> location.id.equals(id))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException("지원하지 않는 강남구 위치입니다."));
    }
}
