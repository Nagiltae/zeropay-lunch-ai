package com.zeropaylunch.backend.chat.config;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ChatExecutorConfiguration {

    @Bean(destroyMethod = "close")
    ExecutorService chatExecutor() {
        return Executors.newVirtualThreadPerTaskExecutor();
    }
}
