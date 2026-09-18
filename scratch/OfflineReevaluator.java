import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.text.Normalizer;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;

public class OfflineReevaluator {
    private static final Pattern HTML_TAG = Pattern.compile("<[^>]*>");
    private static final Pattern PARENTHESIZED = Pattern.compile("\\([^)]*\\)|\\[[^]]*\\]");
    private static final Pattern NON_TEXT = Pattern.compile("[^\\p{L}\\p{N}]+");
    private static final Pattern WHITESPACE = Pattern.compile("\\s+");
    private static final Pattern ROAD_ADDRESS_PATTERN = 
            Pattern.compile("^(?:서울(?:특별시|시)?\\s*(?:강남구)?\\s*|강남구\\s*)?([가-힣a-zA-Z0-9\\s]+(?:대로|로|길))\\s*(\\d+(?:-\\d+)?)");

    public static void main(String[] args) throws Exception {
        List<String> lines = Files.readAllLines(Path.of("backend/build/reports/naver-enrichment/naver-all-20260919-033129.csv"));
        
        int beforeMatched = 0, beforeAmbiguous = 0, beforeUnmatched = 0;
        int afterMatched = 0, afterAmbiguous = 0, afterUnmatched = 0;
        int matchedToAmbiguous = 0, matchedToUnmatched = 0, ambiguousToMatched = 0, unmatchedToMatched = 0;

        StringBuilder reportCsv = new StringBuilder();
        reportCsv.append("restaurant_id,komsco_name,naver_name,komsco_address,naver_address,parsed_komsco_road,parsed_komsco_number,parsed_naver_road,parsed_naver_number,name_score,address_score,distance_score,category_score,total_score,distance_meters,match_status,recommendation_eligibility\n");

        for (int i = 1; i < lines.size(); i++) {
            String line = lines.get(i);
            if (line.trim().isEmpty()) continue;
            
            // Simple CSV split (not handling commas inside quotes properly if there are any, but let's assume it's mostly safe or we can use a basic regex)
            String[] parts = line.split(",(?=(?:[^\"]*\"[^\"]*\")*[^\"]*$)");
            for (int j = 0; j < parts.length; j++) {
                if (parts[j].startsWith("\"") && parts[j].endsWith("\"")) {
                    parts[j] = parts[j].substring(1, parts[j].length() - 1);
                }
            }

            String restaurantId = parts[0];
            String komscoName = parts[1];
            String komscoAddress = parts[2];
            String legalDong = parts[5];
            String naverTitle = parts[8];
            String naverCategory = parts[9];
            String naverAddress = parts[10];
            String naverRoadAddress = parts[11];
            
            double nameScore = Double.parseDouble(parts[14]);
            double oldAddressScore = Double.parseDouble(parts[15]);
            double distanceScore = Double.parseDouble(parts[16]);
            double categoryScore = Double.parseDouble(parts[17]);
            double oldTotalScore = Double.parseDouble(parts[18]);
            String distanceMetersStr = parts[19];
            Double distanceMeters = distanceMetersStr.isEmpty() ? null : Double.parseDouble(distanceMetersStr);
            String oldRunnerUpScoreStr = parts[20];
            Double runnerUpScore = oldRunnerUpScoreStr.isEmpty() ? null : Double.parseDouble(oldRunnerUpScoreStr);
            String oldMatchStatus = parts[22];

            if ("MATCHED".equals(oldMatchStatus)) beforeMatched++;
            if ("AMBIGUOUS".equals(oldMatchStatus)) beforeAmbiguous++;
            if ("UNMATCHED".equals(oldMatchStatus)) beforeUnmatched++;

            // Evaluate new address score
            String sourceNorm = normalizeAddress(komscoAddress);
            String roadNorm = normalizeAddress(naverRoadAddress);
            String parcelNorm = normalizeAddress(naverAddress);

            double roadScore = singleAddressScore(sourceNorm, roadNorm);
            double parcelScore = singleAddressScore(sourceNorm, parcelNorm);
            double bestAddressScore = Math.max(roadScore, parcelScore);

            if (bestAddressScore == 0.0 && (containsDong(roadNorm, legalDong) || containsDong(parcelNorm, legalDong))) {
                bestAddressScore = 8.0; // sameDongScore
            }

            double newTotalScore = nameScore + bestAddressScore + distanceScore + categoryScore;

            // Recalculate status
            Double gap = runnerUpScore == null ? null : newTotalScore - runnerUpScore;
            String newStatus;
            
            boolean hasStrongEvidence = (bestAddressScore >= 25.0) || (nameScore >= 32.0 && distanceMeters != null && distanceMeters <= 50.0);

            if (newTotalScore < 45.0) {
                newStatus = "UNMATCHED";
            } else if (newTotalScore >= 70.0 && (gap == null || gap >= 8.0) && hasStrongEvidence) {
                newStatus = "MATCHED";
            } else {
                newStatus = "AMBIGUOUS";
            }

            if ("MATCHED".equals(newStatus)) afterMatched++;
            if ("AMBIGUOUS".equals(newStatus)) afterAmbiguous++;
            if ("UNMATCHED".equals(newStatus)) afterUnmatched++;

            if ("MATCHED".equals(oldMatchStatus) && "AMBIGUOUS".equals(newStatus)) {
                matchedToAmbiguous++;
                System.out.println("DEMOTED: " + komscoName + " (" + komscoAddress + " -> " + naverRoadAddress + ") OldAdd:" + oldAddressScore + " NewAdd:" + bestAddressScore);
            }
            if ("MATCHED".equals(oldMatchStatus) && "UNMATCHED".equals(newStatus)) matchedToUnmatched++;
            if ("AMBIGUOUS".equals(oldMatchStatus) && "MATCHED".equals(newStatus)) ambiguousToMatched++;
            if ("UNMATCHED".equals(oldMatchStatus) && "MATCHED".equals(newStatus)) unmatchedToMatched++;

            // If it's a risky matched case, add to report
            boolean isRiskyMatched = "MATCHED".equals(newStatus) && (
                newTotalScore <= 80 || (distanceMeters != null && distanceMeters >= 30) ||
                bestAddressScore < 25 || nameScore < 40
            );

            if (isRiskyMatched) {
                String[] parsedSource = parseAddress(sourceNorm);
                String[] parsedNaver = parseAddress(roadNorm);
                if (parsedNaver == null) parsedNaver = parseAddress(parcelNorm);

                String pSourceRoad = parsedSource != null ? parsedSource[0] : "";
                String pSourceNum = parsedSource != null ? parsedSource[1] : "";
                String pNaverRoad = parsedNaver != null ? parsedNaver[0] : "";
                String pNaverNum = parsedNaver != null ? parsedNaver[1] : "";

                reportCsv.append(String.format("\"%s\",\"%s\",\"%s\",\"%s\",\"%s\",\"%s\",\"%s\",\"%s\",\"%s\",%.1f,%.1f,%.1f,%.1f,%.1f,%s,\"%s\",\"%s\"\n",
                        restaurantId, komscoName, naverTitle, komscoAddress, naverRoadAddress.isEmpty() ? naverAddress : naverRoadAddress,
                        pSourceRoad, pSourceNum, pNaverRoad, pNaverNum,
                        nameScore, bestAddressScore, distanceScore, categoryScore, newTotalScore,
                        distanceMetersStr, newStatus, "ELIGIBLE"
                ));
            }
        }

        System.out.println("=== Before / After ===");
        System.out.println("Before MATCHED: " + beforeMatched);
        System.out.println("Before AMBIGUOUS: " + beforeAmbiguous);
        System.out.println("Before UNMATCHED: " + beforeUnmatched);
        System.out.println("After MATCHED: " + afterMatched);
        System.out.println("After AMBIGUOUS: " + afterAmbiguous);
        System.out.println("After UNMATCHED: " + afterUnmatched);
        System.out.println("MATCHED -> AMBIGUOUS: " + matchedToAmbiguous);
        System.out.println("MATCHED -> UNMATCHED: " + matchedToUnmatched);
        System.out.println("AMBIGUOUS -> MATCHED: " + ambiguousToMatched);
        System.out.println("UNMATCHED -> MATCHED: " + unmatchedToMatched);

        Files.writeString(Path.of("backend/build/reports/naver-enrichment/naver-full-review-address-v2-1.csv"), reportCsv.toString());
        System.out.println("Saved risky matched report to: backend/build/reports/naver-enrichment/naver-full-review-address-v2-1.csv");
    }

    private static String normalizeAddress(String value) {
        if (value == null || value.isEmpty()) return "";
        String address = Normalizer.normalize(value, Normalizer.Form.NFKC)
                .replace("서울특별시", "서울")
                .replace("서울시", "서울");
        address = PARENTHESIZED.matcher(address).replaceAll(" ");
        return normalizeWords(address);
    }
    
    private static String normalizeWords(String value) {
        String normalized = Normalizer.normalize(value, Normalizer.Form.NFKC).toLowerCase();
        normalized = NON_TEXT.matcher(normalized).replaceAll(" ");
        return WHITESPACE.matcher(normalized).replaceAll(" ").trim();
    }

    private static boolean containsDong(String normalizedAddress, String legalDongName) {
        String normalizedDong = normalizeAddress(legalDongName);
        return !normalizedDong.isEmpty() && normalizedAddress.contains(normalizedDong);
    }

    private static String[] parseAddress(String address) {
        if (address == null || address.isEmpty()) return null;
        Matcher m = ROAD_ADDRESS_PATTERN.matcher(address);
        if (m.find()) {
            return new String[]{m.group(1).replace(" ", ""), m.group(2)};
        }
        return null;
    }

    private static double singleAddressScore(String source, String candidate) {
        if (source == null || source.isEmpty() || candidate == null || candidate.isEmpty()) return 0.0;

        String[] pSource = parseAddress(source);
        String[] pCandidate = parseAddress(candidate);

        if (pSource != null && pCandidate != null) {
            if (pSource[0].equals(pCandidate[0])) {
                if (pSource[1].equals(pCandidate[1])) {
                    return 30.0;
                } else {
                    return 0.0;
                }
            }
        }

        if (source.equals(candidate) || source.contains(candidate) || candidate.contains(source)) {
            return 30.0;
        }

        Set<String> leftTokens = new HashSet<>(Arrays.asList(source.split(" ")));
        Set<String> rightTokens = new HashSet<>(Arrays.asList(candidate.split(" ")));
        if (leftTokens.isEmpty() || rightTokens.isEmpty()) return 0.0;
        Set<String> intersection = new HashSet<>(leftTokens);
        intersection.retainAll(rightTokens);
        Set<String> union = new HashSet<>(leftTokens);
        union.addAll(rightTokens);
        double similarity = (double) intersection.size() / union.size();

        if (similarity >= 0.70) return 25.0;
        if (similarity >= 0.45) return 15.0;
        return 0.0;
    }
}
