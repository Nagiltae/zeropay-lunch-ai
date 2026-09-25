package com.zeropaylunch.backend.restaurant.application;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.LocalDate;
import java.time.LocalTime;
import java.util.List;
import org.junit.jupiter.api.Test;

class VerifiedHoursPolicyTests {
    private final VerifiedHoursPolicy policy = new VerifiedHoursPolicy();

    @Test
    void acceptsSameDayAndTwentyFourHourIntervals() {
        var sameDay = policy.evaluate(List.of(hours("매일", "11:00", "22:00", null)),
                LocalDate.of(2026, 9, 25), LocalTime.of(12, 0));
        var allDay = policy.evaluate(List.of(hours("매일", "00:00", "24:00", null)),
                LocalDate.of(2026, 9, 25), LocalTime.of(23, 59));

        assertThat(sameDay.status()).isEqualTo(VerifiedHoursPolicy.Status.OPEN);
        assertThat(allDay.status()).isEqualTo(VerifiedHoursPolicy.Status.OPEN);
    }

    @Test
    void acceptsOvernightBeforeAndAfterMidnight() {
        var beforeMidnight = policy.evaluate(List.of(hours("금", "18:00", "02:00", null)),
                LocalDate.of(2026, 9, 25), LocalTime.of(23, 0));
        var afterMidnight = policy.evaluate(List.of(hours("금", "18:00", "02:00", null)),
                LocalDate.of(2026, 9, 26), LocalTime.of(1, 0));

        assertThat(beforeMidnight.status()).isEqualTo(VerifiedHoursPolicy.Status.OPEN);
        assertThat(afterMidnight.status()).isEqualTo(VerifiedHoursPolicy.Status.OPEN);
    }

    @Test
    void closedDaysAndCurrentDateExceptionsAreClosed() {
        var recurring = new VerifiedHoursPolicy.SourceHours("매일", "00:00", "24:00", null,
                "정기휴무 (매주 금요일)", null, "정기휴무 (매주 금요일)");
        var dateException = hours("매일", "00:00", "24:00", "오늘 휴무 금(9/25) 추석 휴무");

        assertThat(policy.evaluate(List.of(recurring), LocalDate.of(2026, 9, 25), LocalTime.NOON).status())
                .isEqualTo(VerifiedHoursPolicy.Status.CLOSED);
        assertThat(policy.evaluate(List.of(dateException), LocalDate.of(2026, 9, 25), LocalTime.NOON).status())
                .isEqualTo(VerifiedHoursPolicy.Status.CLOSED);
    }

    @Test
    void weeklyClosureDoesNotTreatOtherWeekdayHoursAsClosedDays() {
        var source = hours("목", "14:00", "23:00",
                "정기휴무 (매주 일요일) 월 14:00 - 23:00 화 14:00 - 23:00 수 14:00 - 23:00 목 14:00 - 23:00");

        assertThat(policy.evaluate(List.of(source), LocalDate.of(2026, 9, 24), LocalTime.of(15, 0)).status())
                .isEqualTo(VerifiedHoursPolicy.Status.OPEN);
        assertThat(policy.evaluate(List.of(source), LocalDate.of(2026, 9, 27), LocalTime.of(15, 0)).status())
                .isEqualTo(VerifiedHoursPolicy.Status.CLOSED);
    }

    @Test
    void ambiguousDateExceptionAndBreakFailClosedAsUnknown() {
        var ambiguous = new VerifiedHoursPolicy.SourceHours("매일", "00:00", "24:00", null,
                null, "날짜 미상", "매일 00:00 - 24:00");
        var unparsedBreak = hours("매일", "11:00", "22:00", "매일 브레이크타임 확인 필요");

        assertThat(policy.evaluate(List.of(ambiguous), LocalDate.of(2026, 9, 25), LocalTime.NOON).status())
                .isEqualTo(VerifiedHoursPolicy.Status.UNKNOWN);
        assertThat(policy.evaluate(List.of(unparsedBreak), LocalDate.of(2026, 9, 25), LocalTime.NOON).status())
                .isEqualTo(VerifiedHoursPolicy.Status.UNKNOWN);
    }

    private VerifiedHoursPolicy.SourceHours hours(String day, String open, String close, String description) {
        return new VerifiedHoursPolicy.SourceHours(day, open, close, null, null, null, description);
    }
}
