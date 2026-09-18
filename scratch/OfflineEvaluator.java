import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.List;

public class OfflineEvaluator {
    public static void main(String[] args) throws Exception {
        String url = "jdbc:mysql://localhost:3306/zeropay_lunch";
        String user = "zeropay";
        String password = "zeropay_local";

        int beforeMatched = 0;
        int beforeAmbiguous = 0;
        int beforeUnmatched = 0;

        int afterMatched = 0;
        int afterAmbiguous = 0;
        int afterUnmatched = 0;

        int matchedToAmbiguous = 0;
        int matchedToUnmatched = 0;
        int ambiguousToMatched = 0;
        int unmatchedToMatched = 0;
        
        // This is just a conceptual script. I will execute a Python script to do it more easily with Pandas!
    }
}
