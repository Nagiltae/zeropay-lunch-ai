package com.zeropaylunch.backend.restaurant.application;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.junit.jupiter.api.Test;

class ServingReadinessPolicyTests {
    private final ServingReadinessPolicy policy = new ServingReadinessPolicy();

    @Test
    void separatesCurrentServingInputsFromSemanticProfileAndCategoryFields() {
        var open = new VerifiedHoursPolicy.Decision(VerifiedHoursPolicy.Status.OPEN, List.of());

        var result = policy.assess(true, true, true, true, true, true, true, true,
                open, false, false);

        assertThat(result.status()).isEqualTo(ServingReadinessPolicy.Status.READY);
        assertThat(result.reasons()).isEmpty();
    }

    @Test
    void doesNotPassUnknownBudgetClassificationOrUncertainHours() {
        var unknownHours = new VerifiedHoursPolicy.Decision(VerifiedHoursPolicy.Status.UNKNOWN,
                List.of("UNRESOLVED_DATE_EXCEPTION"));

        var result = policy.assess(true, true, true, true, true, true, true, true,
                unknownHours, true, false);

        assertThat(result.status()).isEqualTo(ServingReadinessPolicy.Status.NOT_READY);
        assertThat(result.reasons()).contains("HOURS_UNCERTAIN", "BUDGET_CLASSIFICATION_UNKNOWN");
    }
}
