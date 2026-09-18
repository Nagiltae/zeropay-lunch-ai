import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class TestParser5 {
    private static final Pattern ROAD_ADDRESS_PATTERN = 
            Pattern.compile("^(?:서울(?:특별시|시)?\\s*(?:강남구)?\\s*|강남구\\s*)?([가-힣a-zA-Z0-9\\s]+(?:대로|로|길))\\s*(\\d+(?:-\\d+)?)");

    public static void main(String[] args) {
        String[] tests = {
            "논현로71길 29",
            "논현로71길 37",
            "헌릉로569길9",
            "강남대로 156길 17-1 1층"
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
