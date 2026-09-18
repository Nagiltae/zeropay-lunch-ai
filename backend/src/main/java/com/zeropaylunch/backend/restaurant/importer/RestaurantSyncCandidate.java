package com.zeropaylunch.backend.restaurant.importer;

import com.zeropaylunch.backend.restaurant.domain.RestaurantSourceSnapshot;

record RestaurantSyncCandidate(RestaurantSourceSnapshot snapshot, boolean eligible) {}
