import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class TestParser2 {
    private static final Pattern ROAD_ADDRESS_PATTERN = 
            Pattern.compile("([가-힣0-9\\s]+(?:대로|로|길))\\s*(\\d+(?:-\\d+)?)");

    public static void main(String[] args) {
        String[] tests = {
            "강남대로 156길 17-1",
            "강남대로156길 17-1",
            "헌릉로569길9",
            "압구정로 34길 16",
            "논현로 175길 61",
            "도곡로63길 28 1층",
            "서울특별시 강남구 테헤란로 103",
            "서울 강남구 언주로134길 33",
            "강남구 봉은사로29길 12"
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
