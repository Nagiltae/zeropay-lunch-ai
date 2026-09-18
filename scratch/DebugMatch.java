package com.zeropaylunch.backend.restaurant.enrichment.naver;
import org.springframework.util.StringUtils;
public class DebugMatch {
    public static void main(String[] args) {
        NaverAddressParser parser = new NaverAddressParser();
        String source = "논현로71길 29 ";
        String candidate = "논현로71길 37";
        System.out.println(parser.parse(source));
        System.out.println(parser.parse(candidate));
    }
}
