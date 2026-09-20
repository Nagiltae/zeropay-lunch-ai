CREATE TABLE subway_stations (
    id VARCHAR(32) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    line VARCHAR(100),
    latitude DECIMAL(10, 7) NOT NULL,
    longitude DECIMAL(10, 7) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    source VARCHAR(255),
    source_updated_at TIMESTAMP
);

INSERT INTO subway_stations (id, name, line, latitude, longitude, active, source) VALUES
('gangnam', '강남역', '2호선', 37.4980, 127.0276, TRUE, 'MANUAL'),
('yeoksam', '역삼역', '2호선', 37.5006, 127.0364, TRUE, 'MANUAL'),
('seolleung', '선릉역', '2호선/수인분당선', 37.5045, 127.0490, TRUE, 'MANUAL'),
('samseong', '삼성역', '2호선', 37.5088, 127.0632, TRUE, 'MANUAL'),
('sinsa', '신사역', '3호선/신분당선', 37.5163, 127.0200, TRUE, 'MANUAL'),
('apgujeong', '압구정역', '3호선', 37.5271, 127.0285, TRUE, 'MANUAL'),
('cheongdam', '청담역', '7호선', 37.5194, 127.0538, TRUE, 'MANUAL'),
('suseo', '수서역', '3호선/수인분당선', 37.4873, 127.1013, TRUE, 'MANUAL');
