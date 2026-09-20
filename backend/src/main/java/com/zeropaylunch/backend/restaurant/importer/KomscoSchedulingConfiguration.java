package com.zeropaylunch.backend.restaurant.importer;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Configuration;

@Configuration
@ConditionalOnProperty(prefix = "app.komsco", name = "scheduler-enabled", havingValue = "true")
class KomscoSchedulingConfiguration {}
