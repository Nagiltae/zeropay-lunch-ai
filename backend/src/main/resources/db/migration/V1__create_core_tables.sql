CREATE TABLE conversations (
    id CHAR(36) PRIMARY KEY,
    location_id VARCHAR(32) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    deactivated_at DATETIME(6) NULL,
    INDEX idx_conversations_active (active),
    INDEX idx_conversations_location (location_id)
);

CREATE TABLE chat_messages (
    id CHAR(36) PRIMARY KEY,
    conversation_id CHAR(36) NOT NULL,
    role VARCHAR(16) NOT NULL,
    status VARCHAR(16) NOT NULL,
    content TEXT NOT NULL,
    created_at DATETIME(6) NOT NULL,
    completed_at DATETIME(6) NULL,
    CONSTRAINT fk_chat_messages_conversation
        FOREIGN KEY (conversation_id) REFERENCES conversations (id),
    INDEX idx_chat_messages_conversation_created (conversation_id, created_at)
);

CREATE TABLE restaurants (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(120) NOT NULL,
    category VARCHAR(40) NOT NULL,
    representative_menu VARCHAR(120) NOT NULL,
    average_price INT NOT NULL,
    address VARCHAR(255) NOT NULL,
    location_id VARCHAR(32) NOT NULL,
    latitude DECIMAL(10, 7) NULL,
    longitude DECIMAL(10, 7) NULL,
    zero_pay_available BOOLEAN NOT NULL,
    sample_data BOOLEAN NOT NULL DEFAULT FALSE,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    CONSTRAINT chk_restaurants_average_price CHECK (average_price >= 0),
    INDEX idx_restaurants_location_active (location_id, active)
);

CREATE TABLE restaurant_schedules (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    restaurant_id BIGINT NOT NULL,
    name VARCHAR(80) NOT NULL,
    CONSTRAINT fk_restaurant_schedules_restaurant
        FOREIGN KEY (restaurant_id) REFERENCES restaurants (id),
    UNIQUE KEY uk_restaurant_schedules_name (restaurant_id, name)
);

CREATE TABLE restaurant_operating_days (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    schedule_id BIGINT NOT NULL,
    day_of_week VARCHAR(16) NOT NULL,
    CONSTRAINT fk_operating_days_schedule
        FOREIGN KEY (schedule_id) REFERENCES restaurant_schedules (id),
    UNIQUE KEY uk_operating_days_schedule_day (schedule_id, day_of_week)
);

CREATE TABLE restaurant_operating_hours (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    schedule_id BIGINT NOT NULL,
    opens_at TIME NOT NULL,
    closes_at TIME NOT NULL,
    CONSTRAINT fk_operating_hours_schedule
        FOREIGN KEY (schedule_id) REFERENCES restaurant_schedules (id),
    CONSTRAINT chk_operating_hours_order CHECK (opens_at < closes_at),
    UNIQUE KEY uk_operating_hours_schedule_time (schedule_id, opens_at, closes_at)
);

CREATE TABLE restaurant_closed_days (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    restaurant_id BIGINT NOT NULL,
    day_of_week VARCHAR(16) NOT NULL,
    CONSTRAINT fk_closed_days_restaurant
        FOREIGN KEY (restaurant_id) REFERENCES restaurants (id),
    UNIQUE KEY uk_closed_days_restaurant_day (restaurant_id, day_of_week)
);

CREATE TABLE restaurant_closed_hours (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    schedule_id BIGINT NOT NULL,
    starts_at TIME NOT NULL,
    ends_at TIME NOT NULL,
    CONSTRAINT fk_closed_hours_schedule
        FOREIGN KEY (schedule_id) REFERENCES restaurant_schedules (id),
    CONSTRAINT chk_closed_hours_order CHECK (starts_at < ends_at),
    UNIQUE KEY uk_closed_hours_schedule_time (schedule_id, starts_at, ends_at)
);

CREATE TABLE message_recommendations (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    message_id CHAR(36) NOT NULL,
    restaurant_id BIGINT NOT NULL,
    recommendation_rank INT NOT NULL,
    reason VARCHAR(500) NOT NULL,
    CONSTRAINT fk_message_recommendations_message
        FOREIGN KEY (message_id) REFERENCES chat_messages (id),
    CONSTRAINT fk_message_recommendations_restaurant
        FOREIGN KEY (restaurant_id) REFERENCES restaurants (id),
    CONSTRAINT chk_message_recommendations_rank CHECK (recommendation_rank > 0),
    UNIQUE KEY uk_message_recommendations_rank (message_id, recommendation_rank),
    UNIQUE KEY uk_message_recommendations_restaurant (message_id, restaurant_id)
);
