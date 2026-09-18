package com.zeropaylunch.backend.restaurant.importer;

import java.util.Set;

enum GangnamLegalDong {
    GAEPO("11680103", "개포동"),
    NONHYEON("11680108", "논현동"),
    DAECHI("11680106", "대치동"),
    DOGOK("11680118", "도곡동"),
    SAMSEONG("11680105", "삼성동"),
    SEGOK("11680111", "세곡동"),
    SUSEO("11680115", "수서동"),
    SINSA("11680107", "신사동"),
    APGUJEONG("11680110", "압구정동"),
    YEOKSAM("11680101", "역삼동"),
    YULHYEON("11680113", "율현동"),
    IRWON("11680114", "일원동"),
    JAGOK("11680112", "자곡동"),
    CHEONGDAM("11680104", "청담동");

    private static final Set<String> CODES = Set.of(
            "11680103", "11680108", "11680106", "11680118", "11680105",
            "11680111", "11680115", "11680107", "11680110", "11680101",
            "11680113", "11680114", "11680112", "11680104");

    private final String code;
    private final String name;

    GangnamLegalDong(String code, String name) {
        this.code = code;
        this.name = name;
    }

    String code() {
        return code;
    }

    String legalDongName() {
        return name;
    }

    static boolean containsCode(String code) {
        return CODES.contains(code);
    }
}
