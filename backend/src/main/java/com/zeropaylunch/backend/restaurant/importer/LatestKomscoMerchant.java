package com.zeropaylunch.backend.restaurant.importer;

import java.time.LocalDate;

record LatestKomscoMerchant(KomscoMerchantRecord source, LocalDate referenceDate) {}
