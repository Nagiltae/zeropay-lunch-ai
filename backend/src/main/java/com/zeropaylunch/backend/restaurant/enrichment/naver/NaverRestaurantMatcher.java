package com.zeropaylunch.backend.restaurant.enrichment.naver;

import com.zeropaylunch.backend.restaurant.domain.ExternalPlaceMatchStatus;
import com.zeropaylunch.backend.restaurant.domain.Restaurant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

@Component
class NaverRestaurantMatcher {

    private final NaverTextNormalizer normalizer;
    private final GeoDistanceCalculator distanceCalculator;
    private final NaverCoordinateParser coordinateParser;
    private final NaverCandidateHardGate hardGate;
    private final NaverAddressParser addressParser;
    private final NaverMatchingProperties policy;

    NaverRestaurantMatcher(
            NaverTextNormalizer normalizer,
            GeoDistanceCalculator distanceCalculator,
            NaverCoordinateParser coordinateParser,
            NaverCandidateHardGate hardGate,
            NaverAddressParser addressParser,
            NaverMatchingProperties policy) {
        this.normalizer = normalizer;
        this.distanceCalculator = distanceCalculator;
        this.coordinateParser = coordinateParser;
        this.hardGate = hardGate;
        this.addressParser = addressParser;
        this.policy = policy;
    }

    NaverMatchDecision match(
            Restaurant restaurant, List<NaverSearchCandidate> candidates, String lastQuery) {
        List<NaverCandidateScore> scores = distinct(candidates).stream()
                .map(candidate -> score(restaurant, candidate))
                .filter(candidate -> candidate != null)
                .sorted(Comparator.comparingDouble(NaverCandidateScore::totalScore).reversed())
                .toList();
        if (scores.isEmpty()) {
            return new NaverMatchDecision(
                    ExternalPlaceMatchStatus.UNMATCHED, null, null, null, lastQuery);
        }

        NaverCandidateScore best = scores.getFirst();
        Double runnerUpScore = scores.size() == 1 ? null : scores.get(1).totalScore();
        Double gap = runnerUpScore == null ? null : best.totalScore() - runnerUpScore;
        ExternalPlaceMatchStatus status;
        if (best.totalScore() < policy.viableThreshold()) {
            status = ExternalPlaceMatchStatus.UNMATCHED;
        } else if (best.totalScore() >= policy.matchedThreshold()
                && (gap == null || gap >= policy.ambiguityMargin())
                && hardGate.hasStrongEvidence(
                        best.nameScore(), best.addressScore(), best.distanceMeters())) {
            status = ExternalPlaceMatchStatus.MATCHED;
        } else {
            status = ExternalPlaceMatchStatus.AMBIGUOUS;
        }
        return new NaverMatchDecision(
                status, best, runnerUpScore, gap, best.candidate().query());
    }

    private NaverCandidateScore score(Restaurant restaurant, NaverSearchCandidate candidate) {
        NaverLocalItem item = candidate.item();
        var candidateLatitude = coordinateParser.latitude(item.mapy());
        var candidateLongitude = coordinateParser.longitude(item.mapx());
        Double distance = distanceCalculator.distanceMeters(
                restaurant.getLatitude(), restaurant.getLongitude(),
                candidateLatitude, candidateLongitude);
        if (distance != null && distance > policy.maximumDistanceMeters()) {
            return null;
        }

        double nameScore = nameScore(restaurant.getName(), item.title());
        if (nameScore < 0.0 || !hardGate.acceptsCandidate(item.category(), nameScore)) {
            return null;
        }
        double addressScore = addressScore(restaurant, item);
        double distanceScore = distanceScore(distance);
        double categoryScore = hardGate.isFoodCategory(item.category())
                ? policy.categoryScore() : 0.0;
        return new NaverCandidateScore(
                candidate,
                nameScore,
                addressScore,
                distanceScore,
                categoryScore,
                nameScore + addressScore + distanceScore + categoryScore,
                distance);
    }

    private double nameScore(String sourceName, String candidateName) {
        NaverNameProfile source = normalizer.nameProfile(sourceName);
        NaverNameProfile candidate = normalizer.nameProfile(candidateName);
        if (!StringUtils.hasText(source.normalizedFull())
                || !StringUtils.hasText(candidate.normalizedFull())) {
            return 0.0;
        }
        if (source.branchName() != null && candidate.branchName() != null
                && !source.branchName().equals(candidate.branchName())) {
            return -1.0;
        }
        if (source.normalizedFull().equals(candidate.normalizedFull())) {
            return policy.nameExactScore();
        }
        if (sameNonEmpty(source.normalizedWithoutParentheses(),
                candidate.normalizedWithoutParentheses())) {
            return policy.nameExactScore();
        }
        if (sameNonEmpty(source.normalizedBase(), candidate.normalizedBase())
                || source.normalizedFull().contains(candidate.normalizedFull())
                || candidate.normalizedFull().contains(source.normalizedFull())) {
            return policy.nameContainsScore();
        }
        double similarity = Math.max(
                normalizer.similarity(source.normalizedFull(), candidate.normalizedFull()),
                normalizer.similarity(source.normalizedBase(), candidate.normalizedBase()));
        if (similarity >= policy.highNameSimilarity()) {
            return policy.nameHighSimilarityScore();
        }
        if (similarity >= policy.moderateNameSimilarity()) {
            return policy.nameModerateSimilarityScore();
        }
        return 0.0;
    }

    private double addressScore(Restaurant restaurant, NaverLocalItem item) {
        String source = normalizer.normalizeAddress(
                restaurant.getAddress() + " " + nullToEmpty(restaurant.getDetailAddress()));
        String road = normalizer.normalizeAddress(item.roadAddress());
        String parcel = normalizer.normalizeAddress(item.address());
        double roadScore = singleAddressScore(source, road);
        double parcelScore = singleAddressScore(source, parcel);
        double best = Math.max(roadScore, parcelScore);
        if (best == 0.0 && (normalizer.containsDong(road, restaurant.getLegalDongName())
                || normalizer.containsDong(parcel, restaurant.getLegalDongName()))) {
            return policy.sameDongScore();
        }
        return best;
    }

    private double singleAddressScore(String source, String candidate) {
        if (!StringUtils.hasText(source) || !StringUtils.hasText(candidate)) {
            return 0.0;
        }

        NaverAddressParser.ParsedAddress parsedSource = addressParser.parse(source);
        NaverAddressParser.ParsedAddress parsedCandidate = addressParser.parse(candidate);

        if (parsedSource != null && parsedCandidate != null) {
            System.out.println("DEBUG: source=" + source + " (" + parsedSource + ")");
            System.out.println("DEBUG: candidate=" + candidate + " (" + parsedCandidate + ")");
            if (parsedSource.roadName().equals(parsedCandidate.roadName())) {
                if (parsedSource.buildingNumber().equals(parsedCandidate.buildingNumber())) {
                    System.out.println("DEBUG: return exact!");
                    return policy.addressExactScore();
                } else {
                    System.out.println("DEBUG: return 0.0!");
                    return 0.0;
                }
            }
        }

        System.out.println("DEBUG: fallback contains? " + source + " / " + candidate);

        if (source.equals(candidate) || source.contains(candidate) || candidate.contains(source)) {
            return policy.addressExactScore();
        }
        double similarity = normalizer.addressTokenSimilarity(source, candidate);
        if (similarity >= policy.highAddressSimilarity()) {
            return policy.addressHighSimilarityScore();
        }
        if (similarity >= policy.moderateAddressSimilarity()) {
            return policy.addressModerateSimilarityScore();
        }
        return 0.0;
    }

    private double distanceScore(Double distance) {
        if (distance == null) {
            return 0.0;
        }
        if (distance <= 50.0) {
            return policy.distance50mScore();
        }
        if (distance <= 100.0) {
            return policy.distance100mScore();
        }
        return policy.distance300mScore();
    }

    private List<NaverSearchCandidate> distinct(List<NaverSearchCandidate> candidates) {
        Map<String, NaverSearchCandidate> distinct = new LinkedHashMap<>();
        for (NaverSearchCandidate candidate : candidates) {
            NaverLocalItem item = candidate.item();
            String key = normalizer.normalizeName(item.title()) + '|'
                    + normalizer.normalizeAddress(
                            StringUtils.hasText(item.roadAddress())
                                    ? item.roadAddress() : item.address()) + '|'
                    + nullToEmpty(item.mapx()) + '|' + nullToEmpty(item.mapy());
            distinct.putIfAbsent(key, candidate);
        }
        return new ArrayList<>(distinct.values());
    }

    private String nullToEmpty(String value) {
        return value == null ? "" : value;
    }

    private boolean sameNonEmpty(String left, String right) {
        return StringUtils.hasText(left) && left.equals(right);
    }
}
