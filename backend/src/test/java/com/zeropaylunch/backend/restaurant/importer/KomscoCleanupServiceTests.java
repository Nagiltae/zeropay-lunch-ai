package com.zeropaylunch.backend.restaurant.importer;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.atLeastOnce;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;

class KomscoCleanupServiceTests {

    @Test
    void dryRunOnlyReadsKomscoRowsAndReportsCounts() {
        JdbcTemplate jdbc = mock(JdbcTemplate.class);
        when(jdbc.queryForObject(anyString(), eq(Long.class))).thenReturn(3L);
        KomscoCleanupService service = new KomscoCleanupService(jdbc);

        assertThat(service.dryRun().restaurants()).isEqualTo(3L);
        verify(jdbc, org.mockito.Mockito.atLeastOnce()).queryForObject(
                org.mockito.ArgumentMatchers.contains("source_provider = 'KOMSCO'"), eq(Long.class));
        verify(jdbc, never()).update(anyString());
    }

    @Test
    void cleanupIsTransactionalAndProtectsUserHistoryBySql() throws Exception {
        assertThat(KomscoCleanupService.class.getMethod("cleanup")
                .getAnnotation(Transactional.class)).isNotNull();
        JdbcTemplate jdbc = mock(JdbcTemplate.class);
        when(jdbc.queryForObject(anyString(), eq(Long.class))).thenReturn(0L);
        new KomscoCleanupService(jdbc).cleanup();
        verify(jdbc, atLeastOnce()).update(org.mockito.ArgumentMatchers.contains("source_provider = 'KOMSCO'"));
    }
}
