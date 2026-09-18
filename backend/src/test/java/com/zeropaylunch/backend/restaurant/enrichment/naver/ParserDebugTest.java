package com.zeropaylunch.backend.restaurant.enrichment.naver;

import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

public class ParserDebugTest {
    @Test
    void debug() {
        NaverTextNormalizer normalizer = new NaverTextNormalizer();
        String source = normalizer.normalizeAddress("논현로71길 29" + " ");
        String candidate = normalizer.normalizeAddress("논현로71길 37");
        
        System.out.println("Source: [" + source + "]");
        System.out.println("Candidate: [" + candidate + "]");
        System.out.println("Contains: " + source.contains(candidate) + " / " + candidate.contains(source));
    }
}
