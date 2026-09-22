package com.zeropaylunch.backend;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class BackendApplication {

	public static void main(String[] args) {
		// Spring이 REST API, 세션, 스케줄러와 설정 프로퍼티를 한 애플리케이션으로 구성한다.
		SpringApplication.run(BackendApplication.class, args);
	}

}
