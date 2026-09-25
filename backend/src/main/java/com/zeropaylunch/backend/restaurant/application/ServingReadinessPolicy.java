package com.zeropaylunch.backend.restaurant.application;

import java.util.ArrayList;
import java.util.List;

/** Serving eligibility is separate from Semantic Profile input readiness. */
public final class ServingReadinessPolicy {
    public enum Status { READY, NOT_READY }

    public record Decision(Status status, List<String> reasons) {
        public Decision {
            reasons = List.copyOf(reasons);
        }
    }

    public Decision assess(boolean active, boolean eligible, boolean zeroPay, boolean targetArea,
            boolean identityVerified, boolean menuCurrent, boolean hasMenu,
            boolean hoursCurrent, VerifiedHoursPolicy.Decision hours,
            boolean budgetRequested, boolean hasApprovedBudgetClassification) {
        List<String> reasons = new ArrayList<>();
        if (!active) reasons.add("INACTIVE");
        if (!eligible) reasons.add("NOT_ELIGIBLE");
        if (!zeroPay) reasons.add("ZERO_PAY_UNAVAILABLE");
        if (!targetArea) reasons.add("OUTSIDE_SERVICE_AREA");
        if (!identityVerified) reasons.add("NO_VERIFIED_IDENTITY");
        if (!menuCurrent) reasons.add("STALE_OR_UNVERIFIED_MENU");
        if (!hasMenu) reasons.add("NO_CURRENT_MENU");
        if (!hoursCurrent) reasons.add("STALE_OR_UNVERIFIED_HOURS");
        if (hours == null || hours.status() == VerifiedHoursPolicy.Status.UNKNOWN) {
            reasons.add("HOURS_UNCERTAIN");
        } else if (hours.status() == VerifiedHoursPolicy.Status.CLOSED) {
            reasons.add("CLOSED_NOW");
        }
        if (budgetRequested && !hasApprovedBudgetClassification) {
            reasons.add("BUDGET_CLASSIFICATION_UNKNOWN");
        }
        return new Decision(reasons.isEmpty() ? Status.READY : Status.NOT_READY, reasons);
    }
}
