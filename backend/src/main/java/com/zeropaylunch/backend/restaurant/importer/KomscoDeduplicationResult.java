package com.zeropaylunch.backend.restaurant.importer;

import java.util.List;

record KomscoDeduplicationResult(List<LatestKomscoMerchant> records, int invalidCount) {}
