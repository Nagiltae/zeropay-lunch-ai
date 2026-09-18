package com.zeropaylunch.backend.restaurant.enrichment.naver;

import java.util.List;
import java.util.Locale;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

@Component
class NaverRestaurantCategoryPolicy {

    private static final List<String> FOOD_CATEGORY_TERMS = List.of(
            "음식점", "한식", "중식", "일식", "양식", "분식", "카페", "디저트",
            "베이커리", "치킨", "피자", "햄버거", "패스트푸드", "술집", "주점",
            "아시아음식", "샌드위치", "도시락", "육류", "고기요리", "해물", "생선요리");

    private static final List<String> NON_FOOD_CATEGORY_TERMS = List.of(
            "약국", "병원", "의료", "복지", "소프트웨어", "컴퓨터프로그래밍",
            "공인중개", "부동산", "쇼핑,유통", "의류", "패션", "미용", "세탁",
            "학원", "교육");

    NaverCategoryClassification classify(String category) {
        if (!StringUtils.hasText(category)) {
            return NaverCategoryClassification.UNKNOWN;
        }
        String normalized = category.toLowerCase(Locale.ROOT);
        if (FOOD_CATEGORY_TERMS.stream().anyMatch(normalized::contains)) {
            return NaverCategoryClassification.FOOD;
        }
        if (NON_FOOD_CATEGORY_TERMS.stream().anyMatch(normalized::contains)) {
            return NaverCategoryClassification.NON_FOOD;
        }
        return NaverCategoryClassification.UNKNOWN;
    }

    boolean isFoodCategory(String category) {
        return classify(category) == NaverCategoryClassification.FOOD;
    }

    boolean isExplicitlyNonFoodCategory(String category) {
        return classify(category) == NaverCategoryClassification.NON_FOOD;
    }
}
