import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class TestParser4 {
    private static final Pattern ROAD_ADDRESS_PATTERN = 
            Pattern.compile("(?:서울(?:특별시|시)?\\s*(?:강남구)?\\s*|강남구\\s*)?([가-힣0-9\\s]+(?:대로|로|길))\\s*(\\d+(?:-\\d+)?)");

    public static void main(String[] args) {
        String[] tests = {
            "논현로71길 29",
            "논현로71길 37",
            "논현로71길 29 ",
            "테스트가게 논현로71길 29",
            "서울특별시 강남구 논현로71길 29"
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
