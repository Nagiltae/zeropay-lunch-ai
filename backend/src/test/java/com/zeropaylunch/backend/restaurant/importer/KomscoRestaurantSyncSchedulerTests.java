package com.zeropaylunch.backend.restaurant.importer;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.lang.reflect.Method;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.scheduling.annotation.Scheduled;

class KomscoRestaurantSyncSchedulerTests {

    @Test
    void delegatesWeeklySynchronizationAndUsesConfiguredThreeAmSchedule() throws Exception {
        RestaurantImportService importService = mock(RestaurantImportService.class);
        RestaurantSyncResult result = new RestaurantSyncResult(
                100, 80, 20, 1, 18, 1, 2, 1, 80, List.of(10L, 11L));
        when(importService.synchronizeRestaurants()).thenReturn(result);

        new KomscoRestaurantSyncScheduler(importService).synchronize();

        verify(importService).synchronizeRestaurants();
        Method method = KomscoRestaurantSyncScheduler.class.getDeclaredMethod("synchronize");
        Scheduled scheduled = method.getAnnotation(Scheduled.class);
        assertThat(scheduled.cron()).isEqualTo("${app.komsco.scheduler-cron}");
        assertThat(scheduled.zone()).isEqualTo("${app.komsco.scheduler-zone}");
    }

    @Test
    void catchesSanitizedApiFailureSoTheNextScheduleCanRun() {
        RestaurantImportService importService = mock(RestaurantImportService.class);
        when(importService.synchronizeRestaurants())
                .thenThrow(new KomscoImportException("request failed"));

        KomscoRestaurantSyncScheduler scheduler =
                new KomscoRestaurantSyncScheduler(importService);

        assertThatCode(scheduler::synchronize).doesNotThrowAnyException();
    }
}
