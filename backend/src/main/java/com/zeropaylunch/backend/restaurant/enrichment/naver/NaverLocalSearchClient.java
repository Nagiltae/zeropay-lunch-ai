package com.zeropaylunch.backend.restaurant.enrichment.naver;

interface NaverLocalSearchClient {

    NaverLocalResponse search(String query);
}
