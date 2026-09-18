package com.zeropaylunch.backend.restaurant.enrichment.naver;

record NaverNameProfile(
        String normalizedFull,
        String normalizedWithoutParentheses,
        String normalizedBase,
        String branchName) {
}
