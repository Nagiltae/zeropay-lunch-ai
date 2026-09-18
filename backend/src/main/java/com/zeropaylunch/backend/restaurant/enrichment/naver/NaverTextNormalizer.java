package com.zeropaylunch.backend.restaurant.enrichment.naver;

import java.text.Normalizer;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.web.util.HtmlUtils;

@Component
class NaverTextNormalizer {

    private static final Pattern HTML_TAG = Pattern.compile("<[^>]*>");
    private static final Pattern PARENTHESIZED = Pattern.compile("\\([^)]*\\)|\\[[^]]*]");
    private static final Pattern BRANCH_IN_PARENTHESES =
            Pattern.compile("\\(([^)]*점)\\)\\s*$|\\[([^]]*점)]\\s*$");
    private static final Pattern TRAILING_BRANCH =
            Pattern.compile("(?:\\s+|[-_/])([\\p{L}\\p{N}]{1,12}점)\\s*$");
    private static final Pattern NON_TEXT = Pattern.compile("[^\\p{L}\\p{N}]+");
    private static final Pattern WHITESPACE = Pattern.compile("\\s+");

    String normalizeName(String value) {
        if (!StringUtils.hasText(value)) {
            return "";
        }
        return compact(cleanTitle(value));
    }

    NaverNameProfile nameProfile(String value) {
        String cleaned = cleanTitle(value);
        if (!StringUtils.hasText(cleaned)) {
            return new NaverNameProfile("", "", "", null);
        }
        String branch = branchName(cleaned);
        String base = cleaned;
        Matcher parenthesized = BRANCH_IN_PARENTHESES.matcher(cleaned);
        if (parenthesized.find()) {
            base = cleaned.substring(0, parenthesized.start());
        } else {
            Matcher trailing = TRAILING_BRANCH.matcher(cleaned);
            if (trailing.find()) {
                base = cleaned.substring(0, trailing.start());
            }
        }
        String withoutParentheses = PARENTHESIZED.matcher(cleaned).replaceAll(" ");
        return new NaverNameProfile(
                compact(cleaned),
                compact(withoutParentheses),
                compact(base),
                branch == null ? null : compact(branch));
    }

    String cleanTitle(String value) {
        if (!StringUtils.hasText(value)) {
            return null;
        }
        String decoded = HtmlUtils.htmlUnescape(value);
        String withoutTags = HTML_TAG.matcher(decoded).replaceAll(" ");
        return WHITESPACE.matcher(withoutTags).replaceAll(" ").trim();
    }

    String normalizeAddress(String value) {
        if (!StringUtils.hasText(value)) {
            return "";
        }
        String address = Normalizer.normalize(value, Normalizer.Form.NFKC)
                .replace("서울특별시", "서울")
                .replace("서울시", "서울");
        address = PARENTHESIZED.matcher(address).replaceAll(" ");
        return normalizeWords(address);
    }

    double similarity(String left, String right) {
        if (!StringUtils.hasText(left) || !StringUtils.hasText(right)) {
            return 0.0;
        }
        if (left.equals(right)) {
            return 1.0;
        }
        int[] previous = new int[right.length() + 1];
        int[] current = new int[right.length() + 1];
        for (int column = 0; column <= right.length(); column++) {
            previous[column] = column;
        }
        for (int row = 1; row <= left.length(); row++) {
            current[0] = row;
            for (int column = 1; column <= right.length(); column++) {
                int substitution = left.charAt(row - 1) == right.charAt(column - 1) ? 0 : 1;
                current[column] = Math.min(
                        Math.min(current[column - 1] + 1, previous[column] + 1),
                        previous[column - 1] + substitution);
            }
            int[] swap = previous;
            previous = current;
            current = swap;
        }
        int maximumLength = Math.max(left.length(), right.length());
        return 1.0 - (double) previous[right.length()] / maximumLength;
    }

    double addressTokenSimilarity(String left, String right) {
        Set<String> leftTokens = tokens(left);
        Set<String> rightTokens = tokens(right);
        if (leftTokens.isEmpty() || rightTokens.isEmpty()) {
            return 0.0;
        }
        Set<String> intersection = new HashSet<>(leftTokens);
        intersection.retainAll(rightTokens);
        Set<String> union = new HashSet<>(leftTokens);
        union.addAll(rightTokens);
        return (double) intersection.size() / union.size();
    }

    boolean containsDong(String normalizedAddress, String legalDongName) {
        String normalizedDong = normalizeAddress(legalDongName);
        return StringUtils.hasText(normalizedDong) && normalizedAddress.contains(normalizedDong);
    }

    private String branchName(String cleaned) {
        Matcher parenthesized = BRANCH_IN_PARENTHESES.matcher(cleaned);
        if (parenthesized.find()) {
            return parenthesized.group(1) == null
                    ? parenthesized.group(2) : parenthesized.group(1);
        }
        Matcher trailing = TRAILING_BRANCH.matcher(cleaned);
        return trailing.find() ? trailing.group(1) : null;
    }

    private String compact(String value) {
        return normalizeWords(value).replace(" ", "");
    }

    private String normalizeWords(String value) {
        String normalized = Normalizer.normalize(value, Normalizer.Form.NFKC).toLowerCase();
        normalized = NON_TEXT.matcher(normalized).replaceAll(" ");
        return WHITESPACE.matcher(normalized).replaceAll(" ").trim();
    }

    private Set<String> tokens(String value) {
        if (!StringUtils.hasText(value)) {
            return Set.of();
        }
        return new HashSet<>(Arrays.asList(value.split(" ")));
    }
}
