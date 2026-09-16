CREATE TABLE user_preferences (
    user_id CHAR(36) PRIMARY KEY,
    default_budget INT NULL,
    spice_level VARCHAR(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    CONSTRAINT fk_user_preferences_user
        FOREIGN KEY (user_id) REFERENCES users (id),
    CONSTRAINT chk_user_preferences_budget
        CHECK (default_budget IS NULL OR (default_budget >= 1000 AND default_budget <= 100000))
);

CREATE TABLE user_preferred_categories (
    user_id CHAR(36) NOT NULL,
    category VARCHAR(40) NOT NULL,
    PRIMARY KEY (user_id, category),
    CONSTRAINT fk_preferred_categories_user
        FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE TABLE user_disliked_categories (
    user_id CHAR(36) NOT NULL,
    category VARCHAR(40) NOT NULL,
    PRIMARY KEY (user_id, category),
    CONSTRAINT fk_disliked_categories_user
        FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE TABLE user_allergies (
    user_id CHAR(36) NOT NULL,
    allergy VARCHAR(80) NOT NULL,
    PRIMARY KEY (user_id, allergy),
    CONSTRAINT fk_user_allergies_user
        FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE TABLE meal_history (
    id CHAR(36) PRIMARY KEY,
    user_id CHAR(36) NOT NULL,
    restaurant_id BIGINT NOT NULL,
    source_message_id CHAR(36) NOT NULL,
    eaten_at DATETIME(6) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    CONSTRAINT fk_meal_history_user
        FOREIGN KEY (user_id) REFERENCES users (id),
    CONSTRAINT fk_meal_history_restaurant
        FOREIGN KEY (restaurant_id) REFERENCES restaurants (id),
    CONSTRAINT fk_meal_history_message
        FOREIGN KEY (source_message_id) REFERENCES chat_messages (id),
    UNIQUE KEY uk_meal_history_recommendation (user_id, source_message_id, restaurant_id),
    INDEX idx_meal_history_user_eaten (user_id, eaten_at)
);
