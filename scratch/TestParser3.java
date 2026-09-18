import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class TestParser3 {
    private static final Pattern ROAD_ADDRESS_PATTERN = 
            Pattern.compile("(?:서울(?:특별시|시)?\\s*(?:강남구)?\\s*|강남구\\s*)?([가-힣0-9\\s]+(?:대로|로|길))\\s*(\\d+(?:-\\d+)?)");

    public static void main(String[] args) {
        String[] tests = {
            "강남대로 156길 17-1",
            "서울특별시 강남구 테헤란로 103",
            "서울 강남구 언주로134길 33",
            "강남구 봉은사로29길 12",
            "서울시 삼성로 726",
            "테헤란로 103"
        };
        for (String t : tests) {
            Matcher m = ROAD_ADDRESS_PATTERN.matcher(t);
            if (m.find()) {
                System.out.println(t + " -> Road: " + m.group(1).replace(" ", "") + ", Number: " + m.group(2));
            } else {
                System.out.println(t + " -> NO MATCH");
            }
        }
    }
}
