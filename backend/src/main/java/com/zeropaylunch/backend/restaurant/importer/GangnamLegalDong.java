package com.zeropaylunch.backend.restaurant.importer;

import java.util.Set;

enum GangnamLegalDong {
    NONHYEON("11680108", "논현동");

    private static final Set<String> CODES = Set.of("11680108");

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
