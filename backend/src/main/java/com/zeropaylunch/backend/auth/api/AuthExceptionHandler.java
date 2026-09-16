package com.zeropaylunch.backend.auth.api;

import com.zeropaylunch.backend.auth.application.DuplicateEmailException;
import com.zeropaylunch.backend.auth.application.InvalidPasswordException;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class AuthExceptionHandler {

    @ExceptionHandler(DuplicateEmailException.class)
    public ResponseEntity<Map<String, String>> duplicateEmail(DuplicateEmailException exception) {
        return ResponseEntity.status(HttpStatus.CONFLICT).body(Map.of(
                "code", "EMAIL_ALREADY_IN_USE",
                "message", exception.getMessage()
        ));
    }

    @ExceptionHandler(InvalidPasswordException.class)
    public ResponseEntity<Map<String, String>> invalidPassword(InvalidPasswordException exception) {
        return ResponseEntity.badRequest().body(Map.of(
                "code", "INVALID_PASSWORD",
                "message", exception.getMessage()
        ));
    }
}
