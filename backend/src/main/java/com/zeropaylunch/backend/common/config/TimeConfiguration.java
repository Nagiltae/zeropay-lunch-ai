package com.zeropaylunch.backend.common.config;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TimeConfiguration {

    @Bean
    Clock appClock(@Value("${app.time-zone}") String timeZone,
            @Value("${app.fixed-clock-instant:}") String fixedInstant) {
        ZoneId zone = ZoneId.of(timeZone);
        return fixedInstant.isBlank()
                ? Clock.system(zone)
                : Clock.fixed(Instant.parse(fixedInstant), zone);
    }
}
