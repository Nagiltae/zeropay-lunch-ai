package com.zeropaylunch.backend.recommendation.application;

import com.zeropaylunch.backend.meal.application.MealHistoryService;
import com.zeropaylunch.backend.preference.application.UserPreferenceService;
import com.zeropaylunch.backend.preference.application.UserPreferenceService.PreferenceSnapshot;
import com.zeropaylunch.backend.recommendation.ai.AiIntentAnalyzer;
import com.zeropaylunch.backend.recommendation.ai.AnalyzedIntent;
import com.zeropaylunch.backend.recommendation.ai.IntentAnalysisRequest;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class RecommendationContextService {

    private final UserPreferenceService preferenceService;
    private final MealHistoryService mealHistoryService;
    private final AiIntentAnalyzer intentAnalyzer;

    public RecommendationContextService(
            UserPreferenceService preferenceService,
            MealHistoryService mealHistoryService,
            AiIntentAnalyzer intentAnalyzer
    ) {
        this.preferenceService = preferenceService;
        this.mealHistoryService = mealHistoryService;
        this.intentAnalyzer = intentAnalyzer;
    }

    @Transactional(readOnly = true)
    public RecommendationContext build(UUID userId, String message) {
        PreferenceSnapshot preferences = preferenceService.get(userId);
        var recentMeals = mealHistoryService.findRecent(userId);
        IntentAnalysisRequest request = new IntentAnalysisRequest(
                message,
                preferences.defaultBudget(),
                preferences.spiceLevel(),
                preferences.preferredCategories(),
                preferences.dislikedCategories(),
                preferences.allergies(),
                recentMeals.stream()
                        .map(meal -> new IntentAnalysisRequest.RecentMeal(
                                meal.restaurantId(), meal.category(), meal.eatenAt()
                        ))
                        .toList()
        );
        AnalyzedIntent intent = intentAnalyzer.analyze(request);
        return new RecommendationContext(request, intent);
    }

    public record RecommendationContext(
            IntentAnalysisRequest request,
            AnalyzedIntent intent
    ) {
    }
}
