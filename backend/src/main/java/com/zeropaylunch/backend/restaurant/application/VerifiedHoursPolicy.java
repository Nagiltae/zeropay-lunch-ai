package com.zeropaylunch.backend.restaurant.application;

import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.LocalTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Fail-closed interpretation for source-grounded NAVER recurring hours. */
public final class VerifiedHoursPolicy {
    private static final Pattern TIME = Pattern.compile("^(\\d{1,2}):(\\d{2})$");
    private static final Pattern DATED_CLOSURE = Pattern.compile(
            "([월화수목금토일])\\s*\\((\\d{1,2})/(\\d{1,2})\\)\\s*[^월화수목금토일]{0,24}(휴무|정기휴무)");
    private static final Pattern WEEKDAY = Pattern.compile("월|화|수|목|금|토|일");
    private static final Pattern WEEKLY_CLOSURE = Pattern.compile("매주\\s*([월화수목금토일])(?:요일)?");

    public enum Status { OPEN, CLOSED, UNKNOWN }

    public record SourceHours(
            String day,
            String openTime,
            String closeTime,
            String breakHours,
            String regularClosedDay,
            String irregularClosedDay,
            String description
    ) { }

    public record Decision(Status status, List<String> reasons) {
        public Decision {
            reasons = List.copyOf(reasons);
        }
    }

    public Decision evaluate(List<SourceHours> rows, LocalDate date, LocalTime time) {
        if (rows == null || rows.isEmpty()) return decision(Status.UNKNOWN, "NO_HOURS");
        if (rows.stream().anyMatch(row -> row.irregularClosedDay() != null
                && !row.irregularClosedDay().isBlank())) {
            return decision(Status.UNKNOWN, "UNRESOLVED_DATE_EXCEPTION");
        }

        boolean dateClosed = false;
        boolean scheduleKnown = false;
        for (SourceHours row : rows) {
            String text = row.description() == null ? "" : row.description();
            if (text.contains("야간휴무") || text.contains("야간 휴무")) {
                return decision(Status.UNKNOWN, "UNRESOLVED_NIGHT_CLOSURE");
            }
            Matcher closure = DATED_CLOSURE.matcher(text);
            while (closure.find()) {
                int month = Integer.parseInt(closure.group(2));
                int day = Integer.parseInt(closure.group(3));
                if (month == date.getMonthValue() && day == date.getDayOfMonth()) dateClosed = true;
            }
        }
        if (dateClosed) return decision(Status.CLOSED, "DATED_CLOSURE_TODAY");
        if (hasRecurringClosure(rows, date.getDayOfWeek())) {
            return decision(Status.CLOSED, "RECURRING_CLOSED_WEEKDAY");
        }

        List<String> reasons = new ArrayList<>();
        for (SourceHours row : rows) {
            boolean appliesToday = applies(row.day(), date.getDayOfWeek());
            boolean appliesYesterday = applies(row.day(), date.getDayOfWeek().minus(1));
            if (!appliesToday && !appliesYesterday) continue;
            Integer open = minute(row.openTime(), false);
            Integer close = minute(row.closeTime(), true);
            if (open == null || close == null || open.equals(close)) {
                reasons.add("UNPARSEABLE_INTERVAL");
                continue;
            }
            scheduleKnown = true;
            int currentMinute = time.toSecondOfDay() / 60;
            boolean overnight = close < open;
            boolean within = overnight
                    ? (appliesToday && currentMinute >= open) || (appliesYesterday && currentMinute < close)
                    : appliesToday && currentMinute >= open && currentMinute < close;
            if (within && row.breakHours() != null && !row.breakHours().isBlank()) {
                Boolean inBreak = inBreak(row.breakHours(), time);
                if (inBreak == null) return decision(Status.UNKNOWN, "UNPARSEABLE_BREAK_INTERVAL");
                if (inBreak) within = false;
            } else if (within && textSuggestsUnparsedBreak(row.description())) {
                return decision(Status.UNKNOWN, "UNSTRUCTURED_BREAK_INTERVAL");
            }
            if (within) return decision(Status.OPEN, close == 1440 ? "OPEN_24_HOURS_INTERVAL" : "WITHIN_VERIFIED_INTERVAL");
        }
        if (scheduleKnown) return decision(Status.CLOSED, "OUTSIDE_VERIFIED_INTERVAL");
        return new Decision(Status.UNKNOWN, reasons.isEmpty() ? List.of("NO_MATCHING_WEEKDAY") : reasons);
    }

    private boolean hasRecurringClosure(List<SourceHours> rows, DayOfWeek day) {
        String korean = koreanDay(day);
        for (SourceHours row : rows) {
            String recurringField = row.regularClosedDay() == null ? "" : row.regularClosedDay();
            Matcher fieldDay = WEEKDAY.matcher(recurringField.replace("요일", ""));
            while (fieldDay.find()) {
                if (fieldDay.group().equals(korean)) return true;
            }
            Matcher descriptionDay = WEEKLY_CLOSURE.matcher(
                    row.description() == null ? "" : row.description());
            while (descriptionDay.find()) if (descriptionDay.group(1).equals(korean)) return true;
        }
        return false;
    }

    private boolean applies(String sourceDay, DayOfWeek day) {
        if (sourceDay == null) return false;
        String normalized = sourceDay.toLowerCase(Locale.ROOT).replace("요일", "").trim();
        return normalized.equals("매일") || normalized.equals(koreanDay(day));
    }

    private String koreanDay(DayOfWeek day) {
        return switch (day) {
            case MONDAY -> "월";
            case TUESDAY -> "화";
            case WEDNESDAY -> "수";
            case THURSDAY -> "목";
            case FRIDAY -> "금";
            case SATURDAY -> "토";
            case SUNDAY -> "일";
        };
    }

    private Integer minute(String value, boolean allowEndOfDay) {
        if (value == null) return null;
        Matcher matcher = TIME.matcher(value.trim());
        if (!matcher.matches()) return null;
        int hour = Integer.parseInt(matcher.group(1));
        int minute = Integer.parseInt(matcher.group(2));
        if (minute > 59 || hour > 24 || (hour == 24 && (!allowEndOfDay || minute != 0))) return null;
        return hour * 60 + minute;
    }

    private Boolean inBreak(String value, LocalTime time) {
        Matcher matcher = Pattern.compile("(\\d{1,2}:\\d{2})\\s*[-~–]\\s*(\\d{1,2}:\\d{2})")
                .matcher(value);
        if (!matcher.matches()) return null;
        Integer start = minute(matcher.group(1), false);
        Integer end = minute(matcher.group(2), true);
        if (start == null || end == null || end <= start) return null;
        int current = time.toSecondOfDay() / 60;
        return current >= start && current < end;
    }

    private boolean textSuggestsUnparsedBreak(String text) {
        return text != null && (text.contains("브레이크타임") || text.contains("브레이크 타임"));
    }

    private Decision decision(Status status, String reason) {
        return new Decision(status, List.of(reason));
    }
}
