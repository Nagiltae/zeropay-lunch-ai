package com.zeropaylunch.backend.meal.api;

import com.zeropaylunch.backend.meal.application.MealHistoryService;
import com.zeropaylunch.backend.meal.application.MealHistoryService.MealRecord;
import jakarta.validation.Valid;
import java.util.List;
import java.util.UUID;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/meals")
public class MealHistoryController {

    private final MealHistoryService mealHistoryService;

    public MealHistoryController(MealHistoryService mealHistoryService) {
        this.mealHistoryService = mealHistoryService;
    }

    @GetMapping("/recent")
    public List<MealRecord> recent(Authentication authentication) {
        return mealHistoryService.findRecent((UUID) authentication.getPrincipal());
    }

    @PostMapping
    public MealRecord markEaten(
            @Valid @RequestBody MarkMealRequest request,
            Authentication authentication
    ) {
        return mealHistoryService.markEaten(
                (UUID) authentication.getPrincipal(),
                request.sourceMessageId(),
                request.restaurantId()
        );
    }
}
