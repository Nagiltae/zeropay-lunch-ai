package com.zeropaylunch.backend.restaurant.importer;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

@Configuration
@EnableScheduling
@ConditionalOnProperty(prefix = "app.komsco", name = "scheduler-enabled", havingValue = "true")
class KomscoSchedulingConfiguration {}
