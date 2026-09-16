package com.zeropaylunch.backend.preference.infrastructure;

import com.zeropaylunch.backend.preference.domain.UserPreference;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface UserPreferenceJpaRepository extends JpaRepository<UserPreference, UUID> {
}
