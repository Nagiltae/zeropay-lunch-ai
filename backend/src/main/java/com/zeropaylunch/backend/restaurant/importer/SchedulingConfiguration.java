package com.zeropaylunch.backend.restaurant.importer;

import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

/** Enables the scheduling infrastructure; individual jobs own their enable flags. */
@Configuration
@EnableScheduling
class SchedulingConfiguration {
}
