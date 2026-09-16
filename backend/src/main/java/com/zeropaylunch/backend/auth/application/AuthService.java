package com.zeropaylunch.backend.auth.application;

import com.zeropaylunch.backend.auth.domain.User;
import com.zeropaylunch.backend.auth.domain.UserCredentials;
import com.zeropaylunch.backend.auth.domain.UserStatus;
import com.zeropaylunch.backend.auth.infrastructure.UserCredentialsRepository;
import com.zeropaylunch.backend.auth.infrastructure.UserRepository;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Clock;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.Optional;
import java.util.UUID;
import org.springframework.dao.DataIntegrityViolationException;

@Service
public class AuthService {

    private final UserRepository userRepository;
    private final UserCredentialsRepository userCredentialsRepository;
    private final PasswordEncoder passwordEncoder;
    private final Clock clock;

    public AuthService(UserRepository userRepository,
                       UserCredentialsRepository userCredentialsRepository,
                       PasswordEncoder passwordEncoder,
                       Clock clock) {
        this.userRepository = userRepository;
        this.userCredentialsRepository = userCredentialsRepository;
        this.passwordEncoder = passwordEncoder;
        this.clock = clock;
    }

    @Transactional
    public User signup(String email, String rawPassword, String displayName) {
        String normalizedEmail = normalizeEmail(email);
        validatePasswordByteLength(rawPassword);
        if (userRepository.existsByEmail(normalizedEmail)) {
            throw new DuplicateEmailException();
        }

        User user = User.create(normalizedEmail, displayName.trim(), clock.instant());
        try {
            userRepository.saveAndFlush(user);
        } catch (DataIntegrityViolationException exception) {
            throw new DuplicateEmailException();
        }

        UserCredentials credentials = new UserCredentials(user.getId(), passwordEncoder.encode(rawPassword));
        userCredentialsRepository.save(credentials);

        return user;
    }

    @Transactional
    public Optional<User> authenticate(String email, String rawPassword) {
        validatePasswordByteLength(rawPassword);
        Optional<User> userOpt = userRepository.findByEmail(normalizeEmail(email));
        if (userOpt.isEmpty()) {
            return Optional.empty();
        }
        User user = userOpt.get();
        if (user.getStatus() != UserStatus.ACTIVE) {
            return Optional.empty();
        }

        Optional<UserCredentials> credOpt = userCredentialsRepository.findById(user.getId());
        if (credOpt.isEmpty()) {
            return Optional.empty();
        }
        UserCredentials credentials = credOpt.get();

        if (passwordEncoder.matches(rawPassword, credentials.getPasswordHash())) {
            credentials.resetFailedLogin();
            user.updateLoginTime(clock.instant());
            return Optional.of(user);
        } else {
            credentials.recordFailedLogin();
            return Optional.empty();
        }
    }
    
    @Transactional(readOnly = true)
    public Optional<User> findById(UUID id) {
        return userRepository.findById(id);
    }

    private String normalizeEmail(String email) {
        return email.trim().toLowerCase(Locale.ROOT);
    }

    private void validatePasswordByteLength(String rawPassword) {
        if (rawPassword.getBytes(StandardCharsets.UTF_8).length > 72) {
            throw new InvalidPasswordException("비밀번호는 UTF-8 기준 72바이트 이하여야 합니다.");
        }
    }
}
